"""Sentence-BERT Semantic Embedding Engine (TRACE Stage 1).

Produces genuine 384-dimensional dense sentence embeddings using
sentence-transformers/all-MiniLM-L6-v2. Embeds sanitized, privacy-scrubbed
incident text to provide dense semantic representations for failure classification
and root-cause retrieval.
"""

from typing import List, Union, Optional
from pathlib import Path
import numpy as np
from app.core.config import settings
from app.core.security import SecretMasker

class SentenceBertEmbedder:
    """
    TRACE Stage 1 Semantic Embedder.
    Converts sanitized log text into genuine 384-dimensional dense vectors.
    """

    def __init__(self, model_name: Optional[str] = None, cache_folder: Optional[Path] = None):
        self.model_name = model_name or settings.SBERT_MODEL_NAME
        self.cache_folder = cache_folder or (settings.MODELS_CACHE_DIR / "sbert")
        self.model = None
        self.dimension: int = 384
        self.is_loaded: bool = False

    def load(self) -> bool:
        """
        Load the SentenceTransformer model onto CPU.
        Provides clear, actionable error handling if dependencies or weights are unavailable.
        """
        if self.is_loaded and self.model is not None:
            return True

        try:
            from sentence_transformers import SentenceTransformer
            self.cache_folder.mkdir(parents=True, exist_ok=True)
            try:
                self.model = SentenceTransformer(
                    self.model_name,
                    cache_folder=str(self.cache_folder),
                    local_files_only=True
                )
            except Exception:
                self.model = SentenceTransformer(
                    self.model_name,
                    cache_folder=str(self.cache_folder)
                )
            # Verify embedding dimensionality
            sample_emb = self.model.encode(["probe verification"], show_progress_bar=False)
            if sample_emb.shape[-1] != self.dimension:
                raise ValueError(f"Model output dimension mismatch: expected {self.dimension}, got {sample_emb.shape[-1]}")
            self.is_loaded = True
            return True
        except ImportError as e:
            self.is_loaded = False
            raise RuntimeError(
                "sentence-transformers library is not installed in the virtual environment. "
                "Run: pip install sentence-transformers torch"
            ) from e
        except Exception as e:
            self.is_loaded = False
            raise RuntimeError(
                f"Failed to load Sentence-BERT model '{self.model_name}'. "
                f"Ensure network access to Hugging Face Hub or weights exist in '{self.cache_folder}'. Details: {str(e)}"
            ) from e

    def preprocess(self, text: str) -> str:
        """
        Scrub secrets, mask IPs, and normalize identifiers to ensure zero PII leakage
        before passing into the transformer encoder.
        """
        if not text or not text.strip():
            raise ValueError("Input text cannot be empty or whitespace-only.")
        cleaned = SecretMasker.sanitize(text, mask_ips=True, normalize_identifiers=True)
        return cleaned.strip()

    def encode(
        self,
        texts: Union[str, List[str]],
        batch_size: int = 32,
        normalize_embeddings: bool = True
    ) -> np.ndarray:
        """
        Encode sanitized text or a batch of texts into genuine 384-D dense embeddings.
        Returns a float32 numpy array of shape (384,) for single string or (N, 384) for list.
        """
        if not self.is_loaded:
            if not self.load():
                raise RuntimeError("SentenceBertEmbedder model is not loaded.")

        is_single = isinstance(texts, str)
        raw_list = [texts] if is_single else list(texts)

        if len(raw_list) == 0:
            return np.empty((0, self.dimension), dtype=np.float32)

        processed_list = [self.preprocess(t) for t in raw_list]
        embeddings = self.model.encode(
            processed_list,
            batch_size=batch_size,
            show_progress_bar=False,
            normalize_embeddings=normalize_embeddings,
            convert_to_numpy=True
        ).astype(np.float32)

        return embeddings[0] if is_single else embeddings

    def encode_single(self, text: str) -> np.ndarray:
        """Encode a single log text string into a 384-D dense vector."""
        return self.encode(text)
