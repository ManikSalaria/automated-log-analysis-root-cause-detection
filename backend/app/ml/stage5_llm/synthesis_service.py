"""Evidence-Grounded Root Cause Synthesis Service for TRACE Stage 5.

Orchestrates:
1. Incident loading / validation from SQLite or raw log snippet.
2. Stage 1-3 ML classifier inference (GraphSAGE, XGBoost, or Baseline RF).
3. Rule-based RootCauseCandidateAnalyzer heuristic guidance.
4. Stage 4 Hybrid RAG retrieval over historical incident records.
5. Evidence package construction with stable citations (E1, E2, E3...).
6. Configurable LLM provider execution (local Ollama or Mock adapter).
7. Strict citation verification, grounding validation, and prompt injection isolation.
8. Explicit provider-unavailable fallback without synthetic report fabrication.
"""

import time
import re
import json
from typing import Optional, Dict, Any, List
from fastapi import HTTPException

from app.core.config import settings
from app.core.database import get_connection
from app.core.security import SecretMasker
from app.ml.model_registry import predict_with_model
from app.analysis.root_cause_candidate import RootCauseCandidateAnalyzer
from app.ml.stage4_rag.rag_service import get_rag_retriever
from app.ml.stage4_rag.context_builder import _fetch_surrounding_log_lines
from app.ml.stage5_llm.providers import get_llm_provider
from app.ml.stage5_llm.prompt_builder import (
    format_evidence_package, build_synthesis_prompt
)
from app.ml.stage5_llm.citation_validator import validate_and_sanitize_synthesis
from app.schemas.synthesis_schema import (
    SynthesizeRequest, SynthesizeResponse, SynthesisReport
)


