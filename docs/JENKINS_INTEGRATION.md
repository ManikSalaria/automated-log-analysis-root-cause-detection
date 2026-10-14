# TRACE Jenkins CI/CD Pipeline Integration Guide

This guide details how external engineering teams can connect remote Jenkins instances to TRACE to automatically stream build console output, scrub sensitive credentials, parse multiline runtime telemetry, classify failure categories via machine learning, and formulate explainable root-cause candidate recommendations.

---

## 1. Architecture & Push-Model Request Flow

TRACE operates on an **inbound push model**:

```
+-----------------------------------------------------------------------------------+
|                            Remote Jenkins Build Agent                             |
|                                                                                   |
|   1. Executes checkout, test suite, and compilation.                              |
|   2. Captures console log in `post { always { ... } }` block.                     |
|   3. Resolves TRACE token from Jenkins Credentials (`withCredentials`).          |
|   4. Issues authenticated HTTP POST to TRACE (`/api/v1/jenkins/ingest`).           |
+-----------------------------------------------------------------------------------+
                                          |
                                          | HTTPS / HTTP POST
                                          | Authorization: Bearer <trc_token>
                                          v
+-----------------------------------------------------------------------------------+
|                             TRACE Backend Platform                                |
|                                                                                   |
|   1. Token Verification: Validates SHA-256 hash of token in SQLite.               |
|   2. Idempotency Check: Checks build hash to prevent duplicate records on retry.  |
|   3. In-Memory Sanitizer: Redacts AWS keys, tokens, passwords, and IPs.           |
|   4. Structural Parser: Extracts timestamps, components, severities, and traces.  |
|   5. ML Inference: Predicts failure category using Review-1 baseline model.        |
|   6. RCA Candidate Formulation: Generates explainable remediation guidance.       |
|   7. SQLite Persistence: Updates `jenkins_builds`, `parsed_events`, `incidents`.   |
+-----------------------------------------------------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                             TRACE React Dashboard                                 |
|                                                                                   |
|   Real-time Jenkins feed, incident inspector, and root-cause candidate workbench. |
+-----------------------------------------------------------------------------------+
```

> **Important Security Architecture Note:** TRACE does **not** poll or initiate inbound network connections into private Jenkins networks or controller nodes. External Jenkins instances push console logs outward to TRACE over standard HTTP/HTTPS.

---

## 2. Setting Up the Integration

### Step 1: Generate an Integration Token in TRACE
1. Open the TRACE Web Dashboard at `http://localhost:3000` (or your deployed URL).
2. Navigate to the **Jenkins Integration** tab.
3. Under **Generate Integration Token**, enter a descriptive name (e.g. `Jenkins Master - Production`) and click **Generate New Token**.
4. Copy the generated secret token (prefixed with `trc_`).
   > **Note:** The plaintext token is displayed only once upon generation. TRACE stores only its secure SHA-256 hash in SQLite.

### Step 2: Store the Token in Jenkins Credentials
1. In your Jenkins Controller UI, navigate to:
   **Manage Jenkins** &rarr; **Credentials** &rarr; **System** &rarr; **Global credentials (unrestricted)**.
2. Click **Add Credentials**.
3. Configure the credential fields:
   - **Kind:** `Secret text`
   - **Scope:** `Global`
   - **Secret:** Paste the TRACE integration token (`trc_...`)
   - **ID:** `trace-api-token`
   - **Description:** `TRACE AI Platform Integration Token`
4. Click **Create**.

### Step 3: Embed the Pipeline Post-Action in `Jenkinsfile`
Copy the declarative pipeline post-action into your repository's `Jenkinsfile`:

```groovy
post {
    always {
        withCredentials([string(credentialsId: 'trace-api-token', variable: 'TRACE_TOKEN')]) {
            sh '''
                set +x  # Prevent printing credentials or command traces

                CONSOLE_LOG="jenkins_${BUILD_NUMBER}.log"

                # Retrieve full console text via Jenkins build REST API
                if [ -n "$BUILD_URL" ]; then
                    curl -s -k --globoff "${BUILD_URL}consoleText" > "$CONSOLE_LOG" 2>/dev/null || true
                fi

                # Fallback if consoleText API endpoint was not reachable
                if [ ! -s "$CONSOLE_LOG" ]; then
                    echo "[INFO] Build ${JOB_NAME} #${BUILD_NUMBER} completed with status: ${currentBuild.currentResult}" > "$CONSOLE_LOG"
                fi

                # Submit log and build metadata to TRACE backend
                HTTP_CODE=$(curl -s -w "%{http_code}" -o trace_response.json \
                    -X POST "http://127.0.0.1:8000/api/v1/jenkins/ingest" \
                    -H "Authorization: Bearer ${TRACE_TOKEN}" \
                    -F "job_name=${JOB_NAME}" \
                    -F "build_number=${BUILD_NUMBER}" \
                    -F "build_status=${currentBuild.currentResult}" \
                    -F "build_url=${BUILD_URL}" \
                    -F "repo_url=${GIT_URL}" \
                    -F "commit_sha=${GIT_COMMIT}" \
                    -F "file=@${CONSOLE_LOG}")

                if [ "$HTTP_CODE" -eq 200 ]; then
                    echo "[TRACE] Ingestion successful. Build analysis ready on TRACE dashboard."
                else
                    echo "[TRACE] Ingestion returned HTTP $HTTP_CODE (non-fatal, build result preserved)."
                    cat trace_response.json 2>/dev/null || true
                    echo ""
                fi

                rm -f "$CONSOLE_LOG" trace_response.json
            '''
        }
    }
}
```

