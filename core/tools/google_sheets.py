"""
Google Sheets OAuth helper — handles OAuth2 flow for Google Sheets write destination
Stores tokens locally in the data directory
"""

import json
import logging
import os
from pathlib import Path

from core.config.settings import DATA_DIR

logger = logging.getLogger(__name__)

TOKENS_FILE = DATA_DIR / "google_tokens.json"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def get_credentials():
    """Get valid Google credentials, refreshing if needed"""
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request

        if not TOKENS_FILE.exists():
            return None

        with open(TOKENS_FILE) as f:
            token_data = json.load(f)

        creds = Credentials.from_authorized_user_info(token_data, SCOPES)

        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            _save_credentials(creds)

        return creds if creds and creds.valid else None

    except ImportError:
        logger.warning("google-auth not installed: pip install google-auth google-auth-oauthlib google-api-python-client")
        return None
    except Exception as e:
        logger.error(f"Google credentials error: {e}")
        return None


def _save_credentials(creds):
    """Persist credentials to disk"""
    with open(TOKENS_FILE, "w") as f:
        f.write(creds.to_json())


async def write_to_sheet(spreadsheet_id: str, sheet_name: str, data: dict, record_id: str) -> dict:
    """
    Append a row to a Google Sheet.
    Returns {"success": bool, "message": str}
    """
    creds = get_credentials()
    if not creds:
        return {
            "success": False,
            "error": "Google Sheets not authenticated. Please complete OAuth flow in Settings → Destinations."
        }

    try:
        from googleapiclient.discovery import build

        service = build("sheets", "v4", credentials=creds)
        sheet = service.spreadsheets()

        # Get existing headers from row 1
        range_name = f"{sheet_name}!1:1"
        result = sheet.values().get(spreadsheetId=spreadsheet_id, range=range_name).execute()
        existing_headers = result.get("values", [[]])[0] if result.get("values") else []

        # Determine column order
        if existing_headers:
            # Use existing header order, append new columns
            headers = existing_headers
            for key in data.keys():
                if key not in headers:
                    headers.append(key)
        else:
            # First write — create headers
            headers = list(data.keys())
            header_body = {"values": [headers]}
            sheet.values().append(
                spreadsheetId=spreadsheet_id,
                range=f"{sheet_name}!A1",
                valueInputOption="RAW",
                body=header_body,
            ).execute()

        # Build row in header order
        row = [str(data.get(h, "")) for h in headers]

        body = {"values": [row]}
        result = sheet.values().append(
            spreadsheetId=spreadsheet_id,
            range=f"{sheet_name}!A1",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body=body,
        ).execute()

        return {
            "success": True,
            "destination": f"Google Sheets: {sheet_name}",
            "record_id": record_id,
            "written_fields": data,
        }

    except Exception as e:
        logger.error(f"Google Sheets write failed: {e}")
        return {"success": False, "error": str(e)}
