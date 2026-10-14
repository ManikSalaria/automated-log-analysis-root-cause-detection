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
    file_id: Optional[int] = None
    evidence_text: Optional[str] = None
    job_name: Optional[str] = None
    build_number: Optional[str] = None
    build_id: Optional[str] = None
    build_url: Optional[str] = None

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

# =========================================================================
# JENKINS INTEGRATION SCHEMAS
# =========================================================================

class JenkinsTokenCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Integration identifier or description, e.g. 'Production Jenkins'")

class JenkinsTokenCreatedResponse(BaseModel):
    id: int
    name: str
    token: str = Field(..., description="Plaintext secret token displayed ONLY once upon generation")
    token_preview: str
    created_at: str
    message: str = "Store this token securely in Jenkins Credentials. It will not be shown again."

class JenkinsTokenItem(BaseModel):
    id: int
    name: str
    token_preview: str
    created_at: str
    last_used_at: Optional[str] = None
    is_active: bool
    revoked_at: Optional[str] = None

class JenkinsBuildIngestRequest(BaseModel):
    job_name: str = Field(..., min_length=1, max_length=200, description="Jenkins Job Name")
    build_number: str = Field(..., min_length=1, max_length=50, description="Jenkins Build Number or Run ID")
    build_url: Optional[str] = None
    repo_url: Optional[str] = None
    commit_sha: Optional[str] = None
    build_status: Optional[str] = Field(default="UNKNOWN", description="Jenkins build status, e.g. SUCCESS, FAILURE, UNSTABLE")
    timestamp: Optional[str] = None
    log_text: Optional[str] = Field(default=None, description="Full console text or snippet if not uploading via multipart file")

class JenkinsBuildIngestResponse(BaseModel):
    build_id: str
    job_name: str
    build_number: str
    build_status: str
    is_failure: bool
    failure_category: Optional[str] = None
    confidence: Optional[float] = None
    root_cause_candidate: Optional[str] = None
    events_count: int
    incidents_count: int
    ingested_at: str
    is_retry: bool = False
    view_url: str

class JenkinsBuildSummaryItem(BaseModel):
    id: int
    build_id: str
    job_name: str
    build_number: str
    build_url: Optional[str] = None
    repo_url: Optional[str] = None
    commit_sha: Optional[str] = None
    build_status: Optional[str] = None
    is_failure: bool
    primary_failure_category: Optional[str] = None
    confidence: Optional[float] = None
    root_cause_candidate: Optional[str] = None
    events_count: int
    incidents_count: int
    ingested_at: str

class JenkinsBuildDetailResponse(JenkinsBuildSummaryItem):
    file_id: int
    incidents: List[Dict[str, Any]] = Field(default_factory=list)
    sample_events: List[Dict[str, Any]] = Field(default_factory=list)

class IngestedLogSummary(BaseModel):
    id: int
    filename: str
    source_type: str
    byte_size: int
    line_count: int
    sha256_hash: str
    ingested_at: str
    origin: str  # "JENKINS" or "MANUAL"
    job_name: Optional[str] = None
    build_number: Optional[str] = None
    build_status: Optional[str] = None
    is_failure: Optional[bool] = None
    events_count: int = 0
    incidents_count: int = 0

class PrivacyAuditDetailResponse(BaseModel):
    file_id: int
    filename: str
    source_type: str
    origin: str
    is_raw_available: bool
    raw_sample: str
    sanitized_sample: str
    leak_count: int
    findings: List[Dict[str, Any]]
    security_notice: str

