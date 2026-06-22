"""
Audit Agent — reviews completed records in batches, produces audit analysis
Runs periodically, not per-record. Receives batches.
"""

import json
import logging
import time
from datetime import datetime
from pathlib import Path

from core.agents.base import BaseAgent
from core.config.settings import AUDIT_DIR
from core.pipeline.state import PipelineRecord, RecordStage

logger = logging.getLogger(__name__)

AUDIT_SYSTEM_PROMPT = """You are the Audit Agent for a professional data entry system. You are a skeptical, rigorous reviewer.

YOUR ROLE:
You receive a batch of completed pipeline records — their full history, decisions, confidence scores, and outcomes — and you produce a critical audit analysis.

YOUR MINDSET:
- You trust nothing by default
- You look for patterns in errors and near-misses
- You identify systematic problems before they become widespread
- You flag anomalies that humans might have missed
- You are never satisfied with "it worked" — you ask "did it work correctly?"

YOU ANALYZE:
1. Were confidence scores appropriate for the decisions made?
2. Did the Reasoning Agent make sound judgment calls?
3. Were HITL escalations appropriate or were they avoidable?
4. Are there patterns in what gets flagged — suggesting a systematic parsing problem?
5. Did any records get written with suspicious data?
6. Were there any silent failures or near-misses?
7. Is the system improving or degrading over time?

YOUR OUTPUT must be a JSON object:
{
  "batch_size": number,
  "issues_found": number,
  "critical_issues": ["description of any critical issues requiring immediate attention"],
  "warnings": ["description of non-critical concerns"],
  "patterns": ["identified patterns across records"],
  "recommendations": ["specific actionable improvements"],
  "overall_assessment": "brief paragraph summary",
  "records_requiring_review": ["record_id_1", "record_id_2"]
}

Be specific. "Invoice #1234 was written with a suspiciously round total ($10,000.00) despite the line items summing to $10,247.50" is correct. "Some records had issues" is not acceptable.

Return ONLY the JSON object. No preamble, no explanation, no markdown.
"""


class AuditAgent(BaseAgent):
    name = "audit"
    stage = RecordStage.AUDIT

    async def _run(self, record: PipelineRecord) -> PipelineRecord:
        """Per-record audit — just persists the audit log"""
        self._persist_audit(record)
        return record

    async def run_batch_audit(self, records: list[PipelineRecord]) -> dict:
        """
        Batch audit — runs periodically over a set of completed records.
        Returns analysis dict.
        """
        start = time.time()

        if not records:
            return {"batch_size": 0, "issues_found": 0, "overall_assessment": "No records to audit"}

        # Build compact summary of each record for the model
        summaries = []
        for r in records:
            summaries.append({
                "id": r.id,
                "source_type": r.source_type,
                "document_type": r.parsed.document_type if r.parsed else "unknown",
                "fields_extracted": len(r.parsed.fields) if r.parsed else 0,
                "confidence_score": r.confidence.overall_score if r.confidence else None,
                "confidence_tier": r.confidence.tier if r.confidence else None,
                "reasoning_applied": r.reasoning is not None,
                "hitl_required": r.reasoning.requires_hitl if r.reasoning else False,
                "validation_passed": r.validation.passed if r.validation else None,
                "write_success": r.write_result.success if r.write_result else None,
                "error": r.error_message,
                "retry_count": r.retry_count,
                "stage_history": [h["stage"] for h in r.stage_history],
            })

        prompt = f"""Audit this batch of {len(records)} completed pipeline records.

RECORDS:
{json.dumps(summaries, indent=2)}

Produce your audit analysis."""

        response = await self.router.complete(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            system=AUDIT_SYSTEM_PROMPT,
            temperature=self.temperature,
            max_tokens=4096,
        )

        try:
            clean = response.strip()
            if clean.startswith("```"):
                clean = clean.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            result = json.loads(clean)
        except Exception as e:
            result = {
                "batch_size": len(records),
                "issues_found": 0,
                "overall_assessment": f"Audit agent error: {str(e)}",
                "error": str(e),
            }

        # Persist audit report
        self._persist_audit_report(result)
        return result

    def _persist_audit(self, record: PipelineRecord):
        """Save record audit trail to disk"""
        audit_file = AUDIT_DIR / f"{record.id}.json"
        audit_data = {
            "record_id": record.id,
            "completed_at": datetime.utcnow().isoformat(),
            "stage": record.stage,
            "entries": [e.model_dump() for e in record.audit_entries],
            "final_confidence": record.confidence.overall_score if record.confidence else None,
            "write_success": record.write_result.success if record.write_result else None,
        }
        try:
            with open(audit_file, "w") as f:
                json.dump(audit_data, f, indent=2, default=str)
            # Emit real-time notification
            self.event_bus.emit_sync("audit:new:entry", {
                "record_id": record.id,
                "write_success": record.write_result.success if record.write_result else None,
                "final_confidence": record.confidence.overall_score if record.confidence else None,
            })
        except Exception as e:
            logger.error(f"Failed to persist audit for {record.id}: {e}")

    def _persist_audit_report(self, report: dict):
        report_file = AUDIT_DIR / f"report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        try:
            with open(report_file, "w") as f:
                json.dump(report, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to persist audit report: {e}")
