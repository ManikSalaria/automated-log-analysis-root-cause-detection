from typing import Optional, List
from fastapi import APIRouter, Query
from app.core.database import get_connection

router = APIRouter()

@router.get("")
def get_parsed_events(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    severity: Optional[str] = None,
    service: Optional[str] = None,
    source_file: Optional[str] = None
):
    """
    Retrieve parsed structured log events for the Parser View in the dashboard.
    """
    conn = get_connection()
    cursor = conn.cursor()

    query = """
        SELECT e.id, f.filename as source_file, e.line_number, e.timestamp,
               e.severity, e.service, e.component, e.node, e.request_id,
               e.trace_id, e.status_code, e.latency_ms, e.sanitized_message
        FROM parsed_events e
        JOIN source_files f ON e.file_id = f.id
        WHERE 1=1
    """
    params = []

    if severity:
        query += " AND e.severity = ?"
        params.append(severity.upper())

    if service:
        query += " AND e.service LIKE ?"
        params.append(f"%{service}%")

    if source_file:
        query += " AND f.filename = ?"
        params.append(source_file)

    # Count total matching
    count_query = query.replace(
        "SELECT e.id, f.filename as source_file, e.line_number, e.timestamp, e.severity, e.service, e.component, e.node, e.request_id, e.trace_id, e.status_code, e.latency_ms, e.sanitized_message", 
        "SELECT COUNT(*)"
    )
    cursor.execute(count_query, params)
    total_count = cursor.fetchone()[0]

    query += " ORDER BY e.id ASC LIMIT ? OFFSET ?;"
    params.extend([limit, offset])

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    return {
        "total": total_count,
        "limit": limit,
        "offset": offset,
        "events": [dict(r) for r in rows]
    }
