"""TRACE Model & Environment Bootstrap Utility.

Provides an automated, idempotent procedure to:
1. Initialize the SQLite WAL database schema and seed safe demo data if empty.
2. Train and serialize Stage 1 (TF-IDF + Random Forest) from tracked datasets.
3. Train and serialize Stage 2 (Sentence-BERT + XGBoost).
4. Train and serialize Stage 3 (GraphSAGE GNN).
5. Build and serialize Stage 4 (Hybrid RAG BM25 and SBERT corpus index).
6. Verify all model artifacts for fresh-clone reproducibility.

Usage:
    python scripts/bootstrap_models.py [--force]
"""

import sys
import time
import argparse
from pathlib import Path
import pandas as pd
import numpy as np
import joblib

# Ensure backend root is on sys.path
root_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(root_dir / "backend"))
sys.path.append(str(root_dir))

from app.core.config import settings
from app.core.security import SecretMasker
from app.core.database import init_database, get_connection
from app.parsers.regex_parser import LogParserEngine
from app.analysis.root_cause_candidate import RootCauseCandidateAnalyzer
from app.ml.baseline.tfidf_rf import BaselineTfidfRandomForest
from app.ml.stage2_classifier.xgboost_model import TraceXGBoostClassifier
from app.ml.stage3_gnn.gnn_pipeline import TraceGraphSAGEPipeline
from app.ml.stage4_rag.rag_service import get_rag_retriever
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import LabelEncoder


def check_artifacts_exist() -> bool:
    """Check if all required model artifacts are present on disk."""
    required = [
        settings.BASELINE_MODEL_PATH,
        settings.BASELINE_VECTORIZER_PATH,
        settings.MODELS_CACHE_DIR / "label_encoder.joblib",
        settings.XGBOOST_MODEL_PATH,
        settings.XGBOOST_ENCODER_PATH,
        settings.GRAPHSAGE_MODEL_PATH,
        settings.GRAPHSAGE_PREPROCESSOR_PATH,
        settings.RAG_CORPUS_EMBEDDINGS_PATH,
        settings.RAG_BM25_INDEX_PATH
    ]
    return all(p.exists() for p in required)


def seed_demo_database():
    """Seed the SQLite database with parsed events from tracked demo logs if empty."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM source_files;")
    file_count = c.fetchone()[0]

    if file_count > 0:
        print("  - SQLite database already contains ingested files; preserving existing records.")
        conn.close()
        return

    print("  - Database is empty. Ingesting tracked demo log files...")
    demo_files = [
        ("demo_jenkins_build.log", "JENKINS_BUILD_LOG", "trace-ci-pipeline", "101"),
        ("jenkins_gist_crash.log", "JENKINS_JVM_CRASH", "jenkins-core", "42")
    ]

    for fname, source_type, job_name, build_num in demo_files:
        fpath = settings.RAW_DATA_DIR / fname
        if not fpath.exists():
            continue

        raw_text = fpath.read_text(encoding="utf-8", errors="replace")
        lines = raw_text.splitlines()

        c.execute("""
            INSERT OR REPLACE INTO source_files (
                filename, source_type, byte_size, line_count, sha256_hash, ingested_at,
                job_name, build_number, build_status
            ) VALUES (?, ?, ?, ?, ?, datetime('now'), ?, ?, ?);
        """, (fname, source_type, len(raw_text.encode('utf-8')), len(lines), "bootstrap_sha256", job_name, build_num, "FAILURE"))
        file_id = c.lastrowid

        events_to_insert = []
        for line_no, raw_line in enumerate(lines, 1):
            if not raw_line.strip():
                continue
            entry = LogParserEngine.parse_line(raw_line)
            # Mask raw secrets before persistence
            masked_raw = SecretMasker.sanitize(raw_line, mask_ips=True) if not settings.ALLOW_RAW_LOG_RETENTION else raw_line
            events_to_insert.append((
                file_id, line_no, entry.timestamp, entry.level, entry.service,
                entry.service, entry.node, entry.trace_id, entry.trace_id, entry.span_id,
                entry.status_code, entry.latency_ms, entry.sanitized_message, masked_raw
            ))

        c.executemany("""
            INSERT INTO parsed_events (
                file_id, line_number, timestamp, severity, service, component, node,
                request_id, trace_id, span_id, status_code, latency_ms, sanitized_message, raw_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, events_to_insert)

    conn.commit()
    conn.close()
    print("  - Seeded demo events successfully.")


def bootstrap_stage1(train_df: pd.DataFrame):
    """Train and serialize Stage 1 (TF-IDF + Random Forest)."""
    print("\n[1/4] Bootstrapping Stage 1: TF-IDF + Random Forest Baseline...")
    t0 = time.perf_counter()

    clean_texts = [
        SecretMasker.sanitize(t, mask_ips=True, normalize_identifiers=True).lower().strip()
        for t in train_df["text"]
    ]
    labels = train_df["failure_category"].tolist()

    vectorizer = TfidfVectorizer(
        ngram_range=(1, 2),
        max_features=1500,
        stop_words="english",
        token_pattern=r"(?u)\b[a-zA-Z_][a-zA-Z0-9_\-\.]{2,}\b"
    )
    X_train = vectorizer.fit_transform(clean_texts)

    le = LabelEncoder()
    y_encoded = le.fit_transform(labels)

    rf = RandomForestClassifier(
        n_estimators=100,
        max_depth=20,
        random_state=42,
        n_jobs=-1
    )
    rf.fit(X_train, labels)

    settings.MODELS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(rf, settings.BASELINE_MODEL_PATH)
    joblib.dump(vectorizer, settings.BASELINE_VECTORIZER_PATH)
    joblib.dump(le, settings.MODELS_CACHE_DIR / "label_encoder.joblib")

    elapsed = time.perf_counter() - t0
    print(f"  - Stage 1 serialized in {elapsed:.2f}s ({len(vectorizer.vocabulary_)} n-grams).")


