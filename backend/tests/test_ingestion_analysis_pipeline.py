import os
import sys
import uuid
from pathlib import Path
from tempfile import gettempdir

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
# Keep these E2E fixture records out of the developer's live SQLite database.
os.environ["TRACE_SQLITE_DB_PATH"] = str(Path(gettempdir()) / f"trace-ingestion-pipeline-tests-{os.getpid()}.db")

from app.core.database import get_connection  # noqa: E402
from app.ml import ingestion_pipeline  # noqa: E402
from app.ml.stage5_llm.prompt_builder import format_evidence_package  # noqa: E402
from app.api.v1.endpoints import ingestion as ingestion_endpoint  # noqa: E402
from main import app  # noqa: E402


client = TestClient(app)


def _install_fast_pipeline_fakes(monkeypatch, seen, grounding_passed=True):
    monkeypatch.setattr(ingestion_endpoint, "process_ingested_log", ingestion_pipeline.process_ingested_log)

    def fake_predict(text, model_name="baseline"):
        seen.setdefault("model_inputs", {})[model_name] = text
        return {
            "model_name": f"fake-{model_name}",
            "predicted_category": "NETWORK_DEPENDENCY_FAILURE",
            "confidence": 0.91,
            "latency_ms": 1.0,
            "feature_dimension": 8,
            "top_probabilities": {"NETWORK_DEPENDENCY_FAILURE": 0.91},
            "rationale": "test classifier received the complete sanitized log",
        }

    def fake_synthesis(request):
        seen["llm_input"] = request.log_text
        seen["llm_classifier"] = request.classifier_model
        return {
            "status": "success",
            "provider": "test",
            "model_name": "test-model",
            "latency_ms": 1.0,
            "llm_latency_ms": 1.0,
            "timeout_sec": 1.0,
            "report": {"incident_summary": "Payment dependency refused the connection."},
            "classifier_output": {"predicted_category": "NETWORK_DEPENDENCY_FAILURE"},
            "retrieval_results": [{"incident_code": "INC-HIST-1"}],
            "validation_details": {
                "grounding_passed": grounding_passed,
                "unsupported_claims_count": 0 if grounding_passed else 1,
            },
        }

    monkeypatch.setattr(ingestion_pipeline, "predict_with_model", fake_predict)
    monkeypatch.setattr(ingestion_pipeline, "execute_synthesis_pipeline", fake_synthesis)


def _representative_log():
    lines = [f"[INFO] Routine build step {idx:03d} completed" for idx in range(70)]
    lines.insert(44, "[ERROR] payment-service Connection refused at payment-db.internal:5432")
    lines.insert(45, "Caused by: java.net.ConnectException: Connection refused")
    lines.append("[INFO] BUILD FAILURE")
    return "\n".join(lines)


def test_manual_upload_runs_complete_analysis_and_keeps_each_ingestion_separate(monkeypatch):
    seen = {}
    _install_fast_pipeline_fakes(monkeypatch, seen)
    filename = f"manual-pipeline-{uuid.uuid4().hex}.log"
    raw_log = _representative_log() + "\n[INFO] password=supersecret123"

    response = client.post(
        "/api/v1/ingest/upload",
        files={"file": (filename, raw_log.encode(), "text/plain")},
    )
    assert response.status_code == 200, response.text
    first = response.json()

    assert first["analysis_status"] == "success"
    assert first["analysis"]["input"]["complete_log_processed"] is True
    assert first["analysis"]["input"]["line_count"] == len(raw_log.splitlines())
    assert first["analysis"]["input"]["privacy_audit"]["leak_count"] == 1
    assert "supersecret123" not in seen["model_inputs"]["baseline"]
    assert "Connection refused" in seen["model_inputs"]["baseline"]
    assert "BUILD FAILURE" in seen["model_inputs"]["xgboost"]
    assert "Caused by: java.net.ConnectException" in seen["model_inputs"]["graphsage"]
    assert "Connection refused" in seen["llm_input"]
    assert "supersecret123" not in seen["llm_input"]
    assert first["analysis"]["rag"]["retrieved_count"] == 1
    assert first["analysis"]["synthesis"]["report"]["incident_summary"].startswith("Payment dependency")

    latest = client.get("/api/v1/ingest/latest/analysis")
    assert latest.status_code == 200
    assert latest.json()["file_id"] == first["file_id"]

    # Re-uploading a manual filename creates a distinct ingestion/report association.
    second_response = client.post(
        "/api/v1/ingest/upload",
        files={"file": (filename, b"[ERROR] a different ingestion with a different failure", "text/plain")},
    )
    assert second_response.status_code == 200, second_response.text
    second = second_response.json()
    assert second["file_id"] != first["file_id"]
    assert second["filename"] != first["filename"]
    assert client.get(f"/api/v1/ingest/{first['file_id']}/analysis").json()["file_id"] == first["file_id"]


