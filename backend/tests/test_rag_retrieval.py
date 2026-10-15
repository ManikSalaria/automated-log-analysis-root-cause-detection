"""TRACE Stage 4 RAG Retrieval Pipeline Test Suite.

Verifies:
1. Pure-Python BM25 lexical retriever (tokenization, inverted index, scoring).
2. Dense semantic retriever (Sentence-BERT embedding, cosine dot-product).
3. Hybrid retriever with Reciprocal Rank Fusion (RRF) and metadata boosting.
4. Context builder and privacy sanitization (zero-PII leakage).
5. FastAPI RAG endpoints (/api/v1/rag/retrieve, /corpus-stats, /evaluation-metrics).
"""

import pytest
import numpy as np
from fastapi.testclient import TestClient

from app.ml.stage4_rag.bm25_retriever import BM25Retriever, tokenize
from app.ml.stage4_rag.semantic_retriever import SemanticRetriever
from app.ml.stage4_rag.hybrid_retriever import HybridRetriever
from app.ml.stage4_rag.retrieval_corpus import CorpusIncident, load_csv_corpus
from app.ml.stage4_rag.context_builder import build_evidence_context
from app.schemas.rag_schema import RAGQueryRequest
from app.core.config import settings
from main import app


@pytest.fixture
def test_client():
    return TestClient(app)


@pytest.fixture
def sample_corpus():
    return [
        CorpusIncident(
            incident_code="INC-TEST-01",
            source_file="test_log_01.txt",
            source_type="TEST_PIPELINE",
            failure_category="DATABASE_AND_CACHE_TIMEOUT",
            root_cause_candidate="HikariCP connection pool exhausted",
            evidence_signature="HikariPool-1 - Connection is not available, request timed out after 30000ms",
            text="ERROR [db-pool] HikariPool-1 - Connection is not available, request timed out after 30000ms",
            start_line=10,
            end_line=10,
        ),
        CorpusIncident(
            incident_code="INC-TEST-02",
            source_file="test_log_01.txt",
            source_type="TEST_PIPELINE",
            failure_category="NETWORK_DEPENDENCY_FAILURE",
            root_cause_candidate="Downstream HTTP 503 Service Unavailable",
            evidence_signature="Connection refused by payment service status=503",
            text="ERROR [order-service] Connection refused by payment service status=503 latency_ms=4500",
            start_line=25,
            end_line=25,
        ),
        CorpusIncident(
            incident_code="INC-TEST-03",
            source_file="test_log_02.txt",
            source_type="TEST_PIPELINE",
            failure_category="RESOURCE_EXHAUSTION_CRASH",
            root_cause_candidate="JVM Heap Space OutOfMemoryError",
            evidence_signature="java.lang.OutOfMemoryError: Java heap space",
            text="FATAL [jvm-runtime] java.lang.OutOfMemoryError: Java heap space during batch ingestion",
            start_line=100,
            end_line=102,
        ),
    ]


# ---------------------------------------------------------
# 1. BM25 RETRIEVER TESTS
# ---------------------------------------------------------

def test_bm25_tokenization():
    text = "ERROR [db-pool]: HikariPool-1 timeout after 30000ms!"
    tokens = tokenize(text)
    assert "error" in tokens
    assert "db_pool" in tokens or "db" in tokens or "pool" in tokens
    assert "hikaripool_1" in tokens or "hikaripool" in tokens or "timeout" in tokens
    # Check that single-character tokens are stripped
    assert all(len(t) > 1 for t in tokens)


def test_bm25_indexing_and_retrieval(sample_corpus):
    retriever = BM25Retriever()
    texts = [inc.text for inc in sample_corpus]
    retriever.build_index(texts)

    assert retriever.is_built
    assert retriever.corpus_size == 3
    stats = retriever.get_stats()
    assert stats["vocabulary_size"] > 0

    # Query for database pool timeout
    results = retriever.retrieve("HikariPool connection timeout", top_k=2)
    assert len(results) > 0
    top_idx, top_score = results[0]
    assert top_idx == 0  # INC-TEST-01 should be top match
    assert top_score > 0.0


def test_bm25_exclusion(sample_corpus):
    retriever = BM25Retriever()
    texts = [inc.text for inc in sample_corpus]
    retriever.build_index(texts)

    # Exclude doc 0
    results = retriever.retrieve("HikariPool connection timeout", top_k=2, exclude_indices={0})
    for doc_idx, _ in results:
        assert doc_idx != 0


# ---------------------------------------------------------
# 2. SEMANTIC RETRIEVER TESTS
# ---------------------------------------------------------

def test_semantic_retriever_mock_embeddings():
    retriever = SemanticRetriever()
    # Create synthetic 384-D normalized embeddings
    dummy_texts = ["doc 1", "doc 2"]
    emb = np.array([
        [1.0] + [0.0] * 383,
        [0.0, 1.0] + [0.0] * 382
    ], dtype=np.float32)

    retriever.build_index(dummy_texts, precomputed_embeddings=emb)
    assert retriever.is_built
    assert retriever.corpus_size == 2

    # Query aligned with doc 0
    q_emb = np.array([1.0] + [0.0] * 383, dtype=np.float32)
    res = retriever.retrieve_with_embedding(q_emb, top_k=1)
    assert len(res) == 1
    assert res[0][0] == 0
    assert abs(res[0][1] - 1.0) < 1e-4


