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

    # Format 4: Maven / Surefire / Console Log Format
    # Supports optional timestamp prefix e.g. "[2026-10-15T12:00:00.000Z] " or "12:00:00 "
    MAVEN_PATTERN = re.compile(
        r"^(?:(?:\[(?P<timestamp_bracket>[^\]]+)\]|(?P<timestamp_plain>\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+\-]\d{2}:?\d{2})?|\d{2}:\d{2}:\d{2}))\s+)?"
        r"\[(?P<level>INFO|WARNING|WARN|ERROR|DEBUG)\]\s*"
        r"(?P<message>.*)$"
    )

    # Test summary pattern: Tests run: X, Failures: Y, Errors: Z, Skipped: W
    TEST_SUMMARY_PATTERN = re.compile(
        r"\bTests run:\s*(\d+),\s*Failures:\s*(\d+),\s*Errors:\s*(\d+)(?:,\s*Skipped:\s*(\d+))?",
        re.IGNORECASE
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
        re.compile(r"(?i)\b(AssertionError|AssertionFailedError|NullPointerException|OutOfMemoryError|Connection refused|Rollback|failed to poll|HTTP 5\d{2})\b"),
        re.compile(r"(?i)\bFAILED\s+([a-zA-Z0-9_\.\/:]+)"),
        re.compile(r"^E\s+(.*)$", re.MULTILINE),
    ]

    @classmethod
    def parse_line(cls, line: str) -> LogEntry:
        """
        Parse a single log line into a structured LogEntry with secrets redacted.
        """
        raw_line = line.strip()
        sanitized_line = SecretMasker.sanitize(raw_line)

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
                sanitized_message=SecretMasker.sanitize(clean_msg if clean_msg else rest.strip())
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
                sanitized_message=SecretMasker.sanitize(groups["message"])
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
                sanitized_message=SecretMasker.sanitize(groups["message"])
            )

        # Try Format 4: Maven / Surefire build log
        match_mvn = cls.MAVEN_PATTERN.match(raw_line)
        if match_mvn:
            groups = match_mvn.groupdict()
            raw_lvl = groups["level"]
            msg = groups["message"]
            timestamp = groups.get("timestamp_bracket") or groups.get("timestamp_plain")

            # Context-aware severity determination for Maven lines
            summary_match = cls.TEST_SUMMARY_PATTERN.search(msg)
            if summary_match:
                failures = int(summary_match.group(2))
                errors = int(summary_match.group(3))
                skipped = int(summary_match.group(4) or 0)
                if failures > 0 or errors > 0:
                    level = "ERROR"
                elif skipped > 0 or raw_lvl in ("WARNING", "WARN"):
                    level = "WARN"
                else:
                    level = "INFO"
            elif raw_lvl == "ERROR":
                level = "ERROR"
            elif raw_lvl in ("WARNING", "WARN"):
                level = "WARN"
            elif raw_lvl == "DEBUG":
                level = "DEBUG"
            else:
                level = "INFO"

            service = "maven-pipeline"
            if msg.startswith("Running "):
                parts = msg.split()
                if len(parts) > 1:
                    service = parts[1]
            elif " - in " in msg:
                service = msg.split(" - in ")[-1].strip()

            return LogEntry(
                timestamp=timestamp,
                level=level,
                service=service,
                node=None,
                raw_message=msg,
                sanitized_message=SecretMasker.sanitize(msg)
            )

        # Fallback: Unstructured line or stack trace line
        level = "INFO"
        service = "pipeline-runner"

        # Check test summary without bracket prefix
        summary_match = cls.TEST_SUMMARY_PATTERN.search(raw_line)
        if summary_match:
            failures = int(summary_match.group(2))
            errors = int(summary_match.group(3))
            skipped = int(summary_match.group(4) or 0)
            if failures > 0 or errors > 0:
                level = "ERROR"
            elif skipped > 0 or "WARN" in raw_line.upper():
                level = "WARN"
            else:
                level = "INFO"
        elif re.match(r"^Running\s+[\w\.\$]+", raw_line):
            level = "INFO"
            parts = raw_line.split()
            if len(parts) > 1:
                service = parts[1]
        elif "BUILD SUCCESS" in raw_line:
            level = "INFO"
        elif (raw_line.startswith(("\tat ", "   at ", "Caused by:", "Traceback (most recent call last):", "E   ", "FAILED ")) or
              re.match(r"^(?:java\.[a-zA-Z0-9_\.]+|[a-zA-Z0-9_\.]+(?:Exception|Error|Failure))(?::\s*.*)?$", raw_line) or
              any(err.search(raw_line) for err in cls.ERROR_INDICATORS)):
            level = "ERROR"
        elif "WARN" in raw_line.upper():
            level = "WARN"

        return LogEntry(
            timestamp=None,
            level=level,
            service=service,
            raw_message=raw_line,
            sanitized_message=sanitized_line
        )

    @classmethod
    def is_incident_start(cls, raw_line: str, entry: Optional[LogEntry] = None) -> bool:
        """
        Context-aware check whether a log line represents the start of an actual failure/incident.
        Distinguishes explicit error log records, actual test failures, exceptions, and stack traces
        from normal informational messages, test runners, skipped tests, and successful build summaries.
        """
        line = raw_line.strip()
        if not line:
            return False

        if entry is None:
            entry = cls.parse_line(raw_line)

        # 1. Definite Non-Incidents (Informational / Warnings / Normal Summaries)
        # Test runner execution message: e.g. [INFO] Running com.tracelab...ExceptionFailureScenarioTest
        if re.match(r"^(?:\[INFO\]\s+)?Running\s+[\w\.\$]+(?:\s+.*)?$", line):
            return False

        # Build success messages and build timing info
        if ("BUILD SUCCESS" in line or line.startswith("[INFO] Total time:") or
            line.startswith("[INFO] Finished at:") or line.startswith("[INFO] Final Memory:")):
            return False

        # Test summaries with 0 failures and 0 errors (even if skipped tests or warnings)
        summary_match = cls.TEST_SUMMARY_PATTERN.search(line)
        if summary_match:
            failures = int(summary_match.group(2))
            errors = int(summary_match.group(3))
            if failures == 0 and errors == 0:
                return False
            else:
                return True

        # Non-fatal warnings (skipped tests, deprecations, warnings)
        if entry.level in ("WARN", "WARNING", "DEBUG"):
            return False

        # Normal informational lines
        if entry.level == "INFO":
            # An INFO line is not an incident unless it contains an explicit failure banner
            if not ("<<< FAILURE!" in line or "<<< ERROR!" in line or "AssertionError" in line):
                return False

        # 2. Definite Incidents
        # Explicit ERROR/CRITICAL/FATAL/SEVERE level
        if entry.level in ("ERROR", "CRITICAL", "SEVERE", "FATAL"):
            return True

        # Test failure markers
        if ("<<< FAILURE!" in line or "<<< ERROR!" in line or
            line.startswith("FAILED ") or line.startswith("E   assert ") or
            line.startswith("[ERROR] Failures:") or line.startswith("[ERROR] Errors:") or
            "AssertionError" in line or "AssertionFailedError" in line):
            return True

        # Stack trace or exception indicators
        if (line.startswith(("Traceback (most recent call last):", "Caused by:")) or
            re.match(r"^(?:java\.[a-zA-Z0-9_\.]+|[a-zA-Z0-9_\.]+(?:Exception|Error))(?::\s*.*)?$", line)):
            return True

        # System error commands
        if any(cmd in line for cmd in ["mkdir:", "qemu-img:"]):
            return True

        return False

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
