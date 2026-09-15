import sqlite3
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

# Ensure backend root is on sys.path
backend_dir = Path(__file__).resolve().parent.parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.core.config import settings

DB_FILE = settings.DATA_DIR / "trace_review1.db"

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_FILE))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_database():
    """Initializes the Review-1 SQLite database schema."""
    conn = get_connection()
    cursor = conn.cursor()

    # 1. Source Files Ingestion Registry
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS source_files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT UNIQUE NOT NULL,
        source_type TEXT NOT NULL,
        byte_size INTEGER NOT NULL,
        line_count INTEGER NOT NULL,
        sha256_hash TEXT NOT NULL,
        ingested_at TEXT NOT NULL
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

    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_database()
    print(f"Database successfully initialized at: {DB_FILE}")
