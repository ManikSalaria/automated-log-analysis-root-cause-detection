import sys
import json
import hashlib
from pathlib import Path
from typing import List, Dict, Any
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split

# Add backend to path
root_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(root_dir / "backend"))
sys.path.append(str(root_dir))

from app.core.config import settings
from app.core.security import SecretMasker
from app.analysis.root_cause_candidate import RootCauseCandidateAnalyzer

def compute_sha256(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()

def extract_authentic_incidents() -> pd.DataFrame:
    raw_dir = settings.RAW_DATA_DIR
    files = [
        ("1130.txt", "MICROSERVICES_TELEMETRY"),
        ("Jenkins_Log_Under_1MB.txt", "JENKINS_PYTEST_QUALIFICATION"),
        ("jenkins_gist_crash.log", "JENKINS_JVM_CRASH")
    ]

    incidents = []
    incident_counter = 1

    for filename, source_type in files:
        filepath = raw_dir / filename
        if not filepath.exists():
            print(f"Notice: Optional raw file '{filename}' not found at {filepath}. Skipping.")
            continue
        
        lines = filepath.read_text(encoding="utf-8", errors="replace").splitlines()
        i = 0
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
                    # Check for stack trace or continuous failure lines
                    if (next_l.startswith("\t") or next_l.startswith("   ") or next_l.startswith("E   ") or 
                        "Caused:" in next_l or "Traceback" in next_l or "assert " in next_l or 
                        (next_l.startswith("FAILED ") and j == i + 1)):
                        block.append(next_l)
                        j += 1
                    else:
                        break

                raw_text = "\n".join(block)
                sanitized_text = SecretMasker.sanitize(raw_text, mask_ips=True, normalize_identifiers=False)
                
                # Analyze root-cause candidate and category
                analysis = RootCauseCandidateAnalyzer.analyze(sanitized_text)
                
                incidents.append({
                    "incident_code": f"INC-{incident_counter:04d}",
                    "source_file": filename,
                    "source_type": source_type,
                    "start_line": start_line,
                    "end_line": j,
                    "line_span": j - start_line + 1,
                    "failure_category": analysis["failure_category"],
                    "root_cause_candidate": analysis["root_cause_candidate"],
                    "evidence_signature": sanitized_text[:120].strip(),
                    "text": sanitized_text,
                    "raw_text": sanitized_text
                })
                incident_counter += 1
                i = j
            else:
                i += 1

    df = pd.DataFrame(incidents)
    return df

def build_and_split_dataset():
    print(f"{'='*80}")
    print("CONSTRUCTING DEFENSIVE REVIEW-1 DATASET FROM AUTHENTIC LOGS")
    print(f"{'='*80}")

    df = extract_authentic_incidents()
    total_incidents = len(df)
    print(f"Total Authentic Failure Incidents Extracted: {total_incidents}")

    # Inspect category distribution
    class_dist = df["failure_category"].value_counts()
    print("\nAuthentic Failure Category Distribution:")
    for cat, count in class_dist.items():
        pct = (count / total_incidents) * 100
        print(f"  - {cat:<40}: {count:>3} incidents ({pct:>5.1f}%)")

    # Save full processed incidents dataset
    processed_dir = settings.PROCESSED_DATA_DIR
    processed_dir.mkdir(parents=True, exist_ok=True)
    full_dataset_path = processed_dir / "authentic_incidents.csv"
    df.to_csv(full_dataset_path, index=False)
    print(f"\nFull authentic dataset saved to: {full_dataset_path}")

    # Incident-level Stratified Train (70%) / Val (15%) / Test (15%) Split
    # Use random_state=42 for deterministic reproducibility
    train_df, temp_df = train_test_split(
        df, 
        test_size=0.30, 
        stratify=df["failure_category"], 
        random_state=42
    )
    val_df, test_df = train_test_split(
        temp_df, 
        test_size=0.50, 
        stratify=temp_df["failure_category"], 
        random_state=42
    )

    # Save individual split partitions
    train_path = processed_dir / "train_incidents.csv"
    val_path = processed_dir / "val_incidents.csv"
    test_path = processed_dir / "test_incidents.csv"

    train_df.to_csv(train_path, index=False)
    val_df.to_csv(val_path, index=False)
    test_df.to_csv(test_path, index=False)

    print(f"\nDataset Partitions Generated:")
    print(f"  - Training Set:   {len(train_df):>3} incidents ({(len(train_df)/total_incidents)*100:.1f}%) -> {train_path.name}")
    print(f"  - Validation Set: {len(val_df):>3} incidents ({(len(val_df)/total_incidents)*100:.1f}%) -> {val_path.name}")
    print(f"  - Held-out Test:  {len(test_df):>3} incidents ({(len(test_df)/total_incidents)*100:.1f}%) -> {test_path.name}")

    # Save Split Manifest
    manifest = {
        "dataset_name": "TRACE Review-1 Authentic CI/CD Failure Corpus",
        "provenance": "100% extracted from genuine user-supplied logs",
        "synthetic_augmentation_used": False,
        "split_method": "Stratified Incident-Level Split",
        "random_seed": 42,
        "total_incidents": total_incidents,
        "train_count": len(train_df),
        "val_count": len(val_df),
        "test_count": len(test_df),
        "category_distribution": class_dist.to_dict(),
        "train_categories": train_df["failure_category"].value_counts().to_dict(),
        "test_categories": test_df["failure_category"].value_counts().to_dict(),
        "source_files": [
            {
                "name": fname,
                "sha256": compute_sha256(settings.RAW_DATA_DIR / fname),
                "lines": len((settings.RAW_DATA_DIR / fname).read_text(encoding="utf-8", errors="replace").splitlines())
            }
            for fname, _ in files
            if (settings.RAW_DATA_DIR / fname).exists()
        ]
    }

    manifest_path = processed_dir / "split_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    print(f"Split manifest saved to: {manifest_path}")

if __name__ == "__main__":
    build_and_split_dataset()
