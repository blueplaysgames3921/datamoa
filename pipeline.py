"""
Pipeline API routes — submit records, query queue, resolve HITL
"""

from typing import Any

from fastapi import APIRouter, HTTPException, Request, UploadFile, File
from pydantic import BaseModel

from core.pipeline.state import PipelineRecord

router = APIRouter()


class SubmitTextRequest(BaseModel):
    text: str
    source_label: str = "text_input"


class HITLResolutionRequest(BaseModel):
    resolved_fields: dict[str, Any]
    notes: str = ""


@router.post("/submit")
async def submit_record(request: Request, body: SubmitTextRequest):
    orchestrator = request.app.state.orchestrator
    record = PipelineRecord(
        source_type="text",
        source_raw=body.text,
        source_path=body.source_label,
    )
    record_id = await orchestrator.submit(record)
    return {"record_id": record_id, "status": "queued"}


@router.post("/submit/file")
async def submit_file(request: Request, file: UploadFile = File(...)):
    orchestrator = request.app.state.orchestrator

    content = await file.read()
    suffix = file.filename.split(".")[-1].lower() if file.filename else "bin"

    import tempfile, os
    with tempfile.NamedTemporaryFile(delete=False, prefix="datamoa_upload_", suffix=f".{suffix}") as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    record = PipelineRecord(
        source_type=suffix,
        source_path=tmp_path,
        source_raw="",
    )
    record_id = await orchestrator.submit(record)
    return {"record_id": record_id, "status": "queued", "filename": file.filename}


@router.get("/queue")
async def get_queue(request: Request):
    orchestrator = request.app.state.orchestrator
    records = await orchestrator.get_queue()
    return records


@router.get("/queue/hitl")
async def get_hitl_queue(request: Request):
    """Get all records currently awaiting HITL resolution"""
    orchestrator = request.app.state.orchestrator
    hitl_record_ids = list(orchestrator._hitl_queue.keys())
    result = []
    for rid in hitl_record_ids:
        record = orchestrator._records.get(rid)
        if record and record.reasoning:
            result.append({
                "record_id": rid,
                "questions": record.reasoning.hitl_questions or [],
                "flagged_fields": record.confidence.flagged_fields if record.confidence else [],
                "parsed_fields": record.parsed.fields if record.parsed else {},
                "reasoning_notes": record.reasoning.reasoning_notes or "",
                "raw_text_excerpt": (record.source_raw or "")[:800],
            })
    return result


@router.get("/search")
async def search_records(
    request: Request,
    stage: str = None,
    tier: str = None,
    source_type: str = None,
    limit: int = 100,
    offset: int = 0,
):
    """Search and filter records in the pipeline"""
    orchestrator = request.app.state.orchestrator
    records = list(orchestrator._records.values())

    # Apply filters
    if stage:
        records = [r for r in records if r.stage.value == stage]
    if tier and records:
        records = [r for r in records if r.confidence and r.confidence.tier.value == tier]
    if source_type:
        records = [r for r in records if r.source_type == source_type]

    # Sort newest first
    records.sort(key=lambda r: r.updated_at, reverse=True)

    total = len(records)
    page = records[offset:offset + limit]

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "records": [r.to_summary() for r in page],
    }


