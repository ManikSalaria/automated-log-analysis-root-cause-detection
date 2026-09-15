"""Review-1 Root Cause Candidate Analysis Engine.

A rule-grounded, explainable root-cause candidate analyzer designed for
academic defense in Review 1. Evaluates genuine textual and structural evidence
from parsed CI/CD and microservice logs without claiming deep graph neural network
or causal inference capabilities.
"""

from typing import Dict, Any, List, Optional
import re

class RootCauseCandidateAnalyzer:
    """Transparent heuristic analyzer mapping error patterns to probable root-cause candidates."""

    RULE_SIGNATURES: List[Dict[str, Any]] = [
        {
            "category": "STORAGE_AND_IO_ERROR",
            "candidate": "Storage Infrastructure / Datastore Configuration Failure",
            "keywords": ["storage", "datastore", "cluster id", "mkdir", "input/output error", "qemu-img", "iscsi", "lun", "gfs2", "alletra"],
            "explanation": "Log lines demonstrate I/O device error or missing storage cluster configuration during volume/datastore provisioning.",
            "remediation_guidance": "Verify iSCSI portal accessibility, cluster configuration IDs, and host mount permissions."
        },
        {
            "category": "DATABASE_AND_CACHE_TIMEOUT",
            "candidate": "Database Connection Pool Exhaustion or Redis Cache Timeout",
            "keywords": ["database connection timeout", "redis connection timeout", "database connection pool", "connection pool nearing capacity", "slow query"],
            "explanation": "Active connection pool reached capacity limit or query execution exceeded timeout threshold.",
            "remediation_guidance": "Check HikariCP/Postgres max connections, statement timeouts, and slow query executions."
        },
        {
            "category": "NETWORK_DEPENDENCY_FAILURE",
            "candidate": "Upstream Dependency Unavailability or Downstream Service HTTP 5xx Failure",
            "keywords": ["connection refused", "http 500", "status=502", "status=503", "status=504", "external service response delayed"],
            "explanation": "Synchronous inter-service RPC failed because dependent service endpoint rejected connection or returned server error.",
            "remediation_guidance": "Inspect payment-service and notification-service health endpoints and retry circuit breakers."
        },
        {
            "category": "MESSAGE_BROKER_FAILURE",
            "candidate": "Message Broker / Kafka Consumer Polling Failure",
            "keywords": ["kafka consumer failed to poll", "kafka", "queue depth above normal", "broker closed channel"],
            "explanation": "Consumer thread timed out polling Kafka topic partition or message queue backlog exceeded processing limit.",
            "remediation_guidance": "Verify Kafka broker health, consumer heartbeat timeout, and partition rebalancing."
        },
        {
            "category": "RESOURCE_EXHAUSTION_CRASH",
            "candidate": "Process / Container Out-Of-Memory (OOM) Heap Exhaustion",
            "keywords": ["out of memory", "outofmemoryerror", "heap space", "oom killer"],
            "explanation": "Memory allocation exceeded maximum container or JVM heap ceiling, triggering process crash.",
            "remediation_guidance": "Increase container cgroup memory limits or tune JVM -Xmx parameter."
        },
        {
            "category": "AUTHENTICATION_SECURITY_ERROR",
            "candidate": "Security Credential Rejection / Expired Auth Token",
            "keywords": ["authentication token validation failed", "jira authentication failed", "csrf", "crumb", "unauthorized", "token validation"],
            "explanation": "Request rejected due to expired JWT/OAuth token or missing Jenkins CSRF crumb descriptor.",
            "remediation_guidance": "Renew authentication tokens and verify Jenkins crumb issuer plugin descriptor."
        },
        {
            "category": "TEST_ASSERTION_FAILURE",
            "candidate": "Automated Test Assertion Failure / State Timeout",
            "keywords": ["failed morpheus_automation", "assertionerror: instance", "assertionerror: response", "assertionerror: expected", "failed test_"],
            "explanation": "Pytest assertion evaluated to False because system did not reach expected operational state within polling window.",
            "remediation_guidance": "Inspect pytest assertion context, diff expected vs actual response payload, and review fixture timeout."
        },
        {
            "category": "PLUGIN_DESCRIPTOR_RESOLUTION_ERROR",
            "candidate": "Jenkins Plugin Class Resolution / Descriptor Failure",
            "keywords": ["classnotfoundexception", "noclassdeffounderror", "cannotresolveclassexception", "configuratorexception", "jellytagexception", "missing its descriptor"],
            "explanation": "Jenkins failed to instantiate required descriptor class or encountered incompatible Jelly tag syntax during plugin load.",
            "remediation_guidance": "Audit Jenkins plugins for version mismatch and ensure missing core descriptors are installed."
        },
        {
            "category": "INTERNAL_APPLICATION_LOGIC_ERROR",
            "candidate": "Unhandled Application Exception / Transaction Rollback",
            "keywords": ["null pointer", "transaction rollback", "failed to process request"],
            "explanation": "Application code encountered unexpected null pointer or database transaction rollback.",
            "remediation_guidance": "Review stack trace line references in application service handler."
        }
    ]

    DEFAULT_CANDIDATE = {
        "category": "ENVIRONMENT_AND_PIPELINE_ERROR",
        "candidate": "Generic Pipeline Environment / Execution Anomaly",
        "explanation": "Unclassified failure or warning event requiring engineer review.",
        "remediation_guidance": "Inspect pipeline console output and system journal logs around the failure timestamp."
    }

    @classmethod
    def analyze(cls, text: str, primary_category: Optional[str] = None) -> Dict[str, Any]:
        """
        Analyze error text and return a Review-1 Root Cause Candidate Analysis.
        """
        t = text.lower()

        # If primary category provided, match rule first
        if primary_category:
            for rule in cls.RULE_SIGNATURES:
                if rule["category"] == primary_category:
                    return {
                        "analysis_framework": "Review-1 Root Cause Candidate Analysis",
                        "failure_category": rule["category"],
                        "root_cause_candidate": rule["candidate"],
                        "explanation": rule["explanation"],
                        "remediation_guidance": rule["remediation_guidance"],
                        "evidence_matched": [kw for kw in rule["keywords"] if kw in t]
                    }

        # Otherwise match by keyword scan
        for rule in cls.RULE_SIGNATURES:
            matched = [kw for kw in rule["keywords"] if kw in t]
            if matched:
                return {
                    "analysis_framework": "Review-1 Root Cause Candidate Analysis",
                    "failure_category": rule["category"],
                    "root_cause_candidate": rule["candidate"],
                    "explanation": rule["explanation"],
                    "remediation_guidance": rule["remediation_guidance"],
                    "evidence_matched": matched
                }

        return {
            "analysis_framework": "Review-1 Root Cause Candidate Analysis",
            "failure_category": cls.DEFAULT_CANDIDATE["category"],
            "root_cause_candidate": cls.DEFAULT_CANDIDATE["candidate"],
            "explanation": cls.DEFAULT_CANDIDATE["explanation"],
            "remediation_guidance": cls.DEFAULT_CANDIDATE["remediation_guidance"],
            "evidence_matched": []
        }