---

## 3. Backend API Reference

### 3.1 Test Connection
- **Endpoint:** `POST /api/v1/jenkins/test-connection`
- **Headers:** `Authorization: Bearer <trc_token>` or `X-TRACE-API-KEY: <trc_token>`
- **Response:**
  ```json
  {
    "status": "CONNECTED",
    "integration_id": 1,
    "integration_name": "Jenkins Master - Production",
    "timestamp": "2026-10-13 00:30:00 UTC",
    "message": "Successfully authenticated as 'Jenkins Master - Production'."
  }
  ```

### 3.2 Ingest Build Log & Metadata
- **Endpoint:** `POST /api/v1/jenkins/ingest`
- **Headers:**
  - `Authorization: Bearer <trc_token>`
  - `Content-Type: application/json` OR `multipart/form-data`
- **JSON Payload Example:**
  ```json
  {
    "job_name": "qualification-cluster-e2e",
    "build_number": "101",
    "build_status": "FAILURE",
    "build_url": "https://jenkins.company.com/job/qualification-cluster-e2e/101/",
    "repo_url": "https://github.com/org/repo.git",
    "commit_sha": "a1b2c3d4e5f67890",
    "log_text": "2026-09-15T09:04:30.123Z ERROR [order-service] Connection refused by payment service\nAssertionError: storage cluster id missing"
  }
  ```
- **Multipart Form Fields:**
  - `job_name` (string, required)
  - `build_number` (string, required)
  - `build_status` (string, optional: `SUCCESS`, `FAILURE`, `UNSTABLE`)
  - `build_url` (string, optional)
  - `repo_url` (string, optional)
  - `commit_sha` (string, optional)
  - `file` (file upload containing console output, or `log_text`)
- **Response Example:**
  ```json
  {
    "build_id": "qualification-cluster-e2e#101",
    "job_name": "qualification-cluster-e2e",
    "build_number": "101",
    "build_status": "FAILURE",
    "is_failure": true,
    "failure_category": "STORAGE_AND_IO_ERROR",
    "confidence": 0.7391,
    "root_cause_candidate": "Storage Infrastructure / Datastore Configuration Failure",
    "events_count": 48,
    "incidents_count": 1,
    "ingested_at": "2026-10-13 00:35:10 UTC",
    "is_retry": false,
    "view_url": "/api/v1/jenkins/builds/qualification-cluster-e2e%23101"
  }
  ```

### 3.3 List Ingested Builds
- **Endpoint:** `GET /api/v1/jenkins/builds?limit=50&offset=0&job_name=&is_failure=`
- **Response:** Array of `JenkinsBuildSummaryItem` objects.

### 3.4 Build Detail & Incidents
- **Endpoint:** `GET /api/v1/jenkins/builds/{build_id}`
- **Response:** Complete build metadata, parsed events preview, detected failure incidents, and classification rationale.

---

## 4. Security, Idempotency & Retry Guarantees

1. **Zero-PII Storage:**
   All ingested logs pass through `SecretMasker.sanitize()` before being persisted to SQLite or analyzed by the ML baseline. Plaintext AWS access keys, GitHub PATs, JWT tokens, passwords, and IPv4 addresses are masked.
2. **Idempotency on Pipeline Retries:**
   If a Jenkins build retries transmission of an identical log, TRACE matches the content SHA-256 hash and returns the existing analysis with `"is_retry": true` without creating duplicate records or bloating SQLite.
3. **Payload Limits:**
   Logs exceeding 20 MB are rejected with HTTP 413 to prevent memory exhaustion.
4. **Non-Breaking Pipeline Execution:**
   The `Jenkinsfile` post-action executes with `|| true` and checks HTTP status codes without failing the parent CI build if TRACE is temporarily unreachable.
5. **Token Revocation:**
   Any compromised token can be immediately revoked via the dashboard or `POST /api/v1/jenkins/tokens/{token_id}/revoke`, preventing any further log ingestion under that token.

---

## 5. Local Testing & Verification

1. **Run Backend Test Suite:**
   ```powershell
   .\.venv\Scripts\pytest.exe backend/tests/ -v
   ```
   Verifies all 32 automated tests (token auth, sanitization, validation, idempotency, ML inference, and Review-1 baseline).

2. **Run Ingestion Simulator from Web Dashboard:**
   - Launch servers via `scripts\start_servers.bat`
   - Open `http://localhost:3000`
   - Navigate to **Jenkins Integration** tab
   - Generate an integration token
   - Click **Simulate Build Upload** in the **Interactive Jenkins Telemetry Simulator** to verify end-to-end ingestion and live RCA formulation.
