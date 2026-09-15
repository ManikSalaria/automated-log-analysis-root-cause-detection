import sys
import time
import json
from pathlib import Path
import pandas as pd
import numpy as np
import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score, precision_recall_fscore_support, 
    confusion_matrix, classification_report
)

# Add backend and root to path
root_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(root_dir / "backend"))
sys.path.append(str(root_dir))

from app.core.config import settings
from app.core.security import SecretMasker
from app.core.database import get_connection, init_database

class AcademicBaselineTrainer:
    """
    Academic Baseline (TF-IDF + Random Forest) Trainer & Evaluator.
    Adheres to strict empirical standards:
    - Vectorizer fit ONLY on training incidents (zero leakage).
    - Unigram + bigram lexical representation with controlled feature capacity.
    - True evaluation on held-out test incidents.
    - Persists evaluation metrics to SQLite.
    """

    def __init__(
        self, 
        max_features: int = 1500,
        n_estimators: int = 100,
        max_depth: int = 20,
        random_state: int = 42
    ):
        self.max_features = max_features
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.random_state = random_state

        self.vectorizer = TfidfVectorizer(
            ngram_range=(1, 2),
            max_features=self.max_features,
            stop_words="english",
            token_pattern=r"(?u)\b[a-zA-Z_][a-zA-Z0-9_\-\.]{2,}\b"
        )
        self.classifier = RandomForestClassifier(
            n_estimators=self.n_estimators,
            max_depth=self.max_depth,
            random_state=self.random_state,
            n_jobs=-1
        )
        self.classes_: list = []

    def preprocess(self, text: str) -> str:
        # Scrub credentials, mask IP addresses, normalize identifiers
        cleaned = SecretMasker.sanitize(text, mask_ips=True, normalize_identifiers=True)
        return cleaned.lower().strip()

    def train_and_evaluate(self) -> dict:
        processed_dir = settings.PROCESSED_DATA_DIR
        train_path = processed_dir / "train_incidents.csv"
        val_path = processed_dir / "val_incidents.csv"
        test_path = processed_dir / "test_incidents.csv"

        assert train_path.exists() and test_path.exists(), "Dataset split missing. Run construct_authentic_dataset.py first."

        train_df = pd.read_csv(train_path)
        val_df = pd.read_csv(val_path)
        test_df = pd.read_csv(test_path)

        print(f"\n{'='*80}")
        print("TRAINING ACADEMIC BASELINE: TF-IDF + RANDOM FOREST")
        print(f"{'='*80}")
        print(f"Hyperparameters: n_estimators={self.n_estimators}, max_depth={self.max_depth}, max_features={self.max_features}, seed={self.random_state}")
        print(f"Training partition: {len(train_df)} authentic incidents")

        t0 = time.perf_counter()

        # Step 1: Preprocess training texts
        train_texts = [self.preprocess(t) for t in train_df["text"]]
        train_labels = train_df["failure_category"].tolist()

        # Step 2: Fit vectorizer ONLY on training partition (zero leakage)
        X_train = self.vectorizer.fit_transform(train_texts)
        y_train = np.array(train_labels)

        # Step 3: Fit Random Forest
        self.classifier.fit(X_train, y_train)
        self.classes_ = list(self.classifier.classes_)
        training_time = time.perf_counter() - t0

        print(f"Training completed in {training_time:.3f} seconds.")
        print(f"Learned vocabulary size: {len(self.vectorizer.vocabulary_)} n-grams.")

        # Step 4: Evaluate on Validation Set
        val_texts = [self.preprocess(t) for t in val_df["text"]]
        X_val = self.vectorizer.transform(val_texts)
        val_preds = self.classifier.predict(X_val)
        val_acc = accuracy_score(val_df["failure_category"], val_preds)
        val_p, val_r, val_f1, _ = precision_recall_fscore_support(
            val_df["failure_category"], val_preds, average="macro", zero_division=0
        )
        print(f"\nValidation Set Results ({len(val_df)} incidents):")
        print(f"  - Accuracy:       {val_acc*100:.2f}%")
        print(f"  - Macro F1:       {val_f1*100:.2f}%")

        # Step 5: Evaluate on Strictly Held-out Test Set (Single Evaluation, No peeking)
        test_texts = [self.preprocess(t) for t in test_df["text"]]
        
        # Benchmark inference latency per sample
        latencies_ms = []
        test_preds = []
        test_probas = []
        for text in test_texts:
            t_inf = time.perf_counter()
            feat = self.vectorizer.transform([text])
            proba = self.classifier.predict_proba(feat)[0]
            pred_idx = np.argmax(proba)
            latencies_ms.append((time.perf_counter() - t_inf) * 1000.0)
            test_preds.append(self.classes_[pred_idx])
            test_probas.append(proba)

        test_labels = test_df["failure_category"].tolist()
        test_acc = accuracy_score(test_labels, test_preds)
        test_p, test_r, test_f1, _ = precision_recall_fscore_support(
            test_labels, test_preds, average="macro", zero_division=0
        )
        cm = confusion_matrix(test_labels, test_preds, labels=self.classes_)

        print(f"\n{'='*80}")
        print(f"HELD-OUT TEST SET EVALUATION ({len(test_df)} INCIDENTS)")
        print(f"{'='*80}")
        print(f"  - Test Accuracy:        {test_acc*100:.2f}%")
        print(f"  - Test Macro Precision: {test_p*100:.2f}%")
        print(f"  - Test Macro Recall:    {test_r*100:.2f}%")
        print(f"  - Test Macro F1-Score:  {test_f1*100:.2f}%")
        print(f"  - Mean Latency:         {np.mean(latencies_ms):.2f} ms")
        print(f"  - p95 Latency:          {np.percentile(latencies_ms, 95):.2f} ms")

        # Detailed Classification Report
        clf_report = classification_report(test_labels, test_preds, labels=self.classes_, zero_division=0, output_dict=True)
        print("\nPer-Category Test Breakdown:")
        for cat in self.classes_:
            if cat in clf_report:
                s = clf_report[cat]
                print(f"  - {cat:<35}: P={s['precision']*100:>5.1f}%  R={s['recall']*100:>5.1f}%  F1={s['f1-score']*100:>5.1f}% (N={s['support']})")

        # Step 6: Persist Models
        settings.MODELS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        model_path = settings.BASELINE_MODEL_PATH
        vec_path = settings.BASELINE_VECTORIZER_PATH
        joblib.dump(self.classifier, model_path)
        joblib.dump(self.vectorizer, vec_path)
        print(f"\nPersisted baseline model to: {model_path}")
        print(f"Persisted vectorizer to:     {vec_path}")

        # Step 7: Persist Evaluation Record to SQLite & JSON
        evaluation_record = {
            "model_name": "Academic Baseline (TF-IDF + Random Forest)",
            "dataset_split": "Held-out Test (15% partitioned before training)",
            "accuracy": round(float(test_acc), 4),
            "precision_macro": round(float(test_p), 4),
            "recall_macro": round(float(test_r), 4),
            "f1_macro": round(float(test_f1), 4),
            "sample_count": len(test_df),
            "feature_dimension": len(self.vectorizer.vocabulary_),
            "training_time_sec": round(float(training_time), 4),
            "avg_latency_ms": round(float(np.mean(latencies_ms)), 2),
            "p95_latency_ms": round(float(np.percentile(latencies_ms, 95)), 2),
            "evaluated_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            "classes": self.classes_,
            "confusion_matrix": cm.tolist(),
            "per_class_metrics": {
                c: {
                    "precision": round(clf_report[c]["precision"], 4),
                    "recall": round(clf_report[c]["recall"], 4),
                    "f1": round(clf_report[c]["f1-score"], 4),
                    "support": clf_report[c]["support"]
                }
                for c in self.classes_ if c in clf_report
            }
        }

        # Save to JSON manifest
        eval_path = settings.DATA_DIR / "evaluation_manifest.json"
        with open(eval_path, "w", encoding="utf-8") as f:
            json.dump(evaluation_record, f, indent=2)

        # Save to SQLite
        try:
            init_database()
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO model_evaluations (
                model_name, dataset_split, accuracy, precision_macro, recall_macro, 
                f1_macro, sample_count, feature_dimension, training_time_sec, 
                avg_latency_ms, p95_latency_ms, evaluated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                evaluation_record["model_name"],
                evaluation_record["dataset_split"],
                evaluation_record["accuracy"],
                evaluation_record["precision_macro"],
                evaluation_record["recall_macro"],
                evaluation_record["f1_macro"],
                evaluation_record["sample_count"],
                evaluation_record["feature_dimension"],
                evaluation_record["training_time_sec"],
                evaluation_record["avg_latency_ms"],
                evaluation_record["p95_latency_ms"],
                evaluation_record["evaluated_at"]
            ))
            conn.commit()
            conn.close()
            print("Evaluation record successfully committed to SQLite database.")
        except Exception as e:
            print(f"Warning: Could not save to SQLite: {e}")

        return evaluation_record

if __name__ == "__main__":
    trainer = AcademicBaselineTrainer()
    metrics = trainer.train_and_evaluate()
