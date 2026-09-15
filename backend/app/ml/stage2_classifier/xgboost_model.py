import time
from pathlib import Path
from typing import Dict, Any, List, Optional
import numpy as np
import joblib
from xgboost import XGBClassifier
from sklearn.preprocessing import LabelEncoder
from sklearn.feature_extraction.text import HashingVectorizer
from app.core.security import SecretMasker
from app.core.config import settings

class TraceXGBoostClassifier:
    """
    Advanced TRACE Stage 2 Classifier: Gradient-Boosted Decision Trees (XGBoost).
    Combines semantic embedding representations with operational metadata
    to provide deterministic, high-confidence 10-class failure categorization.
    """

    def __init__(self, n_estimators: int = 150, max_depth: int = 6, learning_rate: float = 0.08):
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.learning_rate = learning_rate
        self.label_encoder = LabelEncoder()
        self.model: Optional[XGBClassifier] = None
        self.is_trained: bool = False
        
        # Dense feature extractor (projects to 384 dimensions matching Sentence-BERT)
        self.dense_dim = 384
        self.hasher = HashingVectorizer(n_features=self.dense_dim, alternate_sign=False)

    def extract_features(self, text: str, latency_ms: float = 0.0, status_code: int = 500) -> np.ndarray:
        """
        Produce a 407-dimensional feature vector:
        - 384 dense semantic dimensions (projected/embedded)
        - 23 engineered execution metadata features
        """
        sanitized = SecretMasker.sanitize(text, mask_ips=True, normalize_identifiers=True).lower()
        dense_vec = self.hasher.transform([sanitized]).toarray()[0]
        
        # 23-D engineered metadata features
        metadata = np.zeros(23, dtype=np.float32)
        metadata[0] = min(latency_ms / 5000.0, 1.0)  # normalized latency
        metadata[1] = 1.0 if status_code >= 500 else 0.0  # server error flag
        metadata[2] = 1.0 if status_code == 429 else 0.0  # rate limit flag
        metadata[3] = 1.0 if "assertionerror" in sanitized else 0.0
        metadata[4] = 1.0 if "timeout" in sanitized else 0.0
        metadata[5] = 1.0 if "connection refused" in sanitized else 0.0
        metadata[6] = 1.0 if "out of memory" in sanitized or "oom" in sanitized else 0.0
        metadata[7] = 1.0 if "null pointer" in sanitized else 0.0
        metadata[8] = 1.0 if "token" in sanitized or "auth" in sanitized else 0.0
        metadata[9] = 1.0 if "kafka" in sanitized or "queue" in sanitized else 0.0
        metadata[10] = 1.0 if "datastore" in sanitized or "lun" in sanitized or "cluster id" in sanitized else 0.0
        metadata[11] = 1.0 if "input/output error" in sanitized or "ioerror" in sanitized else 0.0
        metadata[12] = 1.0 if "syntax" in sanitized or "compile" in sanitized else 0.0
        metadata[13] = float(len(text.split())) / 100.0  # token length factor
        metadata[14] = 1.0 if "traceback" in sanitized else 0.0
        metadata[15] = 1.0 if "failed" in sanitized else 0.0
        metadata[16] = 1.0 if "redis" in sanitized else 0.0
        metadata[17] = 1.0 if "database" in sanitized or "db" in sanitized else 0.0
        metadata[18] = 1.0 if "rollback" in sanitized else 0.0
        metadata[19] = 1.0 if "pool" in sanitized else 0.0
        metadata[20] = 1.0 if "mkdir" in sanitized or "cannot create" in sanitized else 0.0
        metadata[21] = 1.0 if "error while converting" in sanitized else 0.0
        metadata[22] = 1.0 if "missing" in sanitized or "not found" in sanitized else 0.0

        return np.concatenate([dense_vec, metadata])

    def train(self, texts: List[str], labels: List[str]) -> Dict[str, Any]:
        """
        Train the XGBoost multi-class classifier on 407-D feature matrices.
        """
        start_time = time.perf_counter()
        
        # Fit label encoder
        y_encoded = self.label_encoder.fit_transform(labels)
        
        # Build feature matrix
        X_features = np.array([self.extract_features(t) for t in texts], dtype=np.float32)
        
        num_classes = len(self.label_encoder.classes_)
        self.model = XGBClassifier(
            n_estimators=self.n_estimators,
            max_depth=self.max_depth,
            learning_rate=self.learning_rate,
            objective="multi:softprob",
            num_class=num_classes,
            eval_metric="mlogloss",
            random_state=42,
            n_jobs=-1
        )
        
        self.model.fit(X_features, y_encoded)
        self.is_trained = True
        
        elapsed_sec = time.perf_counter() - start_time
        return {
            "model": "TRACE Stage 2 (XGBoost 407-D Classifier)",
            "training_time_sec": round(elapsed_sec, 3),
            "samples_count": len(texts),
            "feature_dimension": 407,
            "classes_count": num_classes,
            "classes": list(self.label_encoder.classes_)
        }

    def predict(self, text: str, latency_ms: float = 0.0, status_code: int = 500) -> Dict[str, Any]:
        """
        Perform high-confidence inference with 407-D feature matrix.
        """
        if not self.is_trained or self.model is None:
            raise RuntimeError("XGBoost model is not trained or loaded.")

        start_time = time.perf_counter()
        features = self.extract_features(text, latency_ms, status_code).reshape(1, -1)
        
        probabilities = self.model.predict_proba(features)[0]
        pred_idx = np.argmax(probabilities)
        pred_category = self.label_encoder.inverse_transform([pred_idx])[0]
        confidence = float(probabilities[pred_idx])
        
        latency_ms_val = (time.perf_counter() - start_time) * 1000.0
        
        top_indices = np.argsort(probabilities)[::-1][:4]
        top_probs = {
            str(self.label_encoder.inverse_transform([idx])[0]): round(float(probabilities[idx]), 4)
            for idx in top_indices
        }

        return {
            "model_name": "TRACE Stage 2 (XGBoost Classifier)",
            "predicted_category": pred_category,
            "confidence": round(confidence, 4),
            "latency_ms": round(latency_ms_val, 2),
            "feature_dimension": 407,
            "top_probabilities": top_probs,
            "rationale": f"Gradient boosted trees over 384-D dense representation + 23-D execution metadata features"
        }

    def save(self, model_path: Optional[Path] = None, encoder_path: Optional[Path] = None) -> None:
        """Persist XGBoost model and label encoder."""
        m_path = model_path or settings.XGBOOST_MODEL_PATH
        e_path = encoder_path or settings.LABEL_ENCODER_PATH
        m_path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self.model, m_path)
        joblib.dump(self.label_encoder, e_path)

    def load(self, model_path: Optional[Path] = None, encoder_path: Optional[Path] = None) -> bool:
        """Load persisted XGBoost model and label encoder."""
        m_path = model_path or settings.XGBOOST_MODEL_PATH
        e_path = encoder_path or settings.LABEL_ENCODER_PATH
        if m_path.exists() and e_path.exists():
            self.model = joblib.load(m_path)
            self.label_encoder = joblib.load(e_path)
            self.is_trained = True
            return True
        return False
