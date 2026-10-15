"""Verification script for live Jenkins log upload and CI/CD metadata persistence.

Starts an end-to-end verification against the running FastAPI backend,
sends a multipart/form-data upload with all 6 Jenkins metadata fields,
and verifies persistence in both the SQLite database and the REST API.
"""

import sys
import sqlite3
from pathlib import Path
import requests

# Add backend directory
root_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(root_dir / "backend"))

from app.core.config import settings

BASE_URL = "http://127.0.0.1:8000"

def run_live_verification():
    print("=" * 80)
    print("PHASE 1: LIVE JENKINS UPLOAD VERIFICATION")
    print("=" * 80)

    # 1. Health check
    health_resp = requests.get(f"{BASE_URL}/api/v1/health")
    assert health_resp.status_code == 200, f"Health check failed: {health_resp.text}"
    print(f"[1] Health Check: {health_resp.json()['status']}")

    # 2. Authentic Jenkins log content representing a live Surefire failure
    log_content = (
        "[INFO] -------------------------------------------------------\n"
        "[INFO]  T E S T S\n"
        "[INFO] -------------------------------------------------------\n"
        "[INFO] Running com.tracelab.jenkinsloglab.scenarios.AssertionFailureScenarioTest\n"
        "[ERROR] Tests run: 1, Failures: 1, Errors: 0, Skipped: 0, Time elapsed: 0.045 s <<< FAILURE!\n"
        "AssertionError: storage cluster id missing expected: <storage-cluster-east-1> but was: <>\n"
        "\tat org.junit.jupiter.api.AssertionUtils.fail(AssertionUtils.java:55)\n"
        "\tat org.junit.jupiter.api.AssertEquals.assertEquals(AssertEquals.java:182)\n"
        "\tat com.tracelab.jenkinsloglab.scenarios.AssertionFailureScenarioTest.storageClusterIdMustBePresent(AssertionFailureScenarioTest.java:18)\n"
        "[INFO] BUILD FAILURE\n"
    )

    metadata = {
        "job_name": "jenkins-log-lab-live",
        "build_number": "77",
        "build_status": "FAILURE",
        "build_url": "http://jenkins-ci.local:8080/job/jenkins-log-lab-live/77/",
        "repo_url": "https://github.com/tracelab/jenkins-log-lab.git",
        "commit_sha": "5900f15290d4810b247f7fd486739c9963a9d1ba"
    }

    files = {
        "file": ("jenkins-console-77.log", log_content.encode("utf-8"), "text/plain")
    }

    # 3. Post multipart payload to /api/v1/ingest/upload
    print("\n[2] Sending multipart POST /api/v1/ingest/upload with 6 metadata fields...")
    upload_resp = requests.post(f"{BASE_URL}/api/v1/ingest/upload", files=files, data=metadata)
    assert upload_resp.status_code == 200, f"Upload failed: {upload_resp.text}"
    upload_data = upload_resp.json()
    print("Response JSON:")
    for k, v in upload_data.items():
        print(f"  {k}: {v}")

    assert upload_data["filename"] == "jenkins-console-77.log"
    assert upload_data["job_name"] == "jenkins-log-lab-live"
    assert upload_data["build_number"] == "77"
    assert upload_data["build_status"] == "FAILURE"
    assert upload_data["build_url"] == "http://jenkins-ci.local:8080/job/jenkins-log-lab-live/77/"
    assert upload_data["repo_url"] == "https://github.com/tracelab/jenkins-log-lab.git"
    assert upload_data["commit_sha"] == "5900f15290d4810b247f7fd486739c9963a9d1ba"
    assert upload_data["incidents_detected"] >= 1

    # 4. Query SQLite database directly
    print("\n[3] Verifying SQLite persistence in trace_review1.db...")
    conn = sqlite3.connect(str(settings.DATA_DIR / "trace_review1.db"))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM source_files WHERE filename = 'jenkins-console-77.log';")
    sf_row = cursor.fetchone()
    assert sf_row is not None, "source_files row not found!"
    print(f"  source_files ID: {sf_row['id']}")
    print(f"  job_name: {sf_row['job_name']}")
    print(f"  build_number: {sf_row['build_number']}")
    print(f"  build_status: {sf_row['build_status']}")
    print(f"  commit_sha: {sf_row['commit_sha']}")

    cursor.execute("SELECT * FROM incidents WHERE file_id = ?;", (sf_row["id"],))
    inc_rows = cursor.fetchall()
    assert len(inc_rows) >= 1, "No incidents created for file!"
    for r in inc_rows:
        print(f"  Incident {r['incident_code']}: {r['failure_category']} ({r['confidence']*100:.1f}%) | Job={r['job_name']} Build={r['build_number']}")
        assert r["job_name"] == "jenkins-log-lab-live"
        assert r["build_number"] == "77"
    conn.close()

    # 5. Query REST API /api/v1/incidents
    print("\n[4] Verifying REST API GET /api/v1/incidents with query filters...")
    api_resp = requests.get(f"{BASE_URL}/api/v1/incidents?job_name=jenkins-log-lab-live&build_number=77")
    assert api_resp.status_code == 200, f"Incidents API failed: {api_resp.text}"
    incidents_list = api_resp.json()
    assert len(incidents_list) >= 1, "API returned 0 incidents for filter!"
    first_inc = incidents_list[0]
    print(f"  API Incident: {first_inc['incident_code']}")
    print(f"  Category: {first_inc['failure_category']}")
    print(f"  Root Cause: {first_inc['root_cause_candidate']}")
    print(f"  CI/CD: {first_inc['job_name']} #{first_inc['build_number']} ({first_inc['build_status']})")
    print(f"  Commit: {first_inc['commit_sha']}")
    print(f"  Build URL: {first_inc['build_url']}")

    # 6. Query Incident detail endpoint
    print(f"\n[5] Verifying incident detail endpoint /api/v1/incidents/{first_inc['incident_code']}...")
    detail_resp = requests.get(f"{BASE_URL}/api/v1/incidents/{first_inc['incident_code']}")
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["job_name"] == "jenkins-log-lab-live"
    assert detail["build_number"] == "77"
    assert detail["commit_sha"] == "5900f15290d4810b247f7fd486739c9963a9d1ba"
    print("  Detail verified successfully.")

    print("\n" + "=" * 80)
    print("ALL VERIFICATIONS PASSED: Jenkins-to-ML integration contract verified live!")
    print("=" * 80)

if __name__ == "__main__":
    run_live_verification()
