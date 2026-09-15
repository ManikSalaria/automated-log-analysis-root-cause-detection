import json
from pathlib import Path
from fastapi import APIRouter, HTTPException
from app.core.config import settings
from app.schemas.log_schema import EvaluationMetricsResponse

router = APIRouter()

@router.get("", response_model=EvaluationMetricsResponse)
def get_model_evaluation_metrics():
    """
    Returns dynamically evaluated performance metrics for Academic Baseline (TF-IDF + Random Forest).
    Metrics are computed strictly on the held-out test partition (15% split) and saved in evaluation_manifest.json.
    Zero hard-coded values are returned.
    """
    manifest_path = settings.DATA_DIR / "evaluation_manifest.json"
    if not manifest_path.exists():
        raise HTTPException(
            status_code=404, 
            detail="Evaluation manifest not found. Run 'scripts/train_and_evaluate_baseline.py' first."
        )

    with open(manifest_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Document genuine limitations for academic review
    limitations = [
        "Lexical n-gram features are sensitive to vocabulary shifts not observed during training.",
        "Minority categories with small incident counts (N <= 2 in test set) show higher metric variance.",
        "Sequential and temporal event ordering across distributed traces is not modeled by standard bag-of-words.",
        "Transformer-based embeddings and graph neural networks are scheduled for subsequent development phases to address these limitations."
    ]

    return EvaluationMetricsResponse(
        model_name=data["model_name"],
        dataset_split=data["dataset_split"],
        accuracy=data["accuracy"],
        precision_macro=data["precision_macro"],
        recall_macro=data["recall_macro"],
        f1_macro=data["f1_macro"],
        sample_count=data["sample_count"],
        feature_dimension=data["feature_dimension"],
        training_time_sec=data["training_time_sec"],
        avg_latency_ms=data["avg_latency_ms"],
        p95_latency_ms=data["p95_latency_ms"],
        evaluated_at=data["evaluated_at"],
        classes=data["classes"],
        per_class_metrics=data.get("per_class_metrics", {}),
        limitations=limitations
    )
