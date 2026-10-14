import sys
import io
from pathlib import Path

# Add backend and root to sys.path
root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(root_dir / "backend"))
sys.path.append(str(root_dir))

try:
    import pytest
except ImportError:
    pytest = None
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from main import app
from app.core.security import SecretMasker
from app.parsers.regex_parser import LogParserEngine
from app.analysis.root_cause_candidate import RootCauseCandidateAnalyzer
from app.ml.baseline.tfidf_rf import BaselineTfidfRandomForest
from app.core.database import get_connection

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
    if not baseline.load():
        if pytest:
            pytest.skip("Baseline model not trained or cached in models_cache yet.")
        else:
            return

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
    assert data["status"] in ("HEALTHY", "DEGRADED")
    assert data["database"]["connected"] is True

def test_api_metrics_endpoint():
    resp = client.get("/api/v1/metrics")
    assert resp.status_code == 200
    data = resp.json()
    assert data["model_name"] == "Academic Baseline (TF-IDF + Random Forest)"
    assert "Held-out Test" in data["dataset_split"]
    assert data["accuracy"] > 0.85
    assert data["f1_macro"] > 0.85
    assert len(data["limitations"]) > 0

def test_api_predict_endpoint_when_untrained():
    """Verifies that direct prediction returns HTTP 503 when baseline model is not loaded."""
    from app.api.v1.endpoints import classification
    with patch.object(classification.baseline_model, "is_trained", False), \
         patch.object(classification.baseline_model, "load", return_value=False):
        payload = {"text": "AssertionError: storage cluster id is missing from config"}
        resp = client.post("/api/v1/classification/predict", json=payload)
        assert resp.status_code == 503
        assert "Baseline model is not loaded" in resp.json()["detail"]

