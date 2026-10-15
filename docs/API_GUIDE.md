# TRACE REST API Reference Guide

The TRACE platform exposes a high-performance RESTful API powered by **FastAPI**. All endpoints accept and return JSON payloads (except file uploads, which accept `multipart/form-data`).

Base URL: `http://127.0.0.1:8000`  
Interactive Swagger UI: `http://127.0.0.1:8000/docs`  
ReDoc UI: `http://127.0.0.1:8000/redoc`

---

## 1. Health & System Status

### `GET /api/v1/health`
Checks backend service availability, database connectivity, and Ollama LLM sidecar status.

#### Example Request
```bash
curl -X GET http://127.0.0.1:8000/api/v1/health
```

#### Example Response (200 OK)
```json
{
  "status": "healthy",
  "app_name": "TRACE",
  "version": "1.0.0",
  "database": "connected",
  "llm_provider": {
    "provider": "ollama",
    "base_url": "http://localhost:11434",
    "model": "llama3.2:3b",
    "status": "reachable",
    "timeout_sec": 90.0
  }
}
```

---

## 2. Ingestion & Privacy Endpoints

### `POST /api/v1/ingest/upload`
Uploads a raw log file (`.txt`, `.log`). Automatically redacts credentials in-memory, parses multiline events, and extracts incidents.

#### Example Request
```bash
curl -X POST "http://127.0.0.1:8000/api/v1/ingest/upload" \
  -H "accept: application/json" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@backend/data/raw/Jenkins_Log_Under_1MB.txt"
```

#### Example Response (200 OK)
```json
{
  "status": "success",
  "file_id": 1,
  "filename": "Jenkins_Log_Under_1MB.txt",
  "total_lines": 3120,
  "sanitized_tokens_count": 14,
  "events_extracted": 1845,
  "incidents_detected": 18,
  "processing_time_ms": 342.5
}
```

---

### `POST /api/v1/ingest/jenkins`
Ingests a Jenkins CI/CD console log directly from raw text with optional build metadata.

#### Example Request
```bash
curl -X POST "http://127.0.0.1:8000/api/v1/ingest/jenkins" \
  -H "Content-Type: application/json" \
  -d '{
    "job_name": "trace-pipeline-build",
    "build_number": 42,
    "git_commit": "a1b2c3d4e5f6",
    "git_branch": "main",
    "console_log": "2026-10-15 14:22:01 [ERROR] [auth-service] Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.e30.t-ID Invalid JWT signature\n2026-10-15 14:22:02 [FATAL] [auth-service] Authentication failed for user root"
  }'
```

#### Example Response (200 OK)
```json
{
  "status": "success",
  "file_id": 2,
  "job_name": "trace-pipeline-build",
  "build_number": 42,
  "sanitized": true,
  "events_extracted": 2,
  "incidents_detected": 1
}
```

---

## 3. Incidents & Events Endpoints

### `GET /api/v1/incidents`
Lists detected incidents with pagination and optional filtering by severity or component.

#### Query Parameters
- `skip` (int, default: 0): Records to skip for pagination.
- `limit` (int, default: 50): Maximum records to return.
- `severity` (string, optional): Filter by `CRITICAL`, `ERROR`, `WARNING`.
- `component` (string, optional): Filter by component name.

#### Example Request
```bash
curl -X GET "http://127.0.0.1:8000/api/v1/incidents?limit=2"
```

#### Example Response (200 OK)
```json
[
  {
    "incident_id": "INC-0012",
    "file_id": 1,
    "severity": "CRITICAL",
    "component": "storage-controller",
    "start_line": 842,
    "end_line": 855,
    "primary_message": "Disk write failed: No space left on device: /var/lib/docker",
    "category": "STORAGE_AND_IO_ERROR",
    "event_count": 6
  },
  {
    "incident_id": "INC-0013",
    "file_id": 1,
    "severity": "ERROR",
    "component": "auth-service",
    "start_line": 910,
    "end_line": 922,
    "primary_message": "Failed to authenticate client credentials against OAuth2 endpoint",
    "category": "AUTHENTICATION_SECURITY_ERROR",
    "event_count": 4
  }
]
```

---

### `GET /api/v1/incidents/{incident_id}`
Retrieves full details for a specific incident, including stack trace lines and surrounding chronological events.

#### Example Request
```bash
curl -X GET "http://127.0.0.1:8000/api/v1/incidents/INC-0012"
```

