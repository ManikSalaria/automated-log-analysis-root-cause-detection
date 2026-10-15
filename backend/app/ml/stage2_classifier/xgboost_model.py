"""XGBoost Failure Classifier Engine (TRACE Stage 2).

Combines genuine Sentence-BERT dense semantic embeddings (384-D) with
Gradient-Boosted Decision Trees (XGBClassifier) for multi-class CI/CD
failure categorization across authentic failure modes.
"""

import time
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
import numpy as np
import joblib
from xgboost import XGBClassifier
from sklearn.preprocessing import LabelEncoder
from app.core.config import settings
from app.ml.stage1_embedder.sbert_embedder import SentenceBertEmbedder

class TraceXGBoostClassifier:
    """
    TRACE Stage 2 Classifier: Gradient-Boosted Decision Trees over
    genuine 384-dimensional Sentence-BERT dense semantic representations.
    """

    def __init__(
        self,
        n_estimators: int = 100,
        max_depth: int = 4,
        learning_rate: float = 0.05,
        random_state: int = 42
    ):
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.learning_rate = learning_rate
        self.random_state = random_state

        self.embedder = SentenceBertEmbedder()
        self.label_encoder = LabelEncoder()
        self.classifier: Optional[XGBClassifier] = None
        self.is_trained: bool = False
        self.feature_dimension: int = 384
        self.classes_: List[str] = []

    def train(self, texts: List[str], labels: List[str]) -> Dict[str, Any]:
        """
        Fit the XGBoost multi-class classifier on genuine 384-D Sentence-BERT embeddings.
        All preprocessing is strictly fit on training inputs only.
        """
        start_time = time.perf_counter()

        if len(texts) == 0 or len(labels) == 0:
            raise ValueError("Training inputs cannot be empty.")
        if len(texts) != len(labels):
            raise ValueError(f"Mismatch between texts ({len(texts)}) and labels ({len(labels)}).")

        # 1. Encode training labels
        y_encoded = self.label_encoder.fit_transform(labels)
        self.classes_ = [str(c) for c in self.label_encoder.classes_]

        # 2. Extract genuine 384-D Sentence-BERT representations
        if not self.embedder.is_loaded:
            self.embedder.load()

        X_train = self.embedder.encode(texts, batch_size=32, normalize_embeddings=True)
        self.feature_dimension = X_train.shape[1]

        # 3. Fit XGBClassifier
        self.classifier = XGBClassifier(
            n_estimators=self.n_estimators,
            max_depth=self.max_depth,
            learning_rate=self.learning_rate,
            random_state=self.random_state,
            eval_metric="mlogloss",
            tree_method="hist",
            n_jobs=-1
        )
        self.classifier.fit(X_train, y_encoded)
        self.is_trained = True

        duration = time.perf_counter() - start_time
        return {
            "training_time_sec": round(duration, 3),
            "sample_count": len(texts),
            "feature_dimension": self.feature_dimension,
            "classes_count": len(self.classes_),
            "classes": self.classes_
        }

    def predict(self, text: str) -> Dict[str, Any]:
        """
        Predict failure category from log text using Sentence-BERT + XGBoost.
        Measures real inference latency (including embedding time) on CPU.
        """
        if not text or not text.strip():
            raise ValueError("Input text cannot be empty or whitespace.")

        if not self.is_trained:
            if not self.load():
                raise RuntimeError("TRACE XGBoost model is not loaded. Train or populate model cache first.")

        start_time = time.perf_counter()

        # Generate genuine 384-D embedding
        emb = self.embedder.encode(text, normalize_embeddings=True)
        features = np.expand_dims(emb, axis=0)

        probabilities = self.classifier.predict_proba(features)[0]
        pred_idx = int(np.argmax(probabilities))
        pred_category = str(self.label_encoder.inverse_transform([pred_idx])[0])
        confidence = float(probabilities[pred_idx])

        latency_ms = (time.perf_counter() - start_time) * 1000.0

        top_indices = np.argsort(probabilities)[::-1][:4]
        top_probs = {
            str(self.label_encoder.inverse_transform([idx])[0]): round(float(probabilities[idx]), 4)
            for idx in top_indices
        }

        return {
            "model_name": "TRACE Stage 2 (Sentence-BERT + XGBoost)",
            "predicted_category": pred_category,
            "confidence": round(confidence, 4),
            "latency_ms": round(latency_ms, 2),
            "feature_dimension": self.feature_dimension,
            "top_probabilities": top_probs,
            "rationale": (
                f"Predicted by Gradient-Boosted Trees (XGBoost) over 384-dimensional "
                f"dense semantic embeddings from sentence-transformers/all-MiniLM-L6-v2."
            )
        }

    def save(
        self,
        model_path: Optional[Path] = None,
        encoder_path: Optional[Path] = None,
        manifest_path: Optional[Path] = None
    ) -> None:
        """Persist fitted XGBoost model, label encoder, and provenance manifest."""
        if not self.is_trained or self.classifier is None:
            raise RuntimeError("Cannot save an unfitted XGBoost model.")

        m_path = model_path or settings.XGBOOST_MODEL_PATH
        e_path = encoder_path or settings.XGBOOST_ENCODER_PATH
        man_path = manifest_path or settings.XGBOOST_MANIFEST_PATH

        m_path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self.classifier, m_path)
        joblib.dump(self.label_encoder, e_path)

        manifest = {
            "model_name": "TRACE Stage 2 (Sentence-BERT + XGBoost)",
            "embedding_model": settings.SBERT_MODEL_NAME,
            "feature_dimension": self.feature_dimension,
            "classes": self.classes_,
            "n_estimators": self.n_estimators,
            "max_depth": self.max_depth,
            "learning_rate": self.learning_rate,
            "random_state": self.random_state
        }
        with open(man_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

    def load(
        self,
        model_path: Optional[Path] = None,
        encoder_path: Optional[Path] = None,
        manifest_path: Optional[Path] = None
    ) -> bool:
        """Load persisted XGBoost model and label encoder from disk."""
        m_path = model_path or settings.XGBOOST_MODEL_PATH
        e_path = encoder_path or settings.XGBOOST_ENCODER_PATH
        man_path = manifest_path or settings.XGBOOST_MANIFEST_PATH

        if not (m_path.exists() and e_path.exists()):
            self.is_trained = False
            return False

        try:
            self.classifier = joblib.load(m_path)
            self.label_encoder = joblib.load(e_path)
            self.classes_ = [str(c) for c in self.label_encoder.classes_]

            if man_path.exists():
                with open(man_path, "r", encoding="utf-8") as f:
                    manifest = json.load(f)
                    self.feature_dimension = manifest.get("feature_dimension", 384)
            else:
                self.feature_dimension = 384

            if not self.embedder.is_loaded:
                self.embedder.load()

            self.is_trained = True
            return True
        except Exception:
            self.is_trained = False
            return False
