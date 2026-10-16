from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from app.ml.model_registry import predict_with_model
from app.schemas.log_schema import ModelPrediction

router = APIRouter()

class PredictRequest(BaseModel):
    text: str
    model: Optional[str] = "baseline"

@router.post("/predict", response_model=ModelPrediction)
def predict_failure_category(
    request: PredictRequest,
    model: Optional[str] = Query(None, description="Model selection: 'baseline', 'xgboost', or 'graphsage'")
):
    """
    Direct model inference endpoint.
    Supports model selection between:
    - 'baseline': TF-IDF + Random Forest (Stage 1 Academic Baseline)
    - 'xgboost': Sentence-BERT + XGBoost (Stage 2 Gradient Boosted Trees)
    - 'graphsage': Incident Graph Neural Network (Stage 3 GraphSAGE)

    Takes a log line or error trace and returns predicted category, confidence,
    top class probabilities, feature dimensionality, and real inference latency.
    """
    if not request.text or not request.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty.")

    selected_model = (model or request.model or "baseline").strip()
    res = predict_with_model(request.text, model_name=selected_model)

    return ModelPrediction(
        model_name=res["model_name"],
        predicted_category=res["predicted_category"],
        confidence=res["confidence"],
        latency_ms=res["latency_ms"],
        feature_dimension=res["feature_dimension"],
        top_probabilities=res["top_probabilities"],
        rationale=res["rationale"],
        requested_model=selected_model
    )


@router.post("/classify", response_model=ModelPrediction)
def classify_failure_category(
    request: PredictRequest,
    model: Optional[str] = Query(None, description="Model selection: 'baseline', 'xgboost', or 'graphsage'")
):
    """Alias for /api/v1/classification/predict."""
    return predict_failure_category(request, model)

