"""RAG Service Coordinator for TRACE Stage 4.

Provides centralized lazy initialization, caching, and querying for the
hybrid retrieval pipeline. Ensures the SBERT embeddings and BM25 index
are kept in memory across API requests for low latency.
"""

import time
from typing import Optional, List, Dict, Any
from pathlib import Path

from app.ml.stage4_rag.hybrid_retriever import HybridRetriever
from app.ml.stage4_rag.retrieval_corpus import (
    load_full_corpus, load_train_corpus, CorpusIncident
)
from app.ml.stage4_rag.context_builder import build_evidence_context
from app.core.config import settings
from app.core.security import SecretMasker
from app.schemas.rag_schema import (
    RAGQueryRequest, RAGQueryResponse, RetrievedIncidentItem, RAGCorpusStatsResponse
)

_rag_retriever_instance: Optional[HybridRetriever] = None


def get_rag_retriever(force_reload: bool = False, use_train_only: bool = False) -> HybridRetriever:
    """Get or initialize the singleton HybridRetriever instance.
    
    Loads pre-computed embeddings and metadata if available, otherwise
    builds the index from the incident corpus.
    """
    global _rag_retriever_instance
    if _rag_retriever_instance is not None and not force_reload:
        return _rag_retriever_instance

    retriever = HybridRetriever(alpha=0.5, beta=0.3, gamma=0.2)
    corpus: List[CorpusIncident] = load_train_corpus() if use_train_only else load_full_corpus()

    # Check if precomputed embeddings exist in cache
    emb_path = settings.RAG_CORPUS_EMBEDDINGS_PATH
    precomputed = None
    if emb_path.exists():
        try:
            import numpy as np
            loaded_emb = np.load(str(emb_path))
            if loaded_emb.shape[0] == len(corpus):
                precomputed = loaded_emb
        except Exception:
            precomputed = None

    retriever.build_index(corpus, precomputed_embeddings=precomputed)

    # If embeddings weren't precomputed and cached, save them now
    if precomputed is None and retriever.semantic.corpus_embeddings is not None:
        try:
            retriever.semantic.save_embeddings()
        except Exception:
            pass

    _rag_retriever_instance = retriever
    return _rag_retriever_instance


