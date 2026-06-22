"""
Warm Model Pool — keeps a minimal set of model instances "warm" to avoid
re-initialization overhead on every agent call.

Implements:
  1. Warm model consolidation — minimal permanent set, reused across roles
  2. Sequential multi-tenancy — same warm instance handles multiple agents via system prompt swapping
  3. Parallel fast execution — independent tasks run concurrently across the warm pool
  4. System prompt + inference parameter swapping per agent role
  5. Tiered complexity routing — simple/medium/high tasks routed appropriately
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class TaskComplexity(str, Enum):
    SIMPLE  = "simple"   # Direct to baseline warm model
    MEDIUM  = "medium"   # Draft model speculatively decodes, target verifies
    HIGH    = "high"     # Tiny draft → high-capability model


# Per-agent complexity classification
AGENT_COMPLEXITY: dict[str, TaskComplexity] = {
    "intake":       TaskComplexity.SIMPLE,
    "context":      TaskComplexity.SIMPLE,
    "confidence":   TaskComplexity.SIMPLE,
    "validation":   TaskComplexity.SIMPLE,
    "hitl":         TaskComplexity.SIMPLE,
    "learning":     TaskComplexity.SIMPLE,
    "parsing":      TaskComplexity.MEDIUM,
    "enrichment":   TaskComplexity.MEDIUM,
    "write":        TaskComplexity.MEDIUM,
    "audit":        TaskComplexity.MEDIUM,
    "orchestrator": TaskComplexity.MEDIUM,
    "reasoning":    TaskComplexity.HIGH,
    "config_agent": TaskComplexity.HIGH,
}

# Inference parameters per agent role — swapped without changing the model
AGENT_INFERENCE_PARAMS: dict[str, dict[str, Any]] = {
    # Deterministic — never creative
    "intake":       {"temperature": 0.0, "top_p": 1.0,  "repetition_penalty": 1.0},
    "parsing":      {"temperature": 0.0, "top_p": 1.0,  "repetition_penalty": 1.05},
    "context":      {"temperature": 0.0, "top_p": 1.0,  "repetition_penalty": 1.0},
    "confidence":   {"temperature": 0.0, "top_p": 1.0,  "repetition_penalty": 1.0},
    "validation":   {"temperature": 0.0, "top_p": 1.0,  "repetition_penalty": 1.0},
    "hitl":         {"temperature": 0.0, "top_p": 1.0,  "repetition_penalty": 1.0},
    "write":        {"temperature": 0.0, "top_p": 1.0,  "repetition_penalty": 1.0},
    "audit":        {"temperature": 0.0, "top_p": 1.0,  "repetition_penalty": 1.05},
    "learning":     {"temperature": 0.1, "top_p": 0.9,  "repetition_penalty": 1.05},
    # Slight creativity for ambiguity resolution
    "reasoning":    {"temperature": 0.1, "top_p": 0.95, "repetition_penalty": 1.1},
    "enrichment":   {"temperature": 0.1, "top_p": 0.9,  "repetition_penalty": 1.05},
    "orchestrator": {"temperature": 0.0, "top_p": 1.0,  "repetition_penalty": 1.0},
    "config_agent": {"temperature": 0.1, "top_p": 0.9,  "repetition_penalty": 1.05},
}


@dataclass
class WarmSlot:
    """A single warm model slot — one model kept loaded, reused across roles."""
    model_id: str
    roles: list[str]               # which agent roles share this slot
    last_used: float = 0.0
    active_calls: int = 0
    total_calls: int = 0
    total_ms: float = 0.0

    def record_call(self, duration_ms: float):
        self.last_used = time.monotonic()
        self.total_calls += 1
        self.total_ms += duration_ms
        self.active_calls = max(0, self.active_calls - 1)

    @property
    def avg_latency_ms(self) -> float:
        return self.total_ms / self.total_calls if self.total_calls > 0 else 0.0


class WarmPool:
    """
    Manages warm model slots for multi-tenant, low-latency agent execution.

    Strategy:
    - Groups agents by model assignment → minimal set of warm slots
    - Routes via complexity tier: SIMPLE→baseline, MEDIUM→standard, HIGH→best
    - Runs independent SIMPLE tasks in parallel (batch execution)
    - Sequential tasks share the same warm slot (no re-init overhead)
    """

    def __init__(self):
        self._slots: dict[str, WarmSlot] = {}       # model_id → WarmSlot
        self._agent_to_model: dict[str, str] = {}   # agent_name → model_id
        self._lock = asyncio.Lock()

    def configure(self, agent_models: dict[str, str]):
        """
        Build warm slots from agent → model assignment map.
        Groups agents that share the same model into one slot.
        """
        # Invert: model_id → [agent_names]
        model_to_agents: dict[str, list[str]] = {}
        for agent, model in agent_models.items():
            model_to_agents.setdefault(model, []).append(agent)

        self._slots = {
            model_id: WarmSlot(model_id=model_id, roles=roles)
            for model_id, roles in model_to_agents.items()
        }
        self._agent_to_model = dict(agent_models)

        slot_count = len(self._slots)
        agent_count = len(agent_models)
        saved = agent_count - slot_count
        logger.info(
            f"Warm pool configured: {slot_count} slots for {agent_count} agents "
            f"({saved} shared — {saved} fewer model loads)"
        )

    def get_model_for_agent(self, agent_name: str) -> Optional[str]:
        return self._agent_to_model.get(agent_name)

    def get_inference_params(self, agent_name: str) -> dict[str, Any]:
        """Return the agent-specific inference parameters for system prompt swapping."""
        return dict(AGENT_INFERENCE_PARAMS.get(agent_name, {"temperature": 0.0}))

    def get_complexity(self, agent_name: str) -> TaskComplexity:
        return AGENT_COMPLEXITY.get(agent_name, TaskComplexity.MEDIUM)

    def get_slot_stats(self) -> list[dict]:
        """Return stats for all warm slots — used by health monitor."""
        return [
            {
                "model_id": slot.model_id,
                "roles": slot.roles,
                "total_calls": slot.total_calls,
                "avg_latency_ms": round(slot.avg_latency_ms, 1),
                "active_calls": slot.active_calls,
            }
            for slot in self._slots.values()
        ]

    def record_call(self, model_id: str, duration_ms: float):
        if model_id in self._slots:
            self._slots[model_id].record_call(duration_ms)

    def mark_call_start(self, model_id: str):
        if model_id in self._slots:
            self._slots[model_id].active_calls += 1

    def get_parallelizable_agents(self) -> list[str]:
        """Agents that can safely run in parallel (SIMPLE complexity)."""
        return [
            agent for agent, complexity in AGENT_COMPLEXITY.items()
            if complexity == TaskComplexity.SIMPLE
        ]

    def should_use_speculative(self, agent_name: str) -> bool:
        """Only HIGH complexity agents benefit from speculative decoding."""
        return AGENT_COMPLEXITY.get(agent_name, TaskComplexity.MEDIUM) == TaskComplexity.HIGH

    def get_shared_model_groups(self) -> dict[str, list[str]]:
        """Return groups of agents sharing a model — for sequential multi-tenancy."""
        return {
            slot.model_id: slot.roles
            for slot in self._slots.values()
            if len(slot.roles) > 1
        }


# Singleton warm pool
warm_pool = WarmPool()
