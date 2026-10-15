# TRACE Empirical Model Evaluation & Data Leakage Audit

This document provides a comprehensive scientific report on the evaluation methodology, dataset provenance, data leakage audit, comparative classifier benchmarks, RAG retrieval performance, and Stage 5 LLM grounding validation in **TRACE**.

---

## 1. Dataset Provenance & Incident Partitioning

All experiments are conducted exclusively on authentic CI/CD build logs and distributed service telemetry:
- `backend/data/raw/Jenkins_Log_Under_1MB.txt` (3,120 lines, Jenkins build pipeline)
- `backend/data/raw/1130.txt` (2,104 lines, microservice orchestration)
- `backend/data/raw/jenkins_gist_crash.log` (302 lines, JVM crash and fatal pipeline abort)

A total of **374 authentic failure incidents** were extracted by TRACE's context-aware parser across 10 distinct failure categories:
1. `AUTHENTICATION_SECURITY_ERROR`
2. `DATABASE_AND_CACHE_TIMEOUT`
3. `ENVIRONMENT_AND_PIPELINE_ERROR`
4. `INTERNAL_APPLICATION_LOGIC_ERROR`
5. `MESSAGE_BROKER_FAILURE`
6. `NETWORK_DEPENDENCY_FAILURE`
7. `PLUGIN_DESCRIPTOR_RESOLUTION_ERROR`
8. `RESOURCE_EXHAUSTION_CRASH`
9. `STORAGE_AND_IO_ERROR`
10. `TEST_ASSERTION_FAILURE`

---

## 2. The Data Leakage Audit: Naive vs. Group-Aware Splitting

### 2.1 The Data Leakage Vulnerability
In an initial naive evaluation, incidents were partitioned using standard record-level random stratified splitting. This introduced severe data leakage:
1. **Template & Lexical Duplication:** Identical recurring log messages from repetitive Jenkins loops appeared in both training and test sets (10 exact duplicates crossed splits).
2. **Transductive Graph Convolution Leakage:** In the initial GraphSAGE implementation, test nodes were included in the graph adjacency matrix during message passing, allowing test-to-test and train-to-test edge aggregation.

This artificial leakage inflated earlier reported metrics:
- Stage 1 (TF-IDF + Random Forest): **92.98% Accuracy**
- Stage 2 (Sentence-BERT + XGBoost): **96.49% Accuracy**
- Stage 3 (GraphSAGE Transductive): **96.49% Accuracy**

### 2.2 The Canonical Group-Aware Split Solution
To ensure scientific integrity and defensibility, we implemented a **Canonical Group-Aware Stratified Split**:
- Partitioned strictly by source log file and chronological build groupings.
- **Training Set:** 268 incidents (71.7%)
- **Validation Set:** 49 incidents (13.1%)
- **Held-Out Test Set:** 57 incidents (15.2%)
- **Leakage Audit Results:**
  - Exact text overlap between train and test: **0**
  - Incident signature overlap: **0**
  - Source group overlap: **0**

---

## 3. Comparative Classifier Benchmarks (Stages 1–3)

The table below presents the genuine, leakage-free performance of all three classifiers evaluated on the same 57 held-out test incidents:

| Model | Representation | Test Accuracy | Macro-Precision | Macro-Recall | Macro-F1 | Inference Latency |
|:---|:---|:---:|:---:|:---:|:---:|:---:|
| **Stage 1: TF-IDF + Random Forest** | 1500-D Lexical (Unigram + Bigram) | **80.70%** | **72.35%** | **75.89%** | **72.81%** | 32.65 ms |
| **Stage 2: Sentence-BERT + XGBoost** | 384-D Dense Semantic (`all-MiniLM-L6-v2`) | **77.19%** | 64.17% | 71.58% | 65.31% | 34.98 ms |
| **Stage 3: GraphSAGE (Inductive PyG)** | 412-D (SBERT + OneHot + Numerical) | **73.68%** | 61.79% | 74.29% | 64.90% | **30.52 ms** |

*(Weighted F1 for Stage 3 GraphSAGE is 70.04% due to class imbalance).*

### Key Scientific Takeaways:
1. **Why Stage 1 Baseline Outperforms Dense Models:**
   The ground-truth target labels were derived using rule-based heuristic analyzers (`RootCauseCandidateAnalyzer`) that match explicit keywords (e.g., HTTP status `502`, `kafka`, `IOException`, `No space left on device`). The bag-of-words TF-IDF representation memorizes these exact lexical tokens directly.
