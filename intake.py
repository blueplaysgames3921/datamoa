"""
Intake Agent — receives raw input, identifies type, extracts raw text
First agent in the pipeline. Does zero interpretation.
"""

import base64
import logging

from core.agents.base import BaseAgent
from core.pipeline.state import PipelineRecord, RecordStage

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are the Intake Agent for a professional data entry system.

YOUR ROLE:
You receive raw input — a file path, URL, text, or binary content — and your sole job is to:
1. Identify what type of input this is
2. Extract all readable text from it
3. Report what you found — nothing more

YOU DO NOT:
- Interpret the meaning of any content
- Make judgments about data quality
- Attempt to structure or categorize the data
- Add, remove, or modify any content
- Skip any text, even if it seems irrelevant

YOUR OUTPUT must be a JSON object with this exact structure:
{
  "document_type": "invoice | form | spreadsheet | email | table | letter | handwritten | image | unknown",
  "language": "ISO 639-1 language code, e.g. en, fr, de",
  "raw_text": "Every single character of readable text extracted from the input, verbatim",
  "extraction_notes": "Any issues encountered during extraction — missing pages, illegible sections, encoding problems, etc.",
  "confidence": 0.0 to 1.0 — how completely you extracted the content
}

EXTRACTION RULES:
- Preserve all whitespace, line breaks, and formatting as-is
- Include headers, footers, watermarks, and marginalia
- For tables, preserve row/column structure using spacing or pipes
- For forms, include both field labels and their values
- For images with text, transcribe all visible text
- If a section is illegible, mark it as [ILLEGIBLE] — do not guess

