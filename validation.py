"""
Validation Agent — checks resolved data against rules before writing
"""

import json
import logging
import time

from core.agents.base import BaseAgent
from core.pipeline.state import PipelineRecord, RecordStage, ValidationResult

logger = logging.getLogger(__name__)

VALIDATION_SYSTEM_PROMPT = """You are the Validation Agent for a professional data entry system.

YOUR ROLE:
You receive a fully parsed and reasoned record and validate it before it is written to the destination system.

YOU CHECK FOR:
1. Required fields — are all critical fields present and non-null?
2. Format validity — do dates look like dates, numbers like numbers, emails like emails?
3. Logical consistency — do related fields agree? (e.g. line items sum to total, date ranges are valid)
4. Duplicate detection — is there a record ID or combination of fields suggesting this is a duplicate?
5. Range checks — are numeric values within plausible ranges?
6. Cross-field constraints — do conditional fields satisfy their conditions?

YOU DO NOT:
- Look up external data
- Make business decisions
- Approve or reject based on business rules not present in the data itself

VALIDATION RULES:
- A field "fails" if it is missing when it should be present, or its value is clearly in the wrong format
- A field "warns" if it looks suspicious but could be valid
- A field "passes" if it meets all checks
- Mark is_duplicate: true only if you are highly confident this is a duplicate

YOUR OUTPUT must be a JSON object:
{
  "passed": true or false,
  "field_results": {
    "field_name": true (pass) or false (fail)
  },
  "errors": ["specific error message 1"],
  "warnings": ["specific warning message 1"],
  "is_duplicate": true or false,
  "duplicate_of": "record_id if known, else null"
}

passed is true only if there are zero errors (warnings are acceptable).

Return ONLY the JSON object. No preamble, no explanation, no markdown.
"""


class ValidationAgent(BaseAgent):
    name = "validation"
    stage = RecordStage.VALIDATION

    def _check_duplicates(self, record: PipelineRecord) -> tuple[bool, str | None]:
        """
        Check for duplicates against completed records stored on disk.
        Uses key field fingerprinting — not LLM-based.
        """
        if not record.parsed or not record.parsed.fields:
            return False, None

        from core.config.settings import QUEUE_DIR
        import json

        # Build fingerprint from high-value fields
        fp_fields = {}
        for k, v in (record.parsed.fields or {}).items():
            kl = k.lower()
            if any(term in kl for term in ['id', 'number', 'invoice', 'ref', 'order', 'amount', 'total', 'date', 'name', 'email']):
                if v and str(v).strip():
                    fp_fields[k] = str(v).strip().lower()

        if not fp_fields:
            return False, None

        try:
            for rfile in QUEUE_DIR.glob("*.json"):
                if rfile.stem == record.id:
                    continue
                try:
                    existing = json.loads(rfile.read_text())
                    existing_fields = existing.get("parsed", {}).get("fields", {}) if existing.get("parsed") else {}
                    if not existing_fields:
                        continue
                    # Count matching fingerprint fields
                    matches = sum(
                        1 for k, v in fp_fields.items()
                        if str(existing_fields.get(k, "")).strip().lower() == v
                    )
                    if matches >= min(3, len(fp_fields)) and matches > 0:
                        return True, existing.get("id")
                except Exception:
                    continue
        except Exception:
            pass

        return False, None

    async def _run(self, record: PipelineRecord) -> PipelineRecord:
        start = time.time()

        if not record.parsed or not record.parsed.fields:
            record.validation = ValidationResult(
                passed=False,
                errors=["No data to validate"],
            )
            return record

        parsed_fields = record.parsed.fields if record.parsed else {}
        doc_type = record.parsed.document_type if record.parsed else "unknown"
        prompt = f"""Document type: {doc_type}

Fields to validate:
{json.dumps(parsed_fields, indent=2)}

Reasoning notes: {record.reasoning.reasoning_notes if record.reasoning else 'None'}

Validate this record."""

        # Run real duplicate check before LLM validation
        is_dup, dup_of = self._check_duplicates(record)

        response = await self.router.complete(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            system=VALIDATION_SYSTEM_PROMPT,
            temperature=self.temperature,
            max_tokens=2048,
        )

        duration_ms = int((time.time() - start) * 1000)

        try:
            data = await self._parse_json_with_retry(
                response=response,
                system_prompt=VALIDATION_SYSTEM_PROMPT,
                user_message=prompt,
                agent_name=self.name,
            )
            known = {"passed","field_results","errors","warnings","is_duplicate","duplicate_of"}
            result = ValidationResult(**{k:v for k,v in data.items() if k in known})
            # Override duplicate detection with our actual check
            if is_dup:
                result.is_duplicate = True
                result.duplicate_of = dup_of
                if result.passed:  # Fail if we found a real duplicate
                    result.passed = False
                    result.errors.append(f"Duplicate of record {dup_of[:8] if dup_of else 'unknown'}")
            record.validation = result
        except Exception as e:
            record.validation = ValidationResult(
                passed=False,
                errors=[f"Validation agent error: {str(e)}"],
            )

        self._add_audit(
            record,
            action="field_validation",
            input_summary=f"{len(record.parsed.fields)} fields",
            output_summary=f"Passed: {record.validation.passed}, Errors: {len(record.validation.errors)}",
            duration_ms=duration_ms,
        )

        return record
