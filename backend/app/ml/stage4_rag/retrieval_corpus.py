"""Retrieval Corpus Builder for TRACE Stage 4 RAG.

Loads incident records from the authentic CSV corpus and SQLite database,
constructs a retrieval-ready corpus with metadata, embeddings, and
provenance information. Supports group-aware corpus filtering for
leakage-free evaluation.
"""

import json
import csv
from pathlib import Path
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass, asdict, field
import numpy as np

from app.core.config import settings
from app.core.security import SecretMasker


@dataclass
class CorpusIncident:
    """A single incident record in the retrieval corpus."""
    incident_code: str
    source_file: str
    source_type: str
    failure_category: str
    root_cause_candidate: str
    evidence_signature: str
    text: str                   # Sanitized incident text used for embedding
    start_line: int = 0
    end_line: int = 0
    line_span: int = 1
    group_key: str = ""         # For leakage-aware split tracking


def load_csv_corpus(csv_path: Path) -> List[CorpusIncident]:
    """Load incidents from a CSV file into CorpusIncident records.
    
    Reads the authentic incident CSV and returns structured records.
    Handles both the full corpus (without group_key) and group-split
    CSVs (with group_key column).
    """
    incidents = []
    if not csv_path.exists():
        return incidents

    with open(csv_path, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            text = row.get("text", "").strip()
            if not text:
                continue

            incidents.append(CorpusIncident(
                incident_code=row.get("incident_code", ""),
                source_file=row.get("source_file", ""),
                source_type=row.get("source_type", ""),
                failure_category=row.get("failure_category", ""),
                root_cause_candidate=row.get("root_cause_candidate", ""),
                evidence_signature=row.get("evidence_signature", ""),
                text=text,
                start_line=int(row.get("start_line", 0)),
                end_line=int(row.get("end_line", 0)),
                line_span=int(row.get("line_span", 1)),
                group_key=row.get("group_key", "")
            ))

    return incidents


def load_train_corpus() -> List[CorpusIncident]:
    """Load the group-aware training corpus for leakage-free retrieval.
    
    Uses group_train_incidents.csv to ensure that retrieval evaluation
    queries from the test set never appear in the retrieval corpus.
    """
    train_path = settings.PROCESSED_DATA_DIR / "group_train_incidents.csv"
    return load_csv_corpus(train_path)


def load_full_corpus() -> List[CorpusIncident]:
    """Load the full authentic incident corpus for live retrieval.
    
    For production use (not evaluation), the full corpus provides
    maximum retrieval coverage.
    """
    full_path = settings.PROCESSED_DATA_DIR / "authentic_incidents.csv"
    return load_csv_corpus(full_path)


def load_test_queries() -> List[CorpusIncident]:
    """Load the group-aware test set for retrieval evaluation queries."""
    test_path = settings.PROCESSED_DATA_DIR / "group_test_incidents.csv"
    return load_csv_corpus(test_path)


def get_incident_codes_from_csv(csv_path: Path) -> Set[str]:
    """Extract all incident codes from a CSV file for exclusion filtering."""
    codes = set()
    if not csv_path.exists():
        return codes
    with open(csv_path, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            code = row.get("incident_code", "").strip()
            if code:
                codes.add(code)
    return codes


def build_corpus_texts(incidents: List[CorpusIncident]) -> List[str]:
    """Extract sanitized text from corpus incidents for embedding.
    
    Applies SecretMasker sanitization to ensure zero PII leakage
    in the embedding representations.
    """
    texts = []
    for inc in incidents:
        sanitized = SecretMasker.sanitize(
            inc.text, mask_ips=True, normalize_identifiers=True
        )
        texts.append(sanitized.strip())
    return texts


def build_corpus_metadata(incidents: List[CorpusIncident]) -> List[Dict[str, Any]]:
    """Build metadata dicts for each corpus incident for serialization."""
    return [
        {
            "incident_code": inc.incident_code,
            "source_file": inc.source_file,
            "source_type": inc.source_type,
            "failure_category": inc.failure_category,
            "root_cause_candidate": inc.root_cause_candidate,
            "evidence_signature": inc.evidence_signature,
            "start_line": inc.start_line,
            "end_line": inc.end_line,
            "group_key": inc.group_key,
        }
        for inc in incidents
    ]


def save_corpus_metadata(metadata: List[Dict[str, Any]], path: Path) -> None:
    """Persist corpus metadata as JSON for fast reload."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)


def load_corpus_metadata(path: Path) -> List[Dict[str, Any]]:
    """Load previously saved corpus metadata."""
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
