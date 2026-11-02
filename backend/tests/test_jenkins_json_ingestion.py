import sys
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.database import get_connection  # noqa: E402
from main import app  # noqa: E402


client = TestClient(app)


def test_jenkins_json_ingestion_persists_build_provenance():
    job_name = f"trace-json-{uuid.uuid4().hex[:8]}"
    build_number = "17"
    payload = {
        "job_name": job_name,
        "build_number": build_number,
        "build_status": "FAILURE",
        "build_url": f"http://127.0.0.1:8080/job/{job_name}/{build_number}/",
        "repo_url": "https://github.com/ManikSalaria/automated-log-analysis-root-cause-detection",
        "git_commit": "0123456789abcdef",
        "git_branch": "jenkins-int",
        "console_log": (
            "[INFO] build started\n"
            "[ERROR] java.lang.AssertionError: expected success but received failure\n"
        ),
    }

    response = client.post("/api/v1/ingest/jenkins", json=payload)

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["job_name"] == job_name
    assert result["build_number"] == build_number
    assert result["build_status"] == "FAILURE"
    assert result["commit_sha"] == payload["git_commit"]
    assert result["git_branch"] == "jenkins-int"

    with get_connection() as conn:
        row = conn.execute(
            "SELECT job_name, build_number, build_status, commit_sha, git_branch "
            "FROM source_files WHERE id = ?",
            (result["file_id"],),
        ).fetchone()

    assert row is not None
    assert row["job_name"] == job_name
    assert row["build_number"] == build_number
    assert row["build_status"] == "FAILURE"
    assert row["commit_sha"] == payload["git_commit"]
    assert row["git_branch"] == "jenkins-int"

