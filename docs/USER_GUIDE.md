# TRACE User & Operator Guide

This guide walks you through the interactive **TRACE** web dashboard (`http://localhost:5173`), detailing how to ingest logs, inspect parsed telemetry, classify incidents across ML models, retrieve historical evidence, and synthesize grounded remediation reports.

---

## 1. Navigating the Dashboard

The TRACE frontend is organized into cohesive functional tabs accessible from the top navigation bar:

1. **Ingest Logs:** Upload raw files or ingest Jenkins CI/CD console logs with automated credential sanitization.
2. **Parsed Events:** Browse, filter, and inspect structured log events and multiline stack traces.
3. **Incident Registry:** View extracted failure episodes, severity levels, and execution boundaries.
4. **Incident & RCA (ML Stages 1–3):** Classify incidents and compare predictions across TF-IDF, XGBoost, and GraphSAGE.
5. **RAG Retrieval (Stage 4):** Search historical incidents and retrieve chronological evidence packages using hybrid search.
6. **LLM Synthesis (Stage 5):** Generate evidence-grounded root-cause reports with copyable remediation commands.
7. **Model Evaluation:** Inspect canonical group-aware benchmarks, data leakage audits, and confusion matrices.

---

## 2. Ingesting Logs & Sanitizing Secrets

### 2.1 File Upload
1. Click the **Ingest Logs** tab.
2. Drag and drop any raw log file (e.g. `backend/data/raw/Jenkins_Log_Under_1MB.txt` or `1130.txt`) into the drop zone, or click to browse.
3. Click **Process & Sanitize Log**.
4. The system automatically redacts AWS credentials, GitHub PATs, JWT tokens, passwords, and private IP addresses in-memory.
5. The **Ingestion Summary** banner displays:
   - File ID & Name
   - Total Lines Parsed
   - **Secrets Redacted** count (highlighted with a green shield icon)
   - Extracted Events & Detected Incidents count

### 2.2 Jenkins CI/CD Direct Ingestion
1. Switch to the **Jenkins Ingestion** sub-panel.
2. Enter the Jenkins job name (e.g. `trace-ci-pipeline`), build number, and optional Git commit hash.
3. Paste raw console output into the text box.
4. Click **Ingest Jenkins Build**.

---

## 3. Exploring Parsed Events

1. Click the **Parsed Events** tab.
2. Use the **Severity Filter** dropdown to narrow down events (`ALL`, `CRITICAL`, `ERROR`, `WARNING`, `INFO`).
3. Use the **Search Bar** to filter by component name, trace ID, or message keywords.
4. Expand any row containing a stack trace icon to inspect the formatted Java or Python exception traceback.

---

## 4. Inspecting the Incident Registry

1. Click the **Incident Registry** tab.
2. The table enumerates detected failure episodes with:
   - **Incident ID** (e.g. `INC-0012`)
   - **Severity Badge** (Red: `CRITICAL`, Orange: `ERROR`, Yellow: `WARNING`)
   - **Component** (e.g. `storage-controller`, `auth-service`)
   - **Line Boundaries** (`start_line` to `end_line` in the original file)
   - **Primary Error Message**
3. Click **Inspect Incident** to open the side panel, displaying the surrounding timeline of events that preceded and followed the incident.

---

## 5. Root Cause Classification (Stages 1–3)

1. Click the **Incident & RCA** tab.
2. Select an incident from the dropdown or load a sample incident.
3. Select your desired classification model:
   - **Stage 1: TF-IDF + Random Forest** (Fast bag-of-words baseline)
   - **Stage 2: Sentence-BERT + XGBoost** (Dense semantic classifier)
   - **Stage 3: GraphSAGE GNN** (Topological graph neural network)
4. Click **Analyze with [Selected Model]**.
5. Inspect the **Inference Result Panel**:
   - **Model Used Badge:** Visually confirms the backend-executed model (guaranteed to match the server response).
   - **Predicted Root Cause Category:** High-level failure class (e.g. `STORAGE_AND_IO_ERROR`).
   - **Confidence Score:** Estimated category probability.
   - **Inference Latency:** Wall-clock inference time in milliseconds.
   - **Class Probability Distribution:** Horizontal bar chart showing probabilities across all 10 incident categories.
   - **Rule-Grounded Candidates:** Actionable diagnostic advice and root-cause candidate hypotheses.

---

## 6. Hybrid RAG Historical Retrieval (Stage 4)

1. Click the **RAG Retrieval** tab.
2. Select an incident or enter a free-form failure query (e.g. `Disk write failed: No space left on device`).
3. Click **Retrieve Historical Evidence**.
4. Review the **Hybrid Retrieval Results**:
   - **Retrieved Evidence Cards (`[E1]`, `[E2]`, etc.)**:
     - Historical Incident ID and Source Log File.
     - Similarity Score (Dense SBERT Cosine) & RRF Score.
     - Primary Error Message and Line Span.
     - **Chronological Context Events:** Surrounding $\pm 5$ lines showing what happened before and after the failure.
   - **Retrieval Latency:** Displays dual-retrieval and fusion execution time ($\sim 30\text{ ms}$).

---

## 7. LLM-Powered Grounded Synthesis (Stage 5)

1. Click the **LLM Synthesis** tab.
2. Ensure your Ollama engine is running (`ollama run llama3.2:3b`).
3. The top banner displays four decoupled status badges:
   - **Provider:** `Connected (Ollama)` or `Disconnected`
   - **Synthesis Status:** `IDLE`, `RUNNING`, `SUCCESS`, or `TIMEOUT`
   - **Privacy Status:** `Sanitized (Zero Credentials)`
   - **Grounding Status:** `Grounding: Validated (100% Citations Grounded)` or `Grounding: N/A (No Report)`
4. Click **Generate Grounded Synthesis**.
5. Once complete, inspect the structured report:
   - **Executive Summary:** Plain-English summary of the incident.
   - **Evidence-Grounded Root Cause:** Detailed causal explanation with inline citations linking directly to retrieved evidence (`[E1]`, `[E2]`).
   - **Remediation Steps:** Step-by-step diagnostic and remediation commands.
     - Each step includes a **Copy Command** button.
     - Each step indicates its grounding status (`Grounded with [E1]` or `Ungrounded - Human Review Required`).
   - **Diagnostic Principle:** If the error involves null pointers or unhandled exceptions, the report emphasizes tracing the source of the null value before proposing defensive code changes.

---

## 8. Model Evaluation & Benchmarks

1. Click the **Model Evaluation** tab.
2. Review the **Canonical Group-Aware Evaluation Matrix**:
   - Compares Stage 1 (80.70% Acc / 72.81% F1), Stage 2 (77.19% Acc / 65.31% F1), and Stage 3 (73.68% Acc / 64.90% F1).
   - Explains the data leakage audit and why naive splits produced artificially high results.
3. Review **Stage 4 RAG Metrics**: MRR (0.9532), Recall@1, Recall@5, and latency.
4. Review **Stage 5 Grounding Audit Results**: 7/7 test scenarios passing (E99 rejection, non-substitution, injection safety).