def test_api_predict_endpoint_when_trained():
    """Verifies direct prediction returns HTTP 200 when baseline model is available."""
    from app.api.v1.endpoints import classification
    mock_prediction = {
        "model_name": "Academic Baseline (TF-IDF + Random Forest)",
        "predicted_category": "STORAGE_AND_IO_ERROR",
        "confidence": 0.95,
        "latency_ms": 12.5,
        "feature_dimension": 1500,
        "top_probabilities": {"STORAGE_AND_IO_ERROR": 0.95},
        "rationale": "Mocked test rationale"
    }
    with patch.object(classification.baseline_model, "is_trained", True), \
         patch.object(classification.baseline_model, "predict", return_value=mock_prediction):
        payload = {"text": "AssertionError: storage cluster id is missing from config in datastore creation"}
        resp = client.post("/api/v1/classification/predict", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["predicted_category"] == "STORAGE_AND_IO_ERROR"
        assert data["confidence"] == 0.95

def test_api_analyze_model_unavailable_returns_503():
    """
    Regression Test: Ensures that /api/v1/analysis/analyze returns HTTP 503 (not HTTP 500)
    with a clear diagnostic message when baseline model artifacts are missing.
    """
    from app.api.v1.endpoints import analysis
    with patch.object(analysis.baseline_model, "is_trained", False), \
         patch.object(analysis.baseline_model, "load", return_value=False):
        payload = {"log_text": "2026-09-15T09:04:30.123Z ERROR [order-service] Connection refused by payment service"}
        resp = client.post("/api/v1/analysis/analyze", json=payload)
        assert resp.status_code == 503
        assert "Baseline model is not loaded" in resp.json()["detail"]

def test_api_analyze_model_available_returns_200():
    """
    Verifies that /api/v1/analysis/analyze succeeds with HTTP 200 when baseline model is loaded,
    correctly combining parsing, ML classification, and root-cause candidate analysis.
    """
    from app.api.v1.endpoints import analysis
    mock_pred = {
        "model_name": "Academic Baseline (TF-IDF + Random Forest)",
        "predicted_category": "NETWORK_DEPENDENCY_FAILURE",
        "confidence": 0.88,
        "latency_ms": 15.2,
        "feature_dimension": 1500,
        "top_probabilities": {"NETWORK_DEPENDENCY_FAILURE": 0.88},
        "rationale": "Test inference rationale"
    }
    with patch.object(analysis.baseline_model, "is_trained", True), \
         patch.object(analysis.baseline_model, "predict", return_value=mock_pred):
        payload = {"log_text": "2026-09-15T09:04:30.123Z ERROR [notification-service] password=supersecret status=503 Connection refused by payment service"}
        resp = client.post("/api/v1/analysis/analyze", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_failure"] is True
        assert data["classification"]["predicted_category"] == "NETWORK_DEPENDENCY_FAILURE"
        assert "supersecret" not in data["sanitized_input"]
        assert data["privacy_audit"]["clean"] is False
        assert data["root_cause"]["failure_category"] == "NETWORK_DEPENDENCY_FAILURE"
        assert "Upstream Dependency" in data["root_cause"]["root_cause_candidate"]

def test_api_upload_privacy_no_secret_leak_in_db():
    """
    Regression Test: Verifies that uploading logs containing sensitive dummy credentials
    (AWS keys, GitHub PATs, JWTs, passwords, IPv4 addresses) NEVER persists plaintext secrets
    in any SQLite table or column (neither sanitized_message nor raw_message).
    """
    dummy_aws = "AKIAIOSFODNN7EXAMPLE"
    dummy_ghp = "ghp_1234567890abcdefghijklmnopqrstuvwxyz"
    dummy_pwd = "dummy_secret_password_456"
    dummy_jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0"
    dummy_ip = "10.157.171.249"

    log_content = (
        f"2026-09-15T09:00:00.123Z INFO [auth-service] host={dummy_ip} aws_key={dummy_aws}\n"
        f"2026-09-15T09:01:00.123Z WARN [auth-service] token={dummy_ghp} password={dummy_pwd}\n"
        f"2026-09-15T09:02:00.123Z ERROR [auth-service] Bearer {dummy_jwt} Connection refused\n"
    )

    file_bytes = io.BytesIO(log_content.encode("utf-8"))
    resp = client.post(
        "/api/v1/ingest/upload",
        files={"file": ("privacy_regression_test.log", file_bytes, "text/plain")}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["events_inserted"] == 3

    # Inspect SQLite database directly
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT sanitized_message, raw_message FROM parsed_events WHERE file_id = ?;", (data["file_id"],))
    event_rows = c.fetchall()

    c.execute("SELECT detected_signature, evidence_text FROM incidents WHERE file_id = ?;", (data["file_id"],))
    incident_rows = c.fetchall()
    conn.close()

    assert len(event_rows) == 3

    # Verify NO secrets leaked in any row or column of parsed_events
    for row in event_rows:
        for col_name in ("sanitized_message", "raw_message"):
            val = row[col_name]
            assert dummy_aws not in val, f"Leaked AWS key in {col_name}: {val}"
            assert dummy_ghp not in val, f"Leaked GitHub token in {col_name}: {val}"
            assert dummy_pwd not in val, f"Leaked password in {col_name}: {val}"
            assert dummy_jwt not in val, f"Leaked JWT in {col_name}: {val}"
            assert dummy_ip not in val, f"Leaked IP in {col_name}: {val}"

    # Verify NO secrets leaked in incidents table
    for row in incident_rows:
        for col_name in ("detected_signature", "evidence_text"):
            val = row[col_name]
            assert dummy_aws not in val, f"Leaked AWS key in incidents.{col_name}: {val}"
            assert dummy_ghp not in val, f"Leaked GitHub token in incidents.{col_name}: {val}"
            assert dummy_pwd not in val, f"Leaked password in incidents.{col_name}: {val}"
            assert dummy_jwt not in val, f"Leaked JWT in incidents.{col_name}: {val}"
            assert dummy_ip not in val, f"Leaked IP in incidents.{col_name}: {val}"

def test_api_incidents_get():
    resp = client.get("/api/v1/incidents?limit=10")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)

def test_api_events_get():
    resp = client.get("/api/v1/events?limit=10")
    assert resp.status_code == 200
    data = resp.json()
    assert "total" in data
    assert "events" in data

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

def test_api_malformed_empty_input():
    resp = client.post("/api/v1/analysis/analyze", json={"log_text": "   "})
    assert resp.status_code == 400
    assert "empty" in resp.json()["detail"].lower()

if __name__ == "__main__":
    import inspect
    current_module = sys.modules[__name__]
    all_tests = [
        obj for name, obj in inspect.getmembers(current_module)
        if inspect.isfunction(obj) and name.startswith("test_")
    ]
    print(f"\n{'='*75}\nRUNNING REVIEW-1 TEST SUITE DIRECTLY (NO PYTEST REQUIRED)\n{'='*75}")
    passed = 0
    failed = 0
    for test_fn in all_tests:
        try:
            test_fn()
            print(f"  [PASS] {test_fn.__name__}")
            passed += 1
        except Exception as exc:
            print(f"  [FAIL] {test_fn.__name__}: {type(exc).__name__}: {exc}")
            failed += 1
    print(f"{'='*75}\nTEST SUMMARY: {passed} PASSED, {failed} FAILED\n{'='*75}\n")
    if failed > 0:
        sys.exit(1)
