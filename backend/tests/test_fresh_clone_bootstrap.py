"""Regression tests for fresh-clone environment bootstrap and demo log seeding.

Validates that:
1. Bootstrapping on a fresh empty SQLite database initializes schema and seeds
   authentic incident records from the tracked sanitized demo log.
2. GET /api/v1/incidents?limit=15 returns those seeded records.
3. Running bootstrap twice is strictly idempotent (zero duplicates).
4. System health returns exact real database counts instead of hardcoded fallbacks.
5. Seeded incidents can be selected and synthesized in Stage 5 analysis.
All tests use an isolated temporary database without modifying trace_review1.db.
"""

import sys
import sqlite3
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

root_dir = Path(__file__).resolve().parent.parent.parent
backend_dir = root_dir / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from app.core.database import init_database, get_connection
from scripts.bootstrap_models import seed_demo_database
from main import app


@pytest.fixture
def bootstrap_temp_db(tmp_path, monkeypatch):
    """Provides a cleanly bootstrapped temporary SQLite database."""
    test_db = tmp_path / "fresh_clone_test.db"
    monkeypatch.setenv("TRACE_SQLITE_DB_PATH", str(test_db))

    init_database(test_db)
    seed_demo_database(test_db)
    return test_db


def test_fresh_clone_seeding_creates_incidents_and_is_idempotent(tmp_path, monkeypatch):
    """Verify bootstrap creates actual incident records and running twice does not duplicate."""
    test_db = tmp_path / "idempotent_test.db"
    monkeypatch.setenv("TRACE_SQLITE_DB_PATH", str(test_db))

    # 1. Initialize empty database
    init_database(test_db)
    conn = sqlite3.connect(str(test_db))
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM source_files;")
    assert c.fetchone()[0] == 0
    c.execute("SELECT COUNT(*) FROM incidents;")
    assert c.fetchone()[0] == 0
    conn.close()

    # 2. First bootstrap run
    seed_demo_database(test_db)

    conn = sqlite3.connect(str(test_db))
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM source_files;")
    files_run1 = c.fetchone()[0]
    assert files_run1 > 0, "source_files should contain seeded demo files"

    c.execute("SELECT COUNT(*) FROM parsed_events;")
    events_run1 = c.fetchone()[0]
    assert events_run1 > 0, "parsed_events should contain parsed lines"

    c.execute("SELECT COUNT(*) FROM incidents;")
    incidents_run1 = c.fetchone()[0]
    assert incidents_run1 > 0, "incidents table should contain detected failure incidents from demo log"

    # Verify specific demo log incident attributes
    c.execute("""
        SELECT i.incident_code, f.filename, i.start_line, i.end_line, i.failure_category, i.root_cause_candidate
        FROM incidents i
        JOIN source_files f ON i.file_id = f.id
        WHERE f.filename = 'demo_jenkins_build.log';
    """)
    demo_incidents = c.fetchall()
    assert len(demo_incidents) >= 3, "demo_jenkins_build.log should produce at least 3 failure episodes"
    conn.close()

    # 3. Second bootstrap run (must be strictly idempotent)
    seed_demo_database(test_db)

    conn = sqlite3.connect(str(test_db))
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM source_files;")
    assert c.fetchone()[0] == files_run1, "File count must not change on duplicate bootstrap"

    c.execute("SELECT COUNT(*) FROM parsed_events;")
    assert c.fetchone()[0] == events_run1, "Event count must not change on duplicate bootstrap"

    c.execute("SELECT COUNT(*) FROM incidents;")
    assert c.fetchone()[0] == incidents_run1, "Incident count must not change on duplicate bootstrap"
    conn.close()


def test_api_incidents_endpoint_returns_seeded_records(bootstrap_temp_db):
    """Verify GET /api/v1/incidents?limit=15 returns the seeded demo incidents."""
    client = TestClient(app)
    resp = client.get("/api/v1/incidents?limit=15")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) > 0, "GET /api/v1/incidents should return seeded records"

    first = data[0]
    assert "incident_code" in first
    assert first["incident_code"].startswith("INC-")
    assert first["source_file"] in ("demo_jenkins_build.log", "jenkins_gist_crash.log")
    assert first["failure_category"] is not None
    assert first["root_cause_candidate"] is not None


def test_health_endpoint_reports_live_database_counts(bootstrap_temp_db):
    """Verify /api/v1/health returns actual database counts instead of hardcoded fallbacks."""
    client = TestClient(app)
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    health = resp.json()
    db_stats = health.get("database", {})

    assert db_stats.get("connected") is True
    assert db_stats.get("incidents_count") > 0
    assert db_stats.get("parsed_events_count") > 0
    assert db_stats.get("source_files_count") > 0

    # Verify counts match SQLite directly
    conn = sqlite3.connect(str(bootstrap_temp_db))
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM incidents;")
    actual_inc = c.fetchone()[0]
    conn.close()

    assert db_stats["incidents_count"] == actual_inc


def test_root_cause_report_synthesizes_seeded_incident(bootstrap_temp_db):
    """Verify Stage 5 synthesis endpoint can select and synthesize a seeded SQLite incident."""
    client = TestClient(app)
    incidents_resp = client.get("/api/v1/incidents?limit=15")
    assert incidents_resp.status_code == 200
    items = incidents_resp.json()
    assert len(items) > 0

    selected_code = items[0]["incident_code"]
    payload = {
        "incident_code": selected_code,
        "classifier_model": "baseline",
        "retrieval_top_k": 2,
        "provider_override": "mock"
    }

    synth_resp = client.post("/api/v1/analysis/synthesize", json=payload)
    assert synth_resp.status_code == 200, f"Synthesis failed: {synth_resp.text}"
    report_data = synth_resp.json()

    assert report_data["status"] == "success"
    assert report_data["provider"] == "mock"
    assert "report" in report_data and report_data["report"] is not None
    rep = report_data["report"]
    assert rep["predicted_failure_category"] is not None
    assert len(rep["likely_root_causes"]) > 0

    # Current incident evidence should match the selected incident code
    current_evidence = [e for e in rep["evidence"] if e["source_type"] == "CURRENT_INCIDENT"]
    assert len(current_evidence) == 1
    assert current_evidence[0]["incident_code"] == selected_code