#### Example Response (200 OK)
```json
{
  "incident_id": "INC-0012",
  "file_id": 1,
  "severity": "CRITICAL",
  "component": "storage-controller",
  "start_line": 842,
  "end_line": 855,
  "primary_message": "Disk write failed: No space left on device: /var/lib/docker",
  "stack_trace": "java.io.IOException: No space left on device\n\tat java.base/java.io.FileOutputStream.writeBytes(Native Method)\n\tat com.trace.storage.Writer.flush(Writer.java:142)",
  "category": "STORAGE_AND_IO_ERROR",
  "events": [
    {
      "event_id": 1045,
      "line_number": 841,
      "log_level": "WARNING",
      "component": "storage-controller",
      "message": "Storage volume /var/lib/docker usage exceeded 95%"
    },
    {
      "event_id": 1046,
      "line_number": 842,
      "log_level": "CRITICAL",
      "component": "storage-controller",
      "message": "Disk write failed: No space left on device: /var/lib/docker"
    }
  ]
}
```

---

## 4. Machine Learning Classification Endpoint

### `POST /api/v1/classify`
Classifies an incident using one of the three integrated ML models:
- `stage1_baseline`: TF-IDF + Random Forest
- `stage2_xgboost`: Sentence-BERT + XGBoost
- `stage3_graphsage`: GraphSAGE GNN (PyTorch Geometric)

#### Example Request
```bash
curl -X POST "http://127.0.0.1:8000/api/v1/classify" \
  -H "Content-Type: application/json" \
  -d '{
    "incident_id": "INC-0012",
    "model_name": "stage3_graphsage",
    "message": "Disk write failed: No space left on device: /var/lib/docker",
    "stack_trace": "java.io.IOException: No space left on device",
    "component": "storage-controller",
    "severity": "CRITICAL"
  }'
```

#### Example Response (200 OK)
```json
{
  "incident_id": "INC-0012",
  "model_used": "stage3_graphsage",
  "predicted_category": "STORAGE_AND_IO_ERROR",
  "confidence": 0.8842,
  "inference_latency_ms": 31.2,
  "class_probabilities": {
    "STORAGE_AND_IO_ERROR": 0.8842,
    "RESOURCE_EXHAUSTION_CRASH": 0.0815,
    "ENVIRONMENT_AND_PIPELINE_ERROR": 0.0210,
    "DATABASE_AND_CACHE_TIMEOUT": 0.0075,
    "INTERNAL_APPLICATION_LOGIC_ERROR": 0.0058
  }
}
```

---

## 5. Stage 4 Hybrid RAG Retrieval Endpoint

### `POST /api/v1/rag/retrieve`
Retrieves the top-$K$ historical incidents and surrounding chronological log lines using hybrid BM25 + SBERT Reciprocal Rank Fusion.

#### Example Request
```bash
curl -X POST "http://127.0.0.1:8000/api/v1/rag/retrieve" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Disk write failed: No space left on device: /var/lib/docker",
    "incident_id": "INC-0012",
    "component": "storage-controller",
    "category": "STORAGE_AND_IO_ERROR",
    "top_k": 3
  }'
```

#### Example Response (200 OK)
```json
{
  "query": "Disk write failed: No space left on device: /var/lib/docker",
  "total_retrieved": 3,
  "retrieval_latency_ms": 28.4,
  "fusion_method": "Reciprocal Rank Fusion (k=60)",
  "evidence": [
    {
      "evidence_id": "E1",
      "historical_incident_id": "HIST-042",
      "category": "STORAGE_AND_IO_ERROR",
      "similarity_score": 0.9412,
      "rrf_score": 0.0328,
      "primary_message": "IOException: write failed: ENOSPC (No space left on device) during cache commit",
      "component": "storage-controller",
      "source_file": "Jenkins_Log_Under_1MB.txt",
      "line_span": [412, 420],
      "context_events": [
        "Line 411 [WARN] [storage-controller] High watermark 98% reached on volume",
        "Line 412 [ERROR] [storage-controller] Disk write failed: ENOSPC"
      ]
    },
    {
      "evidence_id": "E2",
      "historical_incident_id": "HIST-089",
      "category": "STORAGE_AND_IO_ERROR",
      "similarity_score": 0.8875,
      "rrf_score": 0.0294,
      "primary_message": "Failed to persist artifact bundle: No space left on device",
      "component": "artifact-uploader",
      "source_file": "1130.txt",
      "line_span": [1201, 1208],
      "context_events": [
        "Line 1201 [ERROR] [artifact-uploader] Upload aborted due to local disk fullness"
      ]
    }
  ]
}
```

