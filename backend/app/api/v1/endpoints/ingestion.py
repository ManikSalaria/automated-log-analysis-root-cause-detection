import re
import uuid
import sqlite3
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from app.core.config import settings
from app.core.security import SecretMasker
from app.core.database import get_connection
from app.parsers.regex_parser import LogParserEngine
from app.analysis.root_cause_candidate import RootCauseCandidateAnalyzer
from app.ml.baseline.tfidf_rf import BaselineTfidfRandomForest
from app.schemas.log_schema import IngestionUploadResponse

router = APIRouter()
baseline_model = BaselineTfidfRandomForest()
baseline_model.load()

@router.post("/upload", response_model=IngestionUploadResponse)
async def upload_log_file(
    file: UploadFile = File(...),
    job_name: Optional[str] = Form(None),
    build_number: Optional[str] = Form(None),
    build_status: Optional[str] = Form(None),
    build_url: Optional[str] = Form(None),
    repo_url: Optional[str] = Form(None),
    commit_sha: Optional[str] = Form(None)
):
    """
    Ingest an authentic CI/CD build log or microservice telemetry file (.log / .txt).
    Supports optional Jenkins build metadata (job_name, build_number, build_status,
    build_url, repo_url, commit_sha), computes SHA-256 hash, masks credentials,
    persists events and incident associations to SQLite, and performs baseline ML classification.
    """
    if not file.filename.endswith((".log", ".txt")):
        raise HTTPException(status_code=400, detail="Only .log and .txt files are supported for ingestion.")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    clean_job_name = job_name.strip() if job_name and job_name.strip() else None
    clean_build_number = str(build_number).strip() if build_number and str(build_number).strip() else None
    clean_build_status = build_status.strip() if build_status and build_status.strip() else None
    clean_build_url = build_url.strip() if build_url and build_url.strip() else None
    clean_repo_url = repo_url.strip() if repo_url and repo_url.strip() else None
    clean_commit_sha = commit_sha.strip() if commit_sha and commit_sha.strip() else None

    raw_text = content.decode("utf-8", errors="replace")
    lines = raw_text.splitlines()
    sha256_hash = hashlib.sha256(content).hexdigest()
    ingested_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

    # Determine source type heuristic
    source_type = "JENKINS_BUILD_LOG"
    if any("node-" in l and "trace=" in l for l in lines[:20]):
        source_type = "MICROSERVICES_TELEMETRY"
    elif any("jenkins" in l.lower() or "winstone" in l.lower() for l in lines[:20]):
        source_type = "JENKINS_JVM_CRASH"
    elif any("pytest" in l.lower() or "morpheus" in l.lower() for l in lines[:20]):
        source_type = "JENKINS_PYTEST_QUALIFICATION"

    # Step 1: Parse and structure log events in memory prior to acquiring DB lock
    events_data = []
    parsed_entries = []
    for line_no, raw_line in enumerate(lines, 1):
        if not raw_line.strip():
            parsed_entries.append(None)
            continue
        entry = LogParserEngine.parse_line(raw_line)
        parsed_entries.append(entry)
        # Zero-PII Invariant: secrets are redacted prior to persistent storage.
        # Raw line retention is disabled by default; when disabled, raw_message stores sanitized text.
        persisted_raw = raw_line if settings.ALLOW_RAW_LOG_RETENTION else SecretMasker.sanitize(raw_line, mask_ips=True)
        events_data.append((
            line_no,
            entry.timestamp,
            entry.level,
            entry.service,
            entry.service,
            entry.node,
            entry.trace_id,
            entry.trace_id,
            entry.span_id,
            entry.status_code,
            entry.latency_ms,
            entry.sanitized_message,
            persisted_raw
        ))

    # Step 2: Detect failure blocks and evaluate root-cause candidates in memory
    i = 0
    incidents_data: List[Dict[str, Any]] = []
    while i < len(lines):
        line = lines[i]
        entry = parsed_entries[i] if i < len(parsed_entries) else None
        if LogParserEngine.is_incident_start(line, entry):
            start_line = i + 1
            block = [line]
            j = i + 1
            while j < len(lines):
                next_l = lines[j]
                next_entry = parsed_entries[j] if j < len(parsed_entries) else None
                # If next line is empty or normal INFO/WARNING/DEBUG, the failure block terminates
                if not next_l.strip() or next_l.startswith(("[INFO]", "[WARNING]", "[DEBUG]")):
                    break

                is_continuation = (
                    next_l.startswith(("\t", "   ", "E   ", "Caused by:", "Caused:", "Traceback", "assert ")) or
                    "at " in next_l or next_l.strip().startswith("at ") or
                    next_l.startswith("[ERROR]") or
                    (next_entry and next_entry.level in ("ERROR", "CRITICAL", "SEVERE", "FATAL")) or
                    bool(re.match(r"^(?:java\.[a-zA-Z0-9_\.]+|org\.[a-zA-Z0-9_\.]+|com\.[a-zA-Z0-9_\.]+|[a-zA-Z0-9_\.]+(?:Exception|Error|Failure))", next_l.strip()))
                )
                if not is_continuation:
                    break

                block.append(next_l)
                j += 1

            sanitized_block = SecretMasker.sanitize("\n".join(block), mask_ips=True)
            pred = baseline_model.predict(sanitized_block) if baseline_model.is_trained else {"predicted_category": "UNKNOWN", "confidence": 0.0}
            rca = RootCauseCandidateAnalyzer.analyze(sanitized_block, primary_category=pred["predicted_category"])

            incidents_data.append({
                "start_line": start_line,
                "end_line": j,
                "predicted_category": pred["predicted_category"],
                "confidence": pred["confidence"],
                "root_cause_candidate": rca["root_cause_candidate"],
                "detected_signature": sanitized_block[:150].strip(),
                "evidence_text": sanitized_block
            })
            i = j
        else:
            i += 1

    # Step 3: Atomic database persistence with connection lifecycle guarantees
    conn = get_connection(timeout=30.0)
    try:
        with conn:
            cursor = conn.cursor()

            # Manage source_files record idempotently
            cursor.execute("SELECT id FROM source_files WHERE filename = ?;", (file.filename,))
            existing_row = cursor.fetchone()

            if existing_row:
                file_id = existing_row["id"]
                # Cleanly purge prior parsed events and incidents for this file to ensure zero duplicates
                cursor.execute("DELETE FROM parsed_events WHERE file_id = ?;", (file_id,))
                cursor.execute("DELETE FROM incidents WHERE file_id = ?;", (file_id,))
                cursor.execute("""
                    UPDATE source_files SET
                        source_type = ?, byte_size = ?, line_count = ?, sha256_hash = ?, ingested_at = ?,
                        job_name = ?, build_number = ?, build_status = ?, build_url = ?, repo_url = ?, commit_sha = ?
                    WHERE id = ?;
                """, (
                    source_type, len(content), len(lines), sha256_hash, ingested_at,
                    clean_job_name, clean_build_number, clean_build_status, clean_build_url, clean_repo_url, clean_commit_sha,
                    file_id
                ))
            else:
                cursor.execute("""
                    INSERT INTO source_files (
                        filename, source_type, byte_size, line_count, sha256_hash, ingested_at,
                        job_name, build_number, build_status, build_url, repo_url, commit_sha
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """, (
                    file.filename, source_type, len(content), len(lines), sha256_hash, ingested_at,
                    clean_job_name, clean_build_number, clean_build_status, clean_build_url, clean_repo_url, clean_commit_sha
                ))
                file_id = cursor.lastrowid

            # Insert parsed structured events
            final_events = [
                (file_id, *ev) for ev in events_data
            ]
            cursor.executemany("""
                INSERT INTO parsed_events (
                    file_id, line_number, timestamp, severity, service, component, node,
                    request_id, trace_id, span_id, status_code, latency_ms, sanitized_message, raw_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, final_events)

            # Insert detected incidents
            final_incidents = [
                (
                    f"INC-{file_id:02d}-{inc['start_line']:04d}",
                    file_id,
                    inc["start_line"],
                    inc["end_line"],
                    "ERROR",
                    inc["predicted_category"],
                    inc["confidence"],
                    inc["root_cause_candidate"],
                    inc["detected_signature"],
                    inc["evidence_text"],
                    ingested_at,
                    clean_job_name,
                    clean_build_number
                )
                for inc in incidents_data
            ]
            if final_incidents:
                cursor.executemany("""
                    INSERT INTO incidents (
                        incident_code, file_id, start_line, end_line, primary_severity,
                        failure_category, confidence, root_cause_candidate, detected_signature,
                        evidence_text, created_at, job_name, build_number
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """, final_incidents)

    except sqlite3.OperationalError as oe:
        raise HTTPException(
            status_code=503,
            detail=f"Database is currently locked or busy ({str(oe)}). Transaction rolled back safely; please retry."
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Log ingestion failed: {str(e)}"
        )
    finally:
        conn.close()

    return IngestionUploadResponse(
        file_id=file_id,
        filename=file.filename,
        source_type=source_type,
        byte_size=len(content),
        line_count=len(lines),
        sha256_hash=sha256_hash,
        events_inserted=len(events_data),
        incidents_detected=len(incidents_data),
        ingested_at=ingested_at,
        job_name=clean_job_name,
        build_number=clean_build_number,
        build_status=clean_build_status,
        build_url=clean_build_url,
        repo_url=clean_repo_url,
        commit_sha=clean_commit_sha
    )
