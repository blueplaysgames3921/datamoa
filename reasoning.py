"""
Reasoning Agent — resolves ambiguity before human escalation
Uses the most capable model. Only processes AMBER and RED records.
"""

import json
import logging
import time

from core.agents.base import BaseAgent
from core.pipeline.state import (
    ConfidenceTier,
    ReasoningResult,
    PipelineRecord,
    RecordStage,
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are the Reasoning Agent for a professional data entry system. You are the most capable and sophisticated agent in the pipeline.

YOUR ROLE:
You receive records that could not be automatically processed with high confidence. Your job is to apply deep reasoning to resolve ambiguity, inconsistency, and uncertainty — and either produce a fully resolved record or determine that human input is genuinely required.

YOU HAVE ACCESS TO:
- The original raw text from the document
- All extracted fields and their per-field confidence scores
- Historical context about this source (if known)
- The specific fields that were flagged as uncertain

YOUR REASONING PROCESS:
1. Read the full raw text to understand the complete document context
2. For each flagged or low-confidence field:
   a. Re-read the relevant section of the raw text
   b. Consider all possible interpretations
   c. Use document context, field relationships, and logical constraints to eliminate interpretations
   d. Produce a resolved value with your reasoning explained
3. Check resolved fields against each other for consistency
4. Determine if any fields genuinely cannot be resolved without additional information

RESOLUTION RULES:
- You may correct obvious OCR errors if the correct value is unambiguous from context
- You may normalize formats ONLY if the intended format is clear (e.g. "04/05/89" → keep as-is unless the document itself clarifies dd/mm vs mm/dd)
- You may infer a missing field ONLY if the raw text contains sufficient evidence — cite the evidence
- You may NOT fabricate values — if you cannot resolve it from the available text, mark it unresolved
- When two interpretations are nearly equally likely, mark it unresolved and ask a specific question

ESCALATION RULES:
You must escalate to human (requires_hitl: true) only when:
- A value is genuinely ambiguous with equally valid interpretations
- Critical information is missing and cannot be inferred from context
- There is a direct contradiction that cannot be logically resolved
- The document appears to be corrupted or incomplete in a way that affects critical fields

HITL QUESTIONS must be:
- Specific, not general ("Is this date April 5th or May 4th?" not "Please clarify the date")
- Include the exact text that is ambiguous
- Include the possible interpretations you identified
- Prioritized — most critical questions first

YOUR OUTPUT must be a JSON object with this exact structure:
{
  "resolved_fields": {
    "field_name": "resolved value"
  },
  "unresolved_fields": ["field_name_1"],
  "confidence_after": 0.0 to 1.0,
  "reasoning_notes": "Detailed explanation of your reasoning process for each field",
  "requires_hitl": true or false,
  "hitl_questions": [
    "Specific question 1 with context and options",
    "Specific question 2 with context and options"
  ]
}

If requires_hitl is false, unresolved_fields must be empty.
If requires_hitl is true, hitl_questions must have at least one entry per unresolved field.

Return ONLY the JSON object. No preamble, no explanation, no markdown.
"""


class ReasoningAgent(BaseAgent):
    name = "reasoning"
    stage = RecordStage.REASONING

    async def _run(self, record: PipelineRecord) -> PipelineRecord:
        start = time.time()
        config = self.settings.load_config()

        if not record.parsed or not record.confidence:
            record.reasoning = ReasoningResult(
                confidence_after=0.0,
                tier_after=ConfidenceTier.RED,
                requires_hitl=True,
                hitl_questions=["Record is missing parsed data. Please re-submit the document."],
            )
            return record

        flagged = record.confidence.flagged_fields
        low_confidence_fields = [
            fc for fc in (record.parsed.field_confidences if record.parsed else [])
            if fc.confidence < 0.7
        ]

        context_summary = ""
        if record.context:
            context_summary = f"""
HISTORICAL CONTEXT:
- Known source: {record.context.known_source}
- Source pattern: {record.context.source_pattern or 'None'}
- Previous corrections: {json.dumps(record.context.historical_corrections[:3])}
"""

        prompt = f"""DOCUMENT TYPE: {record.parsed.document_type}
CURRENT CONFIDENCE SCORE: {record.confidence.overall_score:.2f}
ROUTING REASON: {record.confidence.routing_reason}

FLAGGED FIELDS:
{json.dumps(flagged)}

LOW CONFIDENCE FIELDS:
{json.dumps([{"field": fc.field, "value": fc.value, "confidence": fc.confidence, "reason": fc.reason} for fc in low_confidence_fields], indent=2)}

ALL EXTRACTED FIELDS:
{json.dumps(record.parsed.fields, indent=2)}
{context_summary}
ORIGINAL RAW TEXT:
---
{record.source_raw[:6000]}
---

Resolve the ambiguities in this record."""

        response = await self.router.complete(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            system=SYSTEM_PROMPT,
            temperature=self.temperature,
            max_tokens=4096,
        )

        duration_ms = int((time.time() - start) * 1000)

        try:
            data = await self._parse_json_with_retry(
                response=response,
                system_prompt=SYSTEM_PROMPT,
                user_message=prompt,
                agent_name=self.name,
            )
            score = float(data.get("confidence_after", record.confidence.overall_score))
            score = max(0.0, min(1.0, score))

            green = config.pipeline.confidence_green_threshold
            amber = config.pipeline.confidence_amber_threshold
            if score >= green:
                tier = ConfidenceTier.GREEN
            elif score >= amber:
                tier = ConfidenceTier.AMBER
            else:
                tier = ConfidenceTier.RED

            record.reasoning = ReasoningResult(
                resolved_fields=data.get("resolved_fields", {}),
                unresolved_fields=data.get("unresolved_fields", []),
                confidence_after=score,
                tier_after=tier,
                reasoning_notes=data.get("reasoning_notes", ""),
                requires_hitl=data.get("requires_hitl", False),
                hitl_questions=data.get("hitl_questions") or [],
            )

            # Merge resolved fields into parsed data
            if record.reasoning.resolved_fields and record.parsed is not None:
                if record.parsed.fields is None:
                    record.parsed.fields = {}
                record.parsed.fields.update(record.reasoning.resolved_fields)

        except Exception as e:
            logger.error(f"Reasoning agent failed: {e}")
            record.reasoning = ReasoningResult(
                confidence_after=0.0,
                tier_after=ConfidenceTier.RED,
                requires_hitl=True,
                hitl_questions=[f"Automated reasoning failed. Please review this record manually. Error: {str(e)}"],
                reasoning_notes=f"Error: {str(e)}",
            )

        self._add_audit(
            record,
            action="ambiguity_resolution",
            input_summary=f"{len(flagged)} flagged fields, score: {record.confidence.overall_score:.2f}",
            output_summary=f"Resolved {len(record.reasoning.resolved_fields)} fields, HITL: {record.reasoning.requires_hitl}",
            confidence_before=record.confidence.overall_score,
            confidence_after=record.reasoning.confidence_after,
            duration_ms=duration_ms,
        )

        return record
