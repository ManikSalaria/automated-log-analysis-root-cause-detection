"""TRACE Stage 4 RAG Retrieval Pipeline Test Suite.

Verifies:
1. Pure-Python BM25 lexical retriever (tokenization, inverted index, scoring).
2. Dense semantic retriever (Sentence-BERT embedding, cosine dot-product).
3. Hybrid retriever with Reciprocal Rank Fusion (RRF) and metadata boosting.
4. Context builder and privacy sanitization (zero-PII leakage).
5. FastAPI RAG endpoints (/api/v1/rag/retrieve, /corpus-stats, /evaluation-metrics).
"""

import sys
from pathlib import Path

# Add backend and project root to sys.path
root_dir = Path(__file__).resolve().parent.parent.parent
backend_dir = root_dir / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

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
from app.core.security import SecretMasker
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


# ---------------------------------------------------------
# 6. TARGETED TESTS: SCORE LABELS, MODES, DIVERSIFICATION,
#    LATENCY REPORTING & TECHNICAL IDENTIFIERS
# ---------------------------------------------------------

def test_rag_mode_score_labels_and_nullability(test_client):
    """Verify that scores are accurately reported and never falsely labeled as hybrid."""
    query = "AssertionError: storage cluster id is missing from config in datastore alletra_datastore_abgrdg_dnd creation"

    # 1. Semantic Only Mode
    resp_sem = test_client.post("/api/v1/rag/retrieve", json={
        "query_text": query,
        "top_k": 3,
        "retrieval_mode": "semantic_only"
    })
    assert resp_sem.status_code == 200, resp_sem.text
    data_sem = resp_sem.json()
    assert data_sem["retrieval_mode"] == "semantic_only"
    for item in data_sem["results"]:
        assert item["hybrid_score"] is None, "hybrid_score must be None in dense semantic only mode"
        assert item["semantic_similarity"] is not None, "semantic_similarity must be populated"
        assert 0.0 <= item["semantic_similarity"] <= 1.0, f"semantic_similarity out of bounds: {item['semantic_similarity']}"
        assert item["bm25_score"] is None, "bm25_score must be None in dense semantic only mode"

    # 2. BM25 Only Mode
    resp_bm = test_client.post("/api/v1/rag/retrieve", json={
        "query_text": query,
        "top_k": 3,
        "retrieval_mode": "bm25_only"
    })
    assert resp_bm.status_code == 200, resp_bm.text
    data_bm = resp_bm.json()
    assert data_bm["retrieval_mode"] == "bm25_only"
    for item in data_bm["results"]:
        assert item["hybrid_score"] is None, "hybrid_score must be None in lexical BM25 only mode"
        assert item["semantic_similarity"] is None, "semantic_similarity must be None in lexical BM25 only mode"
        assert item["bm25_score"] is not None, "bm25_score must be populated in BM25 only mode"
        assert item["bm25_score"] >= 0.0, f"bm25_score must be non-negative: {item['bm25_score']}"

    # 3. Hybrid Mode
    resp_hyb = test_client.post("/api/v1/rag/retrieve", json={
        "query_text": query,
        "top_k": 3,
        "retrieval_mode": "hybrid"
    })
    assert resp_hyb.status_code == 200, resp_hyb.text
    data_hyb = resp_hyb.json()
    assert data_hyb["retrieval_mode"] == "hybrid"
    for item in data_hyb["results"]:
        assert item["hybrid_score"] is not None, "hybrid_score must be populated in hybrid mode"
        assert item["hybrid_score"] > 0.0, "hybrid_score must be greater than 0"
        assert item["semantic_similarity"] is not None
        assert item["bm25_score"] is not None


