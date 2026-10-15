import sys
import io
from pathlib import Path

# Add backend and root to sys.path
root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(root_dir / "backend"))
sys.path.append(str(root_dir))

import pytest
from fastapi.testclient import TestClient
from main import app
from app.core.security import SecretMasker
from app.parsers.regex_parser import LogParserEngine
from app.analysis.root_cause_candidate import RootCauseCandidateAnalyzer
from app.ml.baseline.tfidf_rf import BaselineTfidfRandomForest

client = TestClient(app)

# =========================================================================
# 1. SECRET SANITIZER & PRIVACY TESTS
# =========================================================================

def test_secret_masker_aws_and_pat():
    raw = "AWS_SECRET_KEY=AKIAIOSFODNN7EXAMPLE and ghp_1234567890abcdefghijklmnopqrstuvwxyz"
    clean = SecretMasker.sanitize(raw)
    assert "AKIAIOSFODNN7EXAMPLE" not in clean
    assert "<REDACTED:AWS_KEY>" in clean
    assert "<REDACTED:GITHUB_TOKEN>" in clean

def test_secret_masker_password_and_ip():
    raw = "password: ***POTENTIAL_SECRET***, host=10.157.171.249"
    clean = SecretMasker.sanitize(raw, mask_ips=True)
    assert "***POTENTIAL_SECRET***" not in clean
    assert "10.157.171.249" not in clean
    assert "<IP>" in clean

def test_privacy_audit_detection():
    raw = "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0"
    audit = SecretMasker.audit_leaks(raw)
    assert not audit["clean"]
    assert audit["leak_count"] > 0

# =========================================================================
# 2. LOG PARSER TESTS (3 AUTHENTIC DIALECTS & MULTILINE)
# =========================================================================

def test_parse_microservices_dialect():
    line = "2026-09-15T09:03:00.123Z ERROR auth-service node-04 trace=trace-9770838 span=span-51467 latency_ms=2755 Null pointer while processing order"
    entry = LogParserEngine.parse_line(line)
    assert entry.timestamp == "2026-09-15T09:03:00.123Z"
    assert entry.level == "ERROR"
    assert entry.service == "auth-service"
    assert entry.node == "node-04"
    assert entry.trace_id == "trace-9770838"
    assert entry.latency_ms == 2755.0
    assert "Null pointer" in entry.sanitized_message

def test_parse_jenkins_pytest_dialect():
    line = "2026-02-25 21:12:39 MST test_vme_storage_plugin_e2e.py:320 ERROR : Actual error is: storage cluster id is missing from config in datastore alletra_datastore_abgrdg_dnd creation"
    entry = LogParserEngine.parse_line(line)
    assert entry.level == "ERROR"
    assert "test_vme_storage_plugin_e2e.py" in entry.service
    assert "storage cluster id is missing" in entry.sanitized_message

def test_parse_jenkins_jvm_dialect():
    line = "2022-10-04 19:25:40.961+0000 [id=19] WARNING h.i.i.InstallUncaughtExceptionHandler#handleException: Caught unhandled exception with ID 2f2d9bc5-7c14"
    entry = LogParserEngine.parse_line(line)
    assert entry.level == "WARN"
    assert "InstallUncaughtExceptionHandler" in entry.service
    assert "Caught unhandled exception" in entry.sanitized_message

# =========================================================================
# 3. ROOT CAUSE CANDIDATE ANALYSIS TESTS
# =========================================================================

def test_root_cause_storage_candidate():
    text = "AssertionError: storage cluster id is missing from config in datastore creation"
    res = RootCauseCandidateAnalyzer.analyze(text)
    assert res["failure_category"] == "STORAGE_AND_IO_ERROR"
    assert "Storage Infrastructure" in res["root_cause_candidate"]
    assert "iSCSI" in res["remediation_guidance"]

