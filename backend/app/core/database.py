import sqlite3
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

# Ensure backend root is on sys.path
backend_dir = Path(__file__).resolve().parent.parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import os
from app.core.config import settings

DB_FILE = settings.DATA_DIR / "trace_review1.db"

def get_db_path() -> Path:
    env_db = os.environ.get("TRACE_SQLITE_DB_PATH")
    if env_db:
        return Path(env_db)
    return DB_FILE

def get_connection(timeout: float = 30.0, db_path: Optional[Path] = None) -> sqlite3.Connection:
    target = db_path or get_db_path()
    conn = sqlite3.connect(str(target), timeout=timeout)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA busy_timeout = 30000;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def migrate_database(conn: sqlite3.Connection):
    """
    Safely and idempotently adds missing columns to existing SQLite tables.
    Preserves all existing records and guarantees backward compatibility.
    """
    cursor = conn.cursor()

    # 1. Migrate source_files table
    cursor.execute("PRAGMA table_info(source_files);")
    source_cols = {row["name"] for row in cursor.fetchall()}
    new_source_cols = [
        ("job_name", "TEXT"),
        ("build_number", "TEXT"),
        ("build_status", "TEXT"),
        ("build_url", "TEXT"),
        ("repo_url", "TEXT"),
        ("commit_sha", "TEXT")
    ]
    for col_name, col_type in new_source_cols:
        if col_name not in source_cols:
            cursor.execute(f"ALTER TABLE source_files ADD COLUMN {col_name} {col_type};")

    # 2. Migrate incidents table
    cursor.execute("PRAGMA table_info(incidents);")
    inc_cols = {row["name"] for row in cursor.fetchall()}
    new_inc_cols = [
        ("job_name", "TEXT"),
        ("build_number", "TEXT")
    ]
    for col_name, col_type in new_inc_cols:
        if col_name not in inc_cols:
            cursor.execute(f"ALTER TABLE incidents ADD COLUMN {col_name} {col_type};")

    conn.commit()

def init_database(db_path: Optional[Path] = None):
    """Initializes and migrates the SQLite database schema."""
    conn = get_connection(db_path=db_path)
    try:
        with conn:
            cursor = conn.cursor()

            # 1. Source Files Ingestion Registry (supports CI/CD provenance metadata)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS source_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT UNIQUE NOT NULL,
                source_type TEXT NOT NULL,
                byte_size INTEGER NOT NULL,
                line_count INTEGER NOT NULL,
                sha256_hash TEXT NOT NULL,
                ingested_at TEXT NOT NULL,
                job_name TEXT,
                build_number TEXT,
                build_status TEXT,
                build_url TEXT,
                repo_url TEXT,
                commit_sha TEXT
            );
            """)

            # 2. Parsed Structured Log Events
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS parsed_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id INTEGER NOT NULL,
                line_number INTEGER NOT NULL,
                timestamp TEXT,
                severity TEXT NOT NULL,
                service TEXT,
                component TEXT,
                node TEXT,
                request_id TEXT,
                trace_id TEXT,
                span_id TEXT,
                status_code INTEGER,
                latency_ms REAL,
                sanitized_message TEXT NOT NULL,
                raw_message TEXT NOT NULL,
                FOREIGN KEY (file_id) REFERENCES source_files(id) ON DELETE CASCADE
            );
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_file ON parsed_events(file_id);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_severity ON parsed_events(severity);")

            # 3. Detected Incidents & Root-Cause Analysis
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS incidents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                incident_code TEXT UNIQUE NOT NULL,
                file_id INTEGER NOT NULL,
                start_line INTEGER NOT NULL,
                end_line INTEGER NOT NULL,
                primary_severity TEXT NOT NULL,
                failure_category TEXT NOT NULL,
                confidence REAL NOT NULL,
                root_cause_candidate TEXT NOT NULL,
                detected_signature TEXT NOT NULL,
                evidence_text TEXT NOT NULL,
                created_at TEXT NOT NULL,
                job_name TEXT,
                build_number TEXT,
                FOREIGN KEY (file_id) REFERENCES source_files(id) ON DELETE CASCADE
            );
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_incidents_file ON incidents(file_id);")

            # 4. Model Evaluation & Benchmark Metrics
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS model_evaluations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model_name TEXT NOT NULL,
                dataset_split TEXT NOT NULL,
                accuracy REAL NOT NULL,
                precision_macro REAL NOT NULL,
                recall_macro REAL NOT NULL,
                f1_macro REAL NOT NULL,
                sample_count INTEGER NOT NULL,
                feature_dimension INTEGER NOT NULL,
                training_time_sec REAL,
                avg_latency_ms REAL NOT NULL,
                p95_latency_ms REAL NOT NULL,
                evaluated_at TEXT NOT NULL
            );
            """)

            # Safely migrate existing databases if columns are absent
            migrate_database(conn)
    finally:
        conn.close()

if __name__ == "__main__":
    init_database()
    print(f"Database successfully initialized and migrated at: {DB_FILE}")
