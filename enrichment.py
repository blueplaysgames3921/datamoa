"""
Enrichment Agent — fills missing fields via external lookups
Only runs when needed (missing fields after reasoning). Uses web search.
"""

import json
import logging
import time

import litellm

from core.agents.base import BaseAgent
from core.pipeline.state import PipelineRecord, RecordStage

logger = logging.getLogger(__name__)

ENRICHMENT_SYSTEM_PROMPT = """You are the Enrichment Agent for a professional data entry system.

YOUR ROLE:
You receive a record with specific missing fields and you attempt to fill them using web search and external lookups.

YOU ONLY:
- Fill fields that are explicitly listed as missing
- Use search results to find the correct value
- Cite where you found the value

YOU NEVER:
- Modify fields that already have values
- Guess — if you can't find it via search, leave it null
- Add fields that weren't requested

ENRICHMENT RULES:
1. Search for the most specific query possible
2. Only accept a value if you are confident it is correct
3. If multiple conflicting results appear, leave the field null
4. Always include the source URL for any enriched value

YOUR OUTPUT must be a JSON object:
{
  "enriched_fields": {
    "field_name": "found value"
  },
  "sources": {
    "field_name": "URL or source where value was found"
  },
  "not_found": ["field_name_1"],
  "enrichment_notes": "summary of what was found and what wasn't"
}

Return ONLY the JSON object. No preamble, no explanation, no markdown.
"""

ENRICHMENT_TOOLS = [
    {
        "type": "web_search_20250305",
        "name": "web_search",
    }
]


class EnrichmentAgent(BaseAgent):
    name = "enrichment"
    stage = RecordStage.ENRICHMENT

    async def _run(self, record: PipelineRecord) -> PipelineRecord:
        start = time.time()

        if not record.parsed:
            return record

        # Find fields with null/missing values
        missing = [
            k for k, v in record.parsed.fields.items()
            if v is None or v == "" or v == "null"
        ]

        if not missing:
            return record

        self.router._inject_keys()

        prompt = f"""Record type: {record.parsed.document_type}

Known fields:
{json.dumps({k: v for k, v in record.parsed.fields.items() if k not in missing}, indent=2)}

Missing fields to enrich:
{json.dumps(missing, indent=2)}

Find the missing values using web search."""

        try:
            messages = [
                {"role": "system", "content": ENRICHMENT_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ]

            response = await litellm.acompletion(
                model=self.model,
                messages=messages,
                tools=ENRICHMENT_TOOLS,
                temperature=0.0,
                max_tokens=2048,
            )

            # Collect all text content from response (may include tool use blocks)
            full_text = ""
            for block in response.choices[0].message.content or []:
                if isinstance(block, str):
                    full_text += block
                elif hasattr(block, "text"):
                    full_text += block.text

            if not full_text:
                full_text = response.choices[0].message.content or ""

            duration_ms = int((time.time() - start) * 1000)

            try:
                clean = full_text.strip()
                if clean.startswith("```"):
                    clean = clean.split("\n", 1)[1].rsplit("```", 1)[0].strip()
                data = json.loads(clean)

                enriched = data.get("enriched_fields", {})
                if enriched and record.parsed:
                    record.parsed.fields.update(enriched)

            except Exception as e:
                logger.warning(f"Enrichment JSON parse failed: {e}")

            self._add_audit(
                record,
                action="field_enrichment",
                input_summary=f"Missing fields: {missing}",
                output_summary=f"Enriched: {list(enriched.keys()) if 'enriched' in locals() else []}",
                duration_ms=duration_ms,
            )

        except Exception as e:
            logger.warning(f"Enrichment agent skipped: {e}")

        return record