def test_root_cause_network_candidate():
    text = "Connection refused by payment service status=503"
    res = RootCauseCandidateAnalyzer.analyze(text)
    assert res["failure_category"] == "NETWORK_DEPENDENCY_FAILURE"
    assert "Upstream Dependency" in res["root_cause_candidate"]

def test_root_cause_database_candidate():
    text = "Database connection timeout latency_ms=4389"
    res = RootCauseCandidateAnalyzer.analyze(text)
    assert res["failure_category"] == "DATABASE_AND_CACHE_TIMEOUT"
    assert "Database" in res["root_cause_candidate"]

# =========================================================================
# 4. ACADEMIC BASELINE MODEL TESTS
# =========================================================================

def test_baseline_model_inference():
    baseline = BaselineTfidfRandomForest()
    assert baseline.load(), "Baseline model failed to load from models_cache."

    sample = "AssertionError: storage cluster id is missing from config in datastore creation"
    pred = baseline.predict(sample)

    assert pred["model_name"] == "Academic Baseline (TF-IDF + Random Forest)"
    assert pred["predicted_category"] == "STORAGE_AND_IO_ERROR"
    assert pred["confidence"] > 0.4
    assert pred["latency_ms"] >= 0
    assert pred["feature_dimension"] > 500
    assert len(pred["top_probabilities"]) > 0

# =========================================================================
# 5. FASTAPI REST ENDPOINTS TESTS
# =========================================================================

def test_api_health_endpoint():
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "HEALTHY"
    assert data["active_model"]["loaded"] is True
    assert data["database"]["connected"] is True
    assert data["database"]["source_files_count"] >= 3

def test_api_metrics_endpoint():
    resp = client.get("/api/v1/metrics")
    assert resp.status_code == 200
    data = resp.json()
    assert data["model_name"] == "Academic Baseline (TF-IDF + Random Forest)"
    assert "Held-out" in data["dataset_split"]
    assert data["accuracy"] > 0.80
    assert data["f1_macro"] > 0.70
    assert len(data["limitations"]) > 0

def test_api_predict_endpoint():
    payload = {"text": "AssertionError: storage cluster id is missing from config in datastore creation"}
    resp = client.post("/api/v1/classification/predict", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["predicted_category"] == "STORAGE_AND_IO_ERROR"
    assert data["confidence"] > 0.4

def test_api_analyze_endpoint():
    payload = {"log_text": "2026-09-15T09:04:30.123Z ERROR [notification-service] password=supersecret status=503 Connection refused by payment service"}
    resp = client.post("/api/v1/analysis/analyze", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_failure"] is True
    assert data["classification"]["predicted_category"] == "NETWORK_DEPENDENCY_FAILURE"
    assert "supersecret" not in data["sanitized_input"]
    assert data["privacy_audit"]["clean"] is False

def test_api_incidents_get():
    resp = client.get("/api/v1/incidents?limit=10")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) > 0
    assert "incident_code" in data[0]
    assert "root_cause_candidate" in data[0]

def test_api_events_get():
    resp = client.get("/api/v1/events?limit=10&severity=ERROR")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] > 0
    assert len(data["events"]) > 0
    assert data["events"][0]["severity"] == "ERROR"

def test_api_upload_file():
    sample_content = "2026-09-15T09:00:00.123Z INFO [auth-service] System initialized\n2026-09-15T09:03:00.123Z ERROR [auth-service] Null pointer while processing order\n"
    file_bytes = io.BytesIO(sample_content.encode("utf-8"))
    resp = client.post(
        "/api/v1/ingest/upload",
        files={"file": ("live_upload_test.log", file_bytes, "text/plain")}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["filename"] == "live_upload_test.log"
    assert data["events_inserted"] == 2
    assert data["incidents_detected"] == 1

def test_api_malformed_empty_input():
    resp = client.post("/api/v1/analysis/analyze", json={"log_text": "   "})
    assert resp.status_code == 400
    assert "empty" in resp.json()["detail"].lower()