def execute_rag_retrieval(request: RAGQueryRequest) -> RAGQueryResponse:
    """Execute a RAG retrieval query and return structured results with context."""
    start_time = time.perf_counter()

    # 1. Privacy Sanitization & Leak Audit
    privacy_audit = SecretMasker.audit_leaks(request.query_text)
    sanitized_query = SecretMasker.sanitize(
        request.query_text, mask_ips=True, normalize_identifiers=True
    )

    # 2. Retrieve candidates
    was_cold_start = (_rag_retriever_instance is None)
    t_load_start = time.perf_counter()
    retriever = get_rag_retriever()
    cold_start_latency_ms = round((time.perf_counter() - t_load_start) * 1000.0, 2) if was_cold_start else 0.0
    exclude_codes = set(request.exclude_incident_codes or [])

    t_retrieval_start = time.perf_counter()
    mode = (request.retrieval_mode or "hybrid").strip().lower()
    if mode == "semantic_only":
        raw_results, meta_info = retriever.retrieve_semantic_only(
            query_text=sanitized_query,
            top_k=request.top_k,
            exclude_incident_codes=exclude_codes,
            similarity_threshold=request.similarity_threshold,
            diversify=True,
            return_meta=True,
        )
        # Adapt keys: explicitly set hybrid_score and bm25_score to None
        retrieved_list = []
        for r in raw_results:
            retrieved_list.append({
                "rank": r["rank"],
                "incident_code": r["incident_code"],
                "failure_category": r["failure_category"],
                "root_cause_candidate": r["root_cause_candidate"],
                "evidence_signature": r.get("evidence_signature", ""),
                "source_file": r.get("source_file", ""),
                "source_type": r.get("source_type", ""),
                "start_line": r.get("start_line", 0),
                "end_line": r.get("end_line", 0),
                "text": r.get("text", ""),
                "hybrid_score": None,
                "semantic_similarity": round(float(r.get("score", 0.0)), 4),
                "bm25_score": None,
                "category_match": (r.get("failure_category") == request.query_category) if request.query_category else False,
                "duplicate_count": r.get("duplicate_count", 0),
                "duplicate_incident_codes": r.get("duplicate_incident_codes", []),
            })
    elif mode == "bm25_only":
        raw_results, meta_info = retriever.retrieve_bm25_only(
            query_text=sanitized_query,
            top_k=request.top_k,
            exclude_incident_codes=exclude_codes,
            diversify=True,
            return_meta=True,
        )
        # Adapt keys: explicitly set hybrid_score and semantic_similarity to None
        retrieved_list = []
        for r in raw_results:
            retrieved_list.append({
                "rank": r["rank"],
                "incident_code": r["incident_code"],
                "failure_category": r["failure_category"],
                "root_cause_candidate": r["root_cause_candidate"],
                "evidence_signature": r.get("evidence_signature", ""),
                "source_file": r.get("source_file", ""),
                "source_type": r.get("source_type", ""),
                "start_line": r.get("start_line", 0),
                "end_line": r.get("end_line", 0),
                "text": r.get("text", ""),
                "hybrid_score": None,
                "semantic_similarity": None,
                "bm25_score": round(float(r.get("score", 0.0)), 2),
                "category_match": (r.get("failure_category") == request.query_category) if request.query_category else False,
                "duplicate_count": r.get("duplicate_count", 0),
                "duplicate_incident_codes": r.get("duplicate_incident_codes", []),
            })
    else:
        # Default: Hybrid RRF
        retrieved_list, meta_info = retriever.retrieve(
            query_text=sanitized_query,
            top_k=request.top_k,
            query_category=request.query_category,
            exclude_incident_codes=exclude_codes,
            similarity_threshold=request.similarity_threshold,
            diversify=True,
            return_meta=True,
        )
    retrieval_latency_ms = round((time.perf_counter() - t_retrieval_start) * 1000.0, 2)

    # 3. Assemble structured context package with surrounding logs
    t_context_start = time.perf_counter()
    context_pkg = build_evidence_context(
        query_text=sanitized_query,
        query_category=request.query_category,
        retrieved_results=retrieved_list,
        include_log_lines=request.include_surrounding_logs,
        max_log_lines_per_incident=6,
    )
    context_latency_ms = round((time.perf_counter() - t_context_start) * 1000.0, 2)

    elapsed_ms = round((time.perf_counter() - start_time) * 1000.0, 2)

    # 4. Map into Pydantic models
    result_items = []
    for item in context_pkg["evidence_items"]:
        result_items.append(RetrievedIncidentItem(
            rank=item["rank"],
            incident_code=item["incident_code"],
            failure_category=item["failure_category"],
            root_cause_candidate=item["root_cause_candidate"],
            evidence_signature=item.get("evidence_signature", ""),
            source_file=item.get("source_file", ""),
            source_type=item.get("source_type", ""),
            start_line=item.get("start_line", 0),
            end_line=item.get("end_line", 0),
            evidence_text=item.get("evidence_text", ""),
            hybrid_score=item["scores"]["hybrid"],
            semantic_similarity=item["scores"]["semantic_similarity"],
            bm25_score=item["scores"]["bm25"],
            category_match=item["scores"]["category_match"],
            duplicate_count=item.get("duplicate_count", 0),
            duplicate_incident_codes=item.get("duplicate_incident_codes", []),
            supporting_log_lines=item.get("supporting_log_lines", []),
        ))

    return RAGQueryResponse(
        query_text=sanitized_query,
        predicted_category=request.query_category,
        retrieval_mode=mode,
        retrieved_count=len(result_items),
        top_k=request.top_k,
        latency_ms=elapsed_ms,
        retrieval_latency_ms=retrieval_latency_ms,
        context_latency_ms=context_latency_ms,
        cold_start_latency_ms=cold_start_latency_ms,
        is_cold_start=was_cold_start,
        is_diversified=meta_info.get("is_diversified", True),
        distinct_clusters_count=meta_info.get("distinct_clusters_count", len(result_items)),
        diversification_summary=meta_info.get("diversification_summary"),
        results=result_items,
        category_distribution=context_pkg.get("category_distribution", {}),
        provenance_summary=context_pkg.get("provenance_summary", {}),
        privacy_audit=privacy_audit,
    )