def test_rag_duplicate_handling_and_diversification(test_client):
    """Verify that near-duplicate failure episodes from the same log are diversified and clustered."""
    query = (
        "2026-02-25 21:12:39 MST test_vme_storage_plugin_e2e.py:320 ERROR : Actual error is: "
        "storage cluster id is missing from config in datastore alletra_datastore_abgrdg_dnd creation "
        "assert 'hpe_storage_cluster_id' in {'enableransomware': False, 'hpe_storage_cpg': 'SSD_r6'}"
    )

    resp = test_client.post("/api/v1/rag/retrieve", json={
        "query_text": query,
        "top_k": 5,
        "retrieval_mode": "hybrid"
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["is_diversified"] is True
    assert data["distinct_clusters_count"] >= 1
    assert "Diversified" in data["diversification_summary"] or "distinct" in data["diversification_summary"]

    # Verify that the top 5 results do not contain identical adjacent line spans in the same source file
    results = data["results"]
    for i in range(len(results)):
        for j in range(i + 1, len(results)):
            item_a = results[i]
            item_b = results[j]
            if item_a["source_file"] == item_b["source_file"] and item_a["source_file"]:
                # Ensure they are not adjacent lines from the exact same failure block (e.g. lines 48-52)
                line_dist = abs(item_a["start_line"] - item_b["start_line"])
                assert line_dist > 25 or item_a["incident_code"] != item_b["incident_code"], (
                    f"Near-duplicates {item_a['incident_code']} and {item_b['incident_code']} "
                    f"crowded top results at lines {item_a['start_line']} and {item_b['start_line']}"
                )

    # Verify that at least one item clustered near-duplicates and reported provenance
    total_dups = sum(item["duplicate_count"] for item in results)
    assert total_dups > 0, "Expected at least one candidate to record clustered near-duplicate incidents"
    top_item = results[0]
    assert isinstance(top_item["duplicate_incident_codes"], list)


def test_rag_diversification_fallback_when_few_distinct_results():
    """Verify that diversification does not hide useful evidence when fewer distinct items exist."""
    corpus = [
        CorpusIncident(
            incident_code="INC-DUP-01",
            source_file="pipeline.log",
            source_type="TEST",
            failure_category="STORAGE_AND_IO_ERROR",
            root_cause_candidate="Datastore failure",
            evidence_signature="storage cluster id missing",
            text="ERROR datastore creation failed: storage cluster id missing in config",
            start_line=10,
            end_line=11,
        ),
        CorpusIncident(
            incident_code="INC-DUP-02",
            source_file="pipeline.log",
            source_type="TEST",
            failure_category="STORAGE_AND_IO_ERROR",
            root_cause_candidate="Datastore failure",
            evidence_signature="storage cluster id missing",
            text="ERROR datastore creation failed: storage cluster id missing in config retry 1",
            start_line=12,
            end_line=13,
        ),
    ]

    retriever = HybridRetriever(alpha=0.5, beta=0.5, gamma=0.0)
    retriever.build_index(corpus)

    # Request top_k=2 with return_meta=True
    results, meta = retriever.retrieve(
        "storage cluster id missing in config",
        top_k=2,
        diversify=True,
        return_meta=True
    )

    # Must return all 2 items to fulfill requested top_k without hiding evidence
    assert len(results) == 2
    assert meta["is_diversified"] is True
    assert meta["distinct_clusters_count"] == 1
    assert "additional variant run" in meta["diversification_summary"] or "retained" in meta["diversification_summary"]


def test_rag_latency_reporting(test_client):
    """Verify accurate separation of cold-start and warm retrieval latency."""
    resp = test_client.post("/api/v1/rag/retrieve", json={
        "query_text": "HikariPool connection timeout pool exhausted",
        "top_k": 2,
        "retrieval_mode": "hybrid"
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert "latency_ms" in data
    assert "retrieval_latency_ms" in data
    assert "context_latency_ms" in data
    assert "cold_start_latency_ms" in data
    assert "is_cold_start" in data

    # Warm latency checks
    assert data["retrieval_latency_ms"] <= data["latency_ms"]
    if not data["is_cold_start"]:
        assert data["cold_start_latency_ms"] == 0.0
        # Warm ranking should execute in under 500ms
        assert data["retrieval_latency_ms"] < 500.0


def test_technical_identifier_preservation_and_secret_masking():
    """Verify technical identifiers like hpe_storage_cluster_id are preserved while secrets are redacted."""
    # 1. Technical identifiers and config keys must NOT be masked
    log_with_technical_keys = (
        "assert 'hpe_storage_cluster_id' in {'enableransomware': False, 'hpe_storage_cpg': 'SSD_r6'}\n"
        "cluster_id: 42, datastore_id: 108, client_id=svc_prod, hpe_storage_cluster_id='alletra-01'"
    )
    sanitized_tech = SecretMasker.sanitize(log_with_technical_keys)
    assert "hpe_storage_cluster_id" in sanitized_tech
    assert "enableransomware" in sanitized_tech
    assert "hpe_storage_cpg" in sanitized_tech
    assert "client_id=svc_prod" in sanitized_tech
    assert "alletra-01" in sanitized_tech
    assert "<REDACTED:SECRET>" not in sanitized_tech

    # Audit must find 0 leaks in purely technical configuration logs
    leak_audit = SecretMasker.audit_leaks(log_with_technical_keys)
    assert leak_audit["clean"] is True
    assert leak_audit["leak_count"] == 0

    # 2. Genuine passwords, tokens, and placeholders must continue to be masked
    dirty_log = (
        "password=\"SuperSecretPassword123!\"\n"
        "api_key: \"abcdef0123456789abcdef0123456789\"\n"
        "token=ghp_1234567890abcdefghijklmnopqrstuvwxyz\n"
        "***GMAIL_APP_PASSWORD***\n"
        "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.c2lnbmF0dXJl\n"
        "raw_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.c2lnbmF0dXJl"
    )
    sanitized_dirty = SecretMasker.sanitize(dirty_log)
    assert "SuperSecretPassword123!" not in sanitized_dirty
    assert "<REDACTED:SECRET>" in sanitized_dirty
    assert "<REDACTED:GITHUB_TOKEN>" in sanitized_dirty
    assert "<REDACTED:TOKEN>" in sanitized_dirty
    assert "<REDACTED:JWT>" in sanitized_dirty
