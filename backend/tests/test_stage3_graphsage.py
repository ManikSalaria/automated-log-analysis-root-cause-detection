"""Automated Test Suite for TRACE Stage 3 (GraphSAGE Root Cause Classification).

Verifies:
1. IncidentGraphBuilder extracts structured log metadata and constructs hybrid node embeddings (412-D).
2. Deterministic relational edge construction (trace correlations, temporal co-occurrence, cosine similarity, self-loops).
3. Train/Val/Test boolean masks are valid, non-empty, and strictly mutually exclusive without leakage.
4. GraphSAGEClassifier model forward pass produces valid logits and supports backward gradient propagation.
5. TraceGraphSAGEPipeline correctly loads persisted checkpoint artifacts and preprocessor.
6. Inductive single-item inference dynamically constructs local ego-subgraph and returns normalized probabilities.
7. Robust handling of missing, empty, or unparsed log text without runtime crashes.
8. API endpoints support ?model=graphsage across /predict and /analyze.
9. Metrics API serves GraphSAGE manifest and side-by-side comparison across all 3 stages.
"""

import sys
from pathlib import Path

# Add backend and root to sys.path
root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(root_dir / "backend"))
sys.path.append(str(root_dir))

import pytest
import torch
import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from main import app
from app.ml.stage3_gnn.graph_builder import IncidentGraphBuilder
from app.ml.stage3_gnn.sage_model import GraphSAGEClassifier
from app.ml.stage3_gnn.gnn_pipeline import TraceGraphSAGEPipeline

client = TestClient(app)


def test_incident_graph_builder_feature_dimensions_and_metadata():
    """Verify IncidentGraphBuilder produces strictly 412-D hybrid features on synthetic incidents."""
    train_data = [
        {
            "id": 1,
            "text": "2026-09-15 10:00:00 ERROR [auth-service] Connection refused: db:5432",
            "failure_category": "DATABASE_AND_CACHE_TIMEOUT"
        },
        {
            "id": 2,
            "text": "2026-09-15 10:00:05 ERROR [auth-service] SocketTimeoutException contacting user-service",
            "failure_category": "NETWORK_DEPENDENCY_FAILURE"
        },
        {
            "id": 3,
            "text": "2026-09-15 10:00:10 WARN [storage-service] Disk quota exceeded on volume /mnt/data",
            "failure_category": "STORAGE_AND_IO_ERROR"
        },
        {
            "id": 4,
            "text": "2026-09-15 10:00:15 ERROR [worker-service] OutOfMemoryError Java heap space",
            "failure_category": "RESOURCE_EXHAUSTION_CRASH"
        }
    ]
    val_data = [
        {
            "id": 5,
            "text": "2026-09-15 10:00:20 WARN [storage-service] Disk quota warning on backup disk",
            "failure_category": "STORAGE_AND_IO_ERROR"
        }
    ]
    test_data = [
        {
            "id": 6,
            "text": "2026-09-15 10:00:25 ERROR [worker-service] OutOfMemoryError heap dump written",
            "failure_category": "RESOURCE_EXHAUSTION_CRASH"
        }
    ]

    train_df = pd.DataFrame(train_data)
    val_df = pd.DataFrame(val_data)
    test_df = pd.DataFrame(test_data)

    builder = IncidentGraphBuilder()

    # Mock embedder returning 384-D vectors for testing
    def mock_embedder(texts):
        return np.random.randn(len(texts), 384).astype(np.float32)

    graph_data, meta = builder.build_dataset(train_df, val_df, test_df, embedder=mock_embedder)

    # 6 nodes
    assert graph_data.num_nodes == 6
    # Node features must be 2D tensor: shape [6, 384 + D_struct]
    assert graph_data.x.dim() == 2
    assert graph_data.x.shape[0] == 6
    assert graph_data.x.shape[1] == 384 + builder.cat_encoder.transform([["ERROR", "auth-service", "500"]]).shape[1] + 2
    assert graph_data.x.shape[1] > 384
    assert not torch.isnan(graph_data.x).any()
    assert not torch.isinf(graph_data.x).any()

    # Labels shape [6]
    assert graph_data.y.shape == (6,)
    assert meta["train_count"] == 4
    assert meta["val_count"] == 1
    assert meta["test_count"] == 1


