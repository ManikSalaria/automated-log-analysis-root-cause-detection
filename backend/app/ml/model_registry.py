"""Model Registry and Inference Router for TRACE.

Provides unified access to:
- 'baseline': TF-IDF + Random Forest (Stage 1 Academic Baseline)
- 'xgboost': Sentence-BERT + XGBoost (Stage 2 Gradient Boosted Trees)
"""

from typing import Dict, Any, Optional
from fastapi import HTTPException
from app.ml.baseline.tfidf_rf import BaselineTfidfRandomForest
from app.ml.stage2_classifier.xgboost_model import TraceXGBoostClassifier
from app.ml.stage3_gnn.gnn_pipeline import TraceGraphSAGEPipeline

_baseline_instance: Optional[BaselineTfidfRandomForest] = None
_xgboost_instance: Optional[TraceXGBoostClassifier] = None
_graphsage_instance: Optional[TraceGraphSAGEPipeline] = None

def get_baseline_model() -> BaselineTfidfRandomForest:
    global _baseline_instance
    if _baseline_instance is None:
        model = BaselineTfidfRandomForest()
        if not model.load():
            raise HTTPException(
                status_code=503,
                detail="Baseline model (TF-IDF + Random Forest) is not loaded. Run 'python scripts/bootstrap_models.py' to initialize model artifacts."
            )
        _baseline_instance = model
    return _baseline_instance

def get_xgboost_model() -> TraceXGBoostClassifier:
    global _xgboost_instance
    if _xgboost_instance is None:
        model = TraceXGBoostClassifier()
        if not model.load():
            raise HTTPException(
                status_code=503,
                detail="Stage 2 model (Sentence-BERT + XGBoost) is not loaded. Run 'python scripts/bootstrap_models.py' to initialize model artifacts."
            )
        _xgboost_instance = model
    return _xgboost_instance

def get_graphsage_model() -> TraceGraphSAGEPipeline:
    global _graphsage_instance
    if _graphsage_instance is None:
        model = TraceGraphSAGEPipeline()
        if not model.load():
            raise HTTPException(
                status_code=503,
                detail="Stage 3 model (GraphSAGE) is not loaded. Run 'python scripts/bootstrap_models.py' to initialize model artifacts."
            )
        _graphsage_instance = model
    return _graphsage_instance

def predict_with_model(text: str, model_name: str = "baseline") -> Dict[str, Any]:
    norm_name = (model_name or "baseline").strip().lower()
    if norm_name in ("baseline", "tfidf_rf", "rf"):
        model = get_baseline_model()
        return model.predict(text)
    elif norm_name in ("xgboost", "sbert_xgboost", "stage2"):
        model = get_xgboost_model()
        return model.predict(text)
    elif norm_name in ("graphsage", "stage3", "gnn", "sage"):
        model = get_graphsage_model()
        return model.predict(text)
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown model '{model_name}'. Supported models: 'baseline', 'xgboost', 'graphsage'."
        )

