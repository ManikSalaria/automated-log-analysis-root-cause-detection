import json
from pathlib import Path
import pandas as pd
from app.core.config import settings
from app.core.security import SecretMasker

def build_training_dataset() -> Path:
    """
    Compiles curated training samples from raw Jenkins logs,
    microservice transaction streams, and standard failure signatures
    across the 10-class deterministic failure taxonomy.
    """
    samples = []

    # 1. STORAGE_LUN_PROVISIONING_ERROR (From real HPE Jenkins VME log)
    storage_samples = [
        "AssertionError: storage cluster id is missing from config in datastore alletra_datastore_abgrdg_dnd creation assert 'hpe_storage_cluster_id' in {'protocolType': 'iSCSI'}",
        "AssertionError: storage cluster id is missing from config in datastore alletra_datastore_yoopnj_dnd creation",
        "Failed to create server volumes: Failed to clone volume: mkdir: cannot create directory /mnt/de6b63df-0ad0-4b54-8ef8-dbe6f8ef626c : Input/output error",
        "qemu-img: /mnt/de6b63df-0ad0-4b54-8ef8-dbe6f8ef626c/mvm_beta_api_instance/hvm_132-disk-0: error while converting qcow2: Could not create: Input/output error",
        "Volume 348 datastoreId 18 storage cluster unreachable during provisioning on host gen11-91-hydrogen",
        "Unable to attach iSCSI LUN target iqn.2023-24.com.hpe:4uw0002503: target portal connection timeout",
        "Cluster volume allocation failed: storageServer 5 reports LUN active peer persistence replication failure",
        "Storage provider alletra-server timed out waiting for volume resize completion on target LUN",
        "libvirt: Storage Driver error : Storage pool not found: no storage pool with matching name 'alletra-storage'",
        "Failed to format GFS2 filesystem on /dev/mapper/360002ac000000000000079e10007e751 device busy"
    ]
    for s in storage_samples:
        samples.append({"text": s, "category": "STORAGE_LUN_PROVISIONING_ERROR", "source": "JENKINS_VME"})

    # 2. TEST_ASSERTION_FAILURE (From Jenkins pytest runs & Gist assertion errors)
    test_samples = [
        "AssertionError: Instance 132 is not in running state after polling interval assert False",
        "FAILED morpheus_automation/tests/api/test_vme_storage_plugin_e2e.py::TestVMEStoragePlugin::test_create_update_delete_datastore[False]",
        "FAILED morpheus_automation/tests/api/test_gfs2_certification.py::TestGFS2::test_migrate_from_gfs2_to_another_storage_type",
        "java.lang.AssertionError: class hudson.security.csrf.DefaultCrumbIssuer is missing its descriptor at jenkins.model.Jenkins.getDescriptorOrDie",
        "AssertionError: Expected status code 200 but received 502 Bad Gateway assert 502 == 200",
        "pytest.fail: Integration test failed because mock server did not receive webhook callback within 30 seconds",
        "AssertionError: Expected 15 healthy replicas in cluster status but found 12",
        "FAILED test_reconfigure_disks[alletra] - AssertionError: Datastore resize verification failed on node gen11-92",
        "AssertionError: Response body mismatch: expected 'provisioned' but got 'pending'",
        "FAILED test_manage_placement[auto-other] - AssertionError: Server placement move did not trigger"
    ]
    for s in test_samples:
        samples.append({"text": s, "category": "TEST_ASSERTION_FAILURE", "source": "PYTEST_JENKINS"})

    # 3. DATABASE_TIMEOUT_OR_EXHAUSTION (From microservice stream)
    db_samples = [
        "ERROR [payment-service] request_id=req-467506 status=504 latency_ms=4389 Database connection timeout",
        "ERROR [inventory-service] request_id=req-522988 status=500 latency_ms=2433 Database connection timeout",
        "ERROR [order-service] [node-03] request_id=req-674295 trace_id=trace-9757456 Database connection timeout",
        "WARN auth-service node-01 trace=trace-3791137 span=span-49251 latency_ms=264 Database connection pool nearing capacity",
        "WARN [payment-service] request_id=req-774567 status=503 latency_ms=1059 Database connection pool nearing capacity",
        "WARN [order-service] [node-03] request_id=req-865630 trace_id=trace-8486970 Database connection pool nearing capacity",
        "ERROR user-service node-02 trace=trace-1034351 span=span-89794 latency_ms=2221 Database connection timeout",
        "HikariPool-1 - Connection is not available, request timed out after 30000ms (total=10, active=10, idle=0, waiting=5)",
        "PostgreSQL connection limit exceeded for user db_user on host 10.157.192.20",
        "SQLTimeoutException: Query execution exceeded configured timeout limit of 5000ms"
    ]
    for s in db_samples:
        samples.append({"text": s, "category": "DATABASE_TIMEOUT_OR_EXHAUSTION", "source": "MICROSERVICES"})

    # 4. NETWORK_CONNECTION_REFUSED (From microservice stream)
    network_samples = [
        "ERROR [notification-service] request_id=req-820221 status=503 latency_ms=3371 Connection refused by payment service",
        "ERROR [order-service] request_id=req-810250 status=502 latency_ms=1634 Connection refused by payment service",
        "ERROR api-gateway node-03 trace=trace-4706007 span=span-93839 latency_ms=1952 Connection refused by payment service",
        "ERROR auth-service node-01 trace=trace-4637715 span=span-88562 latency_ms=1864 Connection refused by payment service",
        "ERROR [inventory-service] [node-03] request_id=req-156710 trace_id=trace-2778549 Connection refused by payment service",
        "ERROR [api-gateway] request_id=req-911982 status=503 latency_ms=4040 Connection refused by payment service",
        "ConnectException: Connection refused (Connection refused) to payment-service.internal:8080",
        "SocketException: Network is unreachable while routing outbound request to notification-broker",
        "TCP connection reset by peer during TLS handshake on port 8443",
        "HTTP 502 Bad Gateway: Upstream gateway failed to connect to backend cluster node-04"
    ]
    for s in network_samples:
        samples.append({"text": s, "category": "NETWORK_CONNECTION_REFUSED", "source": "MICROSERVICES"})

    # 5. OUT_OF_MEMORY_CRASH (From microservice stream)
    oom_samples = [
        "ERROR payment-service node-02 trace=trace-2049645 span=span-85674 latency_ms=3796 Out of memory while processing batch",
        "ERROR [api-gateway] [node-02] request_id=req-130726 trace_id=trace-5713268 Out of memory while processing batch",
        "ERROR order-service node-05 trace=trace-1207430 span=span-91665 latency_ms=1721 Out of memory while processing batch",
        "ERROR [inventory-service] request_id=req-645752 status=503 latency_ms=3591 Out of memory while processing batch",
        "ERROR notification-service node-02 trace=trace-7365080 span=span-99383 latency_ms=1227 Out of memory while processing batch",
        "java.lang.OutOfMemoryError: Java heap space during Jenkins pipeline execution",
        "Kernel killed process: OOM killer terminated container worker-mvm due to memory exhaustion",
        "Node out of memory: unable to allocate 4194304 bytes in memory pool",
        "Memory quota exceeded: pod order-service-worker exceeded memory limit of 4GiB",
        "Fatal error: JavaScript heap out of memory during frontend production asset build"
    ]
    for s in oom_samples:
        samples.append({"text": s, "category": "OUT_OF_MEMORY_CRASH", "source": "MICROSERVICES"})

    # 6. QUEUE_OR_BROKER_POLL_FAILURE (From microservice stream)
    queue_samples = [
        "ERROR inventory-service node-05 trace=trace-5038756 span=span-38199 latency_ms=1214 Kafka consumer failed to poll",
        "ERROR api-gateway node-04 trace=trace-8962169 span=span-86923 latency_ms=2139 Kafka consumer failed to poll",
        "ERROR auth-service node-03 trace=trace-8649174 span=span-78195 latency_ms=1896 Kafka consumer failed to poll",
        "ERROR [notification-service] request_id=req-386275 status=502 latency_ms=4566 Kafka consumer failed to poll",
        "ERROR [payment-service] request_id=req-693071 status=503 latency_ms=3130 Kafka consumer failed to poll",
        "ERROR payment-service node-05 trace=trace-2782278 span=span-89827 latency_ms=2560 Kafka consumer failed to poll",
        "RabbitMQ broker closed channel unexpectedly: PRECONDITION_FAILED - queue depth overflow",
        "KafkaConsumer error: CommitFailedException: The consumer instance has spent too much time processing",
        "Message broker partition offline: unable to commit offset for topic order_events_v1",
        "WARN notification-service node-01 trace=trace-8309439 span=span-87184 latency_ms=960 Queue depth above normal"
    ]
    for s in queue_samples:
        samples.append({"text": s, "category": "QUEUE_OR_BROKER_POLL_FAILURE", "source": "MICROSERVICES"})

    # 7. AUTHENTICATION_TOKEN_EXPIRED (From microservice stream & Gist logs)
    auth_samples = [
        "ERROR [payment-service] [node-01] request_id=req-624139 trace_id=trace-8279795 Authentication token validation failed",
        "ERROR [api-gateway] [node-04] request_id=req-838726 trace_id=trace-1519979 Authentication token validation failed",
        "ERROR [payment-service] request_id=req-416822 status=500 latency_ms=860 Authentication token validation failed",
        "ERROR user-service node-01 trace=trace-1098967 span=span-94072 latency_ms=1394 Authentication token validation failed",
        "ERROR [auth-service] request_id=req-860294 status=503 latency_ms=3606 Authentication token validation failed",
        "ERROR [inventory-service] [node-04] request_id=req-490843 trace_id=trace-2817044 Authentication token validation failed",
        "JWTExpired: Signature has expired at timestamp 1772082400 for user service account",
        "OAuth2 authentication failed: Invalid bearer token signature",
        "Jira authentication failed: Expecting value: line 1 column 1 (char 0)",
        "Unauthorized: Jenkins crumb issuer token validation failed on endpoint /reload-configuration-as-code/"
    ]
    for s in auth_samples:
        samples.append({"text": s, "category": "AUTHENTICATION_TOKEN_EXPIRED", "source": "MICROSERVICES"})

    # 8. ENVIRONMENT_CONFIG_ERROR (From Gist Jenkins core & pipeline setup)
    env_samples = [
        "org.apache.commons.jelly.JellyTagException: jar:file:/var/jenkins_home/war/WEB-INF/lib/jenkins-core-2.363.jar!/lib/layout/view.jelly:42:20: <d:invokeBody> class hudson.security.csrf.DefaultCrumbIssuer is missing its descriptor",
        "EnvironmentError: Missing required environment variable JENKINS_HOME in container runtime",
        "Invalid host IP for On-Prem environment: Retrieval disabled in OnPremInfo Plugin",
        "Configuration loading error: testcase_variable_data.json not found in /resources",
        "Failed to load environment file: .env is missing critical key DATABASE_URL",
        "Missing required secret credentials binding in Jenkinsfile step withCredentials([usernamePassword(...)])",
        "Configuration error: no valid cluster found matching resource pool 'pool-1'",
        "JDK version mismatch: Jenkins master requires Java 11 or 17, but detected Java 8 runtime",
        "Node.js version unsupported: frontend build requires Node >= 18.0.0, current is 14.17.0",
        "Docker daemon not running: Cannot connect to the Docker daemon at unix:///var/run/docker.sock"
    ]
    for s in env_samples:
        samples.append({"text": s, "category": "ENVIRONMENT_CONFIG_ERROR", "source": "JENKINS_GIST"})

    # 9. DEPENDENCY_RESOLUTION_FAILURE (From build logs)
    dep_samples = [
        "Could not resolve dependencies for project com.hpe.trace:trace-core:jar:1.0.0: Failed to collect dependencies",
        "pip._vendor.resolvelib.resolvers.ResolutionImpossible: Could not find a version that satisfies the requirement torch-geometric",
        "npm ERR! code ERESOLVE: unable to resolve dependency tree for react-router-dom and react 18",
        "Maven resolution error: Could not transfer artifact org.springframework.boot:spring-boot-starter-web from nexus repo: 404 Not Found",
        "Gradle build failure: Plugin [id: 'org.jetbrains.kotlin.jvm', version: '1.9.0'] was not found in any of the following sources",
        "Failed to resolve package 'sentence-transformers' from PyPI mirror: SSL certificate verification failed",
        "go: github.com/gin-gonic/gin@v1.9.0: reading checksum mismatch in go.sum",
        "Cargo error: failed to select a version for the requirement `tokio = \"^1.28\"`",
        "Dependency tree conflict: duplicate class found in commons-lang3-3.12.0.jar and commons-lang3-3.9.jar",
        "Docker image pull failed: repository does not exist or may require 'docker login': registry.internal/dev/vme-base:8.1.0"
    ]
    for s in dep_samples:
        samples.append({"text": s, "category": "DEPENDENCY_RESOLUTION_FAILURE", "source": "SYNTHETIC_BUILD"})

    # 10. BUILD_SCRIPT_SYNTAX_ERROR (From Jenkinsfile / build scripts)
    syntax_samples = [
        "WorkflowScript: 14: unexpected token: stage @ line 14, column 5. Expected closing bracket for pipeline block",
        "SyntaxError: invalid syntax in setup.py line 42: if os.name == 'nt'",
        "Bash script execution failed: line 12: syntax error near unexpected token `fi'",
        "Makefile:24: *** missing separator. Stop. (Did you mean TAB instead of 8 spaces?)",
        "Jenkinsfile parse error: groovy.lang.MissingPropertyException: No such property: BUILD_NUMBER for class: Script1",
        "YamlParseException: while parsing a block mapping in docker-compose.yml: expected <block end>, but found '<block mapping>'",
        "TypeScript compilation error TS1005: ';' expected in src/components/Dashboard.tsx line 58",
        "Shell script error: /bin/sh: 1: [: missing `]' in conditional check",
        "Dockerfile parse error: Unknown instruction: DOCKER_BUILD on line 4",
        "Gradle DSL syntax error: Could not find method implementation() for arguments in dependencies block"
    ]
    for s in syntax_samples:
        samples.append({"text": s, "category": "BUILD_SCRIPT_SYNTAX_ERROR", "source": "SYNTHETIC_BUILD"})

    # Replicate and perturb to build a robust 500-sample balanced dataset for training and cross-validation
    augmented_samples = []
    for row in samples:
        base_text = row["text"]
        cat = row["category"]
        src = row["source"]
        # Add original
        augmented_samples.append({"text": base_text, "category": cat, "source": src})
        # Variation with timestamps & log levels
        augmented_samples.append({"text": f"2026-09-15T10:00:00.000Z ERROR [ci-runner] {base_text}", "category": cat, "source": src})
        augmented_samples.append({"text": f"build-node-01: {base_text} [exit_code=1]", "category": cat, "source": src})
        augmented_samples.append({"text": f"FAILURE: {base_text}", "category": cat, "source": src})
        augmented_samples.append({"text": f"{base_text} (failed after 4200ms)", "category": cat, "source": src})

    df = pd.DataFrame(augmented_samples)
    out_path = settings.PROCESSED_DATA_DIR / "labeled_logs_dataset.csv"
    df.to_csv(out_path, index=False)
    print(f"Compiled dataset saved to {out_path} with {len(df)} samples across {df['category'].nunique()} categories.")
    return out_path

if __name__ == "__main__":
    build_training_dataset()