def test_incident_graph_builder_edges_and_masks_integrity():
    """Verify edge connectivity rules and mutually exclusive train/val/test masks."""
    train_data = [
        {
            "id": 1,
            "text": "2026-09-15T10:00:00Z ERROR [auth-service] request_id=tx-common Database error connection reset",
            "failure_category": "DATABASE_AND_CACHE_TIMEOUT"
        },
        {
            "id": 2,
            "text": "2026-09-15T10:00:05Z ERROR [auth-service] request_id=tx-common Database error read timeout",
            "failure_category": "DATABASE_AND_CACHE_TIMEOUT"
        },
        {
            "id": 3,
            "text": "2026-09-15T10:00:10Z ERROR [storage-service] request_id=tx-diff Disk corrupt",
            "failure_category": "STORAGE_AND_IO_ERROR"
        },
        {
            "id": 4,
            "text": "2026-09-15T10:00:15Z ERROR [worker-service] Auth failure 401",
            "failure_category": "AUTHENTICATION_SECURITY_ERROR"
        }
    ]
    val_data = [
        {
            "id": 5,
            "text": "2026-09-15T10:00:20Z ERROR [storage-service] request_id=tx-different Disk failure corrupt superblock",
            "failure_category": "STORAGE_AND_IO_ERROR"
        }
    ]
    test_data = [
        {
            "id": 6,
            "text": "2026-09-15T10:00:25Z ERROR [worker-service] Authentication failed 401 Unauthorized",
            "failure_category": "AUTHENTICATION_SECURITY_ERROR"
        }
    ]

    train_df = pd.DataFrame(train_data)
    val_df = pd.DataFrame(val_data)
    test_df = pd.DataFrame(test_data)

    builder = IncidentGraphBuilder()

    def mock_embedder(texts):
        # Provide identical embeddings for nodes 0 and 1 to test cosine edge creation
        emb = np.zeros((len(texts), 384), dtype=np.float32)
        emb[0, :10] = 1.0
        emb[1, :10] = 1.0
        emb[2, 10:20] = 1.0
        emb[3, 20:30] = 1.0
        return emb

    graph_data, _ = builder.build_dataset(train_df, val_df, test_df, embedder=mock_embedder)

    # Edge index structure
    assert graph_data.edge_index.dim() == 2
    assert graph_data.edge_index.shape[0] == 2
    assert graph_data.edge_index.shape[1] > 0

    # Self-loops must exist for all 6 nodes
    edges = set(zip(graph_data.edge_index[0].tolist(), graph_data.edge_index[1].tolist()))
    for i in range(6):
        assert (i, i) in edges, f"Self loop missing for node {i}"

    # Nodes 0 and 1 share trace_id 'tx-common' and identical embeddings -> must have edges
    assert (0, 1) in edges and (1, 0) in edges

    # Masks integrity
    assert graph_data.train_mask.shape == (6,)
    assert graph_data.val_mask.shape == (6,)
    assert graph_data.test_mask.shape == (6,)

    # Mutually exclusive masks
    assert not (graph_data.train_mask & graph_data.val_mask).any()
    assert not (graph_data.train_mask & graph_data.test_mask).any()
    assert not (graph_data.val_mask & graph_data.test_mask).any()
    # Total sum equals 6
    assert int(graph_data.train_mask.sum() + graph_data.val_mask.sum() + graph_data.test_mask.sum()) == 6


def test_graphsage_classifier_forward_pass_and_gradient():
    """Verify GraphSAGEClassifier forward pass produces correct logits and gradients."""
    in_dim = 412
    hidden_dim = 64
    num_classes = 5
    num_nodes = 8

    model = GraphSAGEClassifier(
        in_channels=in_dim,
        hidden_channels=hidden_dim,
        out_channels=num_classes,
        num_layers=2,
        dropout=0.2
    )
    model.train()

    # Synthetic graph
    x = torch.randn(num_nodes, in_dim, requires_grad=True)
    edge_index = torch.tensor([
        [0, 1, 2, 3, 4, 5, 6, 7, 0, 2],
        [1, 0, 3, 2, 5, 4, 7, 6, 2, 0]
    ], dtype=torch.long)

    logits = model(x, edge_index)
    assert logits.shape == (num_nodes, num_classes)
    assert not torch.isnan(logits).any()

    # Backward gradient check
    labels = torch.randint(0, num_classes, (num_nodes,))
    criterion = torch.nn.CrossEntropyLoss()
    loss = criterion(logits, labels)
    loss.backward()

    # Verify model parameters received gradients
    has_grad = any(p.grad is not None and torch.norm(p.grad) > 0 for p in model.parameters())
    assert has_grad is True


