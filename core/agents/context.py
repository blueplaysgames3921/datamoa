"""
Context Agent — enriches record with historical memory before confidence scoring
"""

import json
import logging
import time

from core.agents.base import BaseAgent
from core.pipeline.state import ContextData, PipelineRecord, RecordStage

logger = logging.getLogger(__name__)

CONTEXT_SYSTEM_PROMPT = """You are the Context Agent for a professional data entry system.

YOUR ROLE:
You receive a parsed record and historical memory about its source. Your job is to determine if this record matches known patterns and use that knowledge to improve field confidence before scoring.

YOU DO:
- Identify if the source is known (same vendor, same form type, same sender)
- Apply known corrections from historical data (e.g. "this vendor always writes dates as MM/DD/YY")
- Enrich fields that historical context makes clear
- Produce a context summary that downstream agents can use

YOU DO NOT:
- Make assumptions without historical evidence
- Change values that have high confidence
- Override explicit document content with memory

YOUR OUTPUT must be a JSON object:
{
  "known_source": true or false,
  "source_pattern": "description of the pattern if known, else null",
  "historical_corrections": [
    {"field": "field_name", "correction": "known correct format or value", "confidence": 0.0-1.0}
  ],
  "enriched_fields": {
    "field_name": "value from context"
  },
  "context_notes": "summary of what historical context was applied"
}

Return ONLY the JSON object. No preamble, no explanation, no markdown.
"""


class ContextAgent(BaseAgent):
    name = "context"
    stage = RecordStage.CONTEXT

    async def _run(self, record: PipelineRecord) -> PipelineRecord:
        start = time.time()

        # Load memory for this source
        memory_summary = self._load_memory(record)

        if not memory_summary:
            # No memory — skip model call, return empty context
            record.context = ContextData(context_notes="No historical context available")
            return record

        prompt = f"""Current record fields:
{json.dumps(record.parsed.fields if record.parsed else {}, indent=2)}

Document type: {record.parsed.document_type if record.parsed else 'unknown'}
Source: {record.source_path or 'unknown'}

Historical memory for this source:
{memory_summary}

Apply relevant context to this record."""

        response = await self.router.complete(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            system=CONTEXT_SYSTEM_PROMPT,
            temperature=self.temperature,
            max_tokens=2048,
        )

        duration_ms = int((time.time() - start) * 1000)

        try:
            data = await self._parse_json_with_retry(
                response=response,
                system_prompt=CONTEXT_SYSTEM_PROMPT,
                user_message=prompt,
                agent_name=self.name,
            )
            record.context = ContextData(**data)
        except Exception as e:
            record.context = ContextData(context_notes=f"Context agent error: {str(e)}")

        self._add_audit(
            record,
            action="context_enrichment",
            output_summary=record.context.context_notes,
            duration_ms=duration_ms,
        )

        return record

    def _load_memory(self, record: PipelineRecord) -> str:
        """
        Load relevant memory entries for this source.
        Matches by: source path, document type, and field name overlap.
        """
        from core.config.settings import MEMORY_DIR

        try:
            memory_files = list(MEMORY_DIR.glob("*.json"))
            if not memory_files:
                return ""

            source_key = (record.source_path or "").lower()
            doc_type = (record.parsed.document_type or "").lower() if record.parsed else ""
            field_names = set((record.parsed.fields or {}).keys()) if record.parsed else set()

            scored = []
            for mf in memory_files[:50]:
                try:
                    with open(mf) as f:
                        entry = json.load(f)

                    score = 0
                    entry_source = entry.get("source", "").lower()

                    # Source path match
                    if source_key and entry_source and (
                        source_key in entry_source or entry_source in source_key
                    ):
                        score += 10

                    # Document type match
                    entry_summary = entry.get("summary", "").lower()
                    if doc_type and doc_type in entry_summary:
                        score += 5

                    # Field name overlap with learned patterns
                    for pattern in entry.get("patterns", []):
                        examples = pattern.get("examples", [])
                        if any(fn in str(examples) for fn in field_names):
                            score += 3

                    # Corrections for known field names
                    for correction in entry.get("corrections", []):
                        if correction.get("field") in field_names:
                            score += 4

                    if score > 0:
                        scored.append((score, entry))
                except Exception:
                    continue

            if not scored:
                return ""

            # Return top 5 by relevance
            scored.sort(key=lambda x: x[0], reverse=True)
            return json.dumps([e for _, e in scored[:5]], indent=2)

        except Exception:
            return ""
