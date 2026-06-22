"""
REST API write tool — POST data to a custom HTTP endpoint
"""

import json
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


async def write_to_api(
    url: str,
    data: dict[str, Any],
    record_id: str,
    auth_header: str = "",
    method: str = "POST",
) -> dict:
    """
    Send data to a REST API endpoint.
    Adds X-DataMoA-Record-ID header for traceability.
    """
    headers = {
        "Content-Type": "application/json",
        "X-DataMoA-Record-ID": record_id,
    }
    if auth_header:
        headers["Authorization"] = auth_header

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            payload = {**data, "_datamoa_record_id": record_id}
            method = method.upper()

            if method == "POST":
                resp = await client.post(url, json=payload, headers=headers)
            elif method == "PUT":
                resp = await client.put(url, json=payload, headers=headers)
            elif method == "PATCH":
                resp = await client.patch(url, json=payload, headers=headers)
            else:
                return {"success": False, "error": f"Unsupported method: {method}"}

            if resp.status_code in (200, 201, 202, 204):
                try:
                    response_data = resp.json()
                    # Try to extract an ID from response
                    remote_id = (
                        response_data.get("id")
                        or response_data.get("_id")
                        or response_data.get("record_id")
                        or str(resp.status_code)
                    )
                except Exception:
                    remote_id = str(resp.status_code)

                return {
                    "success": True,
                    "destination": url,
                    "record_id": remote_id,
                    "written_fields": data,
                }
            else:
                return {
                    "success": False,
                    "error": f"HTTP {resp.status_code}: {resp.text[:200]}",
                }

    except httpx.TimeoutException:
        return {"success": False, "error": f"Request timed out after 30s"}
    except httpx.ConnectError as e:
        return {"success": False, "error": f"Cannot connect to {url}: {str(e)}"}
    except Exception as e:
        return {"success": False, "error": str(e)}
