import hashlib
import secrets
from datetime import datetime
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Header, UploadFile, File, Form, Request, Query
from pydantic import BaseModel

from app.core.config import settings
from app.core.database import get_connection
from app.core.security import SecretMasker
from app.parsers.regex_parser import LogParserEngine
from app.analysis.root_cause_candidate import RootCauseCandidateAnalyzer
from app.ml.baseline.tfidf_rf import BaselineTfidfRandomForest
from app.schemas.log_schema import (
    JenkinsTokenCreate,
    JenkinsTokenCreatedResponse,
    JenkinsTokenItem,
    JenkinsBuildIngestRequest,
    JenkinsBuildIngestResponse,
    JenkinsBuildSummaryItem,
    JenkinsBuildDetailResponse
)

router = APIRouter()
baseline_model = BaselineTfidfRandomForest()
baseline_model.load()

MAX_LOG_SIZE_BYTES = 20 * 1024 * 1024  # 20 MB limit

def hash_token(raw_token: str) -> str:
    """Secure SHA-256 hash for integration token comparison."""
    return hashlib.sha256(raw_token.strip().encode("utf-8")).hexdigest()

def verify_jenkins_token(
    authorization: Optional[str] = Header(None),
    x_trace_api_key: Optional[str] = Header(None)
) -> Dict[str, Any]:
    """
    Authenticate incoming Jenkins requests via high-entropy API token.
    Accepts token via 'Authorization: Bearer <token>' or 'X-TRACE-API-KEY: <token>'.
    Plaintext tokens are never stored; verification checks against SHA-256 hash.
    """
    token_str = None
    if authorization and authorization.lower().startswith("bearer "):
        token_str = authorization[7:].strip()
    elif x_trace_api_key:
        token_str = x_trace_api_key.strip()

    if not token_str:
        raise HTTPException(
            status_code=401,
            detail="Authentication token required. Provide 'Authorization: Bearer <token>' or 'X-TRACE-API-KEY' header."
        )

    t_hash = hash_token(token_str)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, name, is_active FROM jenkins_tokens WHERE token_hash = ?;
    """, (t_hash,))
    row = cursor.fetchone()

    if not row or row["is_active"] != 1:
        conn.close()
        raise HTTPException(
            status_code=401,
            detail="Invalid, expired, or revoked Jenkins integration token."
        )

    # Update last_used_at timestamp
    now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    cursor.execute("UPDATE jenkins_tokens SET last_used_at = ? WHERE id = ?;", (now_str, row["id"]))
    conn.commit()
    conn.close()

    return {"token_id": row["id"], "token_name": row["name"]}

# =========================================================================
# 1. TOKEN MANAGEMENT ENDPOINTS
# =========================================================================

@router.post("/tokens", response_model=JenkinsTokenCreatedResponse)
def create_jenkins_token(payload: JenkinsTokenCreate):
    """
    Generate a high-entropy API token for connecting a Jenkins instance to TRACE.
    Stores only the SHA-256 hash in SQLite. The plaintext token is returned ONLY once.
    """
    raw_token = f"trc_{secrets.token_urlsafe(32)}"
    t_hash = hash_token(raw_token)
    t_preview = f"{raw_token[:7]}...{raw_token[-4:]}"
    created_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO jenkins_tokens (token_hash, name, token_preview, created_at, is_active)
        VALUES (?, ?, ?, ?, 1);
    """, (t_hash, payload.name.strip(), t_preview, created_at))
    token_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return JenkinsTokenCreatedResponse(
        id=token_id,
        name=payload.name.strip(),
        token=raw_token,
        token_preview=t_preview,
        created_at=created_at,
        message="Store this token securely in Jenkins Credentials. It will not be shown again."
    )