---

## 6. Stage 5 LLM Synthesis Endpoint

### `POST /api/v1/rag/synthesize`
Generates an evidence-grounded root cause explanation and diagnostic remediation suggestions using local Ollama (`llama3.2:3b`).

#### Example Request
```bash
curl -X POST "http://127.0.0.1:8000/api/v1/rag/synthesize" \
  -H "Content-Type: application/json" \
  -d '{
    "incident_id": "INC-0012",
    "query": "Disk write failed: No space left on device: /var/lib/docker",
    "component": "storage-controller",
    "category": "STORAGE_AND_IO_ERROR",
    "top_k": 3
  }'
```

#### Example Response (200 OK)
```json
{
  "incident_id": "INC-0012",
  "status": "SUCCESS",
  "provider": "ollama",
  "model": "llama3.2:3b",
  "synthesis_latency_ms": 3210.5,
  "privacy_sanitized": true,
  "report": {
    "summary": "Storage volume exhaustion caused write operations to fail abruptly on /var/lib/docker.",
    "root_cause_analysis": "The storage-controller attempted to flush transaction logs to /var/lib/docker, but the host volume reached 100% inode or block capacity as evidenced by [E1]. This resulted in an unhandled IOException and aborted Docker operations.",
    "remediation_steps": [
      {
        "step_number": 1,
        "action": "Inspect disk usage and prune orphaned containers/images",
        "command": "docker system prune -af --volumes && df -h /var/lib/docker",
        "is_grounded": true,
        "supporting_evidence": ["E1"]
      },
      {
        "step_number": 2,
        "action": "Verify storage volume quota and expand partition if needed",
        "command": "lvextend -r -l +100%FREE /dev/mapper/vg_docker-lv_docker",
        "is_grounded": true,
        "supporting_evidence": ["E1", "E2"]
      }
    ],
    "grounding_audit": {
      "is_valid": true,
      "unsupported_claims_count": 0,
      "grounded_remediations_ratio": "2/2",
      "citations_verified": ["E1", "E2"]
    }
  }
}
```

#### Example Response on Timeout (504 Gateway Timeout or Graceful Status)
```json
{
  "incident_id": "INC-0012",
  "status": "TIMEOUT",
  "provider": "ollama",
  "model": "llama3.2:3b",
  "synthesis_latency_ms": 90150.2,
  "privacy_sanitized": true,
  "report": null,
  "error_message": "LLM request timed out after 90.0 seconds. No report was generated; please verify Ollama resource allocation."
}
```

---

## 7. Model Evaluation & Comparison Endpoint

### `GET /api/v1/metrics/comparison`
Returns empirical comparison metrics across all evaluation stages evaluated on the held-out canonical group-aware dataset (57 test incidents).

#### Example Request
```bash
curl -X GET "http://127.0.0.1:8000/api/v1/metrics/comparison"
```

#### Example Response (200 OK)
```json
{
  "evaluation_split": "Canonical Group-Aware Stratified Split (Leakage-Free)",
  "test_sample_count": 57,
  "models": [
    {
      "stage": "Stage 1",
      "name": "TF-IDF + Random Forest",
      "accuracy": 0.8070,
      "macro_f1": 0.7281,
      "precision_macro": 0.7235,
      "recall_macro": 0.7589,
      "avg_latency_ms": 32.65
    },
    {
      "stage": "Stage 2",
      "name": "Sentence-BERT + XGBoost",
      "accuracy": 0.7719,
      "macro_f1": 0.6531,
      "precision_macro": 0.6417,
      "recall_macro": 0.7158,
      "avg_latency_ms": 34.98
    },
    {
      "stage": "Stage 3",
      "name": "GraphSAGE (PyG Inductive)",
      "accuracy": 0.7368,
      "macro_f1": 0.6490,
      "precision_macro": 0.6179,
      "recall_macro": 0.7429,
      "avg_latency_ms": 30.52
    }
  ],
  "rag_retrieval_metrics": {
    "stage": "Stage 4",
    "mrr": 0.9532,
    "recall_at_5": 0.9474,
    "precision_at_1": 0.9474,
    "avg_latency_ms": 31.63
  },
  "stage5_grounding_audit": {
    "total_scenarios_evaluated": 7,
    "scenarios_passed": 7,
    "pass_rate": 1.0
  }
}
```
