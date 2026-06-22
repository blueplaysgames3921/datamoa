"""
Base Agent — all agents inherit from this
Provides common interface, timing, error handling, and audit logging
"""

import logging
import time
from abc import ABC, abstractmethod
from typing import Any

from core.config.settings import Settings
from core.models.router import ModelRouter
from core.pipeline.state import AuditEntry, PipelineRecord, RecordStage
from core.utils.events import EventBus, Events


class BaseAgent(ABC):
    """
    Every agent inherits from this.
    Handles: timing, audit logging, error wrapping, event emission.
    Subclasses implement _run() only.
    """

    name: str = "base"
    stage: RecordStage = RecordStage.QUEUED

    def __init__(self, settings: Settings, router: ModelRouter, event_bus: EventBus):
        self.settings = settings
        self.router = router
        self.event_bus = event_bus
        self.logger = logging.getLogger(f"datamoa.agent.{self.name}")
        self._model: str = ""

    @property
    def model(self) -> str:
        config = self.settings.load_config()
        return getattr(config.agents, self.name, self._model)

    @property
    def temperature(self) -> float:
        """Agent-specific temperature from warm pool params."""
        return getattr(self, '_current_params', {}).get('temperature', 0.0)

    @property
    def top_p(self) -> float:
        return getattr(self, '_current_params', {}).get('top_p', 1.0)

    async def run(self, record: PipelineRecord) -> PipelineRecord:
        """
        Public entry point. Wraps _run() with timing, logging, and error handling.
        Uses warm pool inference params for this agent role.
        """
        from core.models.warm_pool import warm_pool
        # Apply agent-specific inference params via system prompt swapping
        self._current_params = warm_pool.get_inference_params(self.name)
        self._complexity = warm_pool.get_complexity(self.name)

        start = time.time()
        record.advance_to(self.stage)

        await self.event_bus.emit(Events.AGENT_STATUS, {
            "agent": self.name,
            "status": "running",
            "record_id": record.id,
            "model": self.model,
        })

        try:
            record = await self._run(record)

            duration_ms = int((time.time() - start) * 1000)
            self.logger.info(f"[{self.name}] Record {record.id[:8]} completed in {duration_ms}ms")

            await self.event_bus.emit(Events.AGENT_STATUS, {
                "agent": self.name,
                "status": "idle",
                "record_id": record.id,
                "duration_ms": duration_ms,
            })

            return record

        except Exception as e:
            duration_ms = int((time.time() - start) * 1000)
            self.logger.error(f"[{self.name}] Record {record.id[:8]} failed: {e}")

            record.error_message = str(e)

            await self.event_bus.emit(Events.AGENT_STATUS, {
                "agent": self.name,
                "status": "error",
                "record_id": record.id,
                "error": str(e),
            })

            raise

    async def _parse_json_with_retry(
        self,
        response: str,
        system_prompt: str,
        user_message: str,
        agent_name: str,
        max_retries: int = 2,
    ) -> dict:
        """
        Parse JSON from model response with automatic retry.
        If parsing fails, sends a corrective prompt and tries again.
        """
        from core.utils.json_validator import parse_agent_json, build_retry_prompt, JSONParseError
        
        last_error = None
        last_response = response
        
        for attempt in range(max_retries + 1):
            try:
                return parse_agent_json(last_response, agent_name)
            except JSONParseError as e:
                last_error = e
                if attempt < max_retries:
                    self.logger.warning(
                        f"[{agent_name}] JSON parse failed (attempt {attempt+1}), retrying: {e}"
                    )
                    # Build corrective prompt
                    retry_prompt = build_retry_prompt(
                        original_prompt=user_message,
                        failed_response=last_response,
                        error=str(e),
                    )
                    last_response = await self.router.complete(
                        model=self.model,
                        messages=[{"role": "user", "content": retry_prompt}],
                        system=system_prompt,
                        temperature=0.0,
                        max_tokens=4096,
                    )
        
        raise last_error

    @abstractmethod
    async def _run(self, record: PipelineRecord) -> PipelineRecord:
        """Implement agent logic here"""
        ...

    def _add_audit(
        self,
        record: PipelineRecord,
        action: str,
        input_summary: str = "",
        output_summary: str = "",
        confidence_before: float | None = None,
        confidence_after: float | None = None,
        duration_ms: int = 0,
        error: str | None = None,
    ):
        entry = AuditEntry(
            record_id=record.id,
            stage=self.stage,
            agent=self.name,
            model=self.model,
            action=action,
            input_summary=input_summary,
            output_summary=output_summary,
            confidence_before=confidence_before,
            confidence_after=confidence_after,
            duration_ms=duration_ms,
            error=error,
        )
        record.audit_entries.append(entry)
        return entry
