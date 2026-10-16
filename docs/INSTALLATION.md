# TRACE Installation & Setup Guide (Windows)

This document provides complete, step-by-step instructions to clone, configure, install dependencies, and run the **TRACE** platform on a fresh Windows system.

---

## 1. System Requirements & Prerequisites

Before starting, ensure your system meets the following specifications:

| Component | Minimum Specification | Recommended Specification |
|:---|:---|:---|
| **Operating System** | Windows 10 (64-bit) Build 19041+ | Windows 11 (64-bit) |
| **Processor** | Intel Core i5 / AMD Ryzen 5 (4+ Cores) | Intel Core i7 / AMD Ryzen 7 (8+ Cores) |
| **System Memory (RAM)** | 8 GB | 16 GB or 32 GB |
| **Disk Space** | 5 GB free disk space | 15 GB free disk space (with Ollama model cache) |
| **Python** | Python 3.11.x (64-bit) | Python 3.11.5+ (64-bit) |
| **Node.js** | Node.js 18.x LTS or 20.x LTS | Node.js 20.x LTS with npm 10+ |
| **Local LLM Engine** | Ollama for Windows (v0.3.0+) | Ollama with `llama3.2:3b` |

> [!IMPORTANT]
> Ensure **Python 3.11 (64-bit)** is selected during installation, and check **"Add Python to PATH"**. PyTorch Geometric pre-built wheels are sensitive to Python minor versions.

---

## 2. Repository Cloning

Open **PowerShell** (Run as Administrator or regular user) and clone the repository:

```powershell
# Navigate to your workspace directory
cd C:\Users\hp\workspace

# Clone the repository
git clone https://github.com/ManikSalaria/automated-log-analysis-root-cause-detection.git

# Enter the repository root
cd automated-log-analysis-root-cause-detection
```

---

## 3. Python Virtual Environment Setup

Isolate project dependencies by creating a dedicated virtual environment in the repository root:

```powershell
# Verify Python version (must be 3.11)
python --version

# Create the virtual environment
python -m venv .venv

# Activate the virtual environment
.\.venv\Scripts\Activate.ps1
```

> [!NOTE]
> If PowerShell displays a script execution policy restriction error (`PSSecurityException`), run:
> ```powershell
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```
> Then re-run `.\.venv\Scripts\Activate.ps1`.

---

## 4. Backend Dependencies Installation

With the virtual environment activated, upgrade `pip` and install all required packages:

```powershell
# Upgrade pip, setuptools, and wheel
python -m pip install --upgrade pip setuptools wheel

# Install backend dependencies
pip install -r backend/requirements.txt
```

### PyTorch & PyTorch Geometric (PyG) Notes
`backend/requirements.txt` installs CPU-optimized PyTorch and PyTorch Geometric dependencies:
- `torch>=2.2.0`
- `torch-geometric>=2.5.0`
- `sentence-transformers>=2.5.0`
- `xgboost>=2.0.0`
- `scikit-learn>=1.4.0`

If PyTorch Geometric fails to build wheels on Windows, you can manually install the matching pre-built wheels via:
```powershell
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install torch-scatter torch-sparse torch-cluster torch-spline-conv -f https://data.pyg.org/whl/torch-2.2.0+cpu.html
pip install torch-geometric
```

---

## 5. Environment Configuration

Copy the sample environment file to create your local `.env`:

```powershell
Copy-Item .env.example .env
```

Open `.env` in an editor and review the parameters:

```ini
# TRACE Platform Environment Configuration
APP_NAME=TRACE
APP_ENV=development
DEBUG=True
PORT=8000
HOST=127.0.0.1

# SQLite WAL Database Configuration
DATABASE_URL=sqlite:///./backend/data/trace_review1.db

# LLM Root-Cause Synthesis & Remediation (Stage 5)
TRACE_LLM_PROVIDER=ollama
TRACE_OLLAMA_BASE_URL=http://localhost:11434
TRACE_OLLAMA_MODEL=llama3.2:3b
TRACE_LLM_TIMEOUT_SEC=90.0
TRACE_LLM_MAX_RETRIES=2

# Jenkins CI/CD Ingestion (Optional)
# JENKINS_URL=http://localhost:8080
# JENKINS_USER=admin
# JENKINS_API_TOKEN=your_jenkins_api_token
```

