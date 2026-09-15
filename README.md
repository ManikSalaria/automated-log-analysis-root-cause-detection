# Automated Log Analysis and Root Cause Detection System using Machine Learning

[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/release/python-3110/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-009688.svg)](https://fastapi.tiangolo.com)
[![React 18](https://img.shields.io/badge/React-18.3-61DAFB.svg)](https://react.dev/)
[![Scikit-Learn](https://img.shields.io/badge/scikit--learn-1.4+-F7931E.svg)](https://scikit-learn.org/)
[![Vite](https://img.shields.io/badge/Vite-5.4-646CFF.svg)](https://vitejs.dev/)
[![SQLite WAL](https://img.shields.io/badge/SQLite-WAL--Mode-003B57.svg)](https://www.sqlite.org/wal.html)

An intelligent, privacy-preserving log analytics platform engineered to ingest heterogeneous CI/CD build logs and distributed microservice telemetry, sanitize sensitive credentials, parse multiline runtime events, classify failure categories using machine learning, and formulate explainable root-cause candidate recommendations.

---

## 1. Project Objective & Problem Statement

Modern enterprise continuous integration and deployment (CI/CD) pipelines—particularly Jenkins environments orchestrating automated testing, virtualization provisioning, and microservice transactions—generate tens of thousands of unstructured, noisy log lines per execution. 

### Key Engineering Challenges:
1. **High Diagnostic Latency:** Site Reliability Engineers (SREs) and software engineers spend hours manually inspecting sprawling console logs and complex multi-tier stack traces to diagnose build failures.
2. **Credential Leakage in Logs:** Raw logs frequently expose sensitive credentials (bearer tokens, passwords, AWS access keys, GitHub personal access tokens, private IP addresses), creating major security risks if fed into diagnostic models or external tools.
3. **Noisy and Heterogeneous Dialects:** Logs originate from diverse sources—such as Jenkins JVM core runtimes, Python/pytest test suites, and distributed microservices with trace headers—making centralized parsing difficult.
4. **Lack of Explainable Root-Cause Analysis:** Standard keyword-matching fails on novel phrasing and does not provide actionable remediation guidance.

### Proposed Solution:
This project implements a multi-stage, explainable machine learning architecture designed to automate log parsing, sanitize all credentials in-memory prior to storage, classify failure categories using a validated ML baseline, and provide actionable root-cause candidates with remediation commands.

---

## 2. System Architecture

The end-to-end processing pipeline operates deterministically across all ingested logs:

```
+-------------------------------------------------------------------------+
|                       Authentic Raw Log Ingestion                       |
|   (Jenkins Build Logs / Pytest Automation / Microservices Telemetry)    |
+-------------------------------------------------------------------------+
                                     |
                                     v
+-------------------------------------------------------------------------+
|                  Zero-PII Secret Sanitization Layer                     |
|    (Redacts AWS keys, GitHub PATs, JWTs, Passwords, and Private IPs)    |
+-------------------------------------------------------------------------+
                                     |
                                     v
+-------------------------------------------------------------------------+
|                   Multi-Dialect Structured Log Parser                   |
|   (Extracts timestamps, severities, service nodes, trace IDs, spans)    |
+-------------------------------------------------------------------------+
                                     |
                                     v
+-------------------------------------------------------------------------+
|                     Failure & Anomaly Detector                          |
|        (Extracts contextual multiline stack traces and exceptions)      |
+-------------------------------------------------------------------------+
                                     |
                                     v
+-------------------------------------------------------------------------+
|                       Incident-Level Partitioner                        |
|   (70% Train / 15% Val / 15% Held-Out Test with zero cross-leakage)     |
+-------------------------------------------------------------------------+
                                     |
                                     v
+-------------------------------------------------------------------------+
|                 Academic Baseline Classification Model                  |
|          (TF-IDF [Unigram + Bigram, 1500 features] + Random Forest)     |
+-------------------------------------------------------------------------+
                                     |
                                     v
+-------------------------------------------------------------------------+
|                  Root Cause Candidate Analysis Layer                    |
|      (Rule-grounded candidate matching and SRE remediation guidance)    |
+-------------------------------------------------------------------------+
                                     |
                                     v
+------------------------------------+------------------------------------+
|                                                                         |
v                                                                         v
+------------------------------------+   +--------------------------------+
|       FastAPI REST Endpoints       |   |       SQLite WAL Storage       |
|    (/upload, /analyze, /predict)   |   |   (Events, Incidents, Files)   |
+------------------------------------+   +--------------------------------+
                                     |
                                     v
+-------------------------------------------------------------------------+
|                        React 18 Dashboard UI                            |
|     (Interactive Workbench, Sanitization Audits, Parsed Event Tables)   |
+-------------------------------------------------------------------------+
```

---

## 3. Current Implementation (Review-1 Foundation)

This milestone establishes the **Review-1 Foundation** of the major project, focused on technical defensibility, verified data provenance, and empirical evaluation:

- **100% Authentic Corpus:** Evaluated exclusively on genuine logs (`1130.txt`, `Jenkins_Log_Under_1MB.txt`, `jenkins_gist_crash.log`), encompassing 5,526 lines and 826.8 KB of telemetry. Zero synthetic datasets are used in the active pipeline.
- **Incident-Level Splitting:** 374 authentic failure incidents partitioned without data leakage:
  - **Training:** 261 incidents (69.8%)
  - **Validation:** 56 incidents (15.0%)
  - **Held-Out Test:** 57 incidents (15.2%)
- **Academic ML Baseline:** TF-IDF ($n$-grams $1-2$, 1,500 maximum features) + Random Forest Classifier (100 estimators, max depth 20).
- **Held-Out Test Evaluation:** **92.98% Accuracy** and **91.34% Macro-F1** measured strictly on the held-out test partition.
- **Transparent Root Cause Candidate Layer:** Deterministic heuristic mapping from error signatures to probable architectural root causes and concrete remediation steps.
- **Production API & UI:** High-performance FastAPI backend connected to SQLite (WAL mode) and a responsive React 18 / Tailwind CSS dashboard.

---

## 4. Dataset & Data Provenance

The system is calibrated on three distinct production dialects:

| Raw File | Size (bytes) | Lines | Source Dialect & Characteristics |
|---|---|---|---|
| `1130.txt` | 191,426 | 1,500 | Continuous microservice telemetry across 6 services (`auth`, `order`, `payment`, `inventory`, `notification`, `api-gateway`) with timestamps, HTTP status codes, trace IDs, and latency values. |
| `Jenkins_Log_Under_1MB.txt` | 424,551 | 1,576 | Authentic HPE Morpheus qualification build run (#157) containing datastore provisioning failures, GFS2 I/O errors, and test assertions. |
| `jenkins_gist_crash.log` | 210,699 | 2,450 | Public Jenkins core JVM startup crash stream detailing Winstone/Jetty initialization, Stapler execution, and deep multiline Java stack traces. |

### Supported Failure Categories:
1. `STORAGE_AND_IO_ERROR` (Datastore configuration errors, GFS2 filesystem mount issues, QEMU image conversion I/O errors).
2. `NETWORK_DEPENDENCY_FAILURE` (Connection refused by payment service, HTTP 502/503/504 gateway timeouts).
3. `DATABASE_AND_CACHE_TIMEOUT` (HikariCP connection pool exhaustion, Redis connection timeouts).
4. `AUTHENTICATION_SECURITY_ERROR` (Expired bearer tokens, CSRF crumb issuer token rejection, Jira auth failure).
5. `INTERNAL_APPLICATION_LOGIC_ERROR` (Unhandled null pointers in business logic, transaction rollbacks).
6. `PLUGIN_DESCRIPTOR_RESOLUTION_ERROR` (Jenkins missing plugin descriptors, ClassNotFoundExceptions, Jelly tag errors).
7. `TEST_ASSERTION_FAILURE` (Pytest assertion verification failures, VM state polling timeouts).
8. `MESSAGE_BROKER_FAILURE` (Kafka consumer poll failures, queue depth overflow).
9. `RESOURCE_EXHAUSTION_CRASH` (Container memory limits exceeded, Java heap space out-of-memory).
10. `ENVIRONMENT_AND_PIPELINE_ERROR` (General pipeline environment and runner anomalies).

---

## 5. Core Architectural Components

### 5.1 Zero-PII Secret Sanitizer (`app/core/security.py`)
Scans every line before ingestion or model processing using deterministic regular expressions:
- AWS Access Keys (`AKIA[0-9A-Z]{16}`) -> `<REDACTED:AWS_KEY>`
- GitHub/GitLab Personal Access Tokens (`ghp_[0-9a-zA-Z]{36}`) -> `<REDACTED:GITHUB_TOKEN>`
- JSON Web Tokens (JWT) -> `<REDACTED:TOKEN>`
- Password and secret fields -> `<REDACTED:SECRET>`
- IPv4 Addresses -> `<IP>`

### 5.2 Structured Multi-Dialect Parser (`app/parsers/regex_parser.py`)
Normalizes heterogeneous logs into a structured event model containing `timestamp`, `level`, `service`, `component`, `node`, `trace_id`, `span_id`, `status_code`, `latency_ms`, and `sanitized_message`.

### 5.3 Root Cause Candidate Analysis (`app/analysis/root_cause_candidate.py`)
Translates classified failure categories and error evidence into explainable engineering guidance:
- Storage failure -> Inspects iSCSI target portal, cluster configuration IDs, and host mount permissions.
- Dependency failure -> Recommends checking service health endpoints, circuit breakers, and network routes.
- Database timeout -> Recommends checking connection pool ceilings, slow queries, and deadlocks.

### 5.4 Database Persistence (`app/core/database.py`)
SQLite database operating in Write-Ahead Logging (`WAL`) mode with foreign keys enabled:
- `source_files`: File hashes, sizes, line counts, and timestamps.
- `parsed_events`: Normalized structured log events.
- `incidents`: Detected failure incidents with line spans, predictions, and evidence text.
- `model_evaluations`: Persisted evaluation metrics and confusion matrices.

---

## 6. Repository Folder Structure

```
trace-platform/
├── backend/
│   ├── app/
│   │   ├── analysis/
│   │   │   └── root_cause_candidate.py     # Root cause candidate analysis
│   │   ├── api/
│   │   │   └── v1/
│   │   │       ├── api.py                  # API router aggregation
│   │   │       └── endpoints/
│   │   │           ├── analysis.py         # Full incident analysis endpoint
│   │   │           ├── classification.py   # Baseline prediction endpoint
│   │   │           ├── events.py           # Structured events query endpoint
│   │   │           ├── health.py           # Health check endpoint
│   │   │           ├── incidents.py        # Incidents query endpoint
│   │   │           ├── ingestion.py        # Log file upload endpoint
│   │   │           └── metrics.py          # Dynamic evaluation metrics endpoint
│   │   ├── core/
│   │   │   ├── config.py                   # Settings and taxonomy
│   │   │   ├── database.py                 # SQLite WAL persistence layer
│   │   │   └── security.py                 # Zero-PII secret sanitizer
│   │   ├── ml/
│   │   │   └── baseline/
│   │   │       └── tfidf_rf.py             # TF-IDF + Random Forest baseline
│   │   ├── parsers/
│   │   │   └── regex_parser.py             # Multi-dialect regex log parser
│   │   └── schemas/
│   │       └── log_schema.py               # Pydantic data transfer schemas
│   ├── data/
│   │   ├── processed/                      # Split CSVs and manifests
│   │   │   ├── authentic_incidents.csv
│   │   │   ├── split_manifest.json
│   │   │   ├── train_incidents.csv
│   │   │   ├── val_incidents.csv
│   │   │   └── test_incidents.csv
│   │   ├── raw/                            # Immutable authentic raw logs
│   │   │   ├── 1130.txt
│   │   │   ├── Jenkins_Log_Under_1MB.txt
│   │   │   └── jenkins_gist_crash.log
│   │   ├── dataset_provenance.json         # Checksums and provenance registry
│   │   └── evaluation_manifest.json        # Test-set evaluation metrics
│   ├── tests/
│   │   └── test_review1_pipeline.py        # Comprehensive test suite (18 tests)
│   ├── main.py                             # FastAPI application entry point
│   └── requirements.txt                    # Python dependencies
├── frontend/
│   ├── src/
│   │   ├── App.tsx                         # Main React application dashboard
│   │   └── main.tsx                        # React DOM entry point
│   ├── index.html                          # HTML template
│   ├── package.json                        # Node.js dependencies
│   ├── tsconfig.json                       # TypeScript compiler configuration
│   └── vite.config.ts                      # Vite build configuration
├── scripts/
│   ├── acceptance_blackbox_test.py         # End-to-end black-box verification
│   ├── audit_raw_logs_privacy.py           # Raw log credential scanner
│   ├── construct_authentic_dataset.py      # Incident extractor and splitter
│   ├── ingest_authentic_logs_to_db.py      # Database populator
│   ├── scan_secrets_audit.py               # Repository secret audit script
│   ├── start_servers.bat                   # Server launch batch script
│   ├── train_and_evaluate_baseline.py      # Baseline model training & evaluation
│   └── verify_live_inference.py            # CLI verification script
├── .gitignore                              # Production gitignore rules
└── README.md                               # Project documentation
```

---

## 7. Installation & Setup

### Prerequisites
- Python 3.11+
- Node.js 18+ & npm
- Git

### 7.1 Backend Setup
```bash
# 1. Clone the repository
git clone <https://github.com/ManikSalaria/automated-log-analysis-root-cause-detection.git>
cd trace-platform

# 2. Create and activate a Python 3.11 virtual environment
py -3.11 -m venv .venv
# On Windows:
.\.venv\Scripts\activate
# On Linux/macOS:
# source .venv/bin/activate

# 3. Install Python dependencies
pip install -r backend/requirements.txt
```

### 7.2 Dataset Preparation & Model Training
```bash
# Extract incidents from raw logs and create stratified train/val/test splits
python scripts/construct_authentic_dataset.py

# Train the baseline TF-IDF + Random Forest model and evaluate on held-out test data
python scripts/train_and_evaluate_baseline.py

# Ingest authentic raw logs into SQLite database
python scripts/ingest_authentic_logs_to_db.py
```

### 7.3 Frontend Setup
```bash
cd frontend
npm install
```

---

## 8. Running the Application

### Option A: Quick Launch (Windows)
Double-click or run:
```cmd
scripts\start_servers.bat
```
This concurrently opens the FastAPI backend and Vite frontend in separate terminal windows.

### Option B: Manual Execution
**Terminal 1 (FastAPI Backend):**
```bash
python -m uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload
```
- API Documentation (Swagger UI): `http://127.0.0.1:8000/docs`
- Health Check: `http://127.0.0.1:8000/api/v1/health`

**Terminal 2 (React Frontend):**
```bash
cd frontend
npm run dev
```
- Web Dashboard: `http://localhost:3000`

---

## 9. Testing & Quality Assurance

Run the automated backend test suite covering secret sanitization, multiline parsing, model inference, SQLite transactions, and API endpoints:
```bash
pytest backend/tests/ -v
```
*(All 18 tests pass).*

Run the frontend TypeScript typecheck and production build:
```bash
cd frontend
npm run build
```

Run the end-to-end black-box verification on all authentic log files:
```bash
python scripts/acceptance_blackbox_test.py
```

---

## 10. Empirical Evaluation Metrics

Evaluated on the **57 held-out test incidents** strictly isolated from training:

```
================================================================================
Metric                           | Measured Value (TF-IDF + Random Forest)
--------------------------------------------------------------------------------
Accuracy                         | 92.98%
Macro Precision                  | 93.26%
Macro Recall                     | 92.26%
Macro F1-Score                   | 91.34%
Mean Inference Latency           | 32.97 ms
p95 Inference Latency            | 35.63 ms
Feature Space                    | 1,500 n-gram lexical features (unigram + bigram)
Training Time                    | 0.276 s
Partition Policy                 | Incident-level Stratified Split (70% Train, 15% Val, 15% Test)
================================================================================
```

### Per-Category Test Breakdown:
- `STORAGE_AND_IO_ERROR` ($N=12$): Precision = 100.0%, Recall = 91.7%, **F1 = 95.7%**
- `NETWORK_DEPENDENCY_FAILURE` ($N=7$): Precision = 100.0%, Recall = 85.7%, **F1 = 92.3%**
- `DATABASE_AND_CACHE_TIMEOUT` ($N=4$): Precision = 100.0%, Recall = 100.0%, **F1 = 100.0%**
- `AUTHENTICATION_SECURITY_ERROR` ($N=3$): Precision = 75.0%, Recall = 100.0%, **F1 = 85.7%**
- `TEST_ASSERTION_FAILURE` ($N=2$): Precision = 66.7%, Recall = 100.0%, **F1 = 80.0%**
- `PLUGIN_DESCRIPTOR_RESOLUTION_ERROR` ($N=2$): Precision = 100.0%, Recall = 50.0%, **F1 = 66.7%**
- `RESOURCE_EXHAUSTION_CRASH` ($N=1$): Precision = 100.0%, Recall = 100.0%, **F1 = 100.0%**

---

## 11. Known Limitations

1. **Lexical Vocabulary Shift:** The baseline bag-of-words model matches lexical n-grams and is sensitive to vocabulary shifts when encountering unseen error phrasing not present in training data.
2. **Minority Class Support:** Rare failure modes with few test instances exhibit higher variance.
3. **Sequential Context:** Events in distributed call chains are currently parsed as discrete incidents rather than a temporal graph.

---

## 12. Development Roadmap (Future Phases / Review 2)

The architecture is modularized to support advanced deep learning models without rewriting the ingestion, parsing, and storage foundation:

1. **Sentence-BERT Embedding Stage:** Integration of `all-MiniLM-L6-v2` transformer to generate dense 384-dimensional semantic embeddings, resolving vocabulary shift limitations.
2. **XGBoost Classifier Stage:** 407-dimensional hybrid matrix combining 384 dense semantic features with 23 engineered operational metadata features.
3. **GraphSAGE Topological Root Cause Analysis:** PyTorch Geometric Graph Neural Network (GNN) modeling service call dependencies and pipeline stage DAGs to trace error propagation across microservices.
4. **Historical Incident RAG:** Time-decayed ChromaDB vector retrieval matching active incidents against historical postmortems.
5. **LLM SRE Report Generation:** Automated incident postmortem generation using sanitized context fed to an LLM.

---

## 13. License

This project is developed for educational and research purposes under the academic major project curriculum.
