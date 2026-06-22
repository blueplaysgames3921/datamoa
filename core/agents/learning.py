"""
Learning Agent — analyzes resolved records and updates Context Agent memory
Runs periodically, not per-record. Makes the system smarter over time.
"""

import json
import logging
import time
import uuid
from datetime import datetime

from core.agents.base import BaseAgent
from core.config.settings import MEMORY_DIR
from core.pipeline.state import PipelineRecord, RecordStage

logger = logging.getLogger(__name__)

LEARNING_SYSTEM_PROMPT = """You are the Learning Agent for a professional data entry system.

YOUR ROLE:
You analyze a batch of completed records — including any human corrections made during HITL review — and extract reusable patterns that will help future records from similar sources process more accurately.

YOU IDENTIFY:
1. Source patterns — what does this source consistently look like?
2. Field patterns — how does this source format dates, numbers, names?
3. Common corrections — what did humans fix that the system got wrong?
4. Document type signatures — what fields always appear together?
5. Known entities — company names, codes, abbreviations that recur

YOU DO NOT:
- Store personally identifiable information
- Store specific field values (amounts, names) — only structural patterns
- Create rules that would override explicit document content

YOUR OUTPUT must be a JSON object:
{
  "source_key": "identifier for this source (domain, vendor name, form type)",
  "patterns": [
    {
      "type": "date_format | number_format | field_alias | document_structure | entity",
      "description": "clear description of the pattern",
      "examples": ["example_1", "example_2"],
      "confidence": 0.0 to 1.0
    }
  ],
  "corrections": [
    {
      "field": "field_name",
      "wrong": "what system extracted",
      "right": "what human corrected to",
      "pattern": "explanation of the correction rule"
    }
  ],
  "summary": "brief description of what was learned"
}

Only emit patterns you are confident in (confidence >= 0.7).
Return ONLY the JSON object. No preamble, no explanation, no markdown.
"""


class LearningAgent(BaseAgent):
    name = "learning"
    stage = RecordStage.AUDIT  # Runs after audit, not a pipeline stage per se

    async def run_batch(self, records: list[PipelineRecord]) -> dict:
        """
        Analyze a batch of completed records and update memory.
        Called periodically by the orchestrator.
        """
        start = time.time()

        if not records:
            return {"learned": 0}

        # Only learn from records with HITL corrections — highest signal
        records_with_hitl = [r for r in records if r.hitl and r.hitl.resolved_fields]

        if not records_with_hitl:
            logger.debug("No HITL corrections in batch — skipping learning")
            return {"learned": 0}

        batch_summary = []
        for r in records_with_hitl[:10]:  # Cap batch size
            batch_summary.append({
                "source": r.source_path or r.source_type,
                "document_type": r.parsed.document_type if r.parsed else "unknown",
                "parsing_issues": [
                    fc.model_dump() for fc in (r.parsed.field_confidences if r.parsed else [])
                    if fc.flagged or fc.confidence < 0.7
                ],
                "hitl_corrections": r.hitl.resolved_fields if r.hitl else {},
                "hitl_notes": r.hitl.notes if r.hitl else "",
            })

        prompt = f"""Learn from these {len(records_with_hitl)} corrected records:

{json.dumps(batch_summary, indent=2)}

Extract reusable patterns for future processing."""

        try:
            response = await self.router.complete(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                system=LEARNING_SYSTEM_PROMPT,
                temperature=self.temperature,
                max_tokens=2048,
            )

            clean = response.strip()
            if clean.startswith("```"):
                clean = clean.split("\n", 1)[1].rsplit("```", 1)[0].strip()

            data = json.loads(clean)

            # Persist to memory store
            self._save_memory(data)

            duration_ms = int((time.time() - start) * 1000)
            logger.info(f"Learning agent processed {len(records_with_hitl)} records in {duration_ms}ms")

            return {
                "learned": len(data.get("patterns", [])),
                "corrections": len(data.get("corrections", [])),
                "source": data.get("source_key", "unknown"),
            }

        except Exception as e:
            logger.error(f"Learning agent failed: {e}")
            return {"learned": 0, "error": str(e)}

    def _save_memory(self, data: dict):
        """Persist learned patterns to memory directory"""
        memory_id = str(uuid.uuid4())[:8]
        memory_file = MEMORY_DIR / f"pattern_{memory_id}.json"

        with open(memory_file, "w") as f:
            json.dump({
                "id": memory_id,
                "created_at": datetime.utcnow().isoformat(),
                "source": data.get("source_key", "unknown"),
                "patterns": data.get("patterns", []),
                "corrections": data.get("corrections", []),
                "summary": data.get("summary", ""),
            }, f, indent=2)

        logger.info(f"Saved memory pattern: {memory_id} for source: {data.get('source_key')}")

    async def _run(self, record: PipelineRecord) -> PipelineRecord:
        """Per-record stub — learning runs in batch mode only"""
        return record
