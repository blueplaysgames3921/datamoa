"""Audit API routes"""

import json
from fastapi import APIRouter

router = APIRouter()


@router.get("/logs")
async def get_logs(limit: int = 100):
    from core.config.settings import AUDIT_DIR

    logs = []
    for audit_file in sorted(AUDIT_DIR.glob("*.json"), reverse=True)[:limit]:
        if audit_file.name.startswith("report_"):
            continue
        try:
            with open(audit_file) as f:
                logs.append(json.load(f))
        except Exception:
            continue

    return logs


@router.get("/reports")
async def get_reports(limit: int = 10):
    from core.config.settings import AUDIT_DIR

    reports = []
    for report_file in sorted(AUDIT_DIR.glob("report_*.json"), reverse=True)[:limit]:
        try:
            with open(report_file) as f:
                reports.append(json.load(f))
        except Exception:
            continue

    return reports


@router.get("/export")
async def export_logs(format: str = "json"):
    from core.config.settings import AUDIT_DIR

    all_logs = []
    for audit_file in sorted(AUDIT_DIR.glob("*.json")):
        if audit_file.name.startswith("report_"):
            continue
        try:
            with open(audit_file) as f:
                all_logs.append(json.load(f))
        except Exception:
            continue

    if format == "csv":
        import csv, io
        output = io.StringIO()
        if all_logs:
            writer = csv.DictWriter(output, fieldnames=all_logs[0].keys())
            writer.writeheader()
            writer.writerows(all_logs)
        return {"csv": output.getvalue()}

    return all_logs
