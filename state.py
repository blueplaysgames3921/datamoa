"""
Pipeline state machine — defines all possible states a record can be in
and the data models that flow through the pipeline
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class RecordStage(str, Enum):
    QUEUED = "queued"
    INTAKE = "intake"
    PARSING = "parsing"
    CONTEXT = "context"
    CONFIDENCE = "confidence"
    REASONING = "reasoning"
    VALIDATION = "validation"
    ENRICHMENT = "enrichment"
    HITL = "hitl"
    WRITING = "writing"
    AUDIT = "audit"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ConfidenceTier(str, Enum):
    GREEN = "green"    # >= 0.85 — auto proceed
    AMBER = "amber"    # >= 0.60 — needs reasoning
    RED = "red"        # < 0.60 — needs HITL or deep reasoning


class FieldConfidence(BaseModel):
    field: str
    value: Any
    confidence: float
    reason: str | None = None
    flagged: bool = False


class ParsedData(BaseModel):
    """Output of Parsing Agent"""
    fields: dict[str, Any] = {}
    field_confidences: list[FieldConfidence] = []
    raw_text: str = ""
    document_type: str | None = None
    language: str = "en"
    parse_notes: str = ""


class ContextData(BaseModel):
    """Output of Context Agent"""
    known_source: bool = False
    source_pattern: str | None = None
    historical_corrections: list[dict] = []
    enriched_fields: dict[str, Any] = {}
    context_notes: str = ""


class ConfidenceResult(BaseModel):
    """Output of Confidence Scoring Agent"""
    overall_score: float
    tier: ConfidenceTier
    field_scores: dict[str, float] = {}
    flagged_fields: list[str] = []
    routing_reason: str = ""


class ReasoningResult(BaseModel):
    """Output of Reasoning Agent"""
    resolved_fields: dict[str, Any] = {}
    unresolved_fields: list[str] = []
    confidence_after: float
    tier_after: ConfidenceTier
    reasoning_notes: str = ""
    requires_hitl: bool = False
    hitl_questions: list[str] = []


class ValidationResult(BaseModel):
    """Output of Validation Agent"""
    passed: bool
    field_results: dict[str, bool] = {}
    errors: list[str] = []
    warnings: list[str] = []
    is_duplicate: bool = False
    duplicate_of: str | None = None


class HITLResolution(BaseModel):
    """Human resolution of ambiguous fields"""
    resolved_fields: dict[str, Any] = {}
    notes: str = ""
    resolved_at: datetime = Field(default_factory=datetime.utcnow)
    resolved_by: str = "user"


class WriteResult(BaseModel):
    """Output of Write Agent"""
    success: bool
    destination: str
    record_id: str | None = None
    error: str | None = None
    written_fields: dict[str, Any] = {}


class AuditEntry(BaseModel):
    """Single audit log entry"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    record_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    stage: RecordStage
    agent: str
    model: str
    action: str
    input_summary: str = ""
    output_summary: str = ""
    confidence_before: float | None = None
    confidence_after: float | None = None
    duration_ms: int = 0
    error: str | None = None


class PipelineRecord(BaseModel):
    """
    The central data object that flows through the entire pipeline.
    Every agent reads from and writes to this object.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Input
    source_type: str = ""          # pdf | image | csv | text | email | url
    source_path: str | None = None
    source_raw: str = ""           # raw text content

    # Pipeline state
    stage: RecordStage = RecordStage.QUEUED
    stage_history: list[dict] = []

    # Agent outputs (populated as record progresses)
    parsed: ParsedData | None = None
    context: ContextData | None = None
    confidence: ConfidenceResult | None = None
    reasoning: ReasoningResult | None = None
    validation: ValidationResult | None = None
    hitl: HITLResolution | None = None
    write_result: WriteResult | None = None

    # Final resolved data (what gets written)
    resolved_data: dict[str, Any] = {}

    # Metadata
    retry_count: int = 0
    error_message: str | None = None
    processing_time_ms: int = 0
    audit_entries: list[AuditEntry] = []

    # Set once a terminal (complete/failed/cancelled) record's heavy
    # in-memory payload (source_raw, parsed.raw_text) has been freed to
    # bound memory usage for long-running sessions. The full record
    # remains persisted on disk in the queue directory for history/audit;
    # only the in-memory copy is lightened. Once set, the record can no
    # longer be retried (its source content is gone), so /retry should
    # return a clear error instead of failing deep inside the pipeline.
    trimmed_from_memory: bool = False

    def advance_to(self, stage: RecordStage):
        self.stage_history.append({
            "stage": self.stage,
            "timestamp": datetime.utcnow().isoformat(),
        })
        self.stage = stage
        self.updated_at = datetime.utcnow()

    def to_summary(self) -> dict:
        """Lightweight summary for UI list view"""
        return {
            "id": self.id,
            "stage": self.stage,
            "source_type": self.source_type,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "confidence_tier": self.confidence.tier if self.confidence else None,
            "confidence_score": self.confidence.overall_score if self.confidence else None,
            "has_errors": bool(self.error_message),
            "retry_count": self.retry_count,
        }
