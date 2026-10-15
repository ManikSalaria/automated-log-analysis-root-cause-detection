"""Evidence-Grounded Context Builder for TRACE Stage 4 RAG.

Assembles a structured context package from retrieved incidents,
including evidence text, provenance metadata, root-cause candidates,
and supporting log lines. This context package is designed for
future Stage 5 LLM consumption but is independently useful for
human review.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime

from app.core.security import SecretMasker
from app.core.database import get_connection


def build_evidence_context(
    query_text: str,
    query_category: Optional[str],
    retrieved_results: List[Dict[str, Any]],
    include_log_lines: bool = True,
    max_log_lines_per_incident: int = 10,
) -> Dict[str, Any]:
    """Build a structured evidence-grounded context package.
    
    Assembles retrieved incidents into a format suitable for both
    human review and future LLM prompt augmentation.
    
    Args:
        query_text: The query incident text.
        query_category: Predicted failure category for the query.
        retrieved_results: List of result dicts from HybridRetriever.
        include_log_lines: Whether to fetch surrounding log lines from SQLite.
        max_log_lines_per_incident: Max number of log lines to include per incident.
    
    Returns:
        Structured context package dict.
    """
    context = {
        "query": {
            "text": SecretMasker.sanitize(
                query_text, mask_ips=True, normalize_identifiers=True
            ),
            "predicted_category": query_category or "UNKNOWN",
        },
        "retrieved_count": len(retrieved_results),
        "evidence_items": [],
        "category_distribution": {},
        "provenance_summary": {
            "source_files": set(),
            "source_types": set(),
        },
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }

    category_counts: Dict[str, int] = {}

    for result in retrieved_results:
        evidence_item = {
            "rank": result.get("rank", 0),
            "incident_code": result.get("incident_code", ""),
            "failure_category": result.get("failure_category", ""),
            "root_cause_candidate": result.get("root_cause_candidate", ""),
            "evidence_text": SecretMasker.sanitize(
                result.get("text", ""),
                mask_ips=True, normalize_identifiers=True
            ),
            "evidence_signature": result.get("evidence_signature", ""),
            "source_file": result.get("source_file", ""),
            "source_type": result.get("source_type", ""),
            "start_line": result.get("start_line", 0),
            "end_line": result.get("end_line", 0),
            "scores": {
                "hybrid": result.get("hybrid_score", 0.0),
                "semantic_similarity": result.get("semantic_similarity", 0.0),
                "bm25": result.get("bm25_score", 0.0),
                "category_match": result.get("category_match", False),
            },
            "supporting_log_lines": [],
        }

        # Fetch surrounding log lines from SQLite if requested
        if include_log_lines:
            log_lines = _fetch_surrounding_log_lines(
                result.get("source_file", ""),
                result.get("start_line", 0),
                result.get("end_line", 0),
                max_lines=max_log_lines_per_incident
            )
            evidence_item["supporting_log_lines"] = log_lines

        context["evidence_items"].append(evidence_item)

        # Track category distribution
        cat = result.get("failure_category", "UNKNOWN")
        category_counts[cat] = category_counts.get(cat, 0) + 1

        # Track provenance
        context["provenance_summary"]["source_files"].add(
            result.get("source_file", "")
        )
        context["provenance_summary"]["source_types"].add(
            result.get("source_type", "")
        )

    context["category_distribution"] = category_counts

    # Convert sets to sorted lists for JSON serialization
    context["provenance_summary"]["source_files"] = sorted(
        context["provenance_summary"]["source_files"]
    )
    context["provenance_summary"]["source_types"] = sorted(
        context["provenance_summary"]["source_types"]
    )

    return context


def _fetch_surrounding_log_lines(
    source_file: str,
    start_line: int,
    end_line: int,
    max_lines: int = 10,
    context_window: int = 3,
) -> List[Dict[str, Any]]:
    """Fetch parsed events surrounding an incident from SQLite.
    
    Retrieves log lines in a window around the incident's line range
    to provide execution context for root cause analysis.
    
    Args:
        source_file: The source file name to query.
        start_line: Incident start line number.
        end_line: Incident end line number.
        max_lines: Maximum number of log lines to return.
        context_window: Number of lines before/after the incident to include.
    
    Returns:
        List of sanitized log line dicts with severity, message, and line number.
    """
    if not source_file or start_line <= 0:
        return []

    try:
        conn = get_connection()
        cursor = conn.cursor()

        window_start = max(1, start_line - context_window)
        window_end = end_line + context_window

        cursor.execute("""
            SELECT pe.line_number, pe.severity, pe.sanitized_message,
                   pe.service, pe.timestamp
            FROM parsed_events pe
            JOIN source_files sf ON pe.file_id = sf.id
            WHERE sf.filename = ?
              AND pe.line_number BETWEEN ? AND ?
            ORDER BY pe.line_number
            LIMIT ?;
        """, (source_file, window_start, window_end, max_lines))

        rows = cursor.fetchall()
        conn.close()

        return [
            {
                "line_number": row["line_number"],
                "severity": row["severity"],
                "message": SecretMasker.sanitize(
                    row["sanitized_message"],
                    mask_ips=True, normalize_identifiers=True
                ),
                "service": row["service"],
                "timestamp": row["timestamp"],
            }
            for row in rows
        ]
    except Exception:
        return []


def format_context_for_display(context: Dict[str, Any]) -> str:
    """Format the context package as human-readable text.
    
    Useful for the frontend display and for debugging.
    """
    lines = []
    lines.append(f"=== RAG Retrieval Context ===")
    lines.append(f"Query Category: {context['query']['predicted_category']}")
    lines.append(f"Retrieved: {context['retrieved_count']} incidents")
    lines.append(f"Generated: {context['generated_at']}")
    lines.append("")

    if context.get("category_distribution"):
        lines.append("Category Distribution:")
        for cat, count in sorted(context["category_distribution"].items()):
            lines.append(f"  {cat}: {count}")
        lines.append("")

    for item in context.get("evidence_items", []):
        lines.append(f"--- Rank {item['rank']}: {item['incident_code']} ---")
        lines.append(f"Category: {item['failure_category']}")
        lines.append(f"Root Cause: {item['root_cause_candidate']}")
        lines.append(f"Semantic Sim: {item['scores']['semantic_similarity']:.4f}")
        lines.append(f"BM25 Score: {item['scores']['bm25']:.4f}")
        lines.append(f"Hybrid Score: {item['scores']['hybrid']:.6f}")
        lines.append(f"Evidence: {item['evidence_text'][:200]}...")
        lines.append("")

    return "\n".join(lines)