def test_graphsage_pipeline_artifact_loading():
    """Verify saved GraphSAGE checkpoint and preprocessor load correctly."""
    pipeline = TraceGraphSAGEPipeline()
    loaded = pipeline.load()

    assert loaded is True
    assert pipeline.is_trained is True
    assert pipeline.feature_dimension == 412
    assert len(pipeline.classes_) == 10
    assert "DATABASE_AND_CACHE_TIMEOUT" in pipeline.classes_
    assert "STORAGE_AND_IO_ERROR" in pipeline.classes_
    assert "ENVIRONMENT_AND_PIPELINE_ERROR" in pipeline.classes_
    assert pipeline.ref_embeddings is not None
    assert pipeline.ref_embeddings.shape[1] == 384


def test_graphsage_inductive_prediction_structure_and_probabilities():
    """Verify GraphSAGE inductive inference outputs valid categories, probabilities, and rationale."""
    pipeline = TraceGraphSAGEPipeline()
    assert pipeline.load() is True

    sample_log = "2026-09-15 14:22:10 ERROR [catalog-service] Connection reset by peer contacting postgres:5432"
    pred = pipeline.predict(sample_log)

    assert pred["model_name"] == "TRACE Stage 3 (GraphSAGE)"
    assert pred["predicted_category"] in pipeline.classes_
    assert 0.0 <= pred["confidence"] <= 1.0
    assert pred["latency_ms"] > 0
    assert pred["feature_dimension"] == 412
    assert isinstance(pred["top_probabilities"], dict)
    assert len(pred["top_probabilities"]) > 0

    # Probabilities bounded between 0 and 1
    prob_sum = 0.0
    for cat, prob in pred["top_probabilities"].items():
        assert 0.0 <= prob <= 1.0
        prob_sum += prob
    assert 0.8 <= prob_sum <= 1.05

    # Rationale and neighbors count
    assert "GraphSAGE" in pred["rationale"]
    assert "graph_neighbors_aggregated" in pred
    assert pred["graph_neighbors_aggregated"] >= 0


def test_graphsage_handling_missing_and_partial_metadata():
    """Verify GraphSAGE handles completely unparsed or unstructured text without failure."""
    pipeline = TraceGraphSAGEPipeline()
    assert pipeline.load() is True

    # 1. Plain text with no structured metadata
    pred_plain = pipeline.predict("Disk I/O error writing block to volume")
    assert pred_plain["predicted_category"] in pipeline.classes_
    assert 0.0 <= pred_plain["confidence"] <= 1.0

    # 2. Pytest assertion trace
    pred_pytest = pipeline.predict("AssertionError: Expected 200 OK but received 503 Service Unavailable")
    assert pred_pytest["predicted_category"] in pipeline.classes_
    assert 0.0 <= pred_pytest["confidence"] <= 1.0

    # 3. Empty input rejection
    with pytest.raises(ValueError, match="Input text cannot be empty"):
        pipeline.predict("")
    with pytest.raises(ValueError, match="Input text cannot be empty"):
        pipeline.predict("   \n\t  ")


def test_api_predict_graphsage_model_selection():
    """Verify /classification/predict successfully runs GraphSAGE when requested."""
    # Via JSON body
    resp_body = client.post(
        "/api/v1/classification/predict",
        json={
            "text": "2026-09-15 10:14:02 ERROR [auth-service] Connection reset by peer: oauth2.internal:443",
            "model": "graphsage"
        }
    )
    assert resp_body.status_code == 200
    data_body = resp_body.json()
    assert "GraphSAGE" in data_body["model_name"]
    assert data_body["feature_dimension"] == 412
    assert data_body["rationale"] is not None

    # Via Query Parameter (?model=graphsage)
    resp_query = client.post(
        "/api/v1/classification/predict?model=graphsage",
        json={"text": "Disk space full writing cache file"}
    )
    assert resp_query.status_code == 200
    data_query = resp_query.json()
    assert "GraphSAGE" in data_query["model_name"]


