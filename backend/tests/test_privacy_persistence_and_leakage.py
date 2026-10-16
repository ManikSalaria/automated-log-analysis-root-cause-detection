"""Regression tests for zero-PII secret masking and persistence safety.

Verifies that credentials, authorization tokens, passwords, and private IPs
are never persisted in unmasked form to SQLite tables (parsed_events, incidents)
or returned in API response bodies.
"""

import io
import sys
import sqlite3
import pytest
from fastapi.testclient import TestClient
from pathlib import Path

# Add backend and root to sys.path
root_dir = Path(__file__).resolve().parent.parent.parent
backend_dir = root_dir / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from main import app
from app.core.security import SecretMasker
from app.core.database import get_connection
from app.core.config import settings

client = TestClient(app)

SAMPLE_DIRTY_LOG = """2026-10-15 14:00:01 [INFO] [auth-service] Starting service with client_id=svc_prod
2026-10-15 14:00:02 [ERROR] [auth-service] Connection to database failed with access_key=AKIAIOSFODNN7EXAMPLE and password="SuperSecretPassword123!"
2026-10-15 14:00:03 [CRITICAL] [auth-service] Failed to fetch credentials from host 10.157.192.247 using token ghp_1234567890abcdefghijklmnopqrstuvwxyz
2026-10-15 14:00:04 [ERROR] [auth-service] Authorization rejected for header: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.c2lnbmF0dXJl
2026-10-15 14:00:05 [ERROR] [auth-service] java.sql.SQLException: Connection refused to 192.168.1.50:5432
\tat com.trace.auth.DbPool.connect(DbPool.java:42)
"""

SECRETS_TO_CHECK = [
    "AKIAIOSFODNN7EXAMPLE",
    "ghp_1234567890abcdefghijklmnopqrstuvwxyz",
    "SuperSecretPassword123!",
    "10.157.192.247",
    "192.168.1.50"
]

def test_secret_masker_covers_all_test_vectors():
    """Verify SecretMasker directly sanitizes all target credential types."""
    sanitized = SecretMasker.sanitize(SAMPLE_DIRTY_LOG, mask_ips=True)
    for secret in SECRETS_TO_CHECK:
        assert secret not in sanitized, f"Secret '{secret}' was not masked by SecretMasker!"
    assert "<REDACTED:AWS_KEY>" in sanitized
    assert "<REDACTED:GITHUB_TOKEN>" in sanitized
    assert "<REDACTED:SECRET>" in sanitized
    assert "<IP>" in sanitized

def test_upload_does_not_persist_raw_secrets_to_database():
    """Verify that file upload persists only sanitized data to SQLite."""
    file_bytes = SAMPLE_DIRTY_LOG.encode("utf-8")
    resp = client.post(
        "/api/v1/ingest/upload",
        files={"file": ("dirty_test_log.txt", io.BytesIO(file_bytes), "text/plain")}
    )
    assert resp.status_code == 200, resp.text
    file_id = resp.json()["file_id"]

    conn = get_connection()
    c = conn.cursor()

    # 1. Check parsed_events
    c.execute("SELECT raw_message, sanitized_message FROM parsed_events WHERE file_id = ?", (file_id,))
    rows = c.fetchall()
    assert len(rows) > 0

    for row in rows:
        raw_msg = row["raw_message"]
        san_msg = row["sanitized_message"]
        for secret in SECRETS_TO_CHECK:
            assert secret not in raw_msg, f"Secret '{secret}' leaked into parsed_events.raw_message!"
            assert secret not in san_msg, f"Secret '{secret}' leaked into parsed_events.sanitized_message!"

    # 2. Check incidents
    c.execute("SELECT detected_signature, evidence_text FROM incidents WHERE file_id = ?", (file_id,))
    inc_rows = c.fetchall()
    for inc in inc_rows:
        sig = inc["detected_signature"] or ""
        evidence = inc["evidence_text"] or ""
        for secret in SECRETS_TO_CHECK:
            assert secret not in sig, f"Secret '{secret}' leaked into incidents.detected_signature!"
            assert secret not in evidence, f"Secret '{secret}' leaked into incidents.evidence_text!"

    conn.close()

def test_analyze_endpoint_does_not_leak_raw_secrets_in_response():
    """Verify that /api/v1/analysis/analyze does not echo unmasked secrets."""
    resp = client.post(
        "/api/v1/analysis/analyze",
        json={"log_text": SAMPLE_DIRTY_LOG, "model": "baseline"}
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    resp_str = str(data)
    for secret in SECRETS_TO_CHECK:
        assert secret not in resp_str, f"Secret '{secret}' leaked into /analyze response payload!"
    assert data["privacy_audit"]["clean"] is False
    assert data["privacy_audit"]["leak_count"] > 0
