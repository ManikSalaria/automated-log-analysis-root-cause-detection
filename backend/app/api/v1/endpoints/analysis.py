import uuid
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.core.security import SecretMasker
from app.parsers.regex_parser import LogParserEngine
from app.analysis.root_cause_candidate import RootCauseCandidateAnalyzer
from app.ml.baseline.tfidf_rf import BaselineTfidfRandomForest
from app.schemas.log_schema import (
    FullIncidentAnalysisResponse, ModelPrediction, RootCauseCandidateResponse
)

router = APIRouter()
baseline_model = BaselineTfidfRandomForest()
baseline_model.load()

class AnalyzeRequest(BaseModel):
    log_text: str

@router.post("/analyze", response_model=FullIncidentAnalysisResponse)
def analyze_log_incident(request: AnalyzeRequest):
    """
    Analyzes an authentic log snippet or failure block:
    1. Runs Zero-PII Secret Sanitizer (captures privacy audit diff).
    2. Parses structured attributes (timestamp, severity, service, trace).
    3. Detects failure indicators.
    4. Executes live Academic Baseline (TF-IDF + Random Forest) classification.
    5. Formulates Review-1 Root Cause Candidate Analysis.
    """
    raw_text = request.log_text
    if not raw_text or not raw_text.strip():
        raise HTTPException(status_code=400, detail="Log text cannot be empty.")

    if not baseline_model.is_trained:
        if not baseline_model.load():
            raise HTTPException(
                status_code=503,
                detail="Baseline model is not loaded. Train the model using 'scripts/train_and_evaluate_baseline.py' first."
            )

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

    # Step 3: Run Baseline ML Prediction
    try:
        pred_res = baseline_model.predict(sanitized_text)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Baseline model inference failed: {str(exc)}"
        )
    model_pred = ModelPrediction(
        model_name=pred_res["model_name"],
        predicted_category=pred_res["predicted_category"],
        confidence=pred_res["confidence"],
        latency_ms=pred_res["latency_ms"],
        feature_dimension=pred_res["feature_dimension"],
        top_probabilities=pred_res["top_probabilities"],
        rationale=pred_res["rationale"]
    )

    # Step 4: Root Cause Candidate Analysis
    rca_res = RootCauseCandidateAnalyzer.analyze(sanitized_text, primary_category=model_pred.predicted_category)
    root_cause = RootCauseCandidateResponse(
        analysis_framework="Review-1 Root Cause Candidate Analysis",
        failure_category=rca_res["failure_category"],
        root_cause_candidate=rca_res["root_cause_candidate"],
        explanation=rca_res["explanation"],
        remediation_guidance=rca_res["remediation_guidance"],
        evidence_matched=rca_res["evidence_matched"]
    )

    return FullIncidentAnalysisResponse(
        analysis_id=f"ANL-{uuid.uuid4().hex[:8].upper()}",
        original_input_snippet=raw_text[:350],
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