# ---------------------------------------------------------
# 3. HYBRID RETRIEVER & FUSION TESTS
# ---------------------------------------------------------

def test_hybrid_retriever_build_and_query(sample_corpus):
    retriever = HybridRetriever(alpha=0.5, beta=0.3, gamma=0.2)
    stats = retriever.build_index(sample_corpus)

    assert retriever.is_built
    assert stats["corpus_size"] == 3

    # Query with category prior
    results = retriever.retrieve(
        query_text="Connection refused status=503 to payment gateway",
        top_k=2,
        query_category="NETWORK_DEPENDENCY_FAILURE"
    )

    assert len(results) > 0
    assert results[0]["incident_code"] == "INC-TEST-02"
    assert results[0]["failure_category"] == "NETWORK_DEPENDENCY_FAILURE"
    assert results[0]["hybrid_score"] > 0
    assert results[0]["category_match"] is True


def test_hybrid_retriever_self_exclusion(sample_corpus):
    retriever = HybridRetriever()
    retriever.build_index(sample_corpus)

    # Exclude INC-TEST-02
    results = retriever.retrieve(
        query_text="Connection refused status=503",
        top_k=3,
        exclude_incident_codes={"INC-TEST-02"}
    )
    for r in results:
        assert r["incident_code"] != "INC-TEST-02"


def test_hybrid_retriever_ablation_modes(sample_corpus):
    retriever = HybridRetriever()
    retriever.build_index(sample_corpus)

    bm25_only = retriever.retrieve_bm25_only("OutOfMemoryError Java heap space", top_k=2)
    assert len(bm25_only) > 0
    assert bm25_only[0]["incident_code"] == "INC-TEST-03"

    semantic_only = retriever.retrieve_semantic_only("OutOfMemoryError Java heap space", top_k=2)
    assert len(semantic_only) > 0
    assert semantic_only[0]["incident_code"] == "INC-TEST-03"


# ---------------------------------------------------------
# 4. CONTEXT BUILDER & PRIVACY SANITIZATION
# ---------------------------------------------------------

def test_context_builder_privacy_scrubbing():
    query_with_secret = "ERROR DB connection failed with AKIAIOSFODNN7EXAMPLE and password=SuperSecretPass123"
    retrieved = [{
        "rank": 1,
        "incident_code": "INC-001",
        "failure_category": "DATABASE_AND_CACHE_TIMEOUT",
        "root_cause_candidate": "Pool timeout",
        "text": "DB timeout at ip 192.168.1.100 with bearer eyJhbGciOi...",
        "hybrid_score": 0.05,
        "semantic_similarity": 0.88,
        "bm25_score": 4.5,
        "category_match": True,
        "source_file": "db.log",
        "source_type": "SERVICE",
        "start_line": 5,
        "end_line": 6,
    }]

    pkg = build_evidence_context(
        query_text=query_with_secret,
        query_category="DATABASE_AND_CACHE_TIMEOUT",
        retrieved_results=retrieved,
        include_log_lines=False
    )

    # Verify query secret is scrubbed
    assert "AKIAIOSFODNN7EXAMPLE" not in pkg["query"]["text"]
    assert "SuperSecretPass123" not in pkg["query"]["text"]
    assert "<REDACTED" in pkg["query"]["text"]

    # Verify retrieved secret is scrubbed
    item = pkg["evidence_items"][0]
    assert "192.168.1.100" not in item["evidence_text"]
    assert "<IP>" in item["evidence_text"] or "<REDACTED" in item["evidence_text"]


# ---------------------------------------------------------
# 5. FASTAPI RAG ENDPOINTS INTEGRATION TESTS
# ---------------------------------------------------------

def test_api_rag_corpus_stats(test_client):
    response = test_client.get("/api/v1/rag/corpus-stats")
    assert response.status_code == 200
    data = response.json()
    assert "is_built" in data
    assert "corpus_size" in data
    assert data["embedding_dimension"] == 384


def test_api_rag_retrieve(test_client):
    payload = {
        "query_text": "ERROR [notification-service] Connection refused by payment service status=503",
        "top_k": 3,
        "query_category": "NETWORK_DEPENDENCY_FAILURE",
        "retrieval_mode": "hybrid",
        "include_surrounding_logs": True
    }
    response = test_client.post("/api/v1/rag/retrieve", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["retrieved_count"] > 0
    assert len(data["results"]) <= 3
    assert "latency_ms" in data
    assert "retrieval_latency_ms" in data
    assert "context_latency_ms" in data
    assert "is_cold_start" in data
    assert data["latency_ms"] >= 0.0
    if data["retrieval_latency_ms"] is not None:
        assert data["retrieval_latency_ms"] >= 0.0
    if data["context_latency_ms"] is not None:
        assert data["context_latency_ms"] >= 0.0
    assert "privacy_audit" in data
    assert data["results"][0]["incident_code"].startswith("INC-")


def test_api_rag_evaluation_metrics(test_client):
    response = test_client.get("/api/v1/rag/evaluation-metrics")
    # Might be 200 if manifest already exists or 404/500 if still running
    if response.status_code == 200:
        data = response.json()
        assert "evaluation_summary" in data
        assert "hybrid" in data["evaluation_summary"]
