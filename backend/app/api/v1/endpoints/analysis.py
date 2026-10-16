import uuid
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from app.core.config import settings
from app.core.security import SecretMasker
from app.parsers.regex_parser import LogParserEngine
from app.analysis.root_cause_candidate import RootCauseCandidateAnalyzer
from app.ml.model_registry import predict_with_model
from app.schemas.log_schema import (
    FullIncidentAnalysisResponse, ModelPrediction, RootCauseCandidateResponse
)

router = APIRouter()

class AnalyzeRequest(BaseModel):
    log_text: str
    model: Optional[str] = "baseline"

@router.post("/analyze", response_model=FullIncidentAnalysisResponse)
def analyze_log_incident(
    request: AnalyzeRequest,
    model: Optional[str] = Query(None, description="Model selection: 'baseline', 'xgboost', or 'graphsage'")
):
    """
    Analyzes an authentic log snippet or failure block:
    1. Runs Zero-PII Secret Sanitizer (captures privacy audit diff).
    2. Parses structured attributes (timestamp, severity, service, trace).
    3. Detects failure indicators.
    4. Executes live ML classification with the requested model ('baseline', 'xgboost', or 'graphsage').
    5. Formulates Root Cause Candidate Analysis.
    """
    raw_text = request.log_text
    if not raw_text or not raw_text.strip():
        raise HTTPException(status_code=400, detail="Log text cannot be empty.")

    selected_model = (model or request.model or "baseline").strip()

    # Step 1: Privacy audit & sanitization
    privacy_audit = SecretMasker.audit_leaks(raw_text)
    sanitized_text = SecretMasker.sanitize(raw_text, mask_ips=True, normalize_identifiers=False)

    # Step 2: Parsing & Failure Detection
    lines = sanitized_text.strip().splitlines()
    first_line_entry = LogParserEngine.parse_line(lines[0])
    
    is_failure = any(
        err in sanitized_text.lower() 
        for err in ["error", "fail", "assertionerror", "exception", "refused", "timeout", "rollback", "oom"]
    )

    # Extract failure signature
    failure_sig = lines[0][:150].strip()
    for l in lines:
        if any(w in l for w in ["AssertionError", "Exception", "Error", "FAILED", "mkdir:"]):
            failure_sig = l[:150].strip()
            break

    # Step 3: Run Model Prediction with selected model
    pred_res = predict_with_model(sanitized_text, model_name=selected_model)
    model_pred = ModelPrediction(
        model_name=pred_res["model_name"],
        predicted_category=pred_res["predicted_category"],
        confidence=pred_res["confidence"],
        latency_ms=pred_res["latency_ms"],
        feature_dimension=pred_res["feature_dimension"],
        top_probabilities=pred_res["top_probabilities"],
        rationale=pred_res["rationale"],
        requested_model=selected_model
    )

    # Step 4: Root Cause Candidate Analysis
    rca_res = RootCauseCandidateAnalyzer.analyze(sanitized_text, primary_category=model_pred.predicted_category)
    root_cause = RootCauseCandidateResponse(
        analysis_framework="Root Cause Candidate Analysis",
        failure_category=rca_res["failure_category"],
        root_cause_candidate=rca_res["root_cause_candidate"],
        explanation=rca_res["explanation"],
        remediation_guidance=rca_res["remediation_guidance"],
        evidence_matched=rca_res["evidence_matched"]
    )

    return FullIncidentAnalysisResponse(
        analysis_id=f"ANL-{uuid.uuid4().hex[:8].upper()}",
        original_input_snippet=raw_text[:350] if settings.ALLOW_RAW_LOG_RETENTION else sanitized_text[:350],
        sanitized_input=sanitized_text[:350],
        detected_failure_signature=failure_sig,
        is_failure=is_failure,
        classification=model_pred,
        root_cause=root_cause,
        relevant_log_lines=lines[:10],
        parsed_metadata={
            "timestamp": first_line_entry.timestamp,
            "severity": first_line_entry.level,
            "service": first_line_entry.service,
            "node": first_line_entry.node,
            "trace_id": first_line_entry.trace_id,
            "status_code": first_line_entry.status_code,
            "latency_ms": first_line_entry.latency_ms
        },
        privacy_audit=privacy_audit
    )


# =========================================================================
# STAGE 5: EVIDENCE-GROUNDED LLM SYNTHESIS ENDPOINTS
# =========================================================================

from app.schemas.synthesis_schema import SynthesizeRequest, SynthesizeResponse
from app.ml.stage5_llm.synthesis_service import execute_synthesis_pipeline
from app.ml.stage5_llm.providers import get_llm_provider


@router.post("/synthesize", response_model=SynthesizeResponse)
def synthesize_incident_report(request: SynthesizeRequest):
    """
    Stage 5: LLM-Powered Evidence-Grounded Root Cause Explanation and Remediation.
    
    Synthesizes current log evidence, Stage 1-3 ML classifier predictions,
    and Stage 4 retrieved historical cases into a structured, citation-grounded report
    with explicit prompt injection defense and advisory remediation guidance.
    """
    return execute_synthesis_pipeline(request)


@router.get("/llm-provider-status")
def get_llm_provider_status():
    """Diagnostic health check returning active LLM provider configuration and status."""
    provider = get_llm_provider()
    return provider.get_provider_info()

