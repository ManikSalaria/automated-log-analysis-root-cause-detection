import re
from typing import List, Dict, Any, Optional
from datetime import datetime
from app.core.security import SecretMasker
from app.schemas.log_schema import LogEntry, ParsedIncidentSummary

class LogParserEngine:
    """
    High-performance Log Parsing and Extraction Engine.
    Handles CI/CD build outputs (Jenkins, Pytest, Maven/Gradle)
    and distributed microservice transaction streams.
    """

    # Format 1: ISO Timestamp Microservice Format (JSON/Key-Value)
    MICROSERVICE_PATTERN = re.compile(
        r"^(?P<timestamp>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z)\s+"
        r"(?P<level>INFO|DEBUG|WARN|WARNING|ERROR|FATAL)\s+"
        r"(?:\[(?P<service_bracket>[^\]]+)\]|(?P<service_plain>\S+))"
        r"(?:\s+\[?(?P<node>node-\d+)\]?)?"
        r"(?P<rest>.*)$"
    )

    # Format 2: Python / Pytest / Jenkins Log Format
    JENKINS_PYTEST_PATTERN = re.compile(
        r"^(?P<timestamp>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}(?:\s+[A-Z]{3})?)\s+"
        r"(?P<source>[\w\.\-]+:\d+)\s+"
        r"(?P<level>INFO|DEBUG|WARN|WARNING|ERROR|CRITICAL)\s*:\s*"
        r"(?P<message>.*)$"
    )

    # Format 3: JVM / Jenkins Core Log Format
    JENKINS_JVM_PATTERN = re.compile(
        r"^(?P<timestamp>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+[+\-]\d{4})\s+"
        r"\[id=(?P<thread_id>\d+)\]\s+"
        r"(?P<level>INFO|WARNING|SEVERE|FINE|FINER|FINEST)\s+"
        r"(?P<logger>[^:]+):\s*"
        r"(?P<message>.*)$"
    )

    # Key-value extractors
    KV_PATTERNS = {
        "request_id": re.compile(r"\brequest_id=([^\s,]+)"),
        "trace_id": re.compile(r"\b(?:trace_id|trace)=([^\s,]+)"),
        "span_id": re.compile(r"\b(?:span_id|span)=([^\s,]+)"),
        "status_code": re.compile(r"\bstatus(?:_code)?=(\d{3})\b"),
        "latency_ms": re.compile(r"\blatency_ms=(\d+(?:\.\d+)?)\b"),
    }

    # Error signature heuristics
    ERROR_INDICATORS = [
        re.compile(r"(?i)\b(AssertionError|NullPointer|Exception|Timeout|Connection refused|Rollback|Out of memory|Input/output error|failed to poll|HTTP 5\d{2})\b"),
        re.compile(r"(?i)\bFAILED\s+([a-zA-Z0-9_\.\/:]+)"),
        re.compile(r"^E\s+(.*)$", re.MULTILINE),
    ]

    @classmethod
    def parse_line(cls, line: str, mask_ips: bool = True) -> LogEntry:
        """
        Parse a single log line into a structured LogEntry with secrets and IPs redacted.
        """
        raw_line = line.strip()
        sanitized_line = SecretMasker.sanitize(raw_line, mask_ips=mask_ips)

        # Try Format 1: Microservice log
        match_ms = cls.MICROSERVICE_PATTERN.match(raw_line)
        if match_ms:
            groups = match_ms.groupdict()
            service = groups["service_bracket"] or groups["service_plain"]
            rest = groups["rest"]
            
            # Extract key-values
            extracted_kv = cls._extract_kvs(rest)
            
            # Clean message text
            clean_msg = cls._clean_msg_from_kvs(rest)
            
            level = groups["level"]
            if level == "WARNING":
                level = "WARN"

            return LogEntry(
                timestamp=groups["timestamp"],
                level=level,
                service=service.strip("[]") if service else "unknown",
                node=groups.get("node"),
                trace_id=extracted_kv.get("trace_id"),
                span_id=extracted_kv.get("span_id"),
                status_code=int(extracted_kv["status_code"]) if "status_code" in extracted_kv else None,
                latency_ms=float(extracted_kv["latency_ms"]) if "latency_ms" in extracted_kv else None,
                raw_message=clean_msg if clean_msg else rest.strip(),
                sanitized_message=SecretMasker.sanitize(clean_msg if clean_msg else rest.strip(), mask_ips=mask_ips)
            )

        # Try Format 2: Jenkins Pytest log
        match_py = cls.JENKINS_PYTEST_PATTERN.match(raw_line)
        if match_py:
            groups = match_py.groupdict()
            level = groups["level"]
            if level == "WARNING":
                level = "WARN"
            elif level == "CRITICAL":
                level = "ERROR"

            return LogEntry(
                timestamp=groups["timestamp"],
                level=level,
                service=groups["source"].split(":")[0],
                node=None,
                raw_message=groups["message"],
                sanitized_message=SecretMasker.sanitize(groups["message"], mask_ips=mask_ips)
            )

        # Try Format 3: Jenkins JVM log
        match_jvm = cls.JENKINS_JVM_PATTERN.match(raw_line)
        if match_jvm:
            groups = match_jvm.groupdict()
            level_map = {"WARNING": "WARN", "SEVERE": "ERROR", "FINE": "DEBUG", "FINER": "DEBUG", "FINEST": "DEBUG"}
            level = level_map.get(groups["level"], groups["level"])

            return LogEntry(
                timestamp=groups["timestamp"],
                level=level,
                service=groups["logger"].split("#")[0],
                node=f"thread-{groups.get('thread_id')}",
                raw_message=groups["message"],
                sanitized_message=SecretMasker.sanitize(groups["message"], mask_ips=mask_ips)
            )

        # Fallback: Unstructured line or stack trace line
        level = "INFO"
        if any(err.search(raw_line) for err in cls.ERROR_INDICATORS):
            level = "ERROR"
        elif "WARN" in raw_line.upper():
            level = "WARN"

        return LogEntry(
            timestamp=None,
            level=level,
            service="pipeline-runner",
            raw_message=raw_line,
            sanitized_message=sanitized_line
        )

    @classmethod
    def parse_log_text(cls, text: str) -> List[LogEntry]:
        """
        Parse multi-line log stream or entire build file into structured LogEntry list.
        """
        lines = text.strip().splitlines()
        entries = []
        for line in lines:
            if line.strip():
                entries.append(cls.parse_line(line))
        return entries

    @classmethod
    def summarize_incident(cls, log_text: str, incident_id: str = "INC-AUTO") -> ParsedIncidentSummary:
        """
        Aggregates a batch of log lines into a ParsedIncidentSummary.
        """
        entries = cls.parse_log_text(log_text)
        total_lines = len(entries)
        errors = [e for e in entries if e.level in ("ERROR", "CRITICAL", "SEVERE")]
        warnings = [e for e in entries if e.level in ("WARN", "WARNING")]
        
        # Collect unique error signatures
        error_sigs = []
        seen = set()
        for e in errors:
            sig = e.sanitized_message[:120].strip()
            if sig and sig not in seen:
                seen.add(sig)
                error_sigs.append(sig)

        # Identify impacted services
        impacted = list({e.service for e in errors if e.service and e.service != "unknown"})
        
        # Construct timeline of error progression
        timeline = []
        for e in errors[:10]:
            timeline.append({
                "timestamp": e.timestamp or "N/A",
                "service": e.service,
                "node": e.node,
                "error": e.sanitized_message[:100]
            })

        # Determine probable origin (first recurring failure node)
        root_cause_node = impacted[0] if impacted else "unknown"

        return ParsedIncidentSummary(
            incident_id=incident_id,
            source_type="JENKINS" if any("jenkins" in e.sanitized_message.lower() or "pytest" in e.sanitized_message.lower() for e in entries) else "MICROSERVICES",
            total_lines=total_lines,
            error_count=len(errors),
            warning_count=len(warnings),
            primary_failure_category="UNKNOWN",
            confidence=0.0,
            root_cause_node=root_cause_node,
            error_signatures=error_sigs[:5],
            impacted_services=impacted,
            timeline=timeline
        )

    @classmethod
    def _extract_kvs(cls, text: str) -> Dict[str, str]:
        extracted = {}
        for key, pattern in cls.KV_PATTERNS.items():
            match = pattern.search(text)
            if match:
                extracted[key] = match.group(1)
        return extracted

    @classmethod
    def _clean_msg_from_kvs(cls, text: str) -> str:
        # Remove request_id, trace_id, span_id, status, latency_ms to leave the core message
        cleaned = text
        for pattern in cls.KV_PATTERNS.values():
            cleaned = pattern.sub("", cleaned)
        return re.sub(r"\s+", " ", cleaned).strip()
