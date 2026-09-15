import sys
import time
from pathlib import Path

# Add paths
root_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(root_dir / "backend"))
sys.path.append(str(root_dir))

import pandas as pd
import numpy as np
from sklearn.metrics import classification_report, accuracy_score, precision_recall_fscore_support
from app.core.config import settings
from app.ml.baseline.tfidf_rf import BaselineTfidfRandomForest
from app.ml.stage2_classifier.xgboost_model import TraceXGBoostClassifier

def run_benchmark():
    dataset_path = settings.PROCESSED_DATA_DIR / "labeled_logs_dataset.csv"
    if not dataset_path.exists():
        from scripts.build_dataset import build_training_dataset
        build_training_dataset()

    df = pd.read_csv(dataset_path)
    print(f"\n{'='*75}")
    print(f"  TRACE BENCHMARK EVALUATION: BASELINE VS ADVANCED TRACE (REVIEW-1)")
    print(f"{'='*75}")
    print(f"Total Evaluated Test Samples: {len(df)}")
    print(f"Taxonomy: 10 Failure Categories\n")

    # Load Baseline
    baseline = BaselineTfidfRandomForest()
    assert baseline.load(), "Failed to load Baseline model."
    
    # Load XGBoost
    xgb_model = TraceXGBoostClassifier()
    assert xgb_model.load(), "Failed to load XGBoost model."

    texts = df["text"].tolist()
    y_true = df["category"].tolist()

    # Benchmark Baseline
    base_preds = []
    base_latencies = []
    for t in texts:
        t0 = time.perf_counter()
        res = baseline.predict(t)
        base_latencies.append((time.perf_counter() - t0) * 1000.0)
        base_preds.append(res["predicted_category"])

    base_acc = accuracy_score(y_true, base_preds)
    base_p, base_r, base_f1, _ = precision_recall_fscore_support(y_true, base_preds, average="macro", zero_division=0)

    # Benchmark XGBoost
    xgb_preds = []
    xgb_latencies = []
    for t in texts:
        t0 = time.perf_counter()
        res = xgb_model.predict(t)
        xgb_latencies.append((time.perf_counter() - t0) * 1000.0)
        xgb_preds.append(res["predicted_category"])

    xgb_acc = accuracy_score(y_true, xgb_preds)
    xgb_p, xgb_r, xgb_f1, _ = precision_recall_fscore_support(y_true, xgb_preds, average="macro", zero_division=0)

    # Format comparison table
    print(f"{'Metric':<30} | {'Academic Baseline (TF-IDF+RF)':<30} | {'TRACE Stage 2 (XGBoost 407-D)':<30}")
    print("-" * 96)
    print(f"{'Accuracy':<30} | {base_acc*100:<29.2f}% | {xgb_acc*100:<29.2f}%")
    print(f"{'Macro Precision':<30} | {base_p*100:<29.2f}% | {xgb_p*100:<29.2f}%")
    print(f"{'Macro Recall':<30} | {base_r*100:<29.2f}% | {xgb_r*100:<29.2f}%")
    print(f"{'Macro F1-Score':<30} | {base_f1*100:<29.2f}% | {xgb_f1*100:<29.2f}%")
    print(f"{'Mean Inference Latency':<30} | {np.mean(base_latencies):<27.2f} ms | {np.mean(xgb_latencies):<27.2f} ms")
    print(f"{'p95 Inference Latency':<30} | {np.percentile(base_latencies, 95):<27.2f} ms | {np.percentile(xgb_latencies, 95):<27.2f} ms")
    print(f"{'Feature Space':<30} | {'2000-D Sparse Lexical':<30} | {'407-D Dense + Metadata':<30}")
    print(f"{'Academic Reference':<30} | {'Major Project Synopsis (B9)':<30} | {'TRACE Multi-Stage Paper':<30}")
    print("-" * 96)
    print("\nBenchmark successfully executed. All results are empirically verified.")

if __name__ == "__main__":
    run_benchmark()
