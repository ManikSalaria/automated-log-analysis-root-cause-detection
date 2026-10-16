"""TRACE Stage 4 RAG API Endpoints.

Provides REST endpoints for:
- POST /api/v1/rag/retrieve: Retrieve similar historical incidents & log evidence.
- GET  /api/v1/rag/corpus-stats: Retrieve diagnostic stats on the knowledge index.
- GET  /api/v1/rag/evaluation-metrics: Return benchmark evaluation metrics across retrieval modes.
"""

import json
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query

from app.schemas.rag_schema import (
    RAGQueryRequest, RAGQueryResponse, RAGCorpusStatsResponse
)
from app.ml.stage4_rag.rag_service import (
    execute_rag_retrieval, get_rag_retriever
)
from app.core.config import settings

router = APIRouter()


@router.post("/retrieve", response_model=RAGQueryResponse)
def retrieve_similar_incidents(request: RAGQueryRequest):
    """Retrieve relevant historical incidents and evidence-grounded context.
    
    Combines BM25 lexical matching and Sentence-BERT dense semantic similarity
    with Reciprocal Rank Fusion (RRF) and metadata boosting.
    """
    try:
        return execute_rag_retrieval(request)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"RAG retrieval failure: {str(e)}"
        )


@router.get("/corpus-stats", response_model=RAGCorpusStatsResponse)
def get_corpus_statistics():
    """Retrieve diagnostics and statistics for the RAG knowledge corpus."""
    try:
        retriever = get_rag_retriever()
        stats = retriever.get_stats()
        return RAGCorpusStatsResponse(
            is_built=stats.get("is_built", False),
            corpus_size=stats.get("corpus_size", 0),
            embedding_dimension=384,
            weights=stats.get("weights", {}),
            bm25_stats=stats.get("bm25_stats"),
            semantic_stats=stats.get("semantic_stats"),
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch RAG corpus statistics: {str(e)}"
        )


@router.get("/evaluation-metrics")
def get_evaluation_metrics():
    """Return Stage 4 benchmark retrieval evaluation metrics.
    
    Loads canonical group-aware evaluation metrics (Recall@1, Recall@3, Recall@5,
    MRR, Mean Cosine Similarity) comparing Hybrid, Dense Semantic, and BM25 Lexical.
    """
    manifest_path = settings.RAG_EVALUATION_MANIFEST_PATH
    if not manifest_path.exists():
        raise HTTPException(
            status_code=404,
            detail="RAG evaluation manifest not found. Run scripts/evaluate_rag_retrieval.py first."
        )
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load RAG evaluation manifest: {str(e)}"
        )


from app.schemas.synthesis_schema import SynthesizeRequest, SynthesizeResponse
from app.ml.stage5_llm.synthesis_service import execute_synthesis_pipeline


@router.post("/synthesize", response_model=SynthesizeResponse)
def synthesize_incident_report_alias(request: SynthesizeRequest):
    """Stage 5 LLM Synthesis endpoint alias for /api/v1/analysis/synthesize."""
    return execute_synthesis_pipeline(request)

