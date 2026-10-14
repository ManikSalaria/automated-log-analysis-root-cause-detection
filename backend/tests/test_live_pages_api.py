import sys
from pathlib import Path
root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(root_dir / "backend"))
sys.path.append(str(root_dir))

import pytest
from fastapi.testclient import TestClient
from main import app
from app.core.database import init_database

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_db():
    init_database()

def test_list_ingested_logs():
    resp = client.get("/api/v1/ingest/logs")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    if len(data) > 0:
        item = data[0]
        assert "id" in item
        assert "filename" in item
        assert "source_type" in item
        assert "origin" in item
        assert item["origin"] in ["JENKINS", "MANUAL"]
        assert "events_count" in item
        assert "incidents_count" in item

def test_log_privacy_audit():
    # Fetch first file
    resp_logs = client.get("/api/v1/ingest/logs?limit=5")
    assert resp_logs.status_code == 200
    logs = resp_logs.json()
    if not logs:
        pytest.skip("No logs in database to test privacy audit")

    file_id = logs[0]["id"]
    resp_priv = client.get(f"/api/v1/ingest/logs/{file_id}/privacy")
    assert resp_priv.status_code == 200
    priv_data = resp_priv.json()
    assert priv_data["file_id"] == file_id
    assert "raw_sample" in priv_data
    assert "sanitized_sample" in priv_data
    assert "leak_count" in priv_data
    assert "security_notice" in priv_data

def test_incidents_with_tracking_fields():
    resp = client.get("/api/v1/incidents?limit=5")
    assert resp.status_code == 200
    incidents = resp.json()
    if len(incidents) > 0:
        inc = incidents[0]
        assert "incident_code" in inc
        assert "source_file" in inc
        assert "file_id" in inc
        assert "failure_category" in inc
        assert "confidence" in inc

def test_events_filtering_by_file_id():
    resp_logs = client.get("/api/v1/ingest/logs?limit=1")
    assert resp_logs.status_code == 200
    logs = resp_logs.json()
    if logs:
        f_id = logs[0]["id"]
        resp_events = client.get(f"/api/v1/events?file_id={f_id}&limit=5")
        assert resp_events.status_code == 200
        ev_data = resp_events.json()
        assert "total" in ev_data
        assert "events" in ev_data
