"""
Orchestrator Service — manages the entire pipeline
Routes records, handles retries, tracks state, coordinates all agents
"""

import asyncio
import json
import logging
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from core.agents.audit import AuditAgent
from core.agents.confidence import ConfidenceAgent
from core.agents.context import ContextAgent
from core.agents.enrichment import EnrichmentAgent
from core.agents.intake import IntakeAgent
from core.agents.learning import LearningAgent
from core.agents.parsing import ParsingAgent
from core.agents.reasoning import ReasoningAgent
from core.agents.validation import ValidationAgent
from core.agents.write import WriteAgent
from core.config.settings import QUEUE_DIR, Settings
from core.models.router import ModelRouter
from core.pipeline.state import (
    ConfidenceTier,
    PipelineRecord,
    RecordStage,
)
from core.utils.events import EventBus, Events

logger = logging.getLogger(__name__)


class OrchestratorService:
    """
    The spine of DataMoA.
    Manages pipeline state for every record.
    Never does any data work itself — purely coordination.
    """

    def __init__(self, settings: Settings, event_bus: EventBus):
        self.settings = settings
        self.event_bus = event_bus
        self.router = ModelRouter(settings)

        # Initialize all agents
        agent_kwargs = dict(settings=settings, router=self.router, event_bus=event_bus)
        self.intake = IntakeAgent(**agent_kwargs)
        self.parsing = ParsingAgent(**agent_kwargs)
        self.context = ContextAgent(**agent_kwargs)
        self.confidence = ConfidenceAgent(**agent_kwargs)
        self.reasoning = ReasoningAgent(**agent_kwargs)
        self.validation = ValidationAgent(**agent_kwargs)
        self.enrichment = EnrichmentAgent(**agent_kwargs)
        self.write = WriteAgent(**agent_kwargs)
        self.audit = AuditAgent(**agent_kwargs)
        self.learning = LearningAgent(**agent_kwargs)

        # State
        self._queue: asyncio.Queue = asyncio.Queue()
        self._records: dict[str, PipelineRecord] = {}
        self._hitl_queue: dict[str, asyncio.Future] = {}
        self._paused = False
        self._running = False
        self._worker_task: asyncio.Task | None = None
        self._agent_status: dict[str, str] = defaultdict(lambda: "idle")
        self._completed_since_last_learn: int = 0
        self._learn_every_n: int = 20  # Run learning batch every 20 completions

        # Load persisted queue state
        self._restore_queue()

    async def start(self):
        self._running = True
        self._worker_task = asyncio.create_task(self._worker())

        # Subscribe to agent status events so _agent_status stays current
        async def _on_agent_status(data: dict):
            if isinstance(data, dict):
                agent = data.get("agent", "")
                status = data.get("status", "idle")
                if agent:
                    self._agent_status[agent] = status

        self.event_bus.subscribe(Events.AGENT_STATUS, _on_agent_status)

        # Apply user optimization settings to router
        config = self.settings.load_config()
        self.router.set_speculative_decoding(config.speculative_decoding_enabled)
        self.router.set_prompt_caching(config.prompt_caching_enabled)

        # Detect hardware and build inference profile
        from core.models.hardware import detect_hardware
        hw = detect_hardware()
        self.router.apply_inference_profile(
            vram_gb=hw.gpu_vram_gb,
            ram_gb=hw.ram_gb,
            gpu_name=hw.gpu_name,
        )

        # Configure warm pool from current agent assignments
        agent_models = config.agents.model_dump()
        self.router.configure_warm_pool(agent_models)

        logger.info(
            f"Orchestrator started — "
            f"cache={'on' if config.prompt_caching_enabled else 'off'}, "
            f"speculative={'on' if config.speculative_decoding_enabled else 'off'}, "
            f"engine={self.router._inference_profile.engine.value if self.router._inference_profile else 'unknown'}"
        )

    async def stop(self):
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
        self._persist_queue()
        logger.info("Orchestrator stopped")

    async def submit(self, record: PipelineRecord) -> str:
        """Submit a new record to the pipeline"""
        self._records[record.id] = record
        await self._queue.put(record.id)
        self._persist_record(record)

        await self.event_bus.emit(Events.PIPELINE_UPDATE, {
            "type": "record_added",
            "record": record.to_summary(),
        })

        logger.info(f"Record {record.id[:8]} submitted")
        return record.id

    async def get_queue(self) -> list[dict]:
        return [r.to_summary() for r in self._records.values()]

    async def get_record(self, record_id: str) -> PipelineRecord | None:
        return self._records.get(record_id)

    async def resolve_hitl(self, record_id: str, resolution: dict):
        """Resolve a HITL request — called by human via UI"""
        if record_id in self._hitl_queue:
            future = self._hitl_queue[record_id]
            if not future.done():
                future.set_result(resolution)

    async def pause(self):
        self._paused = True
        await self.event_bus.emit(Events.PIPELINE_PAUSED, {})

    async def resume(self):
        self._paused = False
        await self.event_bus.emit(Events.PIPELINE_RESUMED, {})

    async def cancel(self, record_id: str):
        if record_id in self._records:
            record = self._records[record_id]
            record.advance_to(RecordStage.CANCELLED)
            await self.event_bus.emit(Events.RECORD_UPDATE, record.to_summary())

    def get_agent_status(self) -> dict:
        config = self.settings.load_config()
        agent_models = config.agents.model_dump()
        result = {}
        for agent_name, status in self._agent_status.items():
            result[agent_name] = {
                "status": status,
                "model": agent_models.get(agent_name, "—"),
            }
        # Fill any agents not yet in status dict
        for name, model in agent_models.items():
            if name not in result:
                result[name] = {"status": "idle", "model": model}
        return result

    async def _worker(self):
        """Main pipeline worker — processes records from queue with parallel batching"""
        config = self.settings.load_config()
        semaphore = asyncio.Semaphore(config.pipeline.max_concurrent_records)

        # Collect records that arrive close together for parallel lightweight processing
        batch_window_ms = 50  # Collect records arriving within 50ms into a batch
        pending_batch: list[str] = []

        while self._running:
            if self._paused:
                await asyncio.sleep(0.5)
                continue

            try:
                record_id = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                pending_batch.append(record_id)

                # Drain any more records that arrive immediately (batch window)
                drain_deadline = asyncio.get_event_loop().time() + (batch_window_ms / 1000)
                while asyncio.get_event_loop().time() < drain_deadline:
                    try:
                        extra_id = self._queue.get_nowait()
                        pending_batch.append(extra_id)
                    except asyncio.QueueEmpty:
                        break

            except asyncio.TimeoutError:
                continue

            # Launch all collected records concurrently
            for rid in pending_batch:
                record = self._records.get(rid)
                if not record or record.stage in (RecordStage.CANCELLED, RecordStage.COMPLETE, RecordStage.FAILED):
                    continue
                asyncio.create_task(self._process_record(record, semaphore))

            pending_batch.clear()

    async def _process_record(self, record: PipelineRecord, semaphore: asyncio.Semaphore):
        """Process a single record through the full pipeline"""
        async with semaphore:
            config = self.settings.load_config()
            max_retries = config.pipeline.retry_max_attempts

            try:
                # 1. INTAKE
                record = await self._run_with_retry(self.intake, record, max_retries)
                await self._emit_record_update(record)

                # 2. PARSING
                record = await self._run_with_retry(self.parsing, record, max_retries)
                await self._emit_record_update(record)

                # 3. CONTEXT (configurable)
                if config.pipeline.context_enabled:
                    record = await self._run_with_retry(self.context, record, max_retries)
                    await self._emit_record_update(record)

                # 4. CONFIDENCE SCORING
                record = await self._run_with_retry(self.confidence, record, max_retries)
                await self._emit_record_update(record)

                # 5. ROUTE by confidence tier
                if record.confidence and record.confidence.tier == ConfidenceTier.GREEN:
                    # Green — skip reasoning, go straight to validation
                    pass
                else:
                    # Amber or Red — apply reasoning first
                    record = await self._run_with_retry(self.reasoning, record, max_retries)
                    await self._emit_record_update(record)

                    # After reasoning, check if HITL required
                    if record.reasoning and record.reasoning.requires_hitl:
                        record = await self._handle_hitl(record)
                        await self._emit_record_update(record)

                # 6. VALIDATION
                record = await self._run_with_retry(self.validation, record, max_retries)
                await self._emit_record_update(record)

                # If validation failed, send to HITL
                if record.validation and not record.validation.passed and not record.hitl:
                    from core.pipeline.state import ReasoningResult as _RR, ConfidenceTier as _CT
                    error_msg = "; ".join(record.validation.errors) if record.validation.errors else "Validation failed"
                    hitl_q = [f"Validation failed: {error_msg}. Please correct the flagged fields."]
                    if not record.reasoning:
                        record.reasoning = _RR(
                            confidence_after=record.confidence.overall_score if record.confidence else 0.0,
                            tier_after=_CT.RED,
                            requires_hitl=True,
                            hitl_questions=hitl_q,
                        )
                    else:
                        record.reasoning.requires_hitl = True
                        record.reasoning.hitl_questions = (record.reasoning.hitl_questions or []) + hitl_q
                    record = await self._handle_hitl(record)
                    await self._emit_record_update(record)

                    # Re-validate after HITL
                    record = await self._run_with_retry(self.validation, record, max_retries)
                    await self._emit_record_update(record)

                # 7. ENRICHMENT — fill any remaining null fields
                missing_count = sum(
                    1 for v in (record.parsed.fields or {}).values()
                    if v is None or v == ""
                ) if record.parsed and record.parsed.fields else 0

                if missing_count > 0 and config.pipeline.enrichment_enabled:
                    record = await self._run_with_retry(self.enrichment, record, max_retries)
                    await self._emit_record_update(record)

                # 8. BUILD RESOLVED DATA
                record.resolved_data = {
                    **(record.parsed.fields if record.parsed else {}),
                    **(record.reasoning.resolved_fields if record.reasoning else {}),
                    **(record.hitl.resolved_fields if record.hitl else {}),
                }

                # 9. WRITE
                # Write: always write unless auto_write is disabled AND record is green (user wants manual review of greens)
                should_write = True
                if not config.pipeline.auto_write_on_green and record.confidence and record.confidence.tier == ConfidenceTier.GREEN:
                    should_write = False
                if should_write:
                    record = await self._run_with_retry(self.write, record, max_retries)
                    await self._emit_record_update(record)

                # 10. AUDIT
                record.advance_to(RecordStage.AUDIT)
                await self.audit.run(record)

                # 11. COMPLETE
                record.advance_to(RecordStage.COMPLETE)
                self._persist_record(record)

                # Trigger learning batch periodically
                self._completed_since_last_learn += 1
                if self._completed_since_last_learn >= self._learn_every_n and config.pipeline.learning_enabled:
                    self._completed_since_last_learn = 0
                    asyncio.create_task(self._run_learning_batch())

                await self.event_bus.emit(Events.RECORD_COMPLETE, record.to_summary())
                await self._emit_record_update(record)

                logger.info(f"Record {record.id[:8]} completed successfully")

            except Exception as e:
                logger.error(f"Record {record.id[:8]} pipeline failed: {e}")
                record.stage = RecordStage.FAILED
                record.error_message = str(e)
                self._persist_record(record)

                await self.event_bus.emit(Events.RECORD_FAILED, {
                    **record.to_summary(),
                    "error": str(e),
                })

    async def _run_learning_batch(self):
        """Run learning and audit over recent completed records"""
        try:
            completed = [
                r for r in self._records.values()
                if r.stage == RecordStage.COMPLETE
            ]
            if not completed:
                return
            batch = completed[-50:]
            await self.audit.run_batch_audit(batch)
            await self.learning.run_batch(batch)
            logger.info(f"Learning batch complete over {len(batch)} records")
        except Exception as e:
            logger.error(f"Learning batch failed: {e}")

    async def _run_with_retry(self, agent: Any, record: PipelineRecord, max_retries: int) -> PipelineRecord:
        """Run an agent with retry logic"""
        config = self.settings.load_config()
        last_error = None

        for attempt in range(max_retries + 1):
            try:
                return await agent.run(record)
            except Exception as e:
                last_error = e
                if attempt < max_retries:
                    record.retry_count += 1
                    delay = config.pipeline.retry_delay_seconds * (2 ** attempt)
                    logger.warning(f"Agent {agent.name} failed (attempt {attempt+1}), retrying in {delay}s: {e}")
                    await asyncio.sleep(delay)
                else:
                    raise last_error

    async def _handle_hitl(self, record: PipelineRecord) -> PipelineRecord:
        """
        Pause record and wait for human resolution.
        The UI presents the questions, human answers, resolution flows back here.
        """
        record.advance_to(RecordStage.HITL)

        questions = []
        if record.reasoning and hasattr(record.reasoning, 'hitl_questions'):
            questions = record.reasoning.hitl_questions or []

        # Emit HITL request to UI
        await self.event_bus.emit(Events.HITL_REQUEST, {
            "record_id": record.id,
            "questions": questions,
            "flagged_fields": record.confidence.flagged_fields if record.confidence else [],
            "parsed_fields": record.parsed.fields if record.parsed else {},
            "reasoning_notes": record.reasoning.reasoning_notes if record.reasoning else "",
            "raw_text_excerpt": (record.source_raw or "")[:1000],
        })

        # Create future to wait for resolution
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        self._hitl_queue[record.id] = future

        try:
            # Wait up to 24 hours for human resolution
            resolution = await asyncio.wait_for(future, timeout=86400)

            from core.pipeline.state import HITLResolution
            record.hitl = HITLResolution(
                resolved_fields=resolution.get("resolved_fields", {}),
                notes=resolution.get("notes", ""),
            )

            # Apply HITL resolutions to parsed data
            # Filter: field_* keys are actual field overrides; q_* are question answers
            if record.parsed is not None and record.hitl.resolved_fields:
                field_overrides = {
                    k[len('field_'):] if k.startswith('field_') else k: v
                    for k, v in record.hitl.resolved_fields.items()
                    if not k.startswith('q_') and v  # exclude question answers and empty
                }
                if field_overrides:
                    if record.parsed.fields is None:
                        record.parsed.fields = {}
                    record.parsed.fields.update(field_overrides)
                    record.hitl.resolved_fields = field_overrides  # clean up

        except asyncio.TimeoutError:
            logger.warning(f"HITL timeout for record {record.id[:8]}")
            record.error_message = "HITL timeout — record was not resolved within 24 hours"
            raise

        finally:
            self._hitl_queue.pop(record.id, None)

        return record

    async def _emit_record_update(self, record: PipelineRecord):
        await self.event_bus.emit(Events.RECORD_UPDATE, record.to_summary())
        self._persist_record(record)

    def _persist_record(self, record: PipelineRecord):
        """Persist record state to disk for crash recovery"""
        try:
            record_file = QUEUE_DIR / f"{record.id}.json"
            with open(record_file, "w") as f:
                json.dump(record.model_dump(), f, default=str)
        except Exception as e:
            logger.error(f"Failed to persist record {record.id}: {e}")

    def _persist_queue(self):
        """Persist queue state on shutdown"""
        queue_state = {
            "pending": [
                rid for rid, r in self._records.items()
                if r.stage not in (RecordStage.COMPLETE, RecordStage.FAILED, RecordStage.CANCELLED)
            ]
        }
        try:
            with open(QUEUE_DIR / "queue_state.json", "w") as f:
                json.dump(queue_state, f)
        except Exception as e:
            logger.error(f"Failed to persist queue: {e}")

    def _restore_queue(self):
        """Restore in-progress records after restart"""
        try:
            for record_file in QUEUE_DIR.glob("*.json"):
                if record_file.name == "queue_state.json":
                    continue
                with open(record_file) as f:
                    data = json.load(f)
                record = PipelineRecord(**data)
                if record.stage not in (RecordStage.COMPLETE, RecordStage.FAILED, RecordStage.CANCELLED):
                    self._records[record.id] = record
                    # Re-queue in-progress records
                    self._queue.put_nowait(record.id)
                    logger.info(f"Restored in-progress record {record.id[:8]}")
        except Exception as e:
            logger.error(f"Queue restore error: {e}")
