# TRACE Demonstration & Evaluation Presentation Guide

This document provides a structured, 10-to-12-minute live demonstration script for academic evaluations, thesis defenses, and engineering reviews.

---

## 1. Pre-Demo Setup Checklist (5 Minutes Before)

Before inviting the audience or starting your screen share, verify that all components are running cleanly:

- [ ] **Python Virtual Environment:** Activated in terminal.
- [ ] **FastAPI Backend:** Running on `http://127.0.0.1:8000` (`uvicorn backend.app.main:app`).
- [ ] **React Frontend:** Running on `http://localhost:5173` (`npm run dev`).
- [ ] **Ollama LLM Engine:** Running with `llama3.2:3b` available (`ollama run llama3.2:3b`).
- [ ] **Browser Tabs Open:**
  1. `http://localhost:5173` (TRACE Dashboard)
  2. `http://127.0.0.1:8000/docs` (Swagger API Docs)
- [ ] **Sample Log Files Ready:** `backend/data/raw/Jenkins_Log_Under_1MB.txt` and `1130.txt`.

---

## 2. Minute-by-Minute Demonstration Script

### [00:00 - 02:00] Introduction & Problem Statement
- **Action:** Open the TRACE Dashboard (`http://localhost:5173`) on the Ingest Logs tab.
- **Narrative:**
  > "Modern CI/CD pipelines generate tens of thousands of lines of unstructured logs per build. When a failure occurs, Site Reliability Engineers spend hours manually parsing stack traces to find root causes. Furthermore, developers frequently leak API keys, AWS credentials, and JWT tokens directly into console output, creating severe security risks.
  >
  > TRACE solves these problems through an automated, privacy-preserving, five-stage machine learning and RAG architecture that transforms raw logs into verified, evidence-grounded root-cause reports."

---

### [02:00 - 04:00] Ingestion, Secret Sanitization & Parsing
- **Action:**
  1. Click **Ingest Logs**.
  2. Drag and drop `backend/data/raw/Jenkins_Log_Under_1MB.txt`.
  3. Click **Process & Sanitize Log**.
- **Narrative:**
  > "Notice what happens instantly: before any log text is stored or processed by our models, TRACE runs our Zero-PII SecretMasker. In this file alone, 14 sensitive credentials—including AWS access keys, GitHub PATs, and bearer tokens—were redacted in-memory.
  >
  > Next, our context-aware multiline parser extracted 1,845 structured events and grouped them into 18 distinct failure incidents, isolating full multiline Java and Python stack traces."
- **Action:** Switch to **Parsed Events** tab and expand a critical error row with a stack trace.

---

### [04:00 - 06:00] Multi-Stage Machine Learning Classification (Stages 1–3)
- **Action:**
  1. Navigate to the **Incident & RCA** tab.
  2. Select incident `INC-0012` (Storage IO Error).
  3. Run **Stage 1 (TF-IDF + Random Forest)**: note prediction `STORAGE_AND_IO_ERROR` with $\sim 32\text{ ms}$ latency.
  4. Switch dropdown to **Stage 2 (Sentence-BERT + XGBoost)** and run analysis: note dense semantic confidence and probability distribution.
  5. Switch dropdown to **Stage 3 (GraphSAGE GNN)** and run analysis: explain that GraphSAGE analyzes topological connections between concurrent incidents and trace IDs.
- **Key Talking Point:**
  > "We intentionally evaluated three distinct paradigms:
  > - Stage 1 provides a fast, interpretable lexical baseline.
  > - Stage 2 leverages dense 384-dimensional Sentence-BERT embeddings to handle vocabulary variations across microservice dialects.
  > - Stage 3 uses a 2-layer GraphSAGE Graph Neural Network to capture trace correlations and temporal proximity between concurrent failures."

---

### [06:00 - 08:00] Stage 4: Hybrid RAG Historical Retrieval
- **Action:**
  1. Navigate to the **RAG Retrieval** tab.
  2. Click **Retrieve Historical Evidence** for the selected incident.
- **Narrative:**
  > "Classification tells us *what* type of failure occurred, but engineers need historical context to know *why* it occurred and *how* it was fixed previously.
  >
  > Stage 4 runs a dual-channel retrieval: dense semantic search using Sentence-BERT cosine similarity, and sparse lexical search using Okapi BM25. These rankings are merged using Reciprocal Rank Fusion ($k=60$) with a metadata category prior.
  >
  > On our held-out test set of 57 incidents across 268 corpus incidents, this hybrid approach achieves a Mean Reciprocal Rank (MRR) of 0.9532 and a Recall@5 of 94.74%, significantly outperforming either single modality alone."
