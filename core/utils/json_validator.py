"""
JSON Output Validator — validates structured output from agents and retries if malformed.
Every agent that expects JSON output should use this instead of raw json.loads().
"""

import json
import logging
import re
from typing import Any, Optional, Type

logger = logging.getLogger(__name__)


class JSONParseError(Exception):
    """Raised when JSON cannot be parsed after all retry attempts"""
    pass


def extract_json(text: str) -> str:
    """
    Attempt to extract valid JSON from model output.
    Handles:
    - Raw JSON
    - JSON wrapped in ```json ... ``` blocks  
    - JSON wrapped in ``` ... ``` blocks
    - JSON preceded by explanation text
    - Truncated JSON (attempts repair)
    """
    if not text or not text.strip():
        raise JSONParseError("Empty response from model")

    text = text.strip()

    # Strategy 1: Direct parse
    try:
        json.loads(text)
        return text
    except json.JSONDecodeError:
        pass

    # Strategy 2: Strip markdown code fences
    patterns = [
        r'```json\s*\n?(.*?)\n?```',
        r'```\s*\n?(.*?)\n?```',
        r'`({.*?})`',
        r'`(\[.*?\])`',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            candidate = match.group(1).strip()
            try:
                json.loads(candidate)
                return candidate
            except json.JSONDecodeError:
                pass

    # Strategy 3: Find first { or [ and extract to matching close
    for start_char, end_char in [('{', '}'), ('[', ']')]:
        start_idx = text.find(start_char)
        if start_idx == -1:
            continue

        # Find matching close bracket
        depth = 0
        in_string = False
        escape_next = False

        for i, ch in enumerate(text[start_idx:], start_idx):
            if escape_next:
                escape_next = False
                continue
            if ch == '\\' and in_string:
                escape_next = True
                continue
            if ch == '"':
                in_string = not in_string
            if not in_string:
                if ch == start_char:
                    depth += 1
                elif ch == end_char:
                    depth -= 1
                    if depth == 0:
                        candidate = text[start_idx:i + 1]
                        try:
                            json.loads(candidate)
                            return candidate
                        except json.JSONDecodeError:
                            break

    # Strategy 4: Attempt to repair common truncation issues
    repaired = _attempt_repair(text)
    if repaired:
        try:
            json.loads(repaired)
            return repaired
        except json.JSONDecodeError:
            pass

    raise JSONParseError(f"Could not extract valid JSON from response (first 200 chars): {text[:200]}")


def _attempt_repair(text: str) -> Optional[str]:
    """Attempt to repair common JSON issues"""
    # Find JSON start
    start = text.find('{')
    if start == -1:
        start = text.find('[')
    if start == -1:
        return None

    candidate = text[start:]

    # Remove trailing commas before } or ]
    candidate = re.sub(r',\s*([}\]])', r'\1', candidate)

    # Close unclosed strings
    # Count quotes
    in_string = False
    escape_next = False
    for ch in candidate:
        if escape_next:
            escape_next = False
            continue
        if ch == '\\':
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string

    if in_string:
        candidate += '"'

    # Close unclosed brackets
    opens = candidate.count('{') - candidate.count('}')
    opens_sq = candidate.count('[') - candidate.count(']')

    candidate += ']' * opens_sq + '}' * opens

    try:
        json.loads(candidate)
        return candidate
    except Exception:
        return None


def parse_agent_json(response: str, agent_name: str) -> dict:
    """
    Parse JSON from an agent response with detailed error logging.
    Returns parsed dict or raises JSONParseError.
    """
    try:
        raw = extract_json(response)
        parsed = json.loads(raw)
        if not isinstance(parsed, (dict, list)):
            raise JSONParseError(f"Expected dict or list, got {type(parsed).__name__}")
        return parsed
    except (JSONParseError, json.JSONDecodeError) as e:
        logger.error(f"[{agent_name}] JSON parse failed: {e}")
        logger.debug(f"[{agent_name}] Raw response: {response[:500]}")
        raise JSONParseError(f"Agent '{agent_name}' returned invalid JSON: {e}") from e


def build_retry_prompt(original_prompt: str, failed_response: str, error: str, schema_hint: str = "") -> str:
    """
    Build a retry prompt when JSON parsing failed.
    Tells the model exactly what went wrong and what to fix.
    """
    schema_section = f"\nExpected schema: {schema_hint}" if schema_hint else ""
    return f"""Your previous response could not be parsed as valid JSON.

Error: {error}

Your response was:
{failed_response[:400]}

{schema_section}

IMPORTANT: Return ONLY a valid JSON object. 
- No explanatory text before or after
- No markdown code fences (no ```)
- No trailing commas
- All strings must be properly quoted
- All brackets must be closed

Try again:"""
