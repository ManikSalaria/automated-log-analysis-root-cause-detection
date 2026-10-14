from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.ml.baseline.tfidf_rf import BaselineTfidfRandomForest
from app.schemas.log_schema import ModelPrediction

router = APIRouter()
baseline_model = BaselineTfidfRandomForest()
baseline_model.load()

class PredictRequest(BaseModel):
    text: str

@router.post("/predict", response_model=ModelPrediction)
def predict_failure_category(request: PredictRequest):
    """
    Direct model inference endpoint for Academic Baseline (TF-IDF + Random Forest).
    Takes a log line or error trace and returns predicted category, confidence,
    top class probabilities, feature dimensionality, and real inference latency.
    """
    if not request.text or not request.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty.")

    if not baseline_model.is_trained:
        if not baseline_model.load():
            raise HTTPException(status_code=503, detail="Baseline model is not loaded. Train the model first.")

    try:
        res = baseline_model.predict(request.text)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Baseline model inference failed: {str(exc)}"
        )
    return ModelPrediction(
        model_name=res["model_name"],
        predicted_category=res["predicted_category"],
        confidence=res["confidence"],
        latency_ms=res["latency_ms"],
        feature_dimension=res["feature_dimension"],
        top_probabilities=res["top_probabilities"],
        rationale=res["rationale"]
    )
