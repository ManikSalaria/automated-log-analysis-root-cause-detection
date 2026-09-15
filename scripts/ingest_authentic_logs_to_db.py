import sys
import hashlib
from pathlib import Path
from datetime import datetime

# Add paths
root_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(root_dir / "backend"))
sys.path.append(str(root_dir))

from app.core.config import settings
from app.core.database import get_connection, init_database
from app.core.security import SecretMasker
from app.parsers.regex_parser import LogParserEngine
from app.analysis.root_cause_candidate import RootCauseCandidateAnalyzer
from app.ml.baseline.tfidf_rf import BaselineTfidfRandomForest

def sha256_of_file(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()

def ingest_all_raw_files():
    init_database()
    conn = get_connection()
    cursor = conn.cursor()

    baseline = BaselineTfidfRandomForest()
    assert baseline.load(), "Baseline model must be trained and cached."

    raw_files = [
        ("1130.txt", "MICROSERVICES_TELEMETRY"),
        ("Jenkins_Log_Under_1MB.txt", "JENKINS_PYTEST_QUALIFICATION"),
        ("jenkins_gist_crash.log", "JENKINS_JVM_CRASH")
    ]

    print("=" * 80)
    print("INGESTING AUTHENTIC RAW LOGS INTO SQLITE DATABASE")
    print("=" * 80)

    for filename, source_type in raw_files:
        filepath = settings.RAW_DATA_DIR / filename
        if not filepath.exists():
            print(f"Skipping {filename}: file not found.")
            continue

        raw_content = filepath.read_text(encoding="utf-8", errors="replace")
        lines = raw_content.splitlines()
        file_hash = sha256_of_file(filepath)
        ingested_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

        # 1. Register source file
        cursor.execute("""
            INSERT OR REPLACE INTO source_files (filename, source_type, byte_size, line_count, sha256_hash, ingested_at)
            VALUES (?, ?, ?, ?, ?, ?);
        """, (filename, source_type, filepath.stat().st_size, len(lines), file_hash, ingested_at))
        file_id = cursor.lastrowid
        print(f"Registered file '{filename}' (ID={file_id}, lines={len(lines)}, size={filepath.stat().st_size} bytes)")

        # 2. Parse and insert events
        events_to_insert = []
        for line_no, raw_line in enumerate(lines, 1):
            if not raw_line.strip():
                continue
            entry = LogParserEngine.parse_line(raw_line)
            events_to_insert.append((
                file_id,
                line_no,
                entry.timestamp,
                entry.level,
                entry.service,
                entry.service,
                entry.node,
                entry.trace_id,
                entry.trace_id,
                entry.span_id,
                entry.status_code,
                entry.latency_ms,
                entry.sanitized_message,
                raw_line
            ))

        cursor.executemany("""
            INSERT INTO parsed_events (
                file_id, line_number, timestamp, severity, service, component, node,
                request_id, trace_id, span_id, status_code, latency_ms, sanitized_message, raw_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, events_to_insert)
        print(f"  Inserted {len(events_to_insert)} parsed structured events.")

        # 3. Extract and insert failure incidents
        i = 0
        incident_count = 0
        while i < len(lines):
            line = lines[i]
            is_error = False

            if filename == "1130.txt" and "ERROR" in line:
                is_error = True
            elif filename == "Jenkins_Log_Under_1MB.txt" and any(k in line for k in ["ERROR", "FAILED ", "AssertionError", "mkdir:", "qemu-img:"]):
                is_error = True
            elif filename == "jenkins_gist_crash.log" and any(k in line for k in ["Exception", "Error:", "AssertionError", "WARNING"]):
                is_error = True

            if is_error:
                start_line = i + 1
                block = [line]
                j = i + 1
                while j < len(lines):
                    next_l = lines[j]
                    if (next_l.startswith("\t") or next_l.startswith("   ") or next_l.startswith("E   ") or 
                        "Caused:" in next_l or "Traceback" in next_l or "assert " in next_l or 
                        (next_l.startswith("FAILED ") and j == i + 1)):
                        block.append(next_l)
                        j += 1
                    else:
                        break

                raw_block = "\n".join(block)
                sanitized_block = SecretMasker.sanitize(raw_block, mask_ips=True, normalize_identifiers=False)
                
                # Baseline model prediction
                pred = baseline.predict(sanitized_block)
                category = pred["predicted_category"]
                confidence = pred["confidence"]
                
                # Root cause candidate analysis
                rca = RootCauseCandidateAnalyzer.analyze(sanitized_block, primary_category=category)
                
                incident_code = f"INC-{filename[:3].upper()}-{start_line:04d}"
                cursor.execute("""
                    INSERT OR REPLACE INTO incidents (
                        incident_code, file_id, start_line, end_line, primary_severity,
                        failure_category, confidence, root_cause_candidate, detected_signature,
                        evidence_text, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """, (
                    incident_code,
                    file_id,
                    start_line,
                    j,
                    "ERROR",
                    category,
                    confidence,
                    rca["root_cause_candidate"],
                    sanitized_block[:150].strip(),
                    sanitized_block,
                    ingested_at
                ))
                incident_count += 1
                i = j
            else:
                i += 1

        print(f"  Extracted and persisted {incident_count} failure incidents with model predictions.")

    conn.commit()
    conn.close()
    print("\nAll authentic raw files successfully ingested into SQLite database.")

if __name__ == "__main__":
    ingest_all_raw_files()