@router.get("/tokens", response_model=List[JenkinsTokenItem])
def list_jenkins_tokens():
    """
    List all generated Jenkins integration tokens (active and revoked).
    Plaintext secrets are never returned.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, name, token_preview, created_at, last_used_at, is_active, revoked_at
        FROM jenkins_tokens
        ORDER BY id DESC;
    """)
    rows = cursor.fetchall()
    conn.close()

    return [
        JenkinsTokenItem(
            id=r["id"],
            name=r["name"],
            token_preview=r["token_preview"],
            created_at=r["created_at"],
            last_used_at=r["last_used_at"],
            is_active=bool(r["is_active"]),
            revoked_at=r["revoked_at"]
        )
        for r in rows
    ]

@router.post("/tokens/{token_id}/revoke")
@router.delete("/tokens/{token_id}")
def revoke_jenkins_token(token_id: int):
    """
    Revoke a Jenkins integration token. Revoked tokens immediately reject further requests.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, is_active FROM jenkins_tokens WHERE id = ?;", (token_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Token with ID {token_id} not found.")

    revoked_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    cursor.execute("UPDATE jenkins_tokens SET is_active = 0, revoked_at = ? WHERE id = ?;", (revoked_at, token_id))
    conn.commit()
    conn.close()

    return {"status": "REVOKED", "token_id": token_id, "revoked_at": revoked_at}

# =========================================================================
# 2. TEST CONNECTION ENDPOINT
# =========================================================================

@router.post("/test-connection")
def test_jenkins_connection(token_info: Dict[str, Any] = Depends(verify_jenkins_token)):
    """
    Validates token authentication and confirms backend connectivity from Jenkins.
    """
    return {
        "status": "CONNECTED",
        "integration_id": token_info["token_id"],
        "integration_name": token_info["token_name"],
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
        "message": f"Successfully authenticated as '{token_info['token_name']}'."
    }

# =========================================================================
# 3. AUTHENTICATED JENKINS BUILD INGESTION
# =========================================================================

@router.post("/ingest", response_model=JenkinsBuildIngestResponse)
async def ingest_jenkins_build(
    request: Request,
    token_info: Dict[str, Any] = Depends(verify_jenkins_token),
    # Support multipart form fields if uploaded as form
    file: Optional[UploadFile] = File(None),
    job_name: Optional[str] = Form(None),
    build_number: Optional[str] = Form(None),
    build_url: Optional[str] = Form(None),
    repo_url: Optional[str] = Form(None),
    commit_sha: Optional[str] = Form(None),
    build_status: Optional[str] = Form(None),
    log_text: Optional[str] = Form(None)
):
    """
    Authenticated ingestion endpoint for Jenkins build console output.
    Supports either JSON payload or multipart/form-data upload.
    Sanitizes credentials, normalizes events, detects failures, and classifies with ML baseline.
    Idempotent: Identical retried uploads update or return the existing analysis without duplication.
    """
    content_type = request.headers.get("content-type", "")

    # Extract parameters from JSON if Content-Type is application/json
    if "application/json" in content_type:
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON payload.")
        job_name = body.get("job_name")
        build_number = str(body.get("build_number", ""))
        build_url = body.get("build_url")
        repo_url = body.get("repo_url")
        commit_sha = body.get("commit_sha")
        build_status = body.get("build_status", "UNKNOWN")
        raw_log_content = body.get("log_text", "")
    else:
        # Multipart form data
        if file:
            file_bytes = await file.read()
            if len(file_bytes) > MAX_LOG_SIZE_BYTES:
                raise HTTPException(status_code=413, detail=f"Log file exceeds maximum allowed size ({MAX_LOG_SIZE_BYTES // (1024*1024)} MB).")
            raw_log_content = file_bytes.decode("utf-8", errors="replace")
        elif log_text:
            raw_log_content = log_text
        else:
            raw_log_content = ""

    # Validations
    if not job_name or not str(job_name).strip():
        raise HTTPException(status_code=400, detail="Missing required field 'job_name'.")
    if not build_number or not str(build_number).strip():
        raise HTTPException(status_code=400, detail="Missing required field 'build_number'.")
    
    clean_job = str(job_name).strip()
    clean_build = str(build_number).strip()
    build_id = f"{clean_job}#{clean_build}"

    if not raw_log_content or not raw_log_content.strip():
        raise HTTPException(status_code=400, detail="Console log text cannot be empty.")
    
    log_bytes = raw_log_content.encode("utf-8")
    if len(log_bytes) > MAX_LOG_SIZE_BYTES:
        raise HTTPException(status_code=413, detail=f"Log payload exceeds maximum allowed size ({MAX_LOG_SIZE_BYTES // (1024*1024)} MB).")

    lines = raw_log_content.splitlines()
    sha256_hash = hashlib.sha256(log_bytes).hexdigest()
    ingested_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

    conn = get_connection()
    cursor = conn.cursor()

    # Check for existing build (idempotency check)
    cursor.execute("""
        SELECT b.id, b.build_id, b.file_id, b.build_status, b.is_failure, 
               b.primary_failure_category, b.confidence, b.root_cause_candidate,
               b.events_count, b.incidents_count, f.sha256_hash
        FROM jenkins_builds b
        JOIN source_files f ON b.file_id = f.id
        WHERE b.build_id = ?;
    """, (build_id,))
    existing_build = cursor.fetchone()

    # If already ingested with identical content hash, return existing analysis (idempotent)
    if existing_build and existing_build["sha256_hash"] == sha256_hash:
        conn.close()
        return JenkinsBuildIngestResponse(
            build_id=existing_build["build_id"],
            job_name=clean_job,
            build_number=clean_build,
            build_status=existing_build["build_status"] or "UNKNOWN",
            is_failure=bool(existing_build["is_failure"]),
            failure_category=existing_build["primary_failure_category"],
            confidence=existing_build["confidence"],
            root_cause_candidate=existing_build["root_cause_candidate"],
            events_count=existing_build["events_count"],
            incidents_count=existing_build["incidents_count"],
            ingested_at=ingested_at,
            is_retry=True,
            view_url=f"/api/v1/jenkins/builds/{build_id}"
        )

    # If updating an existing build with new log content, remove previous source_file and cascade
    if existing_build:
        cursor.execute("DELETE FROM source_files WHERE id = ?;", (existing_build["file_id"],))

    # 1. Register in source_files
    virtual_filename = f"jenkins_{clean_job.replace('/', '_')}_{clean_build}.log"
    cursor.execute("""
        INSERT OR REPLACE INTO source_files (filename, source_type, byte_size, line_count, sha256_hash, ingested_at)
        VALUES (?, ?, ?, ?, ?, ?);
    """, (virtual_filename, "JENKINS_BUILD_LOG", len(log_bytes), len(lines), sha256_hash, ingested_at))
    file_id = cursor.lastrowid

    # 2. Parse and insert events (strictly sanitized before SQLite persistence)
    events_to_insert = []
    for line_no, raw_line in enumerate(lines, 1):
        if not raw_line.strip():
            continue
        entry = LogParserEngine.parse_line(raw_line)
        sanitized_raw_line = SecretMasker.sanitize(raw_line, mask_ips=True)
        events_to_insert.append((
            file_id,
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
            sanitized_raw_line
        ))

    cursor.executemany("""
        INSERT INTO parsed_events (
            file_id, line_number, timestamp, severity, service, component, node,
            request_id, trace_id, span_id, status_code, latency_ms, sanitized_message, raw_message
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, events_to_insert)

    # 3. Detect failure blocks, classify, and formulate root-cause candidate
    i = 0
    incidents_count = 0
    top_category = None
    top_confidence = None
    top_root_cause = None

    if not baseline_model.is_trained:
        baseline_model.load()

    while i < len(lines):
        line = lines[i]
        if any(k in line for k in ["ERROR", "FAILED", "AssertionError", "Exception", "mkdir:", "qemu-img:"]):
            start_line = i + 1
            block = [line]
            j = i + 1
            while j < len(lines):
                next_l = lines[j]
                if (next_l.startswith("\t") or next_l.startswith("   ") or next_l.startswith("E   ") or 
                    "Caused:" in next_l or "Traceback" in next_l or "assert " in next_l or 
                    (next_l.startswith("FAILED ") and j == i + 1)):
                    block.append(next_l)
                    j += 1
                else:
                    break

            sanitized_block = SecretMasker.sanitize("\n".join(block), mask_ips=True)
            pred = baseline_model.predict(sanitized_block) if baseline_model.is_trained else {"predicted_category": "UNKNOWN", "confidence": 0.0}
            rca = RootCauseCandidateAnalyzer.analyze(sanitized_block, primary_category=pred["predicted_category"])
            incident_code = f"INC-JK-{file_id:02d}-{start_line:04d}"

            cursor.execute("""
                INSERT INTO incidents (
                    incident_code, file_id, start_line, end_line, primary_severity,
                    failure_category, confidence, root_cause_candidate, detected_signature,
                    evidence_text, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                incident_code,
                file_id,
                start_line,
                j,
                "ERROR",
                pred["predicted_category"],
                pred["confidence"],
                rca["root_cause_candidate"],
                sanitized_block[:150].strip(),
                sanitized_block,
                ingested_at
            ))

            if top_category is None:
                top_category = pred["predicted_category"]
                top_confidence = pred["confidence"]
                top_root_cause = rca["root_cause_candidate"]

            incidents_count += 1
            i = j
        else:
            i += 1

    normalized_build_status = str(build_status or "UNKNOWN").strip().upper()
    if normalized_build_status == "SUCCESS":
        # Jenkins' terminal result is authoritative when it is available. Log
        # incidents remain useful diagnostics, but may describe recovered errors.
        is_failure = False
        top_category = None
        top_confidence = None
        top_root_cause = None
    else:
        is_failure = (incidents_count > 0) or (normalized_build_status in ["FAILURE", "FAILED", "UNSTABLE"])
    
    # If build marked failed by Jenkins but no specific error regex triggered
    if is_failure and top_category is None:
        top_category = "ENVIRONMENT_AND_PIPELINE_ERROR"
        top_confidence = 0.65
        top_root_cause = "Pipeline Runner or Environment Execution Failure"

    # 4. Save to jenkins_builds registry
    cursor.execute("""
        INSERT OR REPLACE INTO jenkins_builds (
            job_name, build_number, build_id, token_id, file_id, build_url,
            repo_url, commit_sha, build_status, is_failure, primary_failure_category,
            confidence, root_cause_candidate, events_count, incidents_count,
            ingested_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, (
        clean_job,
        clean_build,
        build_id,
        token_info["token_id"],
        file_id,
        build_url,
        repo_url,
        commit_sha,
        build_status or ("FAILURE" if is_failure else "SUCCESS"),
        1 if is_failure else 0,
        top_category,
        top_confidence,
        top_root_cause,
        len(events_to_insert),
        incidents_count,
        ingested_at,
        ingested_at
    ))

    conn.commit()
    conn.close()

    return JenkinsBuildIngestResponse(
        build_id=build_id,
        job_name=clean_job,
        build_number=clean_build,
        build_status=build_status or ("FAILURE" if is_failure else "SUCCESS"),
        is_failure=is_failure,
        failure_category=top_category,
        confidence=top_confidence,
        root_cause_candidate=top_root_cause,
        events_count=len(events_to_insert),
        incidents_count=incidents_count,
        ingested_at=ingested_at,
        is_retry=False,
        view_url=f"/api/v1/jenkins/builds/{build_id}"
    )

# =========================================================================
# 4. JENKINS BUILDS QUERY & DETAIL ENDPOINTS
# =========================================================================

@router.get("/builds", response_model=List[JenkinsBuildSummaryItem])
def list_jenkins_builds(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    job_name: Optional[str] = None,
    is_failure: Optional[bool] = None
):
    """
    Retrieve ingested Jenkins builds with failure status, predicted root causes, and metadata.
    """
    conn = get_connection()
    cursor = conn.cursor()

    query = """
        SELECT id, build_id, job_name, build_number, build_url, repo_url, commit_sha,
               build_status, is_failure, primary_failure_category, confidence,
               root_cause_candidate, events_count, incidents_count, ingested_at
        FROM jenkins_builds
        WHERE 1=1
    """
    params = []

    if job_name:
        query += " AND job_name LIKE ?"
        params.append(f"%{job_name}%")
    if is_failure is not None:
        query += " AND is_failure = ?"
        params.append(1 if is_failure else 0)

    query += " ORDER BY id DESC LIMIT ? OFFSET ?;"
    params.extend([limit, offset])

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    return [
        JenkinsBuildSummaryItem(
            id=r["id"],
            build_id=r["build_id"],
            job_name=r["job_name"],
            build_number=r["build_number"],
            build_url=r["build_url"],
            repo_url=r["repo_url"],
            commit_sha=r["commit_sha"],
            build_status=r["build_status"],
            is_failure=bool(r["is_failure"]),
            primary_failure_category=r["primary_failure_category"],
            confidence=r["confidence"],
            root_cause_candidate=r["root_cause_candidate"],
            events_count=r["events_count"],
            incidents_count=r["incidents_count"],
            ingested_at=r["ingested_at"]
        )
        for r in rows
    ]

@router.get("/builds/{build_id:path}", response_model=JenkinsBuildDetailResponse)
def get_jenkins_build_detail(build_id: str):
    """
    Retrieve complete analysis detail for a specific Jenkins build, including detected incidents.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, build_id, job_name, build_number, token_id, file_id, build_url, repo_url, commit_sha,
               build_status, is_failure, primary_failure_category, confidence,
               root_cause_candidate, events_count, incidents_count, ingested_at
        FROM jenkins_builds
        WHERE build_id = ?;
    """, (build_id,))
    build_row = cursor.fetchone()

    if not build_row:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Jenkins build '{build_id}' not found.")

    file_id = build_row["file_id"]

    # Fetch incidents for this build
    cursor.execute("""
        SELECT incident_code, start_line, end_line, primary_severity, failure_category,
               confidence, root_cause_candidate, detected_signature, evidence_text
        FROM incidents
        WHERE file_id = ?
        ORDER BY start_line ASC;
    """, (file_id,))
    incidents = [dict(r) for r in cursor.fetchall()]

    # Fetch top parsed events
    cursor.execute("""
        SELECT line_number, timestamp, severity, service, sanitized_message
        FROM parsed_events
        WHERE file_id = ?
        ORDER BY id ASC LIMIT 20;
    """, (file_id,))
    sample_events = [dict(r) for r in cursor.fetchall()]

    conn.close()

    return JenkinsBuildDetailResponse(
        id=build_row["id"],
        build_id=build_row["build_id"],
        job_name=build_row["job_name"],
        build_number=build_row["build_number"],
        file_id=build_row["file_id"],
        build_url=build_row["build_url"],
        repo_url=build_row["repo_url"],
        commit_sha=build_row["commit_sha"],
        build_status=build_row["build_status"],
        is_failure=bool(build_row["is_failure"]),
        primary_failure_category=build_row["primary_failure_category"],
        confidence=build_row["confidence"],
        root_cause_candidate=build_row["root_cause_candidate"],
        events_count=build_row["events_count"],
        incidents_count=build_row["incidents_count"],
        ingested_at=build_row["ingested_at"],
        incidents=incidents,
        sample_events=sample_events
    )
