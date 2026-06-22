"""
Markdown formatter — cleans markdown formatting from field values.

When LLMs process data they often include markdown-style formatting:
  **bold text** → should be stored as plain "bold text" or with proper field annotation
  *italic*      → stored as "italic"
  `code`        → stored as "code"
  # Header      → stripped
  - List item   → stored as "List item"

This module detects and strips markdown from field values before writing.
"""

import re
from typing import Any


def clean_field_value(value: Any) -> Any:
    """
    Clean markdown formatting from a field value.
    Returns the cleaned value. Non-strings are passed through unchanged.
    """
    if not isinstance(value, str):
        return value
    
    text = value
    
    # **bold** or __bold__ → bold
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'__(.+?)__', r'\1', text)
    
    # *italic* or _italic_ → italic
    #
    # IMPORTANT: the naive `\*(.+?)\*` / `_(.+?)_` patterns match *any* pair
    # of asterisks/underscores anywhere in a string. Real-world field values
    # routinely contain lone underscores/asterisks that are NOT markdown
    # emphasis — e.g. "INV_2024_0042", "john_doe@example.com",
    # "PROD_SKU_771", or dimension strings like "10*20*30 cm". Without a
    # boundary check, e.g. "PO_2024_001" gets mangled into "PO2024001" and
    # "10*20*30 cm" into "102030 cm".
    #
    # CommonMark itself requires `_` emphasis delimiters to sit at a word
    # boundary (not "intraword") for exactly this reason (so snake_case
    # isn't treated as emphasis). We apply the same word-boundary
    # requirement to `*` here too, since intraword `*` emphasis is
    # essentially never present in extracted business data but `*` is
    # commonly used as a literal multiplication/dimension separator.
    text = re.sub(r'(?<![\w*])\*(?!\*)([^\s*](?:[^*]*[^\s*])?)\*(?!\*)(?![\w*])', r'\1', text)
    text = re.sub(r'(?<![\w_])_(?!_)([^\s_](?:[^_]*[^\s_])?)_(?!_)(?![\w_])', r'\1', text)
    
    # `code` → code
    text = re.sub(r'`(.+?)`', r'\1', text)
    
    # ~~strikethrough~~ → strikethrough
    text = re.sub(r'~~(.+?)~~', r'\1', text)
    
    # ==highlight== → highlight
    text = re.sub(r'==(.+?)==', r'\1', text)
    
    # # Header → Header (remove leading #)
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    
    # > blockquote → just the text
    text = re.sub(r'^>\s*', '', text, flags=re.MULTILINE)
    
    # - or * or + list items → just the text
    text = re.sub(r'^[-*+]\s+', '', text, flags=re.MULTILINE)
    
    # Numbered list items: 1. text → text
    text = re.sub(r'^\d+\.\s+', '', text, flags=re.MULTILINE)
    
    # [link text](url) → link text
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    
    # ![alt](url) → alt
    text = re.sub(r'!\[([^\]]*)\]\([^\)]+\)', r'\1', text)
    
    # Horizontal rules
    text = re.sub(r'^[-*_]{3,}\s*$', '', text, flags=re.MULTILINE)
    
    # Clean up multiple spaces and leading/trailing whitespace
    text = re.sub(r'  +', ' ', text)
    text = text.strip()
    
    return text


def clean_record_data(data: dict) -> dict:
    """
    Apply markdown cleaning to all string values in a data dict.
    Returns a new dict with cleaned values.
    """
    return {k: clean_field_value(v) for k, v in data.items()}


def detect_markdown(value: Any) -> bool:
    """Returns True if the value contains markdown formatting."""
    if not isinstance(value, str):
        return False
    patterns = [
        r'\*\*.+?\*\*',  # bold
        r'__.+?__',       # bold alt
        r'(?<![\w*])\*(?!\*)[^\s*](?:[^*]*[^\s*])?\*(?!\*)(?![\w*])',  # italic
        r'(?<![\w_])_(?!_)[^\s_](?:[^_]*[^\s_])?_(?!_)(?![\w_])',       # italic alt
        r'`.+?`',         # code
        r'~~.+?~~',       # strikethrough
        r'^#{1,6}\s',     # headers
        r'^\s*[-*+]\s',   # lists
        r'\[.+?\]\(.+?\)', # links
    ]
    return any(re.search(p, value, re.MULTILINE) for p in patterns)


def has_markdown_in_data(data: dict) -> list[str]:
    """Return list of field names that contain markdown formatting."""
    return [k for k, v in data.items() if detect_markdown(v)]
