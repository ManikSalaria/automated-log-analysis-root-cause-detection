from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

class LogEntry(BaseModel):
    timestamp: Optional[str] = None
    level: str = "INFO"
    service: Optional[str] = "unknown"
    node: Optional[str] = None
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    latency_ms: Optional[float] = None
    status_code: Optional[int] = None
    raw_message: str
    sanitized_message: str

class ParsedIncidentSummary(BaseModel):
    incident_id: str
    source_type: str = "JENKINS"
    total_lines: int = 0
    error_count: int = 0
    warning_count: int = 0
    primary_failure_category: str = "UNKNOWN"
    confidence: float = 0.0
    root_cause_node: Optional[str] = None
    error_signatures: List[str] = Field(default_factory=list)
    impacted_services: List[str] = Field(default_factory=list)
    timeline: List[Dict[str, Any]] = Field(default_factory=list)

class ModelPrediction(BaseModel):
    model_name: str
    predicted_category: str
    confidence: float
    latency_ms: float
    feature_dimension: int
    top_probabilities: Dict[str, float] = Field(default_factory=dict)
    rationale: Optional[str] = None
    requested_model: Optional[str] = None

class RootCauseCandidateResponse(BaseModel):
    analysis_framework: str = "Review-1 Root Cause Candidate Analysis"
    failure_category: str
    root_cause_candidate: str
    explanation: str
    remediation_guidance: str
    evidence_matched: List[str] = Field(default_factory=list)

class FullIncidentAnalysisResponse(BaseModel):
    analysis_id: str
    original_input_snippet: str
    sanitized_input: str
    detected_failure_signature: str
    is_failure: bool
    classification: ModelPrediction
    root_cause: RootCauseCandidateResponse
    relevant_log_lines: List[str] = Field(default_factory=list)
    parsed_metadata: Dict[str, Any] = Field(default_factory=dict)
    privacy_audit: Dict[str, Any] = Field(default_factory=dict)

class IngestionUploadResponse(BaseModel):
    file_id: int
    filename: str
    source_type: str
    byte_size: int
    line_count: int
    sha256_hash: str
    events_inserted: int
    incidents_detected: int
    ingested_at: str
    job_name: Optional[str] = None
    build_number: Optional[str] = None
    build_status: Optional[str] = None
    build_url: Optional[str] = None
    repo_url: Optional[str] = None
    commit_sha: Optional[str] = None

class IncidentSummaryItem(BaseModel):
    id: int
    incident_code: str
    source_file: str
    start_line: int
    end_line: int
    primary_severity: str
    failure_category: str
    confidence: float
    root_cause_candidate: str
    detected_signature: str
    created_at: str
    job_name: Optional[str] = None
    build_number: Optional[str] = None
    build_status: Optional[str] = None
    build_url: Optional[str] = None
    repo_url: Optional[str] = None
    commit_sha: Optional[str] = None

class EvaluationMetricsResponse(BaseModel):
    model_name: str
    dataset_split: str
    accuracy: float
    precision_macro: float
    recall_macro: float
    f1_macro: float
    sample_count: int
    feature_dimension: int
    training_time_sec: float
    avg_latency_ms: float
    p95_latency_ms: float
    evaluated_at: str
    classes: List[str]
    per_class_metrics: Dict[str, Any] = Field(default_factory=dict)
    limitations: List[str] = Field(default_factory=list)
