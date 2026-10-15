"""Automated Test Suite for TRACE Stage 2 (Sentence-BERT + XGBoost).

Verifies:
1. Sentence-BERT embedder produces valid 384-dimensional dense vectors.
2. Embedder rejects empty/whitespace input strings.
3. TraceXGBoostClassifier loads persisted artifacts correctly.
4. XGBoost inference produces valid categories and normalized probability distributions.
5. API endpoints support model selection (?model=xgboost vs ?model=baseline) across /predict and /analyze.
6. API returns 400 on unknown model name or empty log text.
7. Baseline remains default model when model parameter is omitted.
8. Metrics API provides both individual model metrics and side-by-side comparison.
"""

import sys
from pathlib import Path

# Add backend and root to sys.path
root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(root_dir / "backend"))
sys.path.append(str(root_dir))

import pytest
import numpy as np
from fastapi.testclient import TestClient
from main import app
from app.ml.stage1_embedder.sbert_embedder import SentenceBertEmbedder
from app.ml.stage2_classifier.xgboost_model import TraceXGBoostClassifier

client = TestClient(app)

def test_sbert_embedder_dimensions():
    """Verify Sentence-BERT produces strictly 384-dimensional dense vectors."""
    embedder = SentenceBertEmbedder()
    test_text = "2026-02-25 10:14:02 ERROR [auth-service] Connection reset by peer: oauth2.internal:443"
    vector = embedder.encode_single(test_text)
    
    assert isinstance(vector, np.ndarray)
    assert vector.shape == (384,)
    assert not np.isnan(vector).any()
    assert not np.isinf(vector).any()

def test_sbert_embedder_empty_input_rejected():
    """Verify embedder rejects empty or whitespace-only inputs."""
    embedder = SentenceBertEmbedder()
    with pytest.raises(ValueError, match="Input text cannot be empty"):
        embedder.encode_single("")
    with pytest.raises(ValueError, match="Input text cannot be empty"):
        embedder.encode_single("   \n\t  ")

def test_xgboost_classifier_artifact_loading():
    """Verify saved XGBoost classifier and label encoder load successfully."""
    xgb = TraceXGBoostClassifier()
    loaded = xgb.load()
    assert loaded is True
    assert xgb.is_trained is True
    assert xgb.feature_dimension == 384
    assert len(xgb.classes_) == 10
    assert "DATABASE_AND_CACHE_TIMEOUT" in xgb.classes_
    assert "STORAGE_AND_IO_ERROR" in xgb.classes_

def test_xgboost_prediction_structure_and_probabilities():
    """Verify XGBoost prediction output schema, confidence bounds, and probabilities."""
    xgb = TraceXGBoostClassifier()
    assert xgb.load() is True
    
    sample_log = "ERROR:morpheus_automation.tests.conftest:Actual error is: storage cluster id is missing from config"
    pred = xgb.predict(sample_log)
    
    assert pred["model_name"] == "TRACE Stage 2 (Sentence-BERT + XGBoost)"
    assert pred["predicted_category"] == "STORAGE_AND_IO_ERROR"
    assert 0.0 <= pred["confidence"] <= 1.0
    assert pred["latency_ms"] > 0
    assert pred["feature_dimension"] == 384
    assert isinstance(pred["top_probabilities"], dict)
    assert len(pred["top_probabilities"]) > 0
    # Probabilities should be bounded between 0 and 1
    for cat, prob in pred["top_probabilities"].items():
        assert 0.0 <= prob <= 1.0

