import requests
import json
from pathlib import Path

API_BASE = "http://127.0.0.1:8000/api/v1"
RAW_DIR = Path("backend/data/raw")

files_to_test = [
    "Jenkins_Log_Under_1MB.txt",
    "1130.txt",
    "jenkins_gist_crash.log"
]

print("=" * 80)
print("BLACK-BOX ACCEPTANCE TEST: LIVE UPLOAD & ANALYSIS OF AUTHENTIC FILES")
print("=" * 80)

results = {}

for fname in files_to_test:
    fpath = RAW_DIR / fname
    if not fpath.exists():
        print(f"\n[SKIP] File '{fname}' not found in raw dir (skipping blackbox test for this file).")
        continue

    print(f"\n[1] Testing Live Upload of '{fname}'...")
    with open(fpath, "rb") as f:
        r_up = requests.post(f"{API_BASE}/ingest/upload", files={"file": (fname, f, "text/plain")})
    
    assert r_up.status_code == 200, f"Upload failed for {fname}: {r_up.text}"
    up_data = r_up.json()
    print(f"    - Upload Success: ID={up_data['file_id']}, Size={up_data['byte_size']} bytes, Lines={up_data['line_count']}")
    print(f"    - SHA-256: {up_data['sha256_hash'][:24]}...")
    print(f"    - Events Inserted: {up_data['events_inserted']}")
    print(f"    - Incidents Detected: {up_data['incidents_detected']}")

    # [2] Test Incident Retrieval for this file
    print(f"[2] Querying Persisted Incidents for '{fname}'...")
    r_inc = requests.get(f"{API_BASE}/incidents?source_file={fname}&limit=3")
    assert r_inc.status_code == 200
    inc_list = r_inc.json()
    assert len(inc_list) > 0, f"No incidents returned for {fname}"
    top_inc = inc_list[0]
    print(f"    - Top Incident Code: {top_inc['incident_code']}")
    print(f"    - Category:          {top_inc['failure_category']}")
    print(f"    - Confidence:        {top_inc['confidence']*100:.2f}%")
    print(f"    - Root Cause:        {top_inc['root_cause_candidate']}")
    print(f"    - Signature:         {top_inc['detected_signature'][:80]}...")

    # [3] Test Live Full Incident Analysis Endpoint with authentic snippet
    print(f"[3] Running Live Full Incident Analysis on snippet from '{fname}'...")
    snippet = top_inc['detected_signature']
    r_anl = requests.post(f"{API_BASE}/analysis/analyze", json={"log_text": snippet})
    assert r_anl.status_code == 200
    anl_data = r_anl.json()
    print(f"    - Analysis ID:       {anl_data['analysis_id']}")
    print(f"    - Model:             {anl_data['classification']['model_name']}")
    print(f"    - Predicted Class:   {anl_data['classification']['predicted_category']}")
    print(f"    - Confidence:        {anl_data['classification']['confidence']*100:.2f}%")
    print(f"    - Inference Latency: {anl_data['classification']['latency_ms']:.2f} ms")
    print(f"    - RCA Framework:     {anl_data['root_cause']['analysis_framework']}")
    print(f"    - Root Cause:        {anl_data['root_cause']['root_cause_candidate']}")
    print(f"    - Privacy Clean:     {anl_data['privacy_audit']['clean']}")

    results[fname] = {
        "upload": "PASS",
        "persisted_events": up_data['events_inserted'],
        "persisted_incidents": up_data['incidents_detected'],
        "top_category": top_inc['failure_category'],
        "confidence": top_inc['confidence'],
        "root_cause": top_inc['root_cause_candidate']
    }

print("\n" + "=" * 80)
print(f"ACCEPTANCE TEST SUMMARY: {len(results)} AUTHENTIC LOG PIPELINES VERIFIED")
print("=" * 80)
for k, v in results.items():
    print(f"  {k:<30}: Status=PASS, Events={v['persisted_events']}, Incidents={v['persisted_incidents']}, Class={v['top_category']}")