@router.get("/record/{record_id}")
async def get_record(request: Request, record_id: str):
    orchestrator = request.app.state.orchestrator
    record = await orchestrator.get_record(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    return record.model_dump(mode="json")


@router.post("/hitl/{record_id}/resolve")
async def resolve_hitl(request: Request, record_id: str, body: HITLResolutionRequest):
    orchestrator = request.app.state.orchestrator
    await orchestrator.resolve_hitl(record_id, body.model_dump())
    return {"status": "resolved"}


@router.post("/pause")
async def pause(request: Request):
    await request.app.state.orchestrator.pause()
    return {"status": "paused"}


@router.post("/resume")
async def resume(request: Request):
    await request.app.state.orchestrator.resume()
    return {"status": "resumed"}


@router.post("/cancel/{record_id}")
async def cancel(request: Request, record_id: str):
    await request.app.state.orchestrator.cancel(record_id)
    return {"status": "cancelled"}


@router.post("/retry/{record_id}")
async def retry_record(request: Request, record_id: str):
    """Re-queue a failed record from the beginning"""
    orchestrator = request.app.state.orchestrator
    record = orchestrator._records.get(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    
    from core.pipeline.state import RecordStage
    
    # Only retry failed/cancelled records
    if record.stage not in (RecordStage.FAILED, RecordStage.CANCELLED, RecordStage.COMPLETE):
        raise HTTPException(status_code=400, detail=f"Cannot retry record in stage '{record.stage}'")

    # Records this old have had their source content freed from memory to
    # bound long-running sessions (see OrchestratorService._trim_old_records).
    # The full record is still available in the on-disk queue history for
    # reference, but it can no longer be reprocessed.
    if record.trimmed_from_memory:
        raise HTTPException(
            status_code=400,
            detail="This record's source data was freed from memory to save space "
                   "and can no longer be retried. It remains available in the queue history.",
        )
    
    # Reset record state while preserving source data
    record.stage = RecordStage.QUEUED
    record.stage_history = []
    record.parsed = None
    record.context = None
    record.confidence = None
    record.reasoning = None
    record.validation = None
    record.hitl = None
    record.write_result = None
    record.resolved_data = {}
    record.error_message = None
    record.retry_count += 1
    record.audit_entries = []
    
    await orchestrator._queue.put(record_id)
    orchestrator._persist_record(record)
    
    return {"status": "requeued", "record_id": record_id, "retry_count": record.retry_count}


@router.get("/export")
async def export_records(
    request: Request,
    format: str = "json",
    stage: str = "complete",
):
    """Export processed records as JSON or CSV"""
    orchestrator = request.app.state.orchestrator
    from core.pipeline.state import RecordStage
    
    records = [
        r for r in orchestrator._records.values()
        if stage == "all" or r.stage.value == stage
    ]
    
    if format == "csv":
        import csv, io
        
        if not records:
            return {"csv": ""}
        
        # Collect all field keys across records
        all_keys = set()
        for r in records:
            if r.resolved_data:
                all_keys.update(r.resolved_data.keys())
        
        all_keys = sorted(all_keys)
        meta_keys = ["_record_id", "_stage", "_confidence", "_source_type", "_created_at"]
        headers = meta_keys + all_keys
        
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=headers, extrasaction='ignore')
        writer.writeheader()
        
        for r in records:
            row = {
                "_record_id": r.id,
                "_stage": r.stage.value,
                "_confidence": round(r.confidence.overall_score, 3) if r.confidence else "",
                "_source_type": r.source_type,
                "_created_at": r.created_at.isoformat(),
            }
            row.update(r.resolved_data or {})
            writer.writerow(row)
        
        return {"csv": output.getvalue(), "count": len(records)}
    
    # JSON format
    return {
        "records": [
            {
                "id": r.id,
                "stage": r.stage.value,
                "confidence": r.confidence.overall_score if r.confidence else None,
                "source_type": r.source_type,
                "created_at": r.created_at.isoformat(),
                "data": r.resolved_data or (r.parsed.fields if r.parsed else {}),
            }
            for r in records
        ],
        "count": len(records),
    }


@router.post("/test-destination")
async def test_destination(request: Request):
    """Test a write destination connection before saving"""
    body = await request.json()
    dest_type = body.get("type", "")
    config = body.get("config", {})

    if dest_type == "csv":
        import os
        file_path = config.get("file_path", "")
        if not file_path:
            return {"ok": False, "message": "No file path specified"}
        dir_path = os.path.dirname(file_path) or "."
        if not os.path.exists(dir_path):
            return {"ok": False, "message": f"Directory does not exist: {dir_path}"}
        return {"ok": True, "message": f"Path is valid"}

    elif dest_type == "airtable":
        import httpx
        settings = request.app.state.orchestrator.settings
        key = settings.get_key("airtable")
        if not key:
            return {"ok": False, "message": "Airtable API key not configured in Keys settings"}
        base_id = config.get("base_id", "")
        if not base_id:
            return {"ok": False, "message": "Base ID required"}
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(
                    f"https://api.airtable.com/v0/meta/bases/{base_id}/tables",
                    headers={"Authorization": f"Bearer {key}"},
                )
            if resp.status_code == 200:
                return {"ok": True, "message": "Connected to Airtable base"}
            elif resp.status_code == 401:
                return {"ok": False, "message": "Invalid API key"}
            elif resp.status_code == 404:
                return {"ok": False, "message": "Base not found — check Base ID"}
            else:
                return {"ok": False, "message": f"Error: {resp.status_code}"}
        except Exception as e:
            return {"ok": False, "message": str(e)}

    elif dest_type == "api":
        import httpx
        url = config.get("url", "")
        if not url:
            return {"ok": False, "message": "URL required"}
        try:
            headers = {}
            auth = config.get("auth_header", "")
            if auth:
                headers["Authorization"] = auth
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.options(url, headers=headers)
            return {"ok": True, "message": f"Endpoint reachable (status {resp.status_code})"}
        except Exception as e:
            return {"ok": False, "message": str(e)}

    elif dest_type == "google_sheets":
        return {"ok": True, "message": "Google Sheets requires OAuth — will prompt on first write"}

    elif dest_type == "database":
        conn = config.get("connection_string", "")
        if not conn:
            return {"ok": False, "message": "Connection string required"}
        try:
            import asyncpg
            conn_obj = await asyncpg.connect(conn, timeout=5)
            await conn_obj.close()
            return {"ok": True, "message": "Database connected"}
        except ImportError:
            return {"ok": False, "message": "asyncpg not installed — run: pip install asyncpg"}
        except Exception as e:
            return {"ok": False, "message": str(e)}

    return {"ok": False, "message": f"Unknown destination type: {dest_type}"}


@router.post("/audit/batch")
async def trigger_batch_audit(request: Request):
    """Trigger a learning+audit batch run over recent completed records"""
    orchestrator = request.app.state.orchestrator
    import asyncio

    async def _run():
        # Collect completed records
        completed = [
            r for r in orchestrator._records.values()
            if r.stage.value == "complete"
        ]
        if not completed:
            return

        # Audit batch
        audit_result = await orchestrator.audit.run_batch_audit(completed[-50:])

        # Learning batch
        if hasattr(orchestrator, 'learning'):
            learn_result = await orchestrator.learning.run_batch(completed[-50:])
        else:
            from core.agents.learning import LearningAgent
            learning = LearningAgent(
                settings=orchestrator.settings,
                router=orchestrator.router,
                event_bus=orchestrator.event_bus,
            )
            learn_result = await learning.run_batch(completed[-50:])

        from core.utils.events import event_bus, Events
        await event_bus.emit("audit:batch:complete", {
            "audit": audit_result,
            "learning": learn_result,
            "records_analyzed": len(completed[-50:]),
        })

    asyncio.create_task(_run())
    return {"status": "started"}


class SubmitURLRequest(BaseModel):
    url: str
    label: str = ""


@router.post("/submit/url")
async def submit_url(request: Request, body: SubmitURLRequest):
    orchestrator = request.app.state.orchestrator
    record = PipelineRecord(
        source_type="url",
        source_path=body.url,
        source_raw=body.url,
    )
    record_id = await orchestrator.submit(record)
    return {"record_id": record_id, "status": "queued", "url": body.url}


@router.get("/stats")
async def get_stats(request: Request):
    """Summary stats for the dashboard"""
    orchestrator = request.app.state.orchestrator
    records = list(orchestrator._records.values())
    from core.pipeline.state import RecordStage
    return {
        "total": len(records),
        "active": sum(1 for r in records if r.stage not in (RecordStage.COMPLETE, RecordStage.FAILED, RecordStage.CANCELLED)),
        "complete": sum(1 for r in records if r.stage == RecordStage.COMPLETE),
        "failed": sum(1 for r in records if r.stage == RecordStage.FAILED),
        "hitl": sum(1 for r in records if r.stage == RecordStage.HITL),
        "success_rate": round(
            sum(1 for r in records if r.stage == RecordStage.COMPLETE) /
            max(1, sum(1 for r in records if r.stage in (RecordStage.COMPLETE, RecordStage.FAILED))) * 100, 1
        ),
    }
