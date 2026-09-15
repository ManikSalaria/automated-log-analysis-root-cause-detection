import sys
from pathlib import Path

# Add backend and scripts root to sys.path
root_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(root_dir / "backend"))
sys.path.append(str(root_dir))

import pandas as pd
from app.core.config import settings
from app.ml.baseline.tfidf_rf import BaselineTfidfRandomForest
from scripts.build_dataset import build_training_dataset

def run_train_baseline():
    dataset_path = settings.PROCESSED_DATA_DIR / "labeled_logs_dataset.csv"
    if not dataset_path.exists():
        build_training_dataset()

    df = pd.read_csv(dataset_path)
    print(f"Loaded {len(df)} samples for Academic Baseline training.")
    
    baseline = BaselineTfidfRandomForest(n_estimators=100, max_features=2000)
    results = baseline.train(df["text"].tolist(), df["category"].tolist())
    
    print("Baseline Training Results:")
    for k, v in results.items():
        print(f"  - {k}: {v}")
        
    baseline.save()
    print(f"Saved baseline model and vectorizer to {settings.MODELS_CACHE_DIR}")

    # Test sample inference on real Jenkins failure
    test_sample = "AssertionError: storage cluster id is missing from config in datastore alletra_datastore_abgrdg_dnd creation"
    pred = baseline.predict(test_sample)
    print(f"\nVerification Prediction for '{test_sample}':")
    print(f"  Predicted Category: {pred['predicted_category']}")
    print(f"  Confidence: {pred['confidence']}")
    print(f"  Inference Latency: {pred['latency_ms']} ms")
    print(f"  Top Probabilities: {pred['top_probabilities']}")

if __name__ == "__main__":
    run_train_baseline()