Return ONLY the JSON object. No preamble, no explanation, no markdown.
"""


class IntakeAgent(BaseAgent):
    name = "intake"
    stage = RecordStage.INTAKE

    async def _run(self, record: PipelineRecord) -> PipelineRecord:
        """
        Extract raw text from the input source.
        Tries native extraction first (pdfplumber, openpyxl, etc.)
        Falls back to model-based OCR for images and handwritten content.
        """
        import time
        start = time.time()

        raw_text = ""
        source_type = record.source_type

        # --- Native extraction (no model needed) ---
        if source_type == "text":
            raw_text = record.source_raw
            doc_type = "text"

        elif source_type == "pdf" and record.source_path:
            raw_text, doc_type = self._extract_pdf(record.source_path)

        elif source_type == "csv" and record.source_path:
            raw_text, doc_type = self._extract_csv(record.source_path)

        elif source_type in ("xlsx", "xls") and record.source_path:
            raw_text, doc_type = self._extract_excel(record.source_path)

        elif source_type in ("docx",) and record.source_path:
            raw_text, doc_type = self._extract_docx(record.source_path)

        elif source_type in ("png", "jpg", "jpeg", "webp", "tiff", "bmp"):
            # Use model for OCR
            raw_text, doc_type = await self._extract_image(record)

        elif source_type in ("eml", "email"):
            from core.tools.extractors import extract_email
            raw_text, doc_type = extract_email(path=record.source_path, raw=record.source_raw)

        elif source_type in ("url", "http", "https"):
            from core.tools.extractors import extract_url
            url = record.source_path or record.source_raw or ""
            raw_text, doc_type = await extract_url(url)

        else:
            # Fallback — pass raw content to model
            raw_text = record.source_raw or ""
            doc_type = "unknown"

        # If native extraction (or image OCR) got good content, no further
        # model call is needed. For images, even short OCR output is treated
        # as final — re-sending the base64 image bytes as plain "text" to a
        # second model call (the branch below) would be both wasteful and
        # nonsensical, since that branch doesn't do multimodal extraction.
        if (raw_text and len(raw_text.strip()) > 20) or doc_type == "image":
            record.source_raw = raw_text
            from core.pipeline.state import ParsedData
            record.parsed = record.parsed or ParsedData()
            record.parsed.raw_text = raw_text
            record.parsed.document_type = doc_type

        else:
            # Use model to extract what we couldn't natively
            response = await self.router.complete(
                model=self.model,
                messages=[{"role": "user", "content": f"Extract all text from this content:\n\n{record.source_raw or '[binary content]'}"}],
                system=SYSTEM_PROMPT,
                temperature=self.temperature,
                max_tokens=8192,
            )

            import json
            try:
                data = json.loads(response)
                raw_text = data.get("raw_text", "")
                doc_type = data.get("document_type", "unknown")

                from core.pipeline.state import ParsedData
                record.parsed = record.parsed or ParsedData()
                record.parsed.raw_text = raw_text
                record.parsed.document_type = doc_type
                record.parsed.language = data.get("language", "en")
                record.source_raw = raw_text
            except json.JSONDecodeError:
                record.source_raw = response
                record.parsed = record.parsed or ParsedData()
                record.parsed.raw_text = response

        duration_ms = int((time.time() - start) * 1000)
        self._add_audit(
            record,
            action="text_extraction",
            input_summary=f"Source: {record.source_type}, path: {record.source_path}",
            output_summary=f"Extracted {len(record.source_raw)} characters",
            duration_ms=duration_ms,
        )

        return record

    def _extract_pdf(self, path: str) -> tuple[str, str]:
        try:
            import pdfplumber
            text_parts = []
            with pdfplumber.open(path) as pdf:
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        text_parts.append(text)
            return "\n\n".join(text_parts), "pdf"
        except Exception as e:
            logger.warning(f"PDF extraction failed: {e}")
            return "", "pdf"

    def _extract_csv(self, path: str) -> tuple[str, str]:
        try:
            import csv
            rows = []
            with open(path, newline="", encoding="utf-8-sig") as f:
                reader = csv.reader(f)
                for row in reader:
                    rows.append(" | ".join(row))
            return "\n".join(rows), "spreadsheet"
        except Exception as e:
            logger.warning(f"CSV extraction failed: {e}")
            return "", "spreadsheet"

    def _extract_excel(self, path: str) -> tuple[str, str]:
        try:
            import openpyxl
            wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
            parts = []
            for sheet in wb.worksheets:
                parts.append(f"=== Sheet: {sheet.title} ===")
                for row in sheet.iter_rows(values_only=True):
                    parts.append(" | ".join(str(c) if c is not None else "" for c in row))
            return "\n".join(parts), "spreadsheet"
        except Exception as e:
            logger.warning(f"Excel extraction failed: {e}")
            return "", "spreadsheet"

    def _extract_docx(self, path: str) -> tuple[str, str]:
        try:
            from docx import Document
            doc = Document(path)
            return "\n".join(p.text for p in doc.paragraphs), "document"
        except Exception as e:
            logger.warning(f"DOCX extraction failed: {e}")
            return "", "document"

    async def _extract_image(self, record: PipelineRecord) -> tuple[str, str]:
        """Use model for image OCR"""
        image_b64 = ""
        mime_type = "image/png"

        if record.source_path:
            with open(record.source_path, "rb") as f:
                content = f.read()
            image_b64 = base64.b64encode(content).decode()
            record.source_raw = image_b64

            ext = record.source_type.lower()
            mime_map = {
                "jpg": "image/jpeg", "jpeg": "image/jpeg",
                "png": "image/png", "webp": "image/webp",
                "tiff": "image/tiff", "bmp": "image/bmp",
            }
            mime_type = mime_map.get(ext, "image/png")
        elif record.source_raw:
            # Already base64-encoded content with no source_path on disk
            image_b64 = record.source_raw

        if not image_b64:
            return "", "image"

        # Send the actual image bytes to the model as a multimodal message —
        # without this, the model receives only a text instruction and has
        # nothing to transcribe.
        response = await self.router.complete(
            model=self.model,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": "Extract all text from this image."},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime_type};base64,{image_b64}"},
                    },
                ],
            }],
            system=SYSTEM_PROMPT,
            temperature=self.temperature,
            max_tokens=8192,
        )

        # Parse the structured JSON response (same schema as the generic
        # model-based extraction path below) instead of treating the raw
        # JSON-formatted response string as the extracted text.
        import json
        try:
            data = json.loads(response)
            raw_text = data.get("raw_text", "")
            doc_type = data.get("document_type", "image")
            return raw_text, doc_type
        except (json.JSONDecodeError, TypeError):
            # Model didn't return valid JSON — fall back to the raw response
            return response, "image"
