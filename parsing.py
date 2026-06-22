"""
Parsing Agent — extracts structured data from raw text
Most LLM-intensive agent in the pipeline
"""

import json
import logging
import time

from core.agents.base import BaseAgent
from core.pipeline.state import (
    FieldConfidence,
    ParsedData,
    PipelineRecord,
    RecordStage,
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are the Parsing Agent for a professional data entry system.

YOUR ROLE:
You receive raw extracted text from a document and your job is to identify and extract every discrete piece of data it contains into structured fields.

YOU ARE NOT:
- Interpreting business logic
- Making decisions about what to do with the data
- Validating against external rules
- Enriching or filling in missing data
- Guessing values that are not present in the text

YOUR JOB IS ONLY:
- Identifying what fields exist in this document
- Extracting the value for each field exactly as it appears
- Assigning a confidence score to each extraction
- Flagging anything ambiguous or uncertain

EXTRACTION RULES:
1. Extract every field you can identify — do not skip any
2. Use the exact value as it appears in the text — do not normalize, reformat, or clean
3. If a field appears multiple times with different values, extract all occurrences with a suffix: field_1, field_2, etc.
4. If a value is partially illegible, extract what you can and mark confidence low
5. If a field label exists but the value is blank, extract it with value null and confidence 0.0
6. Numbers: extract exactly as written — "1,234.56" stays "1,234.56", not 1234.56
7. Dates: extract exactly as written — "04/05/89" stays "04/05/89", not converted
8. Names: extract exactly as written — do not reorder first/last name
9. Currency: extract with symbol — "$1,234" not "1234"

CONFIDENCE SCORING:
- 1.0: Completely clear, unambiguous, clean text
- 0.8-0.99: Clear but minor formatting uncertainty
- 0.6-0.79: Somewhat unclear — OCR artifacts, ambiguous abbreviations, context-dependent
- 0.4-0.59: Significant uncertainty — multiple interpretations possible
- 0.0-0.39: Very low confidence — mostly guessing, illegible, or inferred

FLAG a field if:
- Its value could reasonably mean two different things
- The field label is ambiguous
- The value has OCR artifacts or damage
- There is a conflict between two values for the same apparent field
- You had to infer the field name from context

YOUR OUTPUT must be a JSON object with this exact structure:
{
  "fields": {
    "field_name": "exact value as extracted"
  },
  "field_confidences": [
    {
      "field": "field_name",
      "value": "exact value",
      "confidence": 0.0 to 1.0,
      "reason": "brief explanation if confidence < 0.9 or flagged",
      "flagged": true or false
    }
  ],
  "document_type": "invoice | purchase_order | receipt | form | contract | table | letter | report | unknown",
  "language": "ISO 639-1 code",
  "parse_notes": "Any overall observations about parsing difficulty, document quality, or important context"
}

Return ONLY the JSON object. No preamble, no explanation, no markdown code blocks.
"""


class ParsingAgent(BaseAgent):
    name = "parsing"
    stage = RecordStage.PARSING

    async def _run(self, record: PipelineRecord) -> PipelineRecord:
        start = time.time()

        if not record.source_raw or len(record.source_raw.strip()) < 5:
            record.parsed = ParsedData(
                raw_text=record.source_raw or "",
                parse_notes="No content to parse",
            )
            return record

        response = await self.router.complete(
            model=self.model,
            messages=[{
                "role": "user",
                "content": f"Parse this document and extract all fields:\n\n{record.source_raw}"
            }],
            system=SYSTEM_PROMPT,
            temperature=self.temperature,
            max_tokens=8192,
        )

        duration_ms = int((time.time() - start) * 1000)

        try:
            data = await self._parse_json_with_retry(
                response=response,
                system_prompt=SYSTEM_PROMPT,
                user_message=f"Parse this document and extract all fields:\n\n{record.source_raw[:3000]}",
                agent_name=self.name,
            )

            field_confidences = [
                FieldConfidence(**{k: v for k, v in fc.items() if k in {"field","value","confidence","reason","flagged"}})
                for fc in data.get("field_confidences", [])
                if isinstance(fc, dict) and "field" in fc
            ]

            record.parsed = ParsedData(
                fields=data.get("fields", {}),
                field_confidences=field_confidences,
                raw_text=record.source_raw,
                document_type=data.get("document_type", "unknown"),
                language=data.get("language", "en"),
                parse_notes=data.get("parse_notes", ""),
            )

        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"Parsing agent JSON decode failed: {e}\nResponse: {response[:500]}")
            # Graceful degradation — store raw response, mark low confidence
            record.parsed = ParsedData(
                raw_text=record.source_raw,
                parse_notes=f"Parsing failed to produce structured output: {str(e)}",
            )
            if record.parsed is None:
                record.parsed = ParsedData(raw_text=record.source_raw or "")
            record.parsed.field_confidences = [
                FieldConfidence(
                    field="_parse_error",
                    value=response[:200],
                    confidence=0.0,
                    reason="Model returned non-JSON response",
                    flagged=True,
                )
            ]

        self._add_audit(
            record,
            action="field_extraction",
            input_summary=f"{len(record.source_raw)} chars of raw text",
            output_summary=f"Extracted {len(record.parsed.fields)} fields",
            duration_ms=duration_ms,
        )

        return record