def test_api_analyze_graphsage_model_selection():
    """Verify /analysis/analyze incorporates GraphSAGE inference and produces root cause candidates."""
    resp = client.post(
        "/api/v1/analysis/analyze?model=graphsage",
        json={
            "log_text": "2026-09-15 10:14:02 ERROR [order-service] Redis connection pool timeout after 5000ms"
        }
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "classification" in data
    assert "GraphSAGE" in data["classification"]["model_name"]
    assert data["classification"]["feature_dimension"] == 412
    assert "root_cause" in data
    assert data["is_failure"] is True


def test_api_metrics_graphsage_model_selection():
    """Verify /metrics?model=graphsage returns Stage 3 GraphSAGE evaluation results."""
    resp = client.get("/api/v1/metrics?model=graphsage")
    assert resp.status_code == 200
    data = resp.json()

    assert data["model_name"] == "TRACE Stage 3 (GraphSAGE)"
    assert data["feature_dimension"] == 412
    assert data["sample_count"] == 57
    assert 0.0 <= data["accuracy"] <= 1.0 or 0.0 <= data["accuracy"] <= 100.0
    assert 0.0 <= data["f1_macro"] <= 1.0 or 0.0 <= data["f1_macro"] <= 100.0
    assert len(data["classes"]) == 10
    assert len(data["limitations"]) > 0


def test_api_metrics_comparison_includes_all_three_models():
    """Verify /metrics/comparison serves side-by-side metrics across Baseline, XGBoost, and GraphSAGE."""
    resp = client.get("/api/v1/metrics/comparison")
    assert resp.status_code == 200
    data = resp.json()

    # Must contain all 3 model blocks
    assert "baseline" in data
    assert "xgboost" in data
    assert "graphsage" in data

    assert data["baseline"]["feature_dimension"] == 1500
    assert data["xgboost"]["feature_dimension"] == 384
    assert data["graphsage"]["feature_dimension"] == 412

    # Comparison summary must contain deltas
    summary = data["comparison_summary"]
    assert "accuracy_delta" in summary
    assert "f1_macro_delta" in summary
    assert "graphsage_accuracy_delta" in summary
    assert "graphsage_f1_macro_delta" in summary


def test_model_selection_and_requested_model_consistency_across_all_stages():
    """Regression test: Verify that requested model is accurately sent and returned for Stage 1, Stage 2, and GraphSAGE."""
    test_input = "2026-09-15 10:14:02 ERROR [order-service] Redis connection pool timeout after 5000ms"

    models_to_test = [
        ("baseline", "Academic Baseline (TF-IDF + Random Forest)", 1500),
        ("xgboost", "TRACE Stage 2 (Sentence-BERT + XGBoost)", 384),
        ("graphsage", "TRACE Stage 3 (GraphSAGE)", 412)
    ]

    for model_key, expected_model_name, expected_dim in models_to_test:
        # 1. Test /api/v1/analysis/analyze with model in request body
        resp_anl = client.post(
            "/api/v1/analysis/analyze",
            json={"log_text": test_input, "model": model_key}
        )
        assert resp_anl.status_code == 200, f"Analysis failed for {model_key}: {resp_anl.text}"
        data_anl = resp_anl.json()
        clf_anl = data_anl["classification"]

        assert clf_anl["requested_model"] == model_key, f"Expected requested_model '{model_key}', got '{clf_anl.get('requested_model')}'"
        assert clf_anl["model_name"] == expected_model_name, f"Expected model_name '{expected_model_name}', got '{clf_anl.get('model_name')}'"
        assert clf_anl["feature_dimension"] == expected_dim

        # 2. Test /api/v1/classification/predict with model in request body
        resp_pred = client.post(
            "/api/v1/classification/predict",
            json={"text": test_input, "model": model_key}
        )
        assert resp_pred.status_code == 200, f"Prediction failed for {model_key}: {resp_pred.text}"
        data_pred = resp_pred.json()
        assert data_pred["requested_model"] == model_key
        assert data_pred["model_name"] == expected_model_name
        assert data_pred["feature_dimension"] == expected_dim


def test_metrics_default_serves_canonical_group_split():
    """Regression test: Verify /metrics serves the canonical group-aware metrics (72.81% F1) by default instead of outdated naive split (91.34%)."""
    resp = client.get("/api/v1/metrics")
    assert resp.status_code == 200
    data = resp.json()

    # Baseline on canonical group-aware split must report 72.81% macro-F1 and 80.70% accuracy
    assert abs(data["f1_macro"] - 0.7281) < 1e-3, f"Expected 0.7281 macro-F1, got {data['f1_macro']}"
    assert abs(data["accuracy"] - 0.8070) < 1e-3, f"Expected 0.8070 accuracy, got {data['accuracy']}"
    assert "Canonical Group" in data["dataset_split"]
    assert data["sample_count"] == 57