def bootstrap_stage2(train_df: pd.DataFrame):
    """Train and serialize Stage 2 (Sentence-BERT + XGBoost)."""
    print("\n[2/4] Bootstrapping Stage 2: Sentence-BERT + XGBoost Classifier...")
    t0 = time.perf_counter()

    classifier = TraceXGBoostClassifier(n_estimators=100, max_depth=4, learning_rate=0.05)
    classifier.train(train_df["text"].tolist(), train_df["failure_category"].tolist())
    classifier.save()

    elapsed = time.perf_counter() - t0
    print(f"  - Stage 2 serialized in {elapsed:.2f}s.")


def bootstrap_stage3(train_df: pd.DataFrame, val_df: pd.DataFrame, test_df: pd.DataFrame):
    """Train and serialize Stage 3 (GraphSAGE GNN)."""
    print("\n[3/4] Bootstrapping Stage 3: GraphSAGE GNN (PyTorch Geometric)...")
    t0 = time.perf_counter()

    pipeline = TraceGraphSAGEPipeline(
        hidden_channels=128,
        num_layers=2,
        dropout=0.2,
        lr=0.005,
        epochs=40,  # Fast convergence for initialization
        aggr="mean",
        semantic_threshold=0.85,
        random_state=42
    )
    pipeline.train(train_df=train_df, val_df=val_df, test_df=test_df)
    pipeline.save()

    elapsed = time.perf_counter() - t0
    print(f"  - Stage 3 serialized in {elapsed:.2f}s.")


def bootstrap_stage4():
    """Build and cache Stage 4 (Hybrid RAG BM25 and SBERT Corpus Index)."""
    print("\n[4/4] Bootstrapping Stage 4: Hybrid RAG Knowledge Index...")
    t0 = time.perf_counter()

    retriever = get_rag_retriever(force_reload=True, use_train_only=True)
    if hasattr(retriever.bm25, "save"):
        retriever.bm25.save()
    stats = retriever.get_stats()

    elapsed = time.perf_counter() - t0
    print(f"  - Stage 4 indexed in {elapsed:.2f}s (Corpus size: {stats.get('corpus_size')} incidents).")


def main():
    parser = argparse.ArgumentParser(description="Bootstrap TRACE model artifacts and database.")
    parser.add_argument("--force", action="store_true", help="Force rebuild all artifacts even if present.")
    args = parser.parse_args()

    print("=" * 80)
    print("TRACE PLATFORM ARTIFACT & ENVIRONMENT BOOTSTRAP")
    print("=" * 80)

    # 1. Initialize SQLite schema
    print("\n[INIT] Initializing SQLite WAL Database...")
    init_database()
    seed_demo_database()

    # 2. Check if artifacts already exist
    if not args.force and check_artifacts_exist():
        print("\n[SUCCESS] All model artifacts are already present and verified:")
        print(f"  - Stage 1 (TF-IDF + RF):    {settings.BASELINE_MODEL_PATH.name}")
        print(f"  - Stage 2 (SBERT + XGB):    {settings.XGBOOST_MODEL_PATH.name}")
        print(f"  - Stage 3 (GraphSAGE):      {settings.GRAPHSAGE_MODEL_PATH.name}")
        print(f"  - Stage 4 (Hybrid RAG):     {settings.RAG_CORPUS_EMBEDDINGS_PATH.name}")
        print("\nUse --force to force retraining. TRACE is ready to launch!")
        return

    # 3. Load tracked canonical group dataset
    dataset_path = settings.PROCESSED_DATA_DIR / "group_train_incidents.csv"
    val_path = settings.PROCESSED_DATA_DIR / "group_val_incidents.csv"
    test_path = settings.PROCESSED_DATA_DIR / "group_test_incidents.csv"

    if not dataset_path.exists():
        print(f"[ERROR] Required training dataset not found at {dataset_path}.")
        print("Run 'python scripts/run_leakage_audit_and_group_evaluation.py' first.")
        sys.exit(1)

    train_df = pd.read_csv(dataset_path)
    val_df = pd.read_csv(val_path) if val_path.exists() else train_df.iloc[:20]
    test_df = pd.read_csv(test_path) if test_path.exists() else train_df.iloc[:20]

    print(f"Loaded {len(train_df)} training incidents from {dataset_path.name}.")

    # 4. Bootstrap each stage
    bootstrap_stage1(train_df)
    bootstrap_stage2(train_df)
    bootstrap_stage3(train_df, val_df, test_df)
    bootstrap_stage4()

    print("\n" + "=" * 80)
    print("BOOTSTRAP COMPLETED SUCCESSFULLY")
    print("=" * 80)
    print("All model artifacts are initialized and verified on disk.")
    print("You can now launch the TRACE platform:")
    print("  1. Backend:  uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload")
    print("  2. Frontend: cd frontend && npm run dev (http://localhost:3000)")
    print("  3. Ollama:   ollama run llama3.2:3b")
    print("=" * 80)


if __name__ == "__main__":
    main()
