import io
import sys
from pathlib import Path

# Add backend and root to sys.path
root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(root_dir / "backend"))
sys.path.append(str(root_dir))

import pytest
from fastapi.testclient import TestClient
from main import app
from app.core.database import get_connection
from app.parsers.regex_parser import LogParserEngine

client = TestClient(app)

# =========================================================================
# 1. PARSER ENGINE UNIT TESTS FOR MAVEN AND CONTEXT-AWARE SEVERITY
# =========================================================================

def test_maven_runner_line_is_info_not_error():
    """
    Ordinary Maven test execution lines must not be classified as ERROR
    merely because the class name contains 'Exception' or 'Failure'.
    """
    line1 = "[INFO] Running com.tracelab.jenkinsloglab.ExceptionFailureScenarioTest"
    entry1 = LogParserEngine.parse_line(line1)
    assert entry1.level == "INFO"
    assert entry1.service == "com.tracelab.jenkinsloglab.ExceptionFailureScenarioTest"
    assert not LogParserEngine.is_incident_start(line1, entry1)

    line2 = "Running com.tracelab.jenkinsloglab.ExceptionFailureScenarioTest"
    entry2 = LogParserEngine.parse_line(line2)
    assert entry2.level == "INFO"
    assert not LogParserEngine.is_incident_start(line2, entry2)

    line3 = "[INFO] Running com.tracelab.jenkinsloglab.AssertionFailureScenarioTest"
    entry3 = LogParserEngine.parse_line(line3)
    assert entry3.level == "INFO"
    assert not LogParserEngine.is_incident_start(line3, entry3)


def test_skipped_test_summary_is_warn_not_error():
    """
    Test summaries with 0 failures and 0 errors, even with skipped tests,
    must have severity WARN/INFO and must NEVER trigger an ERROR incident.
    """
    line = "[WARNING] Tests run: 1, Failures: 0, Errors: 0, Skipped: 1, Time elapsed: 0.045 s"
    entry = LogParserEngine.parse_line(line)
    assert entry.level == "WARN"
    assert not LogParserEngine.is_incident_start(line, entry)

    unprefixed = "Tests run: 3, Failures: 0, Errors: 0, Skipped: 1"
    entry_un = LogParserEngine.parse_line(unprefixed)
    assert entry_un.level == "WARN"
    assert not LogParserEngine.is_incident_start(unprefixed, entry_un)


def test_actual_test_failures_classified_as_error():
    """
    Maven test summaries with Failures > 0 or Errors > 0 must be ERROR
    and must qualify as incident starts.
    """
    line = "[ERROR] Tests run: 2, Failures: 1, Errors: 0, Skipped: 0 <<< FAILURE!"
    entry = LogParserEngine.parse_line(line)
    assert entry.level == "ERROR"
    assert LogParserEngine.is_incident_start(line, entry)

    line_err = "Tests run: 5, Failures: 0, Errors: 2, Skipped: 0"
    entry_err = LogParserEngine.parse_line(line_err)
    assert entry_err.level == "ERROR"
    assert LogParserEngine.is_incident_start(line_err, entry_err)


# =========================================================================
# 2. END-TO-END INGESTION TESTS: SUCCESSFUL BUILDS VS FAILURES
# =========================================================================

