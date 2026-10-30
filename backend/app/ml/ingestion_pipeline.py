"""Run and persist the existing analysis stages for a newly ingested log."""

import hashlib
import json
from datetime import datetime
from typing import Any, Dict, Optional

from app.core.database import get_connection
from app.core.security import SecretMasker
from app.analysis.root_cause_candidate import RootCauseCandidateAnalyzer
from app.ml.model_registry import predict_with_model
from app.ml.stage5_llm.synthesis_service import execute_synthesis_pipeline
from app.schemas.synthesis_schema import SynthesizeRequest


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "dict"):
        return value.dict()
    return value


def process_ingested_log(file_id: int, raw_text: str) -> Dict[str, Any]:
    """Classify the complete sanitized log, run RAG/LLM synthesis, and persist results.

    Each classifier stage reports its own failure instead of hiding it or preventing
    the already accepted log from remaining available in the registry.
    """
    sanitized = SecretMasker.sanitize(raw_text, mask_ips=True, normalize_identifiers=False)
    predictions: Dict[str, Any] = {}
    for model_name in ("baseline", "xgboost", "graphsage"):
        try:
            predictions[model_name] = {
                "status": "success",
                **predict_with_model(sanitized, model_name=model_name),
            }
        except Exception as exc:
            predictions[model_name] = {
                "status": "unavailable",
                "error": SecretMasker.sanitize(str(exc), mask_ips=True)[:500],
            }

    # Use the strongest available trained classifier to seed the same Stage 4/5
    # pipeline used by the report workbench. GraphSAGE performs its inductive
    # neighbor aggregation here; historical RAG results are supplementary evidence.
    selected = next(
        (name for name in ("graphsage", "xgboost", "baseline")
         if predictions[name]["status"] == "success"),
        None,
    )
    if selected is None:
        raise RuntimeError("No configured classifier could process this ingested log.")

    rca_prediction = predictions[selected]
    rca = RootCauseCandidateAnalyzer.analyze(
        sanitized, primary_category=rca_prediction["predicted_category"]
    )

    # Stage 5 receives the entire sanitized console log, not the build status or a
    # single extracted line. Its own pipeline reruns the selected classifier, does
    # hybrid RAG retrieval, constructs cited evidence, and invokes the configured LLM.
    synthesis = execute_synthesis_pipeline(SynthesizeRequest(
        log_text=sanitized,
        classifier_model=selected,
        retrieval_top_k=4,
    ))
    synthesis_data = _jsonable(synthesis)
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    count_conn = get_connection(timeout=10.0)
    try:
        event_count = count_conn.execute(
            "SELECT COUNT(*) FROM parsed_events WHERE file_id = ?", (file_id,)
        ).fetchone()[0]
    finally:
        count_conn.close()

    analysis = {
        "file_id": file_id,
        "status": synthesis_data.get("status", "error"),
        "input": {
            "complete_log_processed": True,
            "line_count": len(raw_text.splitlines()),
            "raw_byte_count": len(raw_text.encode("utf-8")),
            "sanitized_character_count": len(sanitized),
            "sanitized_sha256": hashlib.sha256(sanitized.encode("utf-8")).hexdigest(),
            "privacy_audit": SecretMasker.audit_leaks(raw_text),
        },
        "parsing": {
            "lines_processed": len(raw_text.splitlines()),
            "nonempty_lines_processed": sum(bool(line.strip()) for line in raw_text.splitlines()),
            "structured_events_persisted": event_count,
            "all_lines_inspected": True,
        },
        "classifiers": predictions,
        "selected_classifier": selected,
        "root_cause_candidate": rca,
        "rag": {
            "retrieved_count": len(synthesis_data.get("retrieval_results") or []),
            "results": synthesis_data.get("retrieval_results") or [],
        },
        "synthesis": synthesis_data,
        "updated_at": now,
    }
    status = synthesis_data.get("status", "error")
    validation = synthesis_data.get("validation_details") or {}
    if synthesis_data.get("report") and validation.get("grounding_passed") is False:
        # Keep the report and evidence for review, but never label a report with
        # validator-flagged claims as a clean success in the ingestion workflow.
        status = "validation_warning"
        analysis["synthesis_status"] = synthesis_data.get("status", "error")
        analysis["status"] = status
    conn = get_connection(timeout=30.0)
    try:
        with conn:
            conn.execute(
                """INSERT INTO ingestion_analyses
                   (file_id, processing_status, analysis_json, synthesis_json, error_message, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(file_id) DO UPDATE SET
                     processing_status=excluded.processing_status,
                     analysis_json=excluded.analysis_json,
                     synthesis_json=excluded.synthesis_json,
                     error_message=excluded.error_message,
                     updated_at=excluded.updated_at""",
                (
                    file_id,
                    status,
                    json.dumps(analysis, ensure_ascii=False),
                    json.dumps(synthesis_data, ensure_ascii=False),
                    synthesis_data.get("error_message"),
                    now,
                ),
            )
    finally:
        conn.close()
    return analysis


def get_ingestion_analysis(file_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection(timeout=10.0)
    try:
        row = conn.execute(
            """SELECT a.*, f.filename, f.job_name, f.build_number, f.build_status,
                      f.build_url, f.repo_url, f.commit_sha, f.git_branch, f.ingested_at
               FROM ingestion_analyses a
               JOIN source_files f ON f.id = a.file_id
               WHERE a.file_id = ?""",
            (file_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "file_id": file_id,
            "processing_status": row["processing_status"],
            "analysis": json.loads(row["analysis_json"]) if row["analysis_json"] else None,
            "synthesis": json.loads(row["synthesis_json"]) if row["synthesis_json"] else None,
            "error_message": row["error_message"],
            "updated_at": row["updated_at"],
            "filename": row["filename"],
            "job_name": row["job_name"],
            "build_number": row["build_number"],
            "build_status": row["build_status"],
            "build_url": row["build_url"],
            "repo_url": row["repo_url"],
            "commit_sha": row["commit_sha"],
            "git_branch": row["git_branch"],
            "ingested_at": row["ingested_at"],
        }
    finally:
        conn.close()