---

## 6. Frontend Dependencies Installation

Navigate to the `frontend/` directory and install the Node packages:

```powershell
cd frontend

# Install node dependencies
npm install

# Verify production build compilation
npm run build

# Return to repository root
cd ..
```

---

## 7. Ollama Local LLM Engine Setup (Stage 5)

TRACE uses Ollama as an on-premises, privacy-preserving LLM sidecar. This ensures that log telemetry and incident data never leave your local infrastructure.

1. Download and run the Windows installer from [ollama.com/download/windows](https://ollama.com/download/windows).
2. After installation, launch Ollama from the Windows Start menu or system tray.
3. Open a separate terminal window and pull the recommended lightweight model:

```powershell
# Pull the 3-billion parameter Llama-3.2 model (~2.0 GB)
ollama pull llama3.2:3b

# Verify Ollama is serving requests locally
curl http://localhost:11434/api/tags
```

> [!NOTE]
> If Ollama is not installed or unavailable, TRACE honestly reports `status="provider_unavailable"` with clear diagnostic guidance rather than fabricating synthetic or hallucinated reports. All other platform capabilities—including context-aware parsing, Stage 1-3 ML classification, and Stage 4 Hybrid RAG retrieval—remain 100% operational.

---

## 8. Bootstrapping Database & Model Artifacts

Before running tests or starting the servers, initialize the SQLite database schema and generate the baseline, XGBoost, GraphSAGE, and BM25 index artifacts:

```powershell
python scripts/bootstrap_models.py
```

This script is idempotent: it initializes the SQLite WAL database, trains the models using the canonical group-aware train partition (`backend/data/processed/group_train_incidents.csv`), builds the BM25 retrieval index, and saves all artifacts to `backend/data/models_cache/` in approximately 30 seconds.

---

## 9. Verifying the Setup

Run the automated backend test suite and verification scripts to confirm that your environment is fully functional:

```powershell
# Run the complete test suite (91 passing tests)
.\.venv\Scripts\python.exe -m pytest backend/tests -v

# Run the Stage 4 RAG retrieval evaluation script
.\.venv\Scripts\python.exe scripts/evaluate_rag_retrieval.py

# Run the Stage 5 LLM synthesis and grounding audit script
.\.venv\Scripts\python.exe scripts/evaluate_stage5_synthesis.py
```

Expected output:
- `backend/tests`: **94 passed** in ~60-70 seconds (including privacy persistence regression tests).
- `evaluate_rag_retrieval.py`: **MRR: 0.9532, HitRate@5: 94.74%, True Recall@5: 15.64%**.
- `evaluate_stage5_synthesis.py`: **7/7 scenarios passed** (Grounding invariant, E99 hallucination rejection, diagnostic remediation, injection safety).

---

## 10. Launching TRACE

To run the complete platform, start both the FastAPI backend and the React frontend development servers.

### Option A: Using the Automated Launch Scripts (Recommended)
```powershell
.\scripts\start_trace.ps1
# OR
.\scripts\start_servers.bat
```

### Option B: Manual Multi-Terminal Launch

**Terminal 1 — FastAPI Backend:**
```powershell
.\.venv\Scripts\Activate.ps1
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```
- API Base URL: `http://localhost:8000`
- Interactive Swagger UI: `http://localhost:8000/docs`
- Health Endpoint: `http://localhost:8000/api/v1/health`

**Terminal 2 — React Dashboard Frontend:**
```powershell
cd frontend
npm run dev
```
- Dashboard URL: `http://localhost:3000`

Open your browser and navigate to `http://localhost:3000` to explore the TRACE workbench.
