"""Hybrid Retriever for TRACE Stage 4 RAG.

Combines BM25 lexical scores with Sentence-BERT semantic scores and
optional structured metadata signals using Reciprocal Rank Fusion (RRF).

The hybrid score for document d given query q is:

    hybrid(d, q) = α · rank_score_semantic(d) + β · rank_score_bm25(d) + γ · metadata_bonus(d)

Where rank scores use RRF: 1 / (k + rank), with k = 60 (standard constant).

This avoids raw score normalization issues between BM25 and cosine similarity.
"""

from typing import List, Dict, Tuple, Optional, Set, Any
from collections import defaultdict
import numpy as np

from app.ml.stage4_rag.bm25_retriever import BM25Retriever
from app.ml.stage4_rag.semantic_retriever import SemanticRetriever
from app.ml.stage4_rag.retrieval_corpus import (
    CorpusIncident, build_corpus_texts, build_corpus_metadata,
    save_corpus_metadata, load_corpus_metadata,
    load_train_corpus, load_full_corpus,
)
from app.ml.stage1_embedder.sbert_embedder import SentenceBertEmbedder
from app.core.config import settings
from app.core.security import SecretMasker


# Standard RRF constant (Cormack et al., 2009)
RRF_K = 60


class HybridRetriever:
    """Hybrid retrieval engine combining BM25 + SBERT + metadata signals.
    
    Attributes:
        alpha: Weight for semantic (dense) retrieval signal. Default 0.5.
        beta: Weight for BM25 (sparse) retrieval signal. Default 0.3.
        gamma: Weight for structured metadata matching bonus. Default 0.2.
    """

    def __init__(
        self,
        alpha: float = 0.5,
        beta: float = 0.3,
        gamma: float = 0.2,
        embedder: Optional[SentenceBertEmbedder] = None,
    ):
        self.alpha = alpha
        self.beta = beta
        self.gamma = gamma

        self.embedder = embedder or SentenceBertEmbedder()
        self.bm25 = BM25Retriever()
        self.semantic = SemanticRetriever(embedder=self.embedder)

        self.corpus_texts: List[str] = []
        self.corpus_metadata: List[Dict[str, Any]] = []
        self.corpus_incidents: List[CorpusIncident] = []
        self._is_built: bool = False

    @property
    def is_built(self) -> bool:
        return self._is_built

    def build_index(
        self,
        incidents: List[CorpusIncident],
        batch_size: int = 64,
        precomputed_embeddings: Optional[np.ndarray] = None,
    ) -> Dict[str, Any]:
        """Build both BM25 and semantic indices from incident records.
        
        Args:
            incidents: List of CorpusIncident records.
            batch_size: Batch size for SBERT encoding.
            precomputed_embeddings: Optional pre-computed (N, 384) embedding matrix.
        
        Returns:
            Dict with index build statistics.
        """
        self.corpus_incidents = incidents
        self.corpus_texts = build_corpus_texts(incidents)
        self.corpus_metadata = build_corpus_metadata(incidents)

        # Build BM25 index (fast, CPU only)
        self.bm25.build_index(self.corpus_texts)

        # Build semantic index (requires SBERT model load)
        self.semantic.build_index(
            self.corpus_texts,
            batch_size=batch_size,
            precomputed_embeddings=precomputed_embeddings,
        )

        self._is_built = True

        return {
            "corpus_size": len(incidents),
            "bm25_stats": self.bm25.get_stats(),
            "semantic_stats": self.semantic.get_stats(),
            "weights": {"alpha": self.alpha, "beta": self.beta, "gamma": self.gamma},
        }

    def build_from_train_corpus(self, batch_size: int = 64) -> Dict[str, Any]:
        """Convenience: build index from the canonical training split.
        
        Used for leakage-free evaluation where the corpus is restricted
        to group_train_incidents.csv only.
        """
        incidents = load_train_corpus()
        return self.build_index(incidents, batch_size=batch_size)

    def build_from_full_corpus(self, batch_size: int = 64) -> Dict[str, Any]:
        """Convenience: build index from the full authentic corpus.
        
        Used for live retrieval where maximum coverage is desired.
        """
        incidents = load_full_corpus()
        return self.build_index(incidents, batch_size=batch_size)

    def _compute_metadata_bonus(
        self,
        query_category: Optional[str],
        doc_idx: int
    ) -> float:
        """Compute structured metadata matching bonus for a document.
        
        Returns 1.0 if the document's failure_category matches the query's
        predicted category (category-aware boosting), 0.0 otherwise.
        """
        if not query_category or doc_idx >= len(self.corpus_metadata):
            return 0.0
        doc_category = self.corpus_metadata[doc_idx].get("failure_category", "")
        return 1.0 if doc_category == query_category else 0.0

    def retrieve(
        self,
        query_text: str,
        top_k: int = 5,
        query_category: Optional[str] = None,
        exclude_incident_codes: Optional[Set[str]] = None,
        exclude_indices: Optional[Set[int]] = None,
        similarity_threshold: float = 0.0,
        candidate_pool_size: int = 50,
    ) -> List[Dict[str, Any]]:
        """Retrieve top-k incidents using hybrid BM25 + semantic + metadata fusion.
        
        Uses Reciprocal Rank Fusion (RRF) to combine rankings from different
        retrieval signals without requiring raw score normalization.
        
        Args:
            query_text: The incident text to find similar historical incidents for.
            top_k: Number of results to return.
            query_category: Optional predicted failure category for metadata boosting.
            exclude_incident_codes: Incident codes to exclude (self, duplicates).
            exclude_indices: Corpus indices to exclude.
            similarity_threshold: Minimum semantic similarity to include.
            candidate_pool_size: Size of candidate pool from each retriever.
        
        Returns:
            List of result dicts with scores, metadata, and provenance.
        """
        if not self._is_built:
            return []

        # Build exclusion index set
        exclude_idx = set(exclude_indices or set())
        if exclude_incident_codes:
            for i, meta in enumerate(self.corpus_metadata):
                if meta.get("incident_code", "") in exclude_incident_codes:
                    exclude_idx.add(i)

        # Get candidates from both retrievers
        bm25_results = self.bm25.retrieve(
            query_text, top_k=candidate_pool_size, exclude_indices=exclude_idx
        )
        semantic_results = self.semantic.retrieve(
            query_text, top_k=candidate_pool_size,
            exclude_indices=exclude_idx,
            similarity_threshold=similarity_threshold
        )

        # Build RRF scores
        rrf_scores: Dict[int, Dict[str, float]] = defaultdict(
            lambda: {"semantic_rrf": 0.0, "bm25_rrf": 0.0, "metadata_bonus": 0.0,
                     "semantic_raw": 0.0, "bm25_raw": 0.0}
        )

        for rank, (idx, raw_score) in enumerate(semantic_results):
            rrf_scores[idx]["semantic_rrf"] = 1.0 / (RRF_K + rank + 1)
            rrf_scores[idx]["semantic_raw"] = raw_score

        for rank, (idx, raw_score) in enumerate(bm25_results):
            rrf_scores[idx]["bm25_rrf"] = 1.0 / (RRF_K + rank + 1)
            rrf_scores[idx]["bm25_raw"] = raw_score

        # Compute hybrid scores with metadata bonus
        scored_results = []
        for idx, scores in rrf_scores.items():
            meta_bonus = self._compute_metadata_bonus(query_category, idx)
            scores["metadata_bonus"] = meta_bonus

            hybrid_score = (
                self.alpha * scores["semantic_rrf"]
                + self.beta * scores["bm25_rrf"]
                + self.gamma * (meta_bonus / (RRF_K + 1))  # Normalize metadata to RRF scale
            )
            scored_results.append((idx, hybrid_score, scores))

        scored_results.sort(key=lambda x: x[1], reverse=True)
        top_results = scored_results[:top_k]

        # Build response objects
        results = []
        for idx, hybrid_score, component_scores in top_results:
            meta = self.corpus_metadata[idx] if idx < len(self.corpus_metadata) else {}
            text = self.corpus_texts[idx] if idx < len(self.corpus_texts) else ""

            results.append({
                "rank": len(results) + 1,
                "incident_code": meta.get("incident_code", ""),
                "failure_category": meta.get("failure_category", ""),
                "root_cause_candidate": meta.get("root_cause_candidate", ""),
                "evidence_signature": meta.get("evidence_signature", ""),
                "source_file": meta.get("source_file", ""),
                "source_type": meta.get("source_type", ""),
                "start_line": meta.get("start_line", 0),
                "end_line": meta.get("end_line", 0),
                "text": text,
                "hybrid_score": round(hybrid_score, 6),
                "semantic_similarity": round(component_scores["semantic_raw"], 4),
                "bm25_score": round(component_scores["bm25_raw"], 4),
                "category_match": component_scores["metadata_bonus"] > 0,
            })

        return results

    def retrieve_semantic_only(
        self,
        query_text: str,
        top_k: int = 5,
        exclude_incident_codes: Optional[Set[str]] = None,
        similarity_threshold: float = 0.0,
    ) -> List[Dict[str, Any]]:
        """Retrieve using only semantic similarity (for ablation comparison)."""
        if not self._is_built:
            return []

        exclude_idx = set()
        if exclude_incident_codes:
            for i, meta in enumerate(self.corpus_metadata):
                if meta.get("incident_code", "") in exclude_incident_codes:
                    exclude_idx.add(i)

        results = self.semantic.retrieve(
            query_text, top_k=top_k,
            exclude_indices=exclude_idx,
            similarity_threshold=similarity_threshold
        )

        return self._format_results(results)

    def retrieve_bm25_only(
        self,
        query_text: str,
        top_k: int = 5,
        exclude_incident_codes: Optional[Set[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve using only BM25 lexical matching (for ablation comparison)."""
        if not self._is_built:
            return []

        exclude_idx = set()
        if exclude_incident_codes:
            for i, meta in enumerate(self.corpus_metadata):
                if meta.get("incident_code", "") in exclude_incident_codes:
                    exclude_idx.add(i)

        results = self.bm25.retrieve(
            query_text, top_k=top_k, exclude_indices=exclude_idx
        )

        return self._format_results(results)

    def _format_results(self, raw_results: List[Tuple[int, float]]) -> List[Dict[str, Any]]:
        """Format raw (index, score) results into response dicts."""
        results = []
        for rank, (idx, score) in enumerate(raw_results):
            meta = self.corpus_metadata[idx] if idx < len(self.corpus_metadata) else {}
            text = self.corpus_texts[idx] if idx < len(self.corpus_texts) else ""
            results.append({
                "rank": rank + 1,
                "incident_code": meta.get("incident_code", ""),
                "failure_category": meta.get("failure_category", ""),
                "root_cause_candidate": meta.get("root_cause_candidate", ""),
                "evidence_signature": meta.get("evidence_signature", ""),
                "source_file": meta.get("source_file", ""),
                "text": text,
                "score": round(score, 4),
            })
        return results

    def save_index(self) -> None:
        """Persist corpus metadata and embeddings for fast reload."""
        save_corpus_metadata(self.corpus_metadata, settings.RAG_CORPUS_METADATA_PATH)
        self.semantic.save_embeddings()

    def load_index(self) -> bool:
        """Load pre-built index from disk (metadata + embeddings).
        
        Rebuilds BM25 from the loaded corpus texts since BM25 is
        fast to reconstruct and has a small memory footprint.
        """
        metadata = load_corpus_metadata(settings.RAG_CORPUS_METADATA_PATH)
        if not metadata:
            return False

        if not self.semantic.load_embeddings():
            return False

        self.corpus_metadata = metadata
        self.corpus_texts = []  # Will need to rebuild from incidents
        self._is_built = True
        return True

    def get_stats(self) -> Dict[str, Any]:
        """Return comprehensive retrieval engine statistics."""
        return {
            "is_built": self._is_built,
            "corpus_size": len(self.corpus_metadata),
            "weights": {"alpha": self.alpha, "beta": self.beta, "gamma": self.gamma},
            "rrf_k": RRF_K,
            "bm25_stats": self.bm25.get_stats() if self.bm25.is_built else None,
            "semantic_stats": self.semantic.get_stats() if self.semantic.is_built else None,
        }