2. **Generalization vs. In-Distribution Memorization:**
   While Stage 1 excels at in-distribution keyword matching, Stage 2 (Sentence-BERT) provides semantic continuity when logs use alternate synonyms or paraphrased exception messages.
3. **GraphSAGE Inductive Evaluation:**
   Evaluating GraphSAGE strictly inductively (where message passing occurs only across subgraphs without access to test-set edges) drops performance from 96.49% to 73.68%. This provides an accurate reflection of how a GNN operates when encountering new, unseen failure episodes in production.
4. **Out-of-Distribution Failures:**
   All models scored 0.0% F1 on `AUTHENTICATION_SECURITY_ERROR` in the held-out test set. The audit revealed that authentication failures in the test set originated from an OAuth2 endpoint syntax not present in the training set, illustrating the importance of leakage-free cross-file evaluation.

---

## 4. Stage 4: Hybrid RAG Retrieval Evaluation

Stage 4 was evaluated across **57 held-out test query incidents** searching a disjoint historical corpus of **268 training incidents**:

| Retrieval Modality | Recall@1 | Recall@3 | Recall@5 | Recall@10 | Precision@1 | MRR | Avg Latency |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Hybrid (BM25 + SBERT + Category Prior)** | **94.74%** | **94.74%** | **94.74%** | **100.0%** | **94.74%** | **0.9532** | 31.63 ms |
| **Sparse Lexical (Okapi BM25)** | 73.68% | 89.47% | 89.47% | 92.98% | 73.68% | 0.8082 | **1.38 ms** |
| **Dense Semantic (Sentence-BERT)** | 71.93% | 87.72% | 89.47% | 94.74% | 71.93% | 0.7946 | 27.47 ms |

### Observations:
- **Reciprocal Rank Fusion Synergy:** Combining sparse lexical matching ($k_1=1.5, b=0.75$) with dense semantic embeddings and a metadata category prior boosts Mean Reciprocal Rank (MRR) from $\sim 0.80$ to **0.9532**.
- **Recall@5:** Reaches **94.74%**, ensuring the subsequent Stage 5 LLM prompt receives highly relevant historical evidence packages.

---

## 5. Stage 5: Grounding, Citation & Safety Audit

The Stage 5 synthesis pipeline was audited using an automated regression suite (`scripts/evaluate_stage5_synthesis.py`) testing 7 critical reliability scenarios:

| # | Audit Scenario | Objective | Status |
|:---:|:---|:---|:---:|
| 1 | **Valid Grounded Report** | Verified that valid citations (`[E1]`, `[E2]`) correctly pass grounding checks. | **PASS** |
| 2 | **E99 Hallucination Rejection** | Confirmed that hallucinated citations (`[E99]`) are **never silently replaced** with `[E1]` and are flagged as unsupported. | **PASS** |
| 3 | **Remediation Grounding Invariant** | Verified that any remediation step with empty evidence (`[]`) is marked `is_grounded: false` and flagged for human review. | **PASS** |
| 4 | **Diagnostic Remediation Principle** | Verified that for null-pointer or crash errors, diagnostic steps (inspecting null sources) are prioritized over blind try-catch blocks. | **PASS** |
| 5 | **Calibrated Confidence Assessment** | Verified that qualitative LLM confidence assessments are labeled heuristic and not presented as calibrated probabilities. | **PASS** |
| 6 | **Prompt Injection Isolation** | Verified that malicious log payloads attempting to override instructions inside `<log_evidence>` are neutralized. | **PASS** |
| 7 | **Configurable Timeout Handling** | Verified that requests respecting `TRACE_LLM_TIMEOUT_SEC` handle timeouts gracefully without false grounding claims. | **PASS** |

**Summary:** 7 out of 7 audit scenarios passed (100% pass rate). Verified manifest saved at `backend/data/stage5_synthesis_audit_manifest.json`.

---

## 6. Academic Disclosures & Ethical Considerations

1. **Weak Supervision Ground Truth:** Incident labels in this research were generated using rule-based heuristics rather than manual SRE annotations. Metrics reflect consistency with these operational rules.
2. **Advisory Remediation:** All remediation commands generated by TRACE are strictly advisory and require human-in-the-loop review prior to production execution.
3. **Local Privacy Guarantee:** By hosting Ollama and all ML models locally, zero proprietary log telemetry or confidential credentials are ever transmitted to third-party cloud APIs.