def test_api_predict_default_is_baseline():
    """Verify /classification/predict defaults to Baseline model when model parameter is omitted."""
    resp = client.post(
        "/api/v1/classification/predict",
        json={"text": "java.lang.NullPointerException: Cannot invoke method on null object"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "Baseline" in data["model_name"]
    assert data["feature_dimension"] == 1500

def test_api_predict_xgboost_model_selection():
    """Verify /classification/predict runs XGBoost when model='xgboost' is specified in body or query."""
    # Via JSON body
    resp_body = client.post(
        "/api/v1/classification/predict",
        json={
            "text": "2026-09-15T09:38:30.123Z ERROR [auth-service] request_id=req-893612 status=502 latency_ms=2653 Database connection timeout",
            "model": "xgboost"
        }
    )
    assert resp_body.status_code == 200
    data_body = resp_body.json()
    assert "XGBoost" in data_body["model_name"]
    assert data_body["feature_dimension"] == 384
    assert data_body["predicted_category"] == "DATABASE_AND_CACHE_TIMEOUT"

    # Via Query param
    resp_query = client.post(
        "/api/v1/classification/predict?model=xgboost",
        json={"text": "Connection timed out connecting to kafka:9092"}
    )
    assert resp_query.status_code == 200
    data_query = resp_query.json()
    assert "XGBoost" in data_query["model_name"]
    assert data_query["feature_dimension"] == 384

def test_api_predict_invalid_model_returns_400():
    """Verify /classification/predict returns 400 on unrecognized model name."""
    resp = client.post(
        "/api/v1/classification/predict",
        json={"text": "Some error log", "model": "invalid_model_v99"}
    )
    assert resp.status_code == 400
    assert "Unknown model" in resp.json()["detail"]

def test_api_analyze_xgboost_model_selection():
    """Verify /analysis/analyze integrates XGBoost model and delivers root cause analysis."""
    resp = client.post(
        "/api/v1/analysis/analyze",
        json={
            "log_text": "2026-09-15T09:38:30.123Z ERROR [auth-service] request_id=req-893612 status=502 latency_ms=2653 Database connection timeout",
            "model": "xgboost"
        }
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "XGBoost" in data["classification"]["model_name"]
    assert data["classification"]["feature_dimension"] == 384
    assert data["classification"]["predicted_category"] == "DATABASE_AND_CACHE_TIMEOUT"
    assert "root_cause" in data
    assert data["root_cause"]["failure_category"] == "DATABASE_AND_CACHE_TIMEOUT"
    assert data["is_failure"] is True

def test_api_metrics_model_selection():
    """Verify /metrics returns metrics for baseline, xgboost, and 400 for unknown models."""
    # Baseline Canonical Default (Leakage-Free)
    r_base = client.get("/api/v1/metrics?model=baseline")
    assert r_base.status_code == 200
    d_base = r_base.json()
    assert "Baseline" in d_base["model_name"]
    assert d_base["feature_dimension"] == 1500
    assert d_base["accuracy"] == 0.8070

    # Baseline Naive (Historical Split)
    r_base_naive = client.get("/api/v1/metrics?model=baseline&split=naive")
    assert r_base_naive.status_code == 200
    assert r_base_naive.json()["accuracy"] == 0.9298

    # Baseline Canonical Explicit (Leakage-Free)
    r_base_canon = client.get("/api/v1/metrics?model=baseline&split=canonical")
    assert r_base_canon.status_code == 200
    assert r_base_canon.json()["accuracy"] == 0.8070

    # XGBoost Canonical Default (Leakage-Free)
    r_xgb = client.get("/api/v1/metrics?model=xgboost")
    assert r_xgb.status_code == 200
    d_xgb = r_xgb.json()
    assert "XGBoost" in d_xgb["model_name"]
    assert d_xgb["feature_dimension"] == 384
    assert d_xgb["accuracy"] == 0.7719

    # XGBoost Naive (Historical Split)
    r_xgb_naive = client.get("/api/v1/metrics?model=xgboost&split=naive")
    assert r_xgb_naive.status_code == 200
    assert r_xgb_naive.json()["accuracy"] == 0.9649

    # XGBoost Canonical Explicit (Leakage-Free)
    r_xgb_canon = client.get("/api/v1/metrics?model=xgboost&split=canonical")
    assert r_xgb_canon.status_code == 200
    assert r_xgb_canon.json()["accuracy"] == 0.7719

    # Invalid model
    r_inv = client.get("/api/v1/metrics?model=gpt_detector")
    assert r_inv.status_code == 400

def test_api_metrics_comparison_endpoint():
    """Verify /metrics/comparison delivers side-by-side empirical performance summary."""
    # Canonical Leakage-Free Default
    resp = client.get("/api/v1/metrics/comparison")
    assert resp.status_code == 200
    data = resp.json()
    assert "baseline" in data
    assert "xgboost" in data
    assert "comparison_summary" in data
    assert data["baseline"]["accuracy"] == 0.8070
    assert data["xgboost"]["accuracy"] == 0.7719

    # Historical Naive
    resp_naive = client.get("/api/v1/metrics/comparison?split=naive")
    assert resp_naive.status_code == 200
    data_naive = resp_naive.json()
    assert data_naive["comparison_summary"]["accuracy_delta"] > 0
    assert data_naive["xgboost"]["accuracy"] == 0.9649

def test_api_metrics_audit_endpoint():
    """Verify /metrics/audit delivers Phase 2.1 Leakage-Resistant audit data."""
    resp = client.get("/api/v1/metrics/audit")
    assert resp.status_code == 200
    data = resp.json()
    assert "leakage_eliminated" in data
    assert data["leakage_eliminated"]["exact_text_overlap"] == 0
    assert data["leakage_eliminated"]["signature_overlap"] == 0
    assert "comparison_with_original_evaluation" in data
    assert data["baseline_metrics"]["accuracy"] == 0.8070
    assert data["xgboost_metrics"]["accuracy"] == 0.7719