def test_jenkins_json_ingestion_runs_same_pipeline_with_all_console_lines(monkeypatch):
    seen = {}
    _install_fast_pipeline_fakes(monkeypatch, seen)
    console = _representative_log()
    job = f"trace-pipeline-{uuid.uuid4().hex[:8]}"
    response = client.post("/api/v1/ingest/jenkins", json={
        "job_name": job,
        "build_number": "421",
        "build_status": "FAILURE",
        "build_url": f"http://jenkins.local/job/{job}/421/",
        "git_branch": "jenkins-int",
        "console_log": console,
    })

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["line_count"] == len(console.splitlines())
    assert data["analysis_status"] == "success"
    assert "payment-service Connection refused" in seen["model_inputs"]["baseline"]
    assert "Routine build step 069" in seen["llm_input"]
    assert "BUILD FAILURE" in seen["llm_input"]
    assert data["analysis"]["selected_classifier"] == "graphsage"

    with get_connection() as conn:
        record = conn.execute(
            "SELECT processing_status, analysis_json FROM ingestion_analyses WHERE file_id = ?",
            (data["file_id"],),
        ).fetchone()
        source = conn.execute(
            "SELECT byte_size, line_count, build_status FROM source_files WHERE id = ?",
            (data["file_id"],),
        ).fetchone()
    assert record["processing_status"] == "success"
    assert source["line_count"] == len(console.splitlines())
    assert source["build_status"] == "FAILURE"


def test_privacy_and_log_registry_views_follow_the_selected_ingestion(monkeypatch):
    seen = {}
    _install_fast_pipeline_fakes(monkeypatch, seen)
    filename = f"privacy-view-{uuid.uuid4().hex}.log"
    source = "[ERROR] connect to 10.20.30.40 failed\nUser: demo.person@example.test\npassword=private-value-123"
    response = client.post(
        "/api/v1/ingest/upload",
        files={"file": (filename, source.encode(), "text/plain")},
    )
    assert response.status_code == 200, response.text
    file_id = response.json()["file_id"]

    listed = client.get("/api/v1/ingest?limit=5")
    assert listed.status_code == 200
    assert any(item["id"] == file_id and item["filename"] == filename for item in listed.json()["logs"])

    privacy = client.get(f"/api/v1/ingest/{file_id}/privacy")
    assert privacy.status_code == 200, privacy.text
    data = privacy.json()
    assert data["raw_log_exposed"] is False
    assert data["privacy_audit"]["available"] is True
    assert {finding["pattern"] for finding in data["privacy_audit"]["findings"]} == {"EMAIL_ADDRESS", "PASSWORD_KV"}
    assert "demo.person@example.test" not in data["sanitized_log"]
    assert "private-value-123" not in data["sanitized_log"]
    assert "<REDACTED:EMAIL>" in data["sanitized_log"]
    assert "<REDACTED:SECRET>" in data["sanitized_log"]
    assert "10.20.30.40" not in data["sanitized_log"]
    assert len(data["sanitized_log"].splitlines()) == len(source.splitlines())

    events = client.get(f"/api/v1/events?file_id={file_id}&limit=20")
    assert events.status_code == 200
    serialized_events = str(events.json())
    assert "demo.person@example.test" not in serialized_events
    assert "<REDACTED:EMAIL>" in serialized_events


def test_validator_flagged_llm_claim_is_not_marked_as_clean_success(monkeypatch):
    seen = {}
    _install_fast_pipeline_fakes(monkeypatch, seen, grounding_passed=False)
    filename = f"validation-warning-{uuid.uuid4().hex}.log"
    response = client.post(
        "/api/v1/ingest/upload",
        files={"file": (filename, b"[ERROR] synthetic test failure", "text/plain")},
    )
    assert response.status_code == 200, response.text
    result = response.json()

    assert result["analysis_status"] == "validation_warning"
    assert result["analysis"]["synthesis_status"] == "success"
    assert result["analysis"]["synthesis"]["validation_details"]["grounding_passed"] is False
    assert client.get(f"/api/v1/ingest/{result['file_id']}/analysis").json()["processing_status"] == "validation_warning"


def test_stage5_evidence_selects_failure_from_late_in_full_log():
    log_lines = [f"[INFO] long routine line {idx:03d} " + ("x" * 90) for idx in range(70)]
    log_lines[55] = "[ERROR] late-stage sentinel: database migration timed out after 90 seconds"
    log = "\n".join(log_lines)

    evidence, _ = format_evidence_package(
        current_log=log,
        classifier_prediction={"predicted_category": "DATABASE_AND_CACHE_TIMEOUT"},
        root_cause_candidate=None,
        retrieved_incidents=[],
    )

    assert "late-stage sentinel" in evidence[0].snippet
    assert "L56" in evidence[0].snippet
    assert evidence[0].line_span.startswith("1-")
