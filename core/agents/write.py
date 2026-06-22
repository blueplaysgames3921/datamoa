"""
Write Agent — the only agent that touches the destination system
Agentic and tool-aware. Uses tools to write to CSV, Sheets, Airtable, DB, or API.
"""

import json
import logging
import time
from typing import Any

from core.agents.base import BaseAgent
from core.pipeline.state import PipelineRecord, RecordStage, WriteResult

logger = logging.getLogger(__name__)

WRITE_SYSTEM_PROMPT = """You are the Write Agent for a professional data entry system.

YOUR ROLE:
You receive fully validated, resolved data and write it to the destination system using the available tools.

YOU ARE THE ONLY AGENT THAT WRITES DATA. This is a critical responsibility.

WRITING RULES:
1. Write every resolved field — do not skip any
2. Map field names to destination schema exactly as specified
3. If a field has no destination mapping, include it in a notes/overflow field if available, otherwise skip it
4. Never write null values to required fields — if a required field is null, abort and return an error
5. Confirm the write succeeded before returning success
6. If the write fails, do not retry — return the error and let the orchestrator handle retries

TOOL USAGE:
- Use exactly one write tool per record
- Choose the tool that matches the configured destination
- Pass all resolved fields as the data parameter
- Include the record ID for traceability

YOUR OUTPUT must be a JSON object:
{
  "success": true or false,
  "destination": "name of destination used",
  "record_id": "ID assigned by destination system if available",
  "written_fields": {"field": "value"},
  "error": "error message if failed, else null"
}

Return ONLY the JSON object after completing the tool call.
"""

# Write tools are defined here and passed to the model via LiteLLM tool calling
WRITE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "write_csv",
            "description": "Append a row of data to a local CSV file. Use when destination type is 'csv'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Absolute path to the CSV file"},
                    "data": {"type": "object", "description": "Field name to value mapping to write as a row"},
                    "record_id": {"type": "string", "description": "Pipeline record ID for traceability"},
                },
                "required": ["file_path", "data", "record_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_google_sheets",
            "description": "Append a row to a Google Sheets spreadsheet. Use when destination type is 'google_sheets'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "spreadsheet_id": {"type": "string", "description": "Google Sheets spreadsheet ID"},
                    "sheet_name": {"type": "string", "description": "Sheet tab name"},
                    "data": {"type": "object", "description": "Field name to value mapping"},
                    "record_id": {"type": "string", "description": "Pipeline record ID"},
                },
                "required": ["spreadsheet_id", "data", "record_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_airtable",
            "description": "Create a new record in an Airtable base. Use when destination type is 'airtable'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "base_id": {"type": "string"},
                    "table_name": {"type": "string"},
                    "data": {"type": "object", "description": "Field name to value mapping"},
                    "record_id": {"type": "string"},
                },
                "required": ["base_id", "table_name", "data", "record_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_database",
            "description": "Insert a row into a SQL database table. Use when destination type is 'database'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "connection_string": {"type": "string"},
                    "table": {"type": "string"},
                    "data": {"type": "object"},
                    "record_id": {"type": "string"},
                },
                "required": ["connection_string", "table", "data", "record_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_api",
            "description": "POST data to a custom REST API endpoint. Use when destination type is 'api'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Full endpoint URL"},
                    "data": {"type": "object", "description": "Field name to value mapping"},
                    "record_id": {"type": "string"},
                    "auth_header": {"type": "string", "description": "Authorization header value, e.g. Bearer token"},
                    "method": {"type": "string", "description": "HTTP method: POST, PUT, or PATCH"},
                },
                "required": ["url", "data", "record_id"],
            },
        },
    },
]


