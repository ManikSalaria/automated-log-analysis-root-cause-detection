from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query
from app.core.database import get_connection
from app.schemas.log_schema import IncidentSummaryItem

router = APIRouter()

@router.get("", response_model=List[IncidentSummaryItem])
def get_recent_incidents(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    category: Optional[str] = None,
    source_file: Optional[str] = None
):
    """
    Retrieve persisted incidents from SQLite database with filtering and pagination.
    """
    conn = get_connection()
    cursor = conn.cursor()

    query = """
        SELECT i.id, i.incident_code, f.filename as source_file, i.start_line, i.end_line,
               i.primary_severity, i.failure_category, i.confidence, i.root_cause_candidate,
               i.detected_signature, i.created_at
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

    query += " ORDER BY i.id DESC LIMIT ? OFFSET ?;"
    params.extend([limit, offset])

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

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
            detected_signature=row["detected_signature"],
            created_at=row["created_at"]
        )
        for row in rows
    ]

@router.get("/{incident_code}")
def get_incident_by_code(incident_code: str):
    """
    Retrieve detailed incident information including complete evidence text.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT i.*, f.filename as source_file, f.source_type
        FROM incidents i
        JOIN source_files f ON i.file_id = f.id
        WHERE i.incident_code = ?;
    """, (incident_code,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail=f"Incident '{incident_code}' not found.")

    return dict(row)
