import sys
import io
import sqlite3
from pathlib import Path

# Add backend and root to sys.path
root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(root_dir / "backend"))
sys.path.append(str(root_dir))

import pytest
from fastapi.testclient import TestClient
from main import app
from app.core.database import get_connection, migrate_database

client = TestClient(app)

# =========================================================================
# 1. DATABASE MIGRATION & BACKWARD-COMPATIBILITY TEST
# =========================================================================

def test_database_migration_idempotent_and_safe(tmp_path):
    """
    Simulate an older Review-1 database schema without Jenkins metadata columns,
    verify that migrate_database adds the new columns without destroying data,
    and verify that re-running migrate_database is idempotent.
    """
    test_db_path = tmp_path / "legacy_test.db"
    conn = sqlite3.connect(str(test_db_path))
    conn.row_factory = sqlite3.Row

    # Create legacy schema without the metadata columns
    conn.execute("""
    CREATE TABLE source_files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT UNIQUE NOT NULL,
        source_type TEXT NOT NULL,
        byte_size INTEGER NOT NULL,
        line_count INTEGER NOT NULL,
        sha256_hash TEXT NOT NULL,
        ingested_at TEXT NOT NULL
    );
    """)
    conn.execute("""
    CREATE TABLE incidents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        incident_code TEXT UNIQUE NOT NULL,
        file_id INTEGER NOT NULL,
        start_line INTEGER NOT NULL,
        end_line INTEGER NOT NULL,
        primary_severity TEXT NOT NULL,
        failure_category TEXT NOT NULL,
        confidence REAL NOT NULL,
        root_cause_candidate TEXT NOT NULL,
        detected_signature TEXT NOT NULL,
        evidence_text TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (file_id) REFERENCES source_files(id) ON DELETE CASCADE
    );
    """)

    # Insert legacy row
    conn.execute("""
    INSERT INTO source_files (filename, source_type, byte_size, line_count, sha256_hash, ingested_at)
    VALUES ('legacy_file.log', 'JENKINS_BUILD_LOG', 1234, 50, 'hash123', '2026-09-15 12:00:00 UTC');
    """)
    conn.commit()

    # Verify columns before migration
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(source_files);")
    cols_before = [r["name"] for r in cursor.fetchall()]
    assert "job_name" not in cols_before
    assert "build_number" not in cols_before

    # Run migration
    migrate_database(conn)

    # Verify columns after migration
    cursor.execute("PRAGMA table_info(source_files);")
    cols_after = [r["name"] for r in cursor.fetchall()]
    for expected_col in ["job_name", "build_number", "build_status", "build_url", "repo_url", "commit_sha"]:
        assert expected_col in cols_after, f"Missing {expected_col} in source_files"

    cursor.execute("PRAGMA table_info(incidents);")
    inc_cols_after = [r["name"] for r in cursor.fetchall()]
    assert "job_name" in inc_cols_after
    assert "build_number" in inc_cols_after

    # Verify pre-existing data is preserved and new columns are NULL
    cursor.execute("SELECT * FROM source_files WHERE filename = 'legacy_file.log';")
    row = cursor.fetchone()
    assert row["filename"] == "legacy_file.log"
    assert row["byte_size"] == 1234
    assert row["job_name"] is None
    assert row["build_number"] is None

    # Idempotency test: running migration again must not throw
    migrate_database(conn)
    conn.close()

# =========================================================================
# 2. LEGACY FILE-ONLY UPLOAD (BACKWARD COMPATIBILITY)
# =========================================================================