class WriteAgent(BaseAgent):
    name = "write"
    stage = RecordStage.WRITING

    async def _run(self, record: PipelineRecord) -> PipelineRecord:
        start = time.time()
        config = self.settings.load_config()

        if not record.parsed or not record.parsed.fields:
            record.write_result = WriteResult(
                success=False,
                destination="none",
                error="No data to write",
            )
            return record

        # Get active destination
        destinations = [d for d in config.destinations if d.enabled]
        if not destinations:
            record.write_result = WriteResult(
                success=False,
                destination="none",
                error="No write destination configured. Please configure a destination in Settings.",
            )
            return record

        dest = destinations[0]

        # Apply field mapping and exclusions
        raw_data = record.resolved_data or (record.parsed.fields if record.parsed else {})
        
        # Clean markdown formatting from values before writing
        from core.utils.markdown_cleaner import clean_record_data, has_markdown_in_data
        markdown_fields = has_markdown_in_data(raw_data)
        if markdown_fields:
            raw_data = clean_record_data(raw_data)
            logger.info(f"Cleaned markdown from {len(markdown_fields)} fields: {markdown_fields}")
        
        write_data: dict = {}
        for k, v in raw_data.items():
            if k in dest.exclude_fields:
                continue
            mapped_key = dest.field_mapping.get(k, k)
            write_data[mapped_key] = v

        prompt = f"""Write this data to the destination.

Destination type: {dest.type}
Destination name: {dest.name}
Destination config: {json.dumps(dest.config)}

Resolved data to write:
{json.dumps(write_data, indent=2)}

Record ID: {record.id}

Use the appropriate write tool."""

        # Use LiteLLM with tool calling
        import litellm
        import os

        self.router._inject_keys()

        messages = [
            {"role": "system", "content": WRITE_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]

        try:
            response = await litellm.acompletion(
                model=self.model,
                messages=messages,
                tools=WRITE_TOOLS,
                tool_choice="auto",
                temperature=0.0,
                max_tokens=2048,
            )

            msg = response.choices[0].message

            if msg.tool_calls:
                tool_call = msg.tool_calls[0]
                tool_name = tool_call.function.name
                tool_args = json.loads(tool_call.function.arguments)

                # Execute the tool
                write_result = await self._execute_write_tool(tool_name, tool_args, dest)
                record.write_result = write_result
            else:
                # Model returned text without tool call — parse as JSON
                content = msg.content or ""
                clean = content.strip()
                if clean.startswith("```"):
                    clean = clean.split("\n", 1)[1].rsplit("```", 1)[0].strip()
                data = json.loads(clean)
                record.write_result = WriteResult(**data)

        except Exception as e:
            logger.error(f"Write agent failed: {e}")
            record.write_result = WriteResult(
                success=False,
                destination=dest.name,
                error=str(e),
            )

        duration_ms = int((time.time() - start) * 1000)
        self._add_audit(
            record,
            action="data_write",
            output_summary=f"Success: {record.write_result.success}, Dest: {record.write_result.destination}",
            duration_ms=duration_ms,
            error=record.write_result.error,
        )

        return record

    async def _execute_write_tool(self, tool_name: str, args: dict, dest: Any) -> WriteResult:
        """Execute the actual write operation"""
        try:
            if tool_name == "write_csv":
                return await self._write_csv(args)
            elif tool_name == "write_google_sheets":
                return await self._write_google_sheets(args)
            elif tool_name == "write_airtable":
                return await self._write_airtable(args)
            elif tool_name == "write_database":
                return await self._write_database(args)
            elif tool_name == "write_api":
                return await self._write_api(args)
            else:
                return WriteResult(success=False, destination=dest.name, error=f"Unknown tool: {tool_name}")
        except Exception as e:
            return WriteResult(success=False, destination=dest.name, error=str(e))

    async def _write_csv(self, args: dict) -> WriteResult:
        import csv
        import aiofiles
        from pathlib import Path
        import os

        file_path = args["file_path"]
        data = args["data"]
        path = Path(file_path)

        # Create parent directories if needed
        path.parent.mkdir(parents=True, exist_ok=True)

        file_exists = path.exists()

        # If no file exists, create it fresh with headers
        async with aiofiles.open(file_path, "a", newline="", encoding="utf-8") as f:
            writer_content = ""
            if not file_exists:
                writer_content += ",".join(f'"{k}"' for k in data.keys()) + "\n"
            writer_content += ",".join(
                f'"{str(v).replace(chr(34), chr(39))}"' if v is not None else '""'
                for v in data.values()
            ) + "\n"
            await f.write(writer_content)

        action = "created" if not file_exists else "appended"
        return WriteResult(
            success=True,
            destination=f"{file_path} ({action})",
            written_fields=data,
        )

    async def _write_google_sheets(self, args: dict) -> WriteResult:
        from core.tools.google_sheets import write_to_sheet
        result = await write_to_sheet(
            spreadsheet_id=args["spreadsheet_id"],
            sheet_name=args.get("sheet_name", "Sheet1"),
            data=args["data"],
            record_id=args["record_id"],
        )
        return WriteResult(**result) if result.get("success") else WriteResult(
            success=False,
            destination="google_sheets",
            error=result.get("error", "Unknown error"),
        )

    async def _write_airtable(self, args: dict) -> WriteResult:
        import httpx

        key = self.settings.get_key("airtable")
        if not key:
            return WriteResult(success=False, destination="airtable", error="Airtable API key not configured")

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"https://api.airtable.com/v0/{args['base_id']}/{args['table_name']}",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"fields": args["data"]},
            )
            if resp.status_code == 200:
                result = resp.json()
                return WriteResult(
                    success=True,
                    destination="airtable",
                    record_id=result.get("id"),
                    written_fields=args["data"],
                )
            else:
                return WriteResult(success=False, destination="airtable", error=resp.text)

    async def _write_database(self, args: dict) -> WriteResult:
        from core.tools.database import write_to_database
        result = await write_to_database(
            connection_string=args["connection_string"],
            table=args["table"],
            data=args["data"],
            record_id=args["record_id"],
        )
        return WriteResult(**result) if result.get("success") else WriteResult(
            success=False,
            destination="database",
            error=result.get("error", "Unknown error"),
        )

    async def _write_api(self, args: dict) -> WriteResult:
        from core.tools.api import write_to_api
        result = await write_to_api(
            url=args["url"],
            data=args["data"],
            record_id=args["record_id"],
            auth_header=args.get("auth_header", ""),
            method=args.get("method", "POST"),
        )
        return WriteResult(**result) if result.get("success") else WriteResult(
            success=False,
            destination=args.get("url", "api"),
            error=result.get("error", "Unknown error"),
        )
