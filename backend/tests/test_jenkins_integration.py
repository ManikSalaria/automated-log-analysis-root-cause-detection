import sys
import io
import uuid
from pathlib import Path

# Add backend and root to sys.path
root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(root_dir / "backend"))
sys.path.append(str(root_dir))

import pytest
from fastapi.testclient import TestClient

from main import app
from app.core.database import get_connection, init_database

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_db():
    init_database()

def create_test_token(name: str = "Test Jenkins"):
    """Helper to generate a fresh integration token."""
    resp = client.post("/api/v1/jenkins/tokens", json={"name": name})
    assert resp.status_code == 200
    data = resp.json()
    return data["id"], data["token"]

# =========================================================================
# 1. TOKEN CREATION, LISTING, AND REVOCATION
# =========================================================================

def test_jenkins_token_lifecycle():
    # 1. Create Token
    token_id, raw_token = create_test_token("CI Runner Token")
    assert raw_token.startswith("trc_")
    assert len(raw_token) > 30

    # 2. List Tokens
    resp = client.get("/api/v1/jenkins/tokens")
    assert resp.status_code == 200
    tokens = resp.json()
    assert any(t["id"] == token_id for t in tokens)
    # Plaintext token must NEVER be returned in listing
    for t in tokens:
        assert "token" not in t or t.get("token") is None
        assert "trc_" not in t["token_preview"][:4] or "..." in t["token_preview"]

    # 3. Test Connection with valid token
    resp_conn = client.post(
        "/api/v1/jenkins/test-connection",
        headers={"Authorization": f"Bearer {raw_token}"}
    )
    assert resp_conn.status_code == 200
    assert resp_conn.json()["status"] == "CONNECTED"

    # Also test X-TRACE-API-KEY header
    resp_conn2 = client.post(
        "/api/v1/jenkins/test-connection",
        headers={"X-TRACE-API-KEY": raw_token}
    )
    assert resp_conn2.status_code == 200
    assert resp_conn2.json()["status"] == "CONNECTED"

    # 4. Revoke Token
    resp_rev = client.post(f"/api/v1/jenkins/tokens/{token_id}/revoke")
    assert resp_rev.status_code == 200
    assert resp_rev.json()["status"] == "REVOKED"

    # 5. Connection with revoked token must fail with 401
    resp_fail = client.post(
        "/api/v1/jenkins/test-connection",
        headers={"Authorization": f"Bearer {raw_token}"}
    )
    assert resp_fail.status_code == 401
    assert "revoked" in resp_fail.json()["detail"].lower()

# =========================================================================
# 2. AUTHENTICATION FAILURE CASES
# =========================================================================

def test_jenkins_ingest_missing_auth():
    resp = client.post("/api/v1/jenkins/ingest", json={"job_name": "demo", "build_number": "1", "log_text": "hello"})
    assert resp.status_code == 401
    assert "token required" in resp.json()["detail"].lower()

def test_jenkins_ingest_invalid_token():
    resp = client.post(
        "/api/v1/jenkins/ingest",
        json={"job_name": "demo", "build_number": "1", "log_text": "hello"},
        headers={"Authorization": "Bearer trc_invalid_dummy_token_1234567890"}
    )
    assert resp.status_code == 401
    assert "invalid" in resp.json()["detail"].lower()

# =========================================================================
# 3. VALIDATION & PAYLOAD ERROR CASES
# =========================================================================

def test_jenkins_ingest_missing_metadata():
    _, raw_token = create_test_token("Validation Test Token")
    headers = {"Authorization": f"Bearer {raw_token}"}

    # Missing job_name
    resp = client.post(
        "/api/v1/jenkins/ingest",
        json={"build_number": "1", "log_text": "some build log"},
        headers=headers
    )
    assert resp.status_code == 400
    assert "job_name" in resp.json()["detail"].lower()

    # Missing build_number
    resp = client.post(
        "/api/v1/jenkins/ingest",
        json={"job_name": "api-tests", "log_text": "some build log"},
        headers=headers
    )
    assert resp.status_code == 400
    assert "build_number" in resp.json()["detail"].lower()

    # Empty log
    resp = client.post(
        "/api/v1/jenkins/ingest",
        json={"job_name": "api-tests", "build_number": "1", "log_text": "   "},
        headers=headers
    )
    assert resp.status_code == 400
    assert "empty" in resp.json()["detail"].lower()

