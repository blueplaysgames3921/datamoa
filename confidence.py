"""
Confidence Scoring Agent — evaluates parsed data holistically and routes the record
This is the traffic controller. Its accuracy directly determines system reliability.
"""

import json
import logging
import time

from core.agents.base import BaseAgent
from core.pipeline.state import (
    ConfidenceResult,
    ConfidenceTier,
    PipelineRecord,
    RecordStage,
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are the Confidence Scoring Agent for a professional data entry system.

YOUR ROLE:
You receive parsed data extracted from a document — a set of fields, values, and per-field confidence scores — and you must produce a holistic confidence assessment for the entire record.

YOUR OUTPUT determines routing:
- GREEN (>= threshold): Record proceeds automatically — no human review
- AMBER (>= lower threshold): Record has uncertainty but may be resolvable by reasoning
- RED (< lower threshold): Record requires human input or cannot be resolved automatically

THIS IS THE MOST CRITICAL ROUTING DECISION IN THE SYSTEM.
A wrong GREEN means bad data gets written silently.
A wrong RED wastes human time.
BIAS STRONGLY TOWARD CAUTION. When in doubt, downgrade.

SCORING RULES:
1. Start from the per-field confidence scores provided
2. Weight critical fields more heavily (amounts, dates, names, IDs) than metadata fields
3. Apply penalties for:
   - Any flagged field: -0.10 per flagged field
   - Any field with confidence below 0.5: -0.15 per field
   - Parse errors: -0.30
   - Missing required fields (amount, date, or name missing): -0.20 per missing type
   - Conflicting values for same apparent field: -0.25
4. Apply bonuses for:
   - Known document type with all expected fields present: +0.05
   - High average field confidence (>= 0.9): +0.05
5. Final score is clamped to 0.0-1.0
6. Final tier is determined by the caller's thresholds — you report the raw score only

FLAGGED FIELDS LIST:
You must list every field that requires attention — both flagged fields from parsing and any fields you identify as problematic during your own review.

YOUR OUTPUT must be a JSON object with this exact structure:
{
  "overall_score": 0.0 to 1.0,
  "field_scores": {
    "field_name": 0.0 to 1.0
  },
  "flagged_fields": ["field_name_1", "field_name_2"],
  "routing_reason": "Clear explanation of why this score was assigned and what the key risk factors are"
}

Be specific in routing_reason. "Low confidence due to illegible date field and missing invoice total" is correct. "Uncertain" is not acceptable.

Return ONLY the JSON object. No preamble, no explanation, no markdown.
"""


class ConfidenceAgent(BaseAgent):
    name = "confidence"
    stage = RecordStage.CONFIDENCE

    async def _run(self, record: PipelineRecord) -> PipelineRecord:
        start = time.time()
        config = self.settings.load_config()

        if not record.parsed:
            # No parsed data — automatic RED
            record.confidence = ConfidenceResult(
                overall_score=0.0,
                tier=ConfidenceTier.RED,
                routing_reason="No parsed data available",
            )
            return record

        # Build input for model
        parsed = record.parsed
        field_summary = {
            fc.field: {
                "value": fc.value,
                "confidence": fc.confidence,
                "flagged": fc.flagged,
                "reason": fc.reason,
            }
            for fc in (parsed.field_confidences if parsed else [])
        }
        field_count = len(parsed.fields) if parsed and parsed.fields else 0
        flag_count = sum(1 for fc in (parsed.field_confidences if parsed else []) if fc.flagged)
        confidences = [fc.confidence for fc in (parsed.field_confidences if parsed else [])]
        avg_conf = sum(confidences) / len(confidences) if confidences else 0.0

        prompt = f"""Document type: {parsed.document_type if parsed else 'unknown'}
Parse notes: {parsed.parse_notes if parsed else ''}

Field extractions:
{json.dumps(field_summary, indent=2)}

Total fields: {field_count}
Flagged fields: {flag_count}
Average field confidence: {avg_conf:.2f}

Score this record's overall confidence."""

        response = await self.router.complete(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            system=SYSTEM_PROMPT,
            temperature=self.temperature,
            max_tokens=1024,
        )

        duration_ms = int((time.time() - start) * 1000)

        try:
            data = await self._parse_json_with_retry(
                response=response,
                system_prompt=SYSTEM_PROMPT,
                user_message=prompt,
                agent_name=self.name,
            )
            score = float(data.get("overall_score", 0.0))
            score = max(0.0, min(1.0, score))

            # Apply tier thresholds from user config
            green = config.pipeline.confidence_green_threshold
            amber = config.pipeline.confidence_amber_threshold

            if score >= green:
                tier = ConfidenceTier.GREEN
            elif score >= amber:
                tier = ConfidenceTier.AMBER
            else:
                tier = ConfidenceTier.RED

            record.confidence = ConfidenceResult(
                overall_score=score,
                tier=tier,
                field_scores=data.get("field_scores", {}),
                flagged_fields=data.get("flagged_fields", []),
                routing_reason=data.get("routing_reason", ""),
            )

        except Exception as e:
            logger.error(f"Confidence scoring failed: {e}")
            record.confidence = ConfidenceResult(
                overall_score=0.0,
                tier=ConfidenceTier.RED,
                routing_reason=f"Confidence scoring error: {str(e)}",
            )

        self._add_audit(
            record,
            action="confidence_scoring",
            input_summary=f"{len(record.parsed.fields)} fields evaluated",
            output_summary=f"Score: {record.confidence.overall_score:.2f}, Tier: {record.confidence.tier}",
            confidence_after=record.confidence.overall_score,
            duration_ms=duration_ms,
        )

        return record
