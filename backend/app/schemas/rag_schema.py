"""Pydantic Request and Response Schemas for TRACE Stage 4 RAG.

Defines validated data structures for query requests, retrieved incidents,
evidence-grounded context packages, and corpus statistics.
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class RAGQueryRequest(BaseModel):
    """Request payload for RAG incident retrieval."""
    query_text: str = Field(..., description="Raw or sanitized log snippet representing the failure incident")
    top_k: int = Field(5, ge=1, le=20, description="Number of most relevant historical incidents to retrieve")
    query_category: Optional[str] = Field(None, description="Optional predicted failure category to guide metadata boosting")
    exclude_incident_codes: Optional[List[str]] = Field(default_factory=list, description="Incident codes to exclude (e.g. self-query or known duplicates)")
    similarity_threshold: float = Field(0.0, ge=0.0, le=1.0, description="Minimum cosine similarity cutoff for dense matches")
    retrieval_mode: str = Field("hybrid", description="Retrieval mode: 'hybrid', 'semantic_only', or 'bm25_only'")
    include_surrounding_logs: bool = Field(True, description="Whether to include surrounding chronological log events from SQLite")


class RetrievedIncidentItem(BaseModel):
    """Detailed representation of a retrieved historical incident."""
    rank: int
    incident_code: str
    failure_category: str
    root_cause_candidate: str
    evidence_signature: str
    source_file: str
    source_type: str
    start_line: int
    end_line: int
    evidence_text: str
    hybrid_score: float
    semantic_similarity: float
    bm25_score: float
    category_match: bool
    supporting_log_lines: List[Dict[str, Any]] = Field(default_factory=list)


class RAGQueryResponse(BaseModel):
    """Response payload containing retrieved incidents and assembled context."""
    query_text: str
    predicted_category: Optional[str] = None
    retrieval_mode: str
    retrieved_count: int
    top_k: int
    latency_ms: float
    retrieval_latency_ms: Optional[float] = Field(None, description="Pure search and ranking latency in milliseconds")
    context_latency_ms: Optional[float] = Field(None, description="SQLite context window retrieval latency in milliseconds")
    is_cold_start: bool = Field(False, description="Whether this request triggered initial model loading or index building")
    results: List[RetrievedIncidentItem]
    category_distribution: Dict[str, int] = Field(default_factory=dict)
    provenance_summary: Dict[str, List[str]] = Field(default_factory=dict)
    privacy_audit: Dict[str, Any] = Field(default_factory=dict)


class RAGCorpusStatsResponse(BaseModel):
    """Statistics about the currently loaded retrieval knowledge corpus."""
    is_built: bool
    corpus_size: int
    embedding_dimension: int = 384
    weights: Dict[str, float] = Field(default_factory=dict)
    bm25_stats: Optional[Dict[str, Any]] = None
    semantic_stats: Optional[Dict[str, Any]] = None