def test_jenkins_ingest_payload_size_limit():
    _, raw_token = create_test_token("Size Limit Token")
    headers = {"Authorization": f"Bearer {raw_token}"}

    # Generate oversized payload (> 20 MB)
    huge_text = "A" * (20 * 1024 * 1024 + 1024)
    resp = client.post(
        "/api/v1/jenkins/ingest",
        json={"job_name": "large-build", "build_number": "99", "log_text": huge_text},
        headers=headers
    )
    assert resp.status_code == 413
    assert "exceeds" in resp.json()["detail"].lower()

# =========================================================================
# 4. SUCCESSFUL BUILD INGESTION (JSON & MULTIPART)
# =========================================================================

def test_jenkins_ingest_successful_clean_build():
    _, raw_token = create_test_token("Clean Build Token")
    headers = {"Authorization": f"Bearer {raw_token}"}

    clean_log = (
        "[INFO] Building project trace-backend 1.0.0\n"
        "[INFO] Running tests...\n"
        "[INFO] Tests run: 45, Failures: 0, Errors: 0, Skipped: 0\n"
        "[INFO] BUILD SUCCESS\n"
    )

    build_num = f"101_{uuid.uuid4().hex[:6]}"
    payload = {
        "job_name": "frontend-pipeline",
        "build_number": build_num,
        "build_url": f"http://jenkins.corp.internal/job/frontend-pipeline/{build_num}/",
        "repo_url": "https://github.com/org/repo.git",
        "commit_sha": "a1b2c3d4e5f6",
        "build_status": "SUCCESS",
        "log_text": clean_log
    }

    resp = client.post("/api/v1/jenkins/ingest", json=payload, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["build_id"] == f"frontend-pipeline#{build_num}"
    assert data["is_failure"] is False
    assert data["incidents_count"] == 0
    assert data["is_retry"] is False

def test_jenkins_success_status_overrides_log_incidents_for_build_classification():
    _, raw_token = create_test_token("Recovered Error Token")
    headers = {"Authorization": f"Bearer {raw_token}"}
    build_num = f"recovered_{uuid.uuid4().hex[:6]}"
    payload = {
        "job_name": "recovered-error-job",
        "build_number": build_num,
        "build_status": "SUCCESS",
        "log_text": "[ERROR] Temporary connection failure; retry succeeded\n[INFO] BUILD SUCCESS\n",
    }

    response = client.post("/api/v1/jenkins/ingest", json=payload, headers=headers)
    assert response.status_code == 200
    ingested = response.json()
    assert ingested["build_status"] == "SUCCESS"
    assert ingested["is_failure"] is False
    assert ingested["failure_category"] is None
    assert ingested["incidents_count"] == 1

    listed = client.get(f"/api/v1/jenkins/builds?job_name={payload['job_name']}")
    assert listed.status_code == 200
    summary = next(item for item in listed.json() if item["build_id"] == ingested["build_id"])
    assert summary["is_failure"] is False
    assert summary["primary_failure_category"] is None

    detail = client.get(f"/api/v1/jenkins/builds/{ingested['build_id'].replace('#', '%23')}")
    assert detail.status_code == 200
    assert detail.json()["is_failure"] is False
    assert detail.json()["incidents_count"] == 1

@pytest.mark.parametrize(
    ("build_status", "log_text", "expected_failure"),
    [
        ("SUCCESS", "[ERROR] recovered after retry\n", False),
        ("FAILURE", "INFO build stopped\n", True),
        ("UNSTABLE", "INFO tests completed with warnings\n", True),
        ("ABORTED", "INFO build stopped by user\n", False),
        ("ABORTED", "[ERROR] failure before abort\n", True),
        ("UNKNOWN", "INFO build completed\n", False),
        ("UNKNOWN", "[ERROR] failure with unknown result\n", True),
        (None, "INFO build completed\n", False),
        (None, "[ERROR] failure with missing result\n", True),
    ],
)
def test_jenkins_build_status_failure_matrix(build_status, log_text, expected_failure):
    _, raw_token = create_test_token("Status Matrix Token")
    headers = {"Authorization": f"Bearer {raw_token}"}
    build_num = f"status_{uuid.uuid4().hex[:8]}"
    payload = {
        "job_name": f"status-matrix-{uuid.uuid4().hex[:8]}",
        "build_number": build_num,
        "log_text": log_text,
    }
    if build_status is not None:
        payload["build_status"] = build_status

    response = client.post("/api/v1/jenkins/ingest", json=payload, headers=headers)
    assert response.status_code == 200
    build = response.json()
    assert build["is_failure"] is expected_failure

    listed = client.get(f"/api/v1/jenkins/builds?job_name={payload['job_name']}")
    assert listed.status_code == 200
    summary = next(item for item in listed.json() if item["build_id"] == build["build_id"])
    assert summary["is_failure"] is expected_failure

    detail = client.get(f"/api/v1/jenkins/builds/{build['build_id'].replace('#', '%23')}")
    assert detail.status_code == 200
    assert detail.json()["is_failure"] is expected_failure

def test_jenkins_ingest_multipart_form():
    _, raw_token = create_test_token("Multipart Token")
    headers = {"Authorization": f"Bearer {raw_token}"}

    log_bytes = b"2026-09-15T09:00:00Z INFO [app] Initialized\n2026-09-15T09:01:00Z INFO [app] Completed successfully\n"
    build_num = f"42_{uuid.uuid4().hex[:6]}"

    resp = client.post(
        "/api/v1/jenkins/ingest",
        data={
            "job_name": "data-sync-job",
            "build_number": build_num,
            "build_status": "SUCCESS"
        },
        files={"file": ("console.log", io.BytesIO(log_bytes), "text/plain")},
        headers=headers
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["build_id"] == f"data-sync-job#{build_num}"
    assert data["events_count"] == 2

# =========================================================================
# 5. FAILURE DETECTION, CLASSIFICATION, AND ROOT CAUSE
# =========================================================================

def test_jenkins_ingest_failure_with_rca():
    _, raw_token = create_test_token("Failure RCA Token")
    headers = {"Authorization": f"Bearer {raw_token}"}

    failed_log = (
        "2026-09-15T09:04:30.123Z INFO [notification-service] Sending alert\n"
        "2026-09-15T09:04:31.123Z ERROR [notification-service] status=503 latency_ms=3371 Connection refused by payment service\n"
        "2026-09-15T09:04:32.123Z INFO [notification-service] Retry exhausted\n"
    )

    build_num = f"78_{uuid.uuid4().hex[:6]}"
    payload = {
        "job_name": "ecommerce-payment-test",
        "build_number": build_num,
        "build_url": f"http://jenkins.corp.internal/job/ecommerce-payment-test/{build_num}/",
        "build_status": "FAILURE",
        "log_text": failed_log
    }

    resp = client.post("/api/v1/jenkins/ingest", json=payload, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_failure"] is True
    assert data["incidents_count"] >= 1
    assert data["failure_category"] in ("NETWORK_DEPENDENCY_FAILURE", "STORAGE_AND_IO_ERROR", "ENVIRONMENT_AND_PIPELINE_ERROR")
    assert data["root_cause_candidate"] is not None
    assert data["confidence"] > 0.4

    listed = client.get(f"/api/v1/jenkins/builds?job_name={payload['job_name']}")
    assert listed.status_code == 200
    summary = next(item for item in listed.json() if item["build_id"] == data["build_id"])
    assert summary["is_failure"] is True

    detail = client.get(f"/api/v1/jenkins/builds/{data['build_id'].replace('#', '%23')}")
    assert detail.status_code == 200
    assert detail.json()["is_failure"] is True

# =========================================================================
# 6. ZERO-PII SECRET SANITIZATION IN JENKINS BUILDS
# =========================================================================

def test_jenkins_ingest_secret_sanitization():
    _, raw_token = create_test_token("Privacy Test Token")
    headers = {"Authorization": f"Bearer {raw_token}"}

    dummy_aws = "AKIAIOSFODNN7EXAMPLE"
    dummy_ghp = "ghp_1234567890abcdefghijklmnopqrstuvwxyz"
    dummy_pwd = "dummy_secret_password_789"
    dummy_ip = "192.168.1.100"

    leak_log = (
        f"[INFO] Deploying with aws_key={dummy_aws} host={dummy_ip}\n"
        f"[ERROR] Auth failed with token={dummy_ghp} password={dummy_pwd} Connection refused by payment service\n"
    )

    build_num = f"5_{uuid.uuid4().hex[:6]}"
    resp = client.post(
        "/api/v1/jenkins/ingest",
        json={
            "job_name": "secure-pipeline",
            "build_number": build_num,
            "build_status": "FAILURE",
            "log_text": leak_log
        },
        headers=headers
    )
    assert resp.status_code == 200
    data = resp.json()
    build_id = data["build_id"]

    # Verify directly in SQLite that NO secrets were saved
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT file_id FROM jenkins_builds WHERE build_id = ?;", (build_id,))
    file_id = c.fetchone()["file_id"]

    c.execute("SELECT sanitized_message, raw_message FROM parsed_events WHERE file_id = ?;", (file_id,))
    events = c.fetchall()

    c.execute("SELECT detected_signature, evidence_text FROM incidents WHERE file_id = ?;", (file_id,))
    incidents = c.fetchall()
    conn.close()

    for row in events:
        for col in ("sanitized_message", "raw_message"):
            val = row[col]
            assert dummy_aws not in val, f"Leaked AWS key in {col}"
            assert dummy_ghp not in val, f"Leaked GitHub token in {col}"
            assert dummy_pwd not in val, f"Leaked password in {col}"
            assert dummy_ip not in val, f"Leaked IP in {col}"

    for row in incidents:
        for col in ("detected_signature", "evidence_text"):
            val = row[col]
            assert dummy_aws not in val, f"Leaked AWS key in incidents.{col}"
            assert dummy_ghp not in val, f"Leaked GitHub token in incidents.{col}"
            assert dummy_pwd not in val, f"Leaked password in incidents.{col}"
            assert dummy_ip not in val, f"Leaked IP in incidents.{col}"

# =========================================================================
# 7. IDEMPOTENCY / RETRIED UPLOADS
# =========================================================================

def test_jenkins_ingest_idempotency_on_retry():
    _, raw_token = create_test_token("Idempotency Token")
    headers = {"Authorization": f"Bearer {raw_token}"}

    sample_log = "[INFO] Initializing task\n[INFO] Complete\n"
    build_num = f"200_{uuid.uuid4().hex[:6]}"
    payload = {
        "job_name": "nightly-sync",
        "build_number": build_num,
        "build_status": "SUCCESS",
        "log_text": sample_log
    }

    # First upload
    resp1 = client.post("/api/v1/jenkins/ingest", json=payload, headers=headers)
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["is_retry"] is False

    # Second identical upload (Jenkins retry)
    resp2 = client.post("/api/v1/jenkins/ingest", json=payload, headers=headers)
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["is_retry"] is True
    assert data2["build_id"] == data1["build_id"]

    # Verify database has only 1 build record and 1 source_file for this build
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM jenkins_builds WHERE build_id = ?;", (f"nightly-sync#{build_num}",))
    assert c.fetchone()[0] == 1
    conn.close()

# =========================================================================
# 8. BUILDS RETRIEVAL (LISTING & DETAIL)
# =========================================================================

def test_jenkins_build_query_endpoints():
    _, raw_token = create_test_token("Query Token")
    headers = {"Authorization": f"Bearer {raw_token}"}

    uid = uuid.uuid4().hex[:6]
    job_a = f"query-job-a-{uid}"
    job_b = f"query-job-b-{uid}"

    client.post(
        "/api/v1/jenkins/ingest",
        json={"job_name": job_a, "build_number": "1", "build_status": "SUCCESS", "log_text": "INFO done"},
        headers=headers
    )
    client.post(
        "/api/v1/jenkins/ingest",
        json={"job_name": job_b, "build_number": "2", "build_status": "FAILURE", "log_text": "ERROR cluster missing"},
        headers=headers
    )

    # 1. List builds
    resp_list = client.get("/api/v1/jenkins/builds?limit=10")
    assert resp_list.status_code == 200
    builds = resp_list.json()
    assert len(builds) >= 2
    assert any(b["build_id"] == f"{job_a}#1" for b in builds)

    # 2. Filter by job_name
    resp_filter = client.get(f"/api/v1/jenkins/builds?job_name={job_b}")
    assert resp_filter.status_code == 200
    filtered = resp_filter.json()
    assert all(job_b in b["job_name"] for b in filtered)

    # 3. Get build detail
    resp_detail = client.get(f"/api/v1/jenkins/builds/{job_b}%232")
    assert resp_detail.status_code == 200
    detail = resp_detail.json()
    assert detail["build_id"] == f"{job_b}#2"
    assert "incidents" in detail
    assert "sample_events" in detail

    # 4. Non-existent build returns 404
    resp_404 = client.get("/api/v1/jenkins/builds/non-existent-job%23999")
    assert resp_404.status_code == 404

if __name__ == "__main__":
    import inspect
    current_module = sys.modules[__name__]
    all_tests = [
        obj for name, obj in inspect.getmembers(current_module)
        if inspect.isfunction(obj) and name.startswith("test_")
    ]
    print(f"\n{'='*75}\nRUNNING JENKINS INTEGRATION TEST SUITE DIRECTLY\n{'='*75}")
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
    print(f"{'='*75}\nJENKINS SUITE SUMMARY: {passed} PASSED, {failed} FAILED\n{'='*75}\n")
    if failed > 0:
        sys.exit(1)
