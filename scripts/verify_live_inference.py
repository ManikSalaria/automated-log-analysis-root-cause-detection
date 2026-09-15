import sys
from pathlib import Path

# Add backend to path
sys.path.append(str(Path(__file__).resolve().parent.parent / "backend"))

from app.ml.baseline.tfidf_rf import BaselineTfidfRandomForest
from app.analysis.root_cause_candidate import RootCauseCandidateAnalyzer

baseline = BaselineTfidfRandomForest()
assert baseline.load(), "Failed to load baseline model."

print("=" * 80)
print("LIVE VERIFICATION OF ALL 3 AUTHENTIC DIALECTS & NOVEL INPUT")
print("=" * 80)

# Test 1: Real Jenkins VME Qualification Log Error
log1 = """2026-02-25 21:12:39 MST test_vme_storage_plugin_e2e.py:320 ERROR : Actual error is: storage cluster id is missing from config in datastore alletra_datastore_abgrdg_dnd creation assert 'hpe_storage_cluster_id' in {'protocolType': 'iSCSI'}
AssertionError: storage cluster id is missing from config in datastore alletra_datastore_abgrdg_dnd creation"""
pred1 = baseline.predict(log1)
rca1 = RootCauseCandidateAnalyzer.analyze(log1, primary_category=pred1["predicted_category"])

print("\n--- TEST 1: REAL JENKINS QUALIFICATION FAILURE ---")
print(f"Predicted Category: {pred1['predicted_category']}")
print(f"Confidence:         {pred1['confidence']*100:.2f}%")
print(f"Inference Latency:  {pred1['latency_ms']:.2f} ms")
print(f"Root Cause:         {rca1['root_cause_candidate']}")
print(f"Remediation:        {rca1['remediation_guidance']}")

# Test 2: Real Microservice Payment Timeout
log2 = """2026-09-15T09:04:30.123Z ERROR [notification-service] request_id=req-820221 status=503 latency_ms=3371 Connection refused by payment service"""
pred2 = baseline.predict(log2)
rca2 = RootCauseCandidateAnalyzer.analyze(log2, primary_category=pred2["predicted_category"])

print("\n--- TEST 2: REAL MICROSERVICE FAILURE ---")
print(f"Predicted Category: {pred2['predicted_category']}")
print(f"Confidence:         {pred2['confidence']*100:.2f}%")
print(f"Inference Latency:  {pred2['latency_ms']:.2f} ms")
print(f"Root Cause:         {rca2['root_cause_candidate']}")
print(f"Remediation:        {rca2['remediation_guidance']}")

# Test 3: Real Jenkins Gist Crash
log3 = """2022-10-04 19:25:40.961+0000 [id=19] WARNING h.i.i.InstallUncaughtExceptionHandler#handleException: Caught unhandled exception with ID 2f2d9bc5
java.lang.AssertionError: class hudson.security.csrf.DefaultCrumbIssuer is missing its descriptor
\tat jenkins.model.Jenkins.getDescriptorOrDie(Jenkins.java:1633)"""
pred3 = baseline.predict(log3)
rca3 = RootCauseCandidateAnalyzer.analyze(log3, primary_category=pred3["predicted_category"])

print("\n--- TEST 3: REAL JENKINS GIST CRASH ---")
print(f"Predicted Category: {pred3['predicted_category']}")
print(f"Confidence:         {pred3['confidence']*100:.2f}%")
print(f"Inference Latency:  {pred3['latency_ms']:.2f} ms")
print(f"Root Cause:         {rca3['root_cause_candidate']}")
print(f"Remediation:        {rca3['remediation_guidance']}")

# Test 4: Genuinely Novel Log (Unseen)
log4 = """CRITICAL: Kubernetes worker node-12 disk pressure detected. Kubelet eviction triggered on pod monitoring-agent."""
pred4 = baseline.predict(log4)
rca4 = RootCauseCandidateAnalyzer.analyze(log4, primary_category=pred4["predicted_category"])

print("\n--- TEST 4: NOVEL UNSEEN LOG ---")
print(f"Predicted Category: {pred4['predicted_category']}")
print(f"Confidence:         {pred4['confidence']*100:.2f}%")
print(f"Inference Latency:  {pred4['latency_ms']:.2f} ms")
print(f"Root Cause:         {rca4['root_cause_candidate']}")
print(f"Remediation:        {rca4['remediation_guidance']}")
print("\nVerification successfully completed.")