def test_successful_maven_build_generates_zero_incidents():
    """
    A successful Maven build log containing skipped tests and test classes
    with 'Exception' or 'Failure' in their names must generate 0 incidents.
    """
    log_content = (
        "[INFO] Scanning for projects...\n"
        "[INFO] ----------------< com.tracelab:jenkins-log-lab >----------------\n"
        "[INFO] Building jenkins-log-lab 0.0.1-SNAPSHOT\n"
        "[INFO] --------------------------------[ jar ]---------------------------------\n"
        "[INFO] --- maven-surefire-plugin:3.2.5:test (default-test) @ jenkins-log-lab ---\n"
        "[INFO] Running com.tracelab.jenkinsloglab.ExceptionFailureScenarioTest\n"
        "[WARNING] Tests run: 1, Failures: 0, Errors: 0, Skipped: 1, Time elapsed: 0.045 s - in com.tracelab.jenkinsloglab.ExceptionFailureScenarioTest\n"
        "[INFO] Running com.tracelab.jenkinsloglab.AssertionFailureScenarioTest\n"
        "[WARNING] Tests run: 1, Failures: 0, Errors: 0, Skipped: 1, Time elapsed: 0.038 s - in com.tracelab.jenkinsloglab.AssertionFailureScenarioTest\n"
        "[INFO] Running com.tracelab.jenkinsloglab.JenkinsLogLabApplicationTests\n"
        "[INFO] Tests run: 1, Failures: 0, Errors: 0, Skipped: 0, Time elapsed: 1.234 s - in com.tracelab.jenkinsloglab.JenkinsLogLabApplicationTests\n"
        "[INFO] Results:\n"
        "[INFO] \n"
        "[WARNING] Tests run: 3, Failures: 0, Errors: 0, Skipped: 2\n"
        "[INFO] \n"
        "[INFO] ------------------------------------------------------------------------\n"
        "[INFO] BUILD SUCCESS\n"
        "[INFO] ------------------------------------------------------------------------\n"
        "[INFO] Total time:  3.456 s\n"
        "[INFO] Finished at: 2026-10-15T12:00:00Z\n"
        "[INFO] ------------------------------------------------------------------------\n"
    )

    file_bytes = io.BytesIO(log_content.encode("utf-8"))
    resp = client.post(
        "/api/v1/ingest/upload",
        files={"file": ("successful_maven_build.log", file_bytes, "text/plain")},
        data={"job_name": "maven-success-job", "build_number": "101", "build_status": "SUCCESS"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["filename"] == "successful_maven_build.log"
    assert data["events_inserted"] > 0
    # Crucial assertion: exactly ZERO false-positive incidents generated
    assert data["incidents_detected"] == 0

    # Verify no incidents persisted in DB for this file
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM incidents WHERE file_id = ?;", (data["file_id"],))
    count = cursor.fetchone()[0]
    conn.close()
    assert count == 0


def test_actual_assertion_failure_extracted_as_incident():
    """
    Verify that an authentic Surefire assertion failure is correctly
    detected, grouped into an incident, and stored with primary_severity ERROR.
    """
    log_content = (
        "[INFO] Running com.tracelab.jenkinsloglab.AssertionFailureScenarioTest\n"
        "[ERROR] Tests run: 1, Failures: 1, Errors: 0, Skipped: 0, Time elapsed: 0.05 s <<< FAILURE! - in com.tracelab.jenkinsloglab.AssertionFailureScenarioTest\n"
        "[ERROR] com.tracelab.jenkinsloglab.AssertionFailureScenarioTest.testStorageClusterMissing -- Time elapsed: 0.021 s <<< FAILURE!\n"
        "org.opentest4j.AssertionFailedError: storage cluster id missing expected: <storage-cluster-east-1> but was: <>\n"
        "\tat org.junit.jupiter.api.AssertionFailureBuilder.build(AssertionFailureBuilder.java:151)\n"
        "\tat com.tracelab.jenkinsloglab.AssertionFailureScenarioTest.testStorageClusterMissing(AssertionFailureScenarioTest.java:42)\n"
        "[INFO] \n"
        "[INFO] Results:\n"
        "[INFO] \n"
        "[ERROR] Failures: \n"
        "[ERROR]   AssertionFailureScenarioTest.testStorageClusterMissing:42 storage cluster id missing expected: <storage-cluster-east-1> but was: <>\n"
        "[INFO] \n"
        "[ERROR] Tests run: 1, Failures: 1, Errors: 0, Skipped: 0\n"
        "[INFO] \n"
        "[INFO] ------------------------------------------------------------------------\n"
        "[INFO] BUILD FAILURE\n"
        "[INFO] ------------------------------------------------------------------------\n"
    )

    file_bytes = io.BytesIO(log_content.encode("utf-8"))
    resp = client.post(
        "/api/v1/ingest/upload",
        files={"file": ("assertion_failure_maven.log", file_bytes, "text/plain")},
        data={"job_name": "maven-fail-assertion", "build_number": "102", "build_status": "FAILURE"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["incidents_detected"] >= 1

    # Verify incident details in database
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM incidents WHERE file_id = ?;", (data["file_id"],))
    rows = cursor.fetchall()
    conn.close()
    assert len(rows) >= 1
    inc = rows[0]
    assert inc["primary_severity"] == "ERROR"
    assert "storage cluster id missing" in inc["evidence_text"]


def test_genuine_error_not_suppressed_by_build_success():
    """
    Context-aware severity must not suppress genuine error records
    or stack traces just because the overall build ends with BUILD SUCCESS.
    """
    log_content = (
        "[INFO] Running com.tracelab.jenkinsloglab.TaskControllerTest\n"
        "2026-10-15 12:00:00 ERROR [task-service] java.lang.NullPointerException: unhandled null pointer during transaction\n"
        "\tat com.tracelab.jenkinsloglab.TaskController.handle(TaskController.java:30)\n"
        "[INFO] Tests run: 1, Failures: 0, Errors: 0, Skipped: 0\n"
        "[INFO] BUILD SUCCESS\n"
    )

    file_bytes = io.BytesIO(log_content.encode("utf-8"))
    resp = client.post(
        "/api/v1/ingest/upload",
        files={"file": ("error_with_build_success.log", file_bytes, "text/plain")}
    )
    assert resp.status_code == 200
    data = resp.json()
    # The genuine error must NOT be suppressed
    assert data["incidents_detected"] >= 1


# =========================================================================
# 3. GET /api/v1/events ORDERING & FILE FILTER TESTS
# =========================================================================

def test_get_events_defaults_to_descending_newest_logs():
    """
    Verify that GET /api/v1/events orders by descending ID by default,
    ensuring that newly ingested log entries appear first rather than being
    hidden behind the earliest legacy entries.
    """
    unique_tag = "UNIQUE_PROBE_MARKER_98765"
    log_content = (
        f"[INFO] Initializing worker for {unique_tag}\n"
        f"[INFO] Worker completed task for {unique_tag}\n"
    )

    file_bytes = io.BytesIO(log_content.encode("utf-8"))
    upload_resp = client.post(
        "/api/v1/ingest/upload",
        files={"file": ("jenkins-console-3.log", file_bytes, "text/plain")},
        data={"job_name": "test-events-job", "build_number": "3"}
    )
    assert upload_resp.status_code == 200
    file_id = upload_resp.json()["file_id"]

    # Query GET /api/v1/events with default parameters (limit=10)
    resp = client.get("/api/v1/events?limit=10")
    assert resp.status_code == 200
    body = resp.json()
    events = body["events"]
    assert len(events) > 0

    # The very first returned event must be from the newest ingested log (jenkins-console-3.log)
    latest_event = events[0]
    assert latest_event["source_file"] == "jenkins-console-3.log"
    assert unique_tag in latest_event["sanitized_message"]

    # Verify descending ordering: event IDs must be strictly monotonically decreasing
    ids = [e["id"] for e in events]
    assert ids == sorted(ids, reverse=True)

    # Verify file filter source_file
    filtered_resp = client.get("/api/v1/events?source_file=jenkins-console-3.log")
    assert filtered_resp.status_code == 200
    filtered_body = filtered_resp.json()
    for e in filtered_body["events"]:
        assert e["source_file"] == "jenkins-console-3.log"

    # Verify file_id filter
    file_id_resp = client.get(f"/api/v1/events?file_id={file_id}")
    assert file_id_resp.status_code == 200
    file_id_body = file_id_resp.json()
    assert len(file_id_body["events"]) == 2

    # Verify explicit ascending order support
    asc_resp = client.get("/api/v1/events?order=asc&limit=5")
    assert asc_resp.status_code == 200
    asc_events = asc_resp.json()["events"]
    asc_ids = [e["id"] for e in asc_events]
    assert asc_ids == sorted(asc_ids)
