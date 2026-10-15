"""BM25 Lexical Retriever for TRACE Stage 4 RAG.

Implements Okapi BM25 scoring for sparse keyword-based retrieval.
This is a pure-Python implementation to avoid external dependencies
on rank_bm25, using the standard BM25 formula:

    score(q, D) = Σ IDF(qi) · (tf(qi, D) · (k1 + 1))
                                / (tf(qi, D) + k1 · (1 - b + b · |D|/avgdl))

Where:
    - IDF(qi) = log((N - n(qi) + 0.5) / (n(qi) + 0.5) + 1)
    - k1 = 1.5, b = 0.75 (standard Okapi BM25 parameters)
"""

import math
import re
from typing import List, Dict, Tuple, Optional
from collections import Counter
import numpy as np


def tokenize(text: str) -> List[str]:
    """Simple whitespace + punctuation tokenizer for log text.
    
    Lowercases, strips non-alphanumeric characters, and removes
    single-character tokens. Designed for structured log messages
    where words like 'ERROR', 'timeout', 'connection' are key signals.
    """
    text = text.lower()
    tokens = re.findall(r'[a-z0-9_]+', text)
    return [t for t in tokens if len(t) > 1]


class BM25Retriever:
    """Okapi BM25 sparse retrieval engine for log incident text.
    
    Builds an inverted index over tokenized corpus documents and
    scores query-document relevance using BM25.
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.corpus_size: int = 0
        self.avgdl: float = 0.0
        self.doc_freqs: Dict[str, int] = {}       # term -> document frequency
        self.idf_cache: Dict[str, float] = {}      # term -> IDF score
        self.doc_lengths: List[int] = []            # per-document token counts
        self.doc_term_freqs: List[Dict[str, int]] = []  # per-document TF vectors
        self._is_built: bool = False

    @property
    def is_built(self) -> bool:
        return self._is_built

    def build_index(self, documents: List[str]) -> None:
        """Build the BM25 inverted index from a list of document strings.
        
        Args:
            documents: List of raw or sanitized incident text strings.
        """
        self.corpus_size = len(documents)
        if self.corpus_size == 0:
            self._is_built = True
            return

        self.doc_term_freqs = []
        self.doc_lengths = []
        self.doc_freqs = {}

        for doc in documents:
            tokens = tokenize(doc)
            self.doc_lengths.append(len(tokens))

            tf = Counter(tokens)
            self.doc_term_freqs.append(dict(tf))

            # Count unique terms per document for IDF
            for term in tf:
                self.doc_freqs[term] = self.doc_freqs.get(term, 0) + 1

        self.avgdl = sum(self.doc_lengths) / self.corpus_size if self.corpus_size > 0 else 1.0

        # Pre-compute IDF for all terms
        self.idf_cache = {}
        for term, df in self.doc_freqs.items():
            # Standard BM25 IDF with +1 smoothing to avoid negative values
            idf = math.log((self.corpus_size - df + 0.5) / (df + 0.5) + 1.0)
            self.idf_cache[term] = idf

        self._is_built = True

    def score_document(self, query_tokens: List[str], doc_idx: int) -> float:
        """Compute BM25 score for a single document against query tokens."""
        if doc_idx >= self.corpus_size:
            return 0.0

        score = 0.0
        doc_tf = self.doc_term_freqs[doc_idx]
        doc_len = self.doc_lengths[doc_idx]

        for term in query_tokens:
            if term not in self.idf_cache:
                continue

            tf = doc_tf.get(term, 0)
            if tf == 0:
                continue

            idf = self.idf_cache[term]
            tf_norm = (tf * (self.k1 + 1)) / (
                tf + self.k1 * (1 - self.b + self.b * doc_len / self.avgdl)
            )
            score += idf * tf_norm

        return score

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        exclude_indices: Optional[set] = None
    ) -> List[Tuple[int, float]]:
        """Retrieve top-k documents by BM25 score for a query string.
        
        Args:
            query: The query text string.
            top_k: Number of top results to return.
            exclude_indices: Set of document indices to exclude (for deduplication).
        
        Returns:
            List of (doc_index, bm25_score) tuples, sorted descending by score.
        """
        if not self._is_built or self.corpus_size == 0:
            return []

        query_tokens = tokenize(query)
        if not query_tokens:
            return []

        exclude = exclude_indices or set()
        scores = []

        for idx in range(self.corpus_size):
            if idx in exclude:
                continue
            s = self.score_document(query_tokens, idx)
            if s > 0:
                scores.append((idx, s))

        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]

    def get_stats(self) -> Dict:
        """Return index statistics for diagnostic purposes."""
        return {
            "corpus_size": self.corpus_size,
            "vocabulary_size": len(self.doc_freqs),
            "avg_document_length": round(self.avgdl, 2),
            "k1": self.k1,
            "b": self.b,
            "is_built": self._is_built,
        }
