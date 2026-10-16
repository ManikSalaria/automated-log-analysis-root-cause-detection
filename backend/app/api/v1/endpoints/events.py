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
    file_id: Optional[int] = None,
    order: Optional[str] = Query("desc", pattern="^(?i)(asc|desc)$")
):
    """
    Retrieve parsed structured log events for the Parser View in the dashboard.
    Defaults to descending ID order so newly ingested events appear first.
    Supports filtering by severity, service, source_file, and file_id.
    """
    conn = get_connection(timeout=10.0)
    try:
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
            query += " AND (f.filename = ? OR f.filename LIKE ?)"
            params.extend([source_file, f"%{source_file}%"])

        if file_id is not None:
            query += " AND e.file_id = ?"
            params.append(file_id)

        # Count total matching
        count_query = query.replace(
            "SELECT e.id, f.filename as source_file, e.line_number, e.timestamp, e.severity, e.service, e.component, e.node, e.request_id, e.trace_id, e.status_code, e.latency_ms, e.sanitized_message",
            "SELECT COUNT(*)"
        )
        cursor.execute(count_query, params)
        total_count = cursor.fetchone()[0]

        order_dir = "ASC" if order and order.lower() == "asc" else "DESC"
        query += f" ORDER BY e.id {order_dir} LIMIT ? OFFSET ?;"
        params.extend([limit, offset])

        cursor.execute(query, params)
        rows = cursor.fetchall()

        return {
            "total": total_count,
            "limit": limit,
            "offset": offset,
            "events": [dict(r) for r in rows]
        }
    finally:
        conn.close()
