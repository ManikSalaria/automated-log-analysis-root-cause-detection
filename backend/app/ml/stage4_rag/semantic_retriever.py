"""Semantic Retriever for TRACE Stage 4 RAG.

Uses the existing Sentence-BERT embedder (all-MiniLM-L6-v2, 384-D)
to compute dense cosine similarity between a query incident and the
retrieval corpus. Since embeddings are L2-normalized, cosine similarity
reduces to a dot product: sim(q, d) = q · d.
"""

from typing import List, Tuple, Optional, Set
from pathlib import Path
import numpy as np

from app.ml.stage1_embedder.sbert_embedder import SentenceBertEmbedder
from app.core.config import settings


class SemanticRetriever:
    """Dense semantic retrieval using Sentence-BERT embeddings.
    
    Maintains a pre-computed embedding matrix for the retrieval corpus
    and computes query-corpus similarity via matrix dot product.
    """

    def __init__(self, embedder: Optional[SentenceBertEmbedder] = None):
        self.embedder = embedder or SentenceBertEmbedder()
        self.corpus_embeddings: Optional[np.ndarray] = None  # (N, 384) float32
        self.corpus_size: int = 0
        self._is_built: bool = False

    @property
    def is_built(self) -> bool:
        return self._is_built

    def build_index(
        self,
        corpus_texts: List[str],
        batch_size: int = 64,
        precomputed_embeddings: Optional[np.ndarray] = None
    ) -> None:
        """Build the semantic index from corpus texts or precomputed embeddings.
        
        Args:
            corpus_texts: List of sanitized incident text strings.
            batch_size: Batch size for SBERT encoding.
            precomputed_embeddings: Optional pre-encoded (N, 384) array to skip
                re-encoding. Must match len(corpus_texts).
        """
        self.corpus_size = len(corpus_texts)
        if self.corpus_size == 0:
            self.corpus_embeddings = np.empty((0, 384), dtype=np.float32)
            self._is_built = True
            return

        if precomputed_embeddings is not None:
            if precomputed_embeddings.shape[0] != self.corpus_size:
                raise ValueError(
                    f"Precomputed embeddings size {precomputed_embeddings.shape[0]} "
                    f"does not match corpus size {self.corpus_size}"
                )
            self.corpus_embeddings = precomputed_embeddings.astype(np.float32)
        else:
            # Ensure embedder is loaded
            if not self.embedder.is_loaded:
                self.embedder.load()

            self.corpus_embeddings = self.embedder.encode(
                corpus_texts, batch_size=batch_size, normalize_embeddings=True
            )

        self._is_built = True

    def encode_query(self, query_text: str) -> np.ndarray:
        """Encode a single query text into a 384-D embedding vector."""
        if not self.embedder.is_loaded:
            self.embedder.load()
        return self.embedder.encode_single(query_text)

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        exclude_indices: Optional[Set[int]] = None,
        similarity_threshold: float = 0.0
    ) -> List[Tuple[int, float]]:
        """Retrieve top-k documents by cosine similarity.
        
        Since embeddings are L2-normalized, cosine similarity = dot product.
        
        Args:
            query: The query text string.
            top_k: Number of top results to return.
            exclude_indices: Set of corpus indices to exclude.
            similarity_threshold: Minimum similarity score to include.
        
        Returns:
            List of (doc_index, similarity_score) tuples, sorted descending.
        """
        if not self._is_built or self.corpus_size == 0:
            return []

        query_emb = self.encode_query(query)  # (384,)

        # Dot product with full corpus: (N, 384) @ (384,) -> (N,)
        similarities = self.corpus_embeddings @ query_emb

        exclude = exclude_indices or set()

        # Build candidate list
        candidates = []
        for idx in range(self.corpus_size):
            if idx in exclude:
                continue
            sim = float(similarities[idx])
            if sim >= similarity_threshold:
                candidates.append((idx, sim))

        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[:top_k]

    def retrieve_with_embedding(
        self,
        query_embedding: np.ndarray,
        top_k: int = 5,
        exclude_indices: Optional[Set[int]] = None,
        similarity_threshold: float = 0.0
    ) -> List[Tuple[int, float]]:
        """Retrieve using a pre-computed query embedding (avoids re-encoding)."""
        if not self._is_built or self.corpus_size == 0:
            return []

        similarities = self.corpus_embeddings @ query_embedding
        exclude = exclude_indices or set()

        candidates = []
        for idx in range(self.corpus_size):
            if idx in exclude:
                continue
            sim = float(similarities[idx])
            if sim >= similarity_threshold:
                candidates.append((idx, sim))

        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[:top_k]

    def save_embeddings(self, path: Optional[Path] = None) -> None:
        """Persist corpus embeddings to disk as .npy for fast reload."""
        save_path = path or settings.RAG_CORPUS_EMBEDDINGS_PATH
        save_path.parent.mkdir(parents=True, exist_ok=True)
        if self.corpus_embeddings is not None:
            np.save(str(save_path), self.corpus_embeddings)

    def load_embeddings(self, path: Optional[Path] = None) -> bool:
        """Load pre-computed corpus embeddings from disk."""
        load_path = path or settings.RAG_CORPUS_EMBEDDINGS_PATH
        if not load_path.exists():
            return False
        self.corpus_embeddings = np.load(str(load_path)).astype(np.float32)
        self.corpus_size = self.corpus_embeddings.shape[0]
        self._is_built = True
        return True

    def get_stats(self) -> dict:
        """Return index statistics for diagnostics."""
        return {
            "corpus_size": self.corpus_size,
            "embedding_dimension": 384,
            "embeddings_shape": list(self.corpus_embeddings.shape) if self.corpus_embeddings is not None else None,
            "is_built": self._is_built,
            "model_name": self.embedder.model_name,
        }
