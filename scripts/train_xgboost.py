import sys
from pathlib import Path

# Add backend and scripts root to sys.path
root_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(root_dir / "backend"))
sys.path.append(str(root_dir))

import pandas as pd
from app.core.config import settings
from app.ml.stage2_classifier.xgboost_model import TraceXGBoostClassifier
from scripts.build_dataset import build_training_dataset

def run_train_xgboost():
    dataset_path = settings.PROCESSED_DATA_DIR / "labeled_logs_dataset.csv"
    if not dataset_path.exists():
        build_training_dataset()

    df = pd.read_csv(dataset_path)
    print(f"Loaded {len(df)} samples for TRACE Stage 2 XGBoost training.")
    
    xgb_classifier = TraceXGBoostClassifier(n_estimators=150, max_depth=6, learning_rate=0.08)
    results = xgb_classifier.train(df["text"].tolist(), df["category"].tolist())
    
    print("XGBoost Training Results:")
    for k, v in results.items():
        if k != "classes":
            print(f"  - {k}: {v}")
        
    xgb_classifier.save()
    print(f"Saved XGBoost model and label encoder to {settings.MODELS_CACHE_DIR}")

    # Test sample inference on real Jenkins failure
    test_sample = "AssertionError: storage cluster id is missing from config in datastore alletra_datastore_abgrdg_dnd creation"
    pred = xgb_classifier.predict(test_sample, latency_ms=1200.0, status_code=500)
    print(f"\nVerification Prediction for '{test_sample}':")
    print(f"  Predicted Category: {pred['predicted_category']}")
    print(f"  Confidence: {pred['confidence']}")
    print(f"  Inference Latency: {pred['latency_ms']} ms")
    print(f"  Top Probabilities: {pred['top_probabilities']}")

if __name__ == "__main__":
    run_train_xgboost()
