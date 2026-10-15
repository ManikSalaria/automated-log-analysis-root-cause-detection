"""Pydantic Request and Response Schemas for TRACE Stage 5 Synthesis.

Defines structured models for LLM-powered root-cause explanation,
evidence citation grounding, proportionate remediation suggestions,
and provider-unavailable diagnostics.
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class SynthesizeRequest(BaseModel):
    """Request payload for Stage 5 LLM evidence-grounded synthesis."""
    incident_code: Optional[str] = Field(None, description="Optional incident code from SQLite incident registry")
    log_text: Optional[str] = Field(None, description="Raw or sanitized log snippet if incident_code is not provided")
    classifier_model: Optional[str] = Field("graphsage", description="Classifier to execute: 'graphsage', 'xgboost', or 'baseline'")
    retrieval_top_k: int = Field(4, ge=0, le=10, description="Number of historical incidents to retrieve via Stage 4 RAG")
    additional_context: Optional[str] = Field(None, description="Optional engineer notes or pipeline metadata")
    provider_override: Optional[str] = Field(None, description="Optional provider override: 'ollama', 'mock'")
    timeout_sec: Optional[float] = Field(None, description="Optional request timeout in seconds override")


class EvidenceItem(BaseModel):
    """Structured citation item with stable identifier (e.g. E1, E2)."""
    evidence_id: str = Field(..., description="Stable evidence identifier e.g. E1, E2, E3")
    source_type: str = Field(..., description="CURRENT_INCIDENT, HISTORICAL_INCIDENT, or CHRONOLOGICAL_LOG")
    incident_code: Optional[str] = Field(None, description="Incident code if from an incident record")
    source_file: Optional[str] = Field(None, description="Source log file name")
    line_span: Optional[str] = Field(None, description="Line number or line span e.g. '320' or '10-15'")
    failure_category: Optional[str] = Field(None, description="Failure category if known")
    snippet: str = Field(..., description="Sanitized log message or stack trace snippet")
    retrieval_score: Optional[float] = Field(None, description="Hybrid retrieval score if retrieved from RAG")


class RootCauseHypothesis(BaseModel):
    """Ranked root cause hypothesis grounded in evidence."""
    rank: int = Field(..., description="Hypothesis rank (1 = most probable)")
    hypothesis: str = Field(..., description="Specific root cause candidate diagnosis")
    supporting_evidence: List[str] = Field(default_factory=list, description="List of valid evidence IDs e.g. ['E1', 'E2']")
    conflicting_evidence: List[str] = Field(default_factory=list, description="List of evidence IDs that contradict or question this hypothesis")
    confidence_assessment: str = Field(..., description="Qualitative confidence assessment with explicit rationale")
    is_grounded: bool = Field(True, description="Whether the hypothesis is adequately grounded in valid, relevant evidence")
    grounding_status: str = Field("SUPPORTED", description="Status: 'SUPPORTED', 'UNSUPPORTED_INVALID_CITATION', 'UNSUPPORTED_MISSING_CITATION', 'UNSUPPORTED_IRRELEVANT_EVIDENCE', 'PARTIALLY_SUPPORTED'")
    validation_warnings: List[str] = Field(default_factory=list, description="Explicit validation warnings for this hypothesis")


class InvestigationStep(BaseModel):
    """Diagnostic step to verify or rule out a hypothesis."""
    step_number: int
    target_hypothesis: str = Field(..., description="Hypothesis being tested")
    action: str = Field(..., description="Concrete diagnostic action to run or inspect")
    expected_outcome: str = Field(..., description="What result confirms or refutes the hypothesis")


class RemediationSuggestion(BaseModel):
    """Proportionate proposed fix with prerequisites and validation."""
    rank: int
    action: str = Field(..., description="Proposed corrective action")
    rationale: str = Field(..., description="Why this action addresses the inferred root cause")
    prerequisites: List[str] = Field(default_factory=list, description="Required checks before executing")
    validation_steps: List[str] = Field(default_factory=list, description="How to verify the fix works")
    is_advisory_only: bool = Field(True, description="Enforces that recommendations are advisory only")
    supporting_evidence: List[str] = Field(default_factory=list, description="Optional evidence IDs supporting this action")
    is_grounded: bool = Field(True, description="Whether the remediation is grounded in valid evidence or verified hypotheses")
    validation_warnings: List[str] = Field(default_factory=list, description="Validation warnings for this remediation")


class HistoricalCaseReference(BaseModel):
    """Reference to a historical incident retrieved from Stage 4."""
    incident_code: str
    evidence_id: str
    failure_category: str
    similarity_score: float
    relevance_notes: str
    metadata_verified: bool = Field(True, description="Whether metadata matches actual retrieved evidence package")
    validation_warnings: List[str] = Field(default_factory=list, description="Metadata mismatch warnings")


class SynthesisReport(BaseModel):
    """Structured evidence-grounded report produced by the LLM."""
    incident_summary: str = Field(..., description="Concise explanation of the detected failure")
    predicted_failure_category: str = Field(..., description="Predicted category clearly identified as a prediction")
    classifier_info: Dict[str, Any] = Field(default_factory=dict, description="Metadata of classifier that produced prediction")
    likely_root_causes: List[RootCauseHypothesis] = Field(default_factory=list)
    evidence: List[EvidenceItem] = Field(default_factory=list)
    recommended_investigations: List[InvestigationStep] = Field(default_factory=list)
    remediation_suggestions: List[RemediationSuggestion] = Field(default_factory=list)
    uncertainties: List[str] = Field(default_factory=list, description="Missing evidence, competing explanations, limitations")
    historical_cases: List[HistoricalCaseReference] = Field(default_factory=list)
    human_review_required: bool = Field(True, description="Always requires human engineering sign-off")
    validation_warnings: List[str] = Field(default_factory=list, description="Global validation warnings regarding dropped citations, unsupported claims, or metadata mismatches")
    unsupported_claims: List[Dict[str, Any]] = Field(default_factory=list, description="Claims flagged as unsupported due to invalid, missing, or irrelevant citations")


class SynthesizeResponse(BaseModel):
    """Full API response for /api/v1/analysis/synthesize."""
    status: str = Field(..., description="'success', 'provider_unavailable', 'limited_evidence', 'validation_fallback', 'timeout', 'error'")
    provider: str = Field(..., description="LLM provider name e.g. 'ollama' or 'mock'")
    model_name: str = Field(..., description="LLM model identifier")
    latency_ms: float = Field(..., description="Total execution latency in milliseconds")
    llm_latency_ms: Optional[float] = Field(None, description="Latency spent specifically in LLM generation")
    timeout_sec: Optional[float] = Field(None, description="Configured timeout in seconds")
    report: Optional[SynthesisReport] = None
    classifier_output: Optional[Dict[str, Any]] = None
    retrieval_results: Optional[List[Dict[str, Any]]] = None
    validation_details: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    setup_guidance: Optional[str] = None
