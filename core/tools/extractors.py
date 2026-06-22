"""
Email and URL extractors for the Intake Agent
"""

import logging
import re
from email import policy
from email.parser import BytesParser, Parser

logger = logging.getLogger(__name__)


def extract_email(path: str = None, raw: str = None) -> tuple[str, str]:
    """
    Extract text from an .eml email file or raw email string.
    Returns (text, document_type)
    """
    try:
        if path:
            with open(path, 'rb') as f:
                msg = BytesParser(policy=policy.default).parse(f)
        elif raw:
            msg = Parser(policy=policy.default).parsestr(raw)
        else:
            return "", "email"

        parts = []

        # Headers
        parts.append(f"From: {msg.get('From', '')}")
        parts.append(f"To: {msg.get('To', '')}")
        parts.append(f"Subject: {msg.get('Subject', '')}")
        parts.append(f"Date: {msg.get('Date', '')}")
        parts.append("")

        # Body
        if msg.is_multipart():
            for part in msg.walk():
                ct = part.get_content_type()
                if ct == 'text/plain':
                    payload = part.get_payload(decode=True)
                    if payload:
                        parts.append(payload.decode(part.get_content_charset() or 'utf-8', errors='replace'))
                elif ct == 'text/html':
                    # Strip HTML tags for plain text
                    payload = part.get_payload(decode=True)
                    if payload:
                        html = payload.decode(part.get_content_charset() or 'utf-8', errors='replace')
                        text = re.sub(r'<[^>]+>', ' ', html)
                        text = re.sub(r'\s+', ' ', text).strip()
                        parts.append(text)
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                parts.append(payload.decode(msg.get_content_charset() or 'utf-8', errors='replace'))

        return '\n'.join(parts), "email"

    except Exception as e:
        logger.warning(f"Email extraction failed: {e}")
        return raw or "", "email"


async def extract_url(url: str) -> tuple[str, str]:
    """
    Fetch a URL and extract its text content.
    Returns (text, document_type)
    """
    try:
        import httpx
        from html.parser import HTMLParser

        class TextExtractor(HTMLParser):
            def __init__(self):
                super().__init__()
                self.text_parts = []
                self.skip_tags = {'script', 'style', 'nav', 'footer', 'header'}
                self.current_skip = 0

            def handle_starttag(self, tag, attrs):
                if tag in self.skip_tags:
                    self.current_skip += 1

            def handle_endtag(self, tag):
                if tag in self.skip_tags:
                    self.current_skip = max(0, self.current_skip - 1)

            def handle_data(self, data):
                if self.current_skip == 0:
                    stripped = data.strip()
                    if stripped:
                        self.text_parts.append(stripped)

        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            headers = {'User-Agent': 'Mozilla/5.0 DataMoA/1.0 (data extraction)'}
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()

            content_type = resp.headers.get('content-type', '')

            if 'text/html' in content_type:
                extractor = TextExtractor()
                extractor.feed(resp.text)
                text = '\n'.join(extractor.text_parts)
                return text, "web_page"

            elif 'application/json' in content_type:
                import json
                data = resp.json()
                return json.dumps(data, indent=2), "json_data"

            elif 'text/' in content_type:
                return resp.text, "text"

            else:
                return f"[Binary content: {content_type}]", "binary"

    except Exception as e:
        logger.warning(f"URL extraction failed for {url}: {e}")
        return f"Failed to fetch {url}: {str(e)}", "url"