- **Action:** Point out evidence cards `[E1]` and `[E2]` showing source files, line spans, and chronological context events.

---

### [08:00 - 10:00] Stage 5: Evidence-Grounded LLM Synthesis & Remediation
- **Action:**
  1. Navigate to the **LLM Synthesis** tab.
  2. Point out the top status badges: Provider `Connected (Ollama)`, Privacy `Sanitized`, Synthesis `IDLE`.
  3. Click **Generate Grounded Synthesis**.
- **Narrative:**
  > "Now, Stage 5 passes the retrieved evidence package into an on-premises Ollama LLM (`llama3.2:3b`). We use local inference so zero log data or telemetry leaves the host machine.
  >
  > Crucially, we enforce strict grounding invariants:
  > 1. The model cannot hallucinate evidence IDs. If it cites a non-existent `[E99]`, our CitationValidator flags it as ungrounded rather than substituting it.
  > 2. Every remediation action must cite verified evidence.
  > 3. For runtime exceptions, the system enforces the **Diagnostic Remediation Principle**: it recommends diagnosing the root cause (e.g., finding the null source) rather than proposing a blanket defensive try-catch block that merely masks the failure."
- **Action:** Highlight the copyable remediation commands and verified grounding audit badges.

---

### [10:00 - 12:00] Evaluation, Transparency & Academic Disclosures
- **Action:** Navigate to the **Model Evaluation** tab.
- **Narrative:**
  > "To ensure complete scientific rigor, we conducted a comprehensive data leakage audit:
  > - In naive record-level splits, identical log lines leaked between train and test sets, artificially inflating accuracy to 96.5%.
  > - We introduced a strict **group-aware stratified split** partitioning incidents strictly by source log file and Jenkins build.
  > - In this leakage-free evaluation: Stage 1 achieves 80.70% accuracy, Stage 2 achieves 77.19%, and Stage 3 (inductive GraphSAGE) achieves 73.68%.
  > - Stage 1 slightly outperforms Stage 2 and 3 on this benchmark because target labels were derived using rule-based heuristics that naturally correlate with exact lexical tokens.
  >
  > This demonstrates the true generalization capabilities of our models without inflated claims."

---

## 3. Fallback / Offline Demonstration Plan

If Ollama is not installed or times out during the presentation:
1. Explain that the TRACE backend has built-in graceful degradation.
2. The UI will clearly display:
   - Provider: `Disconnected` or `Timeout`
   - Grounding: `N/A (No Report)`
3. Show the pre-generated evaluation artifacts in `backend/data/stage5_synthesis_audit_manifest.json` confirming that all 7 grounding scenarios were tested and verified programmatically.

---

## 4. Anticipated Evaluator Questions & Answers

### Q1: "Why does the TF-IDF baseline have higher accuracy than Sentence-BERT or GraphSAGE?"
> **Answer:** "Our ground-truth incident categories were generated using weak supervision heuristic analyzers that match specific keywords (e.g. HTTP status codes like `502`, service names like `kafka`, or keywords like `OutOfMemory`). Bag-of-words TF-IDF memorizes these exact keywords directly. Dense embeddings and GNNs map to a continuous semantic space, trading slight in-distribution keyword accuracy for robustness against novel, out-of-vocabulary phrasing."

### Q2: "Why did earlier project reports report 96.49% for GraphSAGE?"
> **Answer:** "That earlier figure was evaluated under a naive, transductive split where test-node connections participated in graph message passing, and repeated log templates appeared in both train and test splits. When we performed our rigorous data leakage audit and evaluated under an inductive, group-aware split where test incidents originate from separate builds, GraphSAGE achieved a genuine, leakage-free accuracy of 73.68%."

### Q3: "What prevents the LLM from inventing fake commands?"
> **Answer:** "Our Stage 5 architecture implements two defensive layers:
> 1. Strict prompt isolation: log snippets are passed inside inert XML tags to neutralize prompt injection.
> 2. Post-generation `CitationValidator`: parses the model's output JSON, validates every evidence token against the retrieved evidence package, and flags any ungrounded command for mandatory human review."