def test_legacy_file_only_upload():
    """
    Verify that an upload request with NO metadata fields (file only)
    succeeds, parses events, and returns None for optional metadata.
    """
    log_content = (
        "2026-10-15 10:00:00 INFO [main] Application starting\n"
        "2026-10-15 10:01:00 ERROR [main] AssertionError: expected 200 but got 500\n"
    )
    file_bytes = io.BytesIO(log_content.encode("utf-8"))
    resp = client.post(
        "/api/v1/ingest/upload",
        files={"file": ("legacy_upload_test.log", file_bytes, "text/plain")}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["filename"] == "legacy_upload_test.log"
    assert data["events_inserted"] == 2
    assert data["incidents_detected"] >= 1
    assert data["job_name"] is None
    assert data["build_number"] is None
    assert data["build_status"] is None

# =========================================================================
# 3. FULL JENKINS METADATA UPLOAD & PERSISTENCE
# =========================================================================

def test_full_jenkins_metadata_upload():
    """
    Verify that an upload with all six Jenkins metadata fields
    persists all fields to source_files and associates them with incidents.
    """
    log_content = (
        "2026-10-15 12:00:00 INFO [builder] Checkout finished\n"
        "2026-10-15 12:02:00 ERROR [test] AssertionError: storage cluster id missing\n"
    )
    file_bytes = io.BytesIO(log_content.encode("utf-8"))
    metadata = {
        "job_name": "jenkins-log-lab",
        "build_number": "42",
        "build_status": "FAILURE",
        "build_url": "http://jenkins-ci.local:8080/job/jenkins-log-lab/42/",
        "repo_url": "https://github.com/tracelab/jenkins-log-lab.git",
        "commit_sha": "d77cb5700e9be7e1d130c8cc64001316f644bc3f"
    }

    resp = client.post(
        "/api/v1/ingest/upload",
        files={"file": ("jenkins-console-42.log", file_bytes, "text/plain")},
        data=metadata
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["filename"] == "jenkins-console-42.log"
    assert data["job_name"] == "jenkins-log-lab"
    assert data["build_number"] == "42"
    assert data["build_status"] == "FAILURE"
    assert data["build_url"] == "http://jenkins-ci.local:8080/job/jenkins-log-lab/42/"
    assert data["repo_url"] == "https://github.com/tracelab/jenkins-log-lab.git"
    assert data["commit_sha"] == "d77cb5700e9be7e1d130c8cc64001316f644bc3f"
    assert data["incidents_detected"] >= 1

    # Verify persistence in SQLite source_files
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM source_files WHERE filename = 'jenkins-console-42.log';")
    sf_row = cursor.fetchone()
    assert sf_row is not None
    assert sf_row["job_name"] == "jenkins-log-lab"
    assert sf_row["build_number"] == "42"
    assert sf_row["build_status"] == "FAILURE"
    assert sf_row["build_url"] == "http://jenkins-ci.local:8080/job/jenkins-log-lab/42/"
    assert sf_row["repo_url"] == "https://github.com/tracelab/jenkins-log-lab.git"
    assert sf_row["commit_sha"] == "d77cb5700e9be7e1d130c8cc64001316f644bc3f"

    # Verify persistence in SQLite incidents table
    cursor.execute("SELECT * FROM incidents WHERE file_id = ?;", (sf_row["id"],))
    inc_rows = cursor.fetchall()
    assert len(inc_rows) >= 1
    for inc in inc_rows:
        assert inc["job_name"] == "jenkins-log-lab"
        assert inc["build_number"] == "42"
    conn.close()

# =========================================================================
# 4. PARTIAL / MISSING OPTIONAL METADATA UPLOAD
# =========================================================================

def test_partial_jenkins_metadata_upload():
    """
    Verify that an upload with only a subset of metadata fields (e.g., job_name and build_number)
    succeeds and stores None for the omitted fields.
    """
    log_content = (
        "2026-10-15 13:00:00 INFO [main] Maven test started\n"
        "2026-10-15 13:01:00 ERROR [main] java.lang.IllegalStateException: Order fulfillment failed\n"
    )
    file_bytes = io.BytesIO(log_content.encode("utf-8"))
    metadata = {
        "job_name": "partial-meta-job",
        "build_number": "99"
    }

    resp = client.post(
        "/api/v1/ingest/upload",
        files={"file": ("partial_meta.log", file_bytes, "text/plain")},
        data=metadata
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["job_name"] == "partial-meta-job"
    assert data["build_number"] == "99"
    assert data["build_status"] is None
    assert data["build_url"] is None
    assert data["repo_url"] is None
    assert data["commit_sha"] is None

# =========================================================================
# 5. INCIDENT API FILTERING BY JOB NAME & BUILD NUMBER
# =========================================================================

def test_incidents_filtering_by_job_and_build():
    """
    Verify that GET /api/v1/incidents supports filtering by job_name and build_number,
    and returns associated CI/CD provenance metadata in the response.
    """
    # Query incidents filtered by the job uploaded in test 3
    resp = client.get("/api/v1/incidents?job_name=jenkins-log-lab&build_number=42")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) >= 1
    for item in items:
        assert item["job_name"] == "jenkins-log-lab"
        assert item["build_number"] == "42"
        assert item["build_status"] == "FAILURE"
        assert "http://jenkins-ci.local" in item["build_url"]
        assert item["commit_sha"] == "d77cb5700e9be7e1d130c8cc64001316f644bc3f"

    # Query single incident by incident_code
    incident_code = items[0]["incident_code"]
    detail_resp = client.get(f"/api/v1/incidents/{incident_code}")
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["incident_code"] == incident_code
    assert detail["job_name"] == "jenkins-log-lab"
    assert detail["build_number"] == "42"
    assert detail["build_status"] == "FAILURE"
    assert detail["commit_sha"] == "d77cb5700e9be7e1d130c8cc64001316f644bc3f"
