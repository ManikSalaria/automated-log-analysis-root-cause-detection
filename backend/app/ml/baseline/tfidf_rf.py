import time
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
import numpy as np
import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.ensemble import RandomForestClassifier

from app.core.security import SecretMasker
from app.core.config import settings

class BaselineTfidfRandomForest:
    """
    Academic Baseline Model for CI/CD Log Classification.
    Strictly aligns with the NIE Mysore Department of ISE Major Project Synopsis:
    'TF-IDF and Random Forest algorithms to classify failure types'.
    """

    def __init__(self, n_estimators: int = 100, max_depth: int = 20, max_features: int = 1500):
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.max_features = max_features
        self.vectorizer: Optional[TfidfVectorizer] = None
        self.classifier: Optional[RandomForestClassifier] = None
        self.classes_: List[str] = []
        self.is_trained: bool = False

    def preprocess_text(self, text: str) -> str:
        """Sanitize secrets and normalize memory addresses and UUIDs before vectorization."""
        cleaned = SecretMasker.sanitize(text, mask_ips=True, normalize_identifiers=True)
        return cleaned.lower().strip()

    def predict(self, text: str) -> Dict[str, Any]:
        """
        Perform single-log inference with real latency benchmarking.
        """
        if not self.is_trained:
            if not self.load():
                raise RuntimeError("Baseline model is not trained or loaded from models_cache.")

        start_time = time.perf_counter()
        processed = self.preprocess_text(text)
        X = self.vectorizer.transform([processed])
        
        probabilities = self.classifier.predict_proba(X)[0]
        pred_idx = int(np.argmax(probabilities))
        pred_category = self.classes_[pred_idx]
        confidence = float(probabilities[pred_idx])
        
        latency_ms = (time.perf_counter() - start_time) * 1000.0
        
        top_indices = np.argsort(probabilities)[::-1][:5]
        top_probs = {
            str(self.classes_[i]): round(float(probabilities[i]), 4)
            for i in top_indices
        }

        return {
            "model_name": "Academic Baseline (TF-IDF + Random Forest)",
            "predicted_category": pred_category,
            "confidence": round(confidence, 4),
            "latency_ms": round(latency_ms, 2),
            "feature_dimension": len(self.vectorizer.vocabulary_),
            "top_probabilities": top_probs,
            "rationale": f"N-gram lexical matching across {len(self.vectorizer.vocabulary_)} features fit on authentic training partition"
        }

    def load(self, model_path: Optional[Path] = None, vectorizer_path: Optional[Path] = None) -> bool:
        """Load persisted baseline model and vectorizer from models_cache."""
        m_path = model_path or settings.BASELINE_MODEL_PATH
        v_path = vectorizer_path or settings.BASELINE_VECTORIZER_PATH
        if m_path.exists() and v_path.exists():
            self.classifier = joblib.load(m_path)
            self.vectorizer = joblib.load(v_path)
            self.classes_ = list(self.classifier.classes_)
            self.is_trained = True
            return True
        return False

    def get_evaluation_metrics(self) -> Dict[str, Any]:
        """Returns dynamically evaluated metrics from evaluation_manifest.json."""
        eval_path = settings.DATA_DIR / "evaluation_manifest.json"
        if eval_path.exists():
            with open(eval_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"status": "NO_EVALUATION_FOUND"}