def load_incident_from_db(incident_code: str) -> Dict[str, Any]:
    """Retrieve full incident record and joined source file metadata from SQLite."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT i.*, f.filename as source_file, f.source_type
        FROM incidents i
        JOIN source_files f ON i.file_id = f.id
        WHERE i.incident_code = ?;
    """, (incident_code,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        raise HTTPException(
            status_code=404,
            detail=f"Incident with code '{incident_code}' not found in registry."
        )
    return dict(row)


def execute_synthesis_pipeline(request: SynthesizeRequest) -> SynthesizeResponse:
    """Execute the end-to-end Stage 5 evidence-grounded synthesis pipeline."""
    t_start = time.perf_counter()

    # 1. Resolve Input Text & Metadata
    source_file = None
    line_span = None
    incident_code = None

    if request.incident_code:
        inc_data = load_incident_from_db(request.incident_code)
        raw_text = inc_data.get("evidence_text", "")
        source_file = inc_data.get("source_file")
        start_line = inc_data.get("start_line", 0)
        end_line = inc_data.get("end_line", 0)
        line_span = f"{start_line}-{end_line}"
        incident_code = request.incident_code
    elif request.log_text and request.log_text.strip():
        raw_text = request.log_text.strip()
        incident_code = "INC-QUERY"
        source_file = "user_input.log"
        line_span = "1-1"
    else:
        raise HTTPException(
            status_code=400,
            detail="Must provide either 'incident_code' or non-empty 'log_text'."
        )

    # Sanitize input immediately
    sanitized_text = SecretMasker.sanitize(raw_text, mask_ips=True, normalize_identifiers=False)

    # 2. Execute Selected ML Classifier
    clf_model_name = (request.classifier_model or "graphsage").strip().lower()
    try:
        clf_pred = predict_with_model(sanitized_text, model_name=clf_model_name)
    except Exception as e:
        clf_pred = {
            "model_name": clf_model_name,
            "predicted_category": "UNKNOWN",
            "confidence": 0.0,
            "latency_ms": 0.0,
            "feature_dimension": 0,
            "top_probabilities": {},
            "rationale": f"Classifier execution error: {str(e)}"
        }

    # 3. Formulate Rule-Based Root Cause Candidate Heuristics
    predicted_cat = clf_pred.get("predicted_category", "UNKNOWN")
    rca_res = RootCauseCandidateAnalyzer.analyze(sanitized_text, primary_category=predicted_cat)

    # 4. Stage 4 Hybrid RAG Retrieval over Historical Incidents
    retriever = get_rag_retriever()
    exclude_codes = {incident_code} if incident_code else set()

    retrieved_incidents = retriever.retrieve(
        query_text=sanitized_text,
        top_k=request.retrieval_top_k,
        query_category=predicted_cat if predicted_cat != "UNKNOWN" else None,
        exclude_incident_codes=exclude_codes
    )

    # 5. Fetch Chronological Context from SQLite if source file is known
    surrounding_logs = []
    if source_file and line_span and "-" in line_span:
        try:
            s_line, e_line = map(int, line_span.split("-"))
            surrounding_logs = _fetch_surrounding_log_lines(
                source_file=source_file,
                start_line=s_line,
                end_line=e_line,
                max_lines=6
            )
        except Exception:
            surrounding_logs = []

    # 6. Construct Citation-Indexed Evidence Package
    evidence_items, evidence_text = format_evidence_package(
        current_log=sanitized_text,
        classifier_prediction=clf_pred,
        root_cause_candidate=rca_res,
        retrieved_incidents=retrieved_incidents,
        surrounding_logs=surrounding_logs,
        source_file=source_file,
        incident_code=incident_code,
        line_span=line_span
    )

    # 7. Build System & User Prompts with Injection Defense
    sys_prompt, user_prompt = build_synthesis_prompt(
        evidence_items=evidence_items,
        evidence_text=evidence_text,
        classifier_prediction=clf_pred,
        root_cause_candidate=rca_res,
        additional_context=request.additional_context
    )

    # 8. Check Provider Availability
    provider = get_llm_provider(
        provider_name=request.provider_override,
        timeout_sec=request.timeout_sec
    )
    provider_info = provider.get_provider_info()
    elapsed_ms = round((time.perf_counter() - t_start) * 1000.0, 2)

    # Explicit provider_unavailable handling — do NOT fabricate a synthesis report
    if not provider.is_available():
        return SynthesizeResponse(
            status="provider_unavailable",
            provider=provider_info["provider"],
            model_name=provider_info["model"],
            latency_ms=elapsed_ms,
            llm_latency_ms=0.0,
            timeout_sec=provider_info.get("timeout_sec"),
            report=None,
            classifier_output=clf_pred,
            retrieval_results=retrieved_incidents,
            validation_details=None,
            error_message=(
                f"Configured LLM provider '{provider_info['provider']}' is unavailable or model "
                f"'{provider_info['model']}' is not installed."
            ),
            setup_guidance=(
                provider_info.get("setup_command") or
                f"Ensure Ollama is running: 'ollama run {provider_info['model']}'. "
                "Stages 1-4 classifier and retrieval results remain active above."
            )
        )

    # 9. Call LLM Provider
    result = provider.generate(
        prompt=user_prompt,
        system_prompt=sys_prompt,
        json_mode=True
    )
    elapsed_ms = round((time.perf_counter() - t_start) * 1000.0, 2)
    if result.latency_ms > elapsed_ms:
        elapsed_ms = round(elapsed_ms + result.latency_ms, 2)

    if result.status != "success":
        return SynthesizeResponse(
            status=result.status,
            provider=result.provider_name,
            model_name=result.model_name,
            latency_ms=elapsed_ms,
            llm_latency_ms=result.latency_ms,
            timeout_sec=result.timeout_sec or provider_info.get("timeout_sec"),
            report=None,
            classifier_output=clf_pred,
            retrieval_results=retrieved_incidents,
            validation_details=None,
            error_message=result.error_message,
            setup_guidance=result.setup_guidance
        )

    # 10. Parse and Validate Structured Report
    raw_json = result.raw_json
    if not raw_json and result.text:
        # Attempt to recover JSON embedded in response
        match = re.search(r"\{.*\}", result.text, re.DOTALL)
        if match:
            try:
                raw_json = json.loads(match.group(0))
            except json.JSONDecodeError:
                raw_json = None

    if not raw_json:
        return SynthesizeResponse(
            status="validation_fallback",
            provider=result.provider_name,
            model_name=result.model_name,
            latency_ms=elapsed_ms,
            llm_latency_ms=result.latency_ms,
            timeout_sec=result.timeout_sec or provider_info.get("timeout_sec"),
            report=None,
            classifier_output=clf_pred,
            retrieval_results=retrieved_incidents,
            validation_details=None,
            error_message="LLM generated output that did not conform to the expected JSON schema.",
            setup_guidance="Try re-running with a specialized instruct model (e.g. llama3.2:3b or mistral)."
        )

    # Enforce strict citation grounding and metadata validation
    try:
        report, val_details = validate_and_sanitize_synthesis(
            raw_data=raw_json,
            evidence_items=evidence_items,
            classifier_prediction=clf_pred
        )
    except Exception as e:
        return SynthesizeResponse(
            status="error",
            provider=result.provider_name,
            model_name=result.model_name,
            latency_ms=elapsed_ms,
            llm_latency_ms=result.latency_ms,
            timeout_sec=result.timeout_sec or provider_info.get("timeout_sec"),
            report=None,
            classifier_output=clf_pred,
            retrieval_results=retrieved_incidents,
            validation_details=None,
            error_message=f"Validation error during synthesis processing: {str(e)}"
        )

    # Status check for limited evidence
    status = "limited_evidence" if len(evidence_items) <= 1 else "success"

    return SynthesizeResponse(
        status=status,
        provider=result.provider_name,
        model_name=result.model_name,
        latency_ms=elapsed_ms,
        llm_latency_ms=result.latency_ms,
        timeout_sec=result.timeout_sec or provider_info.get("timeout_sec"),
        report=report,
        classifier_output=clf_pred,
        retrieval_results=retrieved_incidents,
        validation_details=val_details
    )
