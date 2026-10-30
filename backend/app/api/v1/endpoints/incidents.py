from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query
from app.core.database import get_connection
from app.core.security import SecretMasker
from app.schemas.log_schema import IncidentSummaryItem

router = APIRouter()

@router.get("", response_model=List[IncidentSummaryItem])
def get_recent_incidents(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    category: Optional[str] = None,
    source_file: Optional[str] = None,
    job_name: Optional[str] = None,
    build_number: Optional[str] = None
):
    """
    Retrieve persisted incidents from SQLite database with filtering and pagination.
    Supports filtering by category, source_file, job_name, and build_number.
    """
    conn = get_connection(timeout=10.0)
    try:
        cursor = conn.cursor()

        query = """
            SELECT i.id, i.incident_code, f.filename as source_file, i.start_line, i.end_line,
                   i.primary_severity, i.failure_category, i.confidence, i.root_cause_candidate,
                   i.detected_signature, i.created_at,
                   COALESCE(i.job_name, f.job_name) as job_name,
                   COALESCE(i.build_number, f.build_number) as build_number,
                   f.build_status, f.build_url, f.repo_url, f.commit_sha, f.git_branch
            FROM incidents i
            JOIN source_files f ON i.file_id = f.id
            WHERE 1=1
        """
        params = []

        if category:
            query += " AND i.failure_category = ?"
            params.append(category)

        if source_file:
            query += " AND f.filename = ?"
            params.append(source_file)

        if job_name:
            query += " AND (f.job_name = ? OR i.job_name = ?)"
            params.extend([job_name, job_name])

        if build_number:
            query += " AND (f.build_number = ? OR i.build_number = ?)"
            params.extend([str(build_number), str(build_number)])

        query += " ORDER BY i.created_at DESC, i.id DESC LIMIT ? OFFSET ?;"
        params.extend([limit, offset])

        cursor.execute(query, params)
        rows = cursor.fetchall()

        return [
            IncidentSummaryItem(
                id=row["id"],
                incident_code=row["incident_code"],
                source_file=row["source_file"],
                start_line=row["start_line"],
                end_line=row["end_line"],
                primary_severity=row["primary_severity"],
                failure_category=row["failure_category"],
                confidence=row["confidence"],
                root_cause_candidate=row["root_cause_candidate"],
                detected_signature=SecretMasker.sanitize(row["detected_signature"] or "", mask_ips=True),
                created_at=row["created_at"],
                job_name=row["job_name"],
                build_number=row["build_number"],
                build_status=row["build_status"],
                build_url=row["build_url"],
                repo_url=row["repo_url"],
                commit_sha=row["commit_sha"],
                git_branch=row["git_branch"]
            )
            for row in rows
        ]
    finally:
        conn.close()

@router.get("/{incident_code}")
def get_incident_by_code(incident_code: str):
    """
    Retrieve detailed incident information including complete evidence text and CI/CD provenance.
    """
    conn = get_connection(timeout=10.0)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT i.*, f.filename as source_file, f.source_type,
                   COALESCE(i.job_name, f.job_name) as job_name,
                   COALESCE(i.build_number, f.build_number) as build_number,
                   f.build_status, f.build_url, f.repo_url, f.commit_sha, f.git_branch
            FROM incidents i
            JOIN source_files f ON i.file_id = f.id
            WHERE i.incident_code = ?;
        """, (incident_code,))
        row = cursor.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail=f"Incident '{incident_code}' not found.")

        result = dict(row)
        for field in ("detected_signature", "evidence_text"):
            if result.get(field):
                result[field] = SecretMasker.sanitize(result[field], mask_ips=True)
        return result
    finally:
        conn.close()
