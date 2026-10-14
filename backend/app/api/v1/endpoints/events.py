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
    source_file: Optional[str] = None,
    file_id: Optional[int] = None
):
    """
    Retrieve parsed structured log events for the Parser View in the dashboard.
    """
    conn = get_connection()
    cursor = conn.cursor()

    query = """
        SELECT e.id, e.file_id, f.filename as source_file, e.line_number, e.timestamp,
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

    if file_id:
        query += " AND e.file_id = ?"
        params.append(file_id)

    # Count total matching
    count_query = f"SELECT COUNT(*) FROM ({query})"
    cursor.execute(count_query, params)
    count_res = cursor.fetchone()
    total_count = count_res[0] if count_res else 0

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
