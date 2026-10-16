import re
from typing import Dict, Any, List, Tuple

class SecretMasker:
    """
    Zero-PII & Secret Sanitizer for CI/CD and Production Logs.
    Ensures that credentials, API keys, bearer tokens, passwords,
    and sensitive identifiers are redacted prior to storage or LLM ingestion.
    """
    
    # Pre-compiled high-efficiency regex patterns
    PATTERNS: List[Tuple[str, re.Pattern, str]] = [
        # AWS Access Keys
        ("AWS_ACCESS_KEY", re.compile(r"\b(AKIA|ABIA|ACCA|ASIA)[0-9A-Z]{16}\b"), "<REDACTED:AWS_KEY>"),
        # GitHub Personal Access Tokens
        ("GITHUB_PAT", re.compile(r"\b(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{36,255}\b"), "<REDACTED:GITHUB_TOKEN>"),
        # GitLab Personal Access Tokens
        ("GITLAB_PAT", re.compile(r"\bglpat-[A-Za-z0-9\-]{20,}\b"), "<REDACTED:GITLAB_TOKEN>"),
        # Generic Bearer Tokens
        ("BEARER_TOKEN", re.compile(r"(?i)\bBearer\s+[A-Za-z0-9\-\._~\+\/]+=*", re.IGNORECASE), "Bearer <REDACTED:TOKEN>"),
        # Password key-value pairs (JSON, query, log output) - enforces word boundaries to preserve technical identifiers
        ("PASSWORD_KV", re.compile(r"""(?i)(["']?\b(?:password|passwd|pwd|secret|api_key|apikey|private_key|token|access_token)\b["']?\s*[:=]\s*["']?)(?!<REDACTED)([^"',\s\}]{3,})""", re.IGNORECASE), r"\1<REDACTED:SECRET>"),
        # Pre-flagged placeholder patterns (as seen in enterprise CI logs)
        ("ENTERPRISE_SECRET_MARKER", re.compile(r"\*\*\*(?:POTENTIAL_SECRET|GMAIL_APP_PASSWORD|[A-Z_]+)\*\*\*"), "<REDACTED:SECRET>"),
        # API Keys in UUID/Hex format when labeled as apiKey
        ("API_KEY_FIELD", re.compile(r"""(?i)(apiKey\s*[:=]\s*['"])([a-f0-9\-]{16,64})(['"])"""), r"\1<REDACTED:API_KEY>\3"),
        # JWT Tokens
        ("JWT_TOKEN", re.compile(r"\beyJ[A-Za-z0-9-_=]+\.eyJ[A-Za-z0-9-_=]+\.[A-Za-z0-9-_.+/=]+\b"), "<REDACTED:JWT>"),
    ]

    # Operational normalizers (for ML feature stabilization)
    HEX_ADDR_PATTERN = re.compile(r"\b0x[0-9a-fA-F]{6,16}\b")
    UUID_PATTERN = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
    IP_PATTERN = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")

    @classmethod
    def sanitize(cls, text: str, mask_ips: bool = False, normalize_identifiers: bool = False) -> str:
        """
        Sanitize input text by scrubbing sensitive secrets and tokens.
        
        Args:
            text: Raw log message or stack trace.
            mask_ips: If True, masks IPv4 addresses.
            normalize_identifiers: If True, replaces UUIDs and hex memory addresses with tokens.
        """
        if not text:
            return ""
            
        sanitized = text
        for _, pattern, replacement in cls.PATTERNS:
            sanitized = pattern.sub(replacement, sanitized)
            
        if mask_ips:
            sanitized = cls.IP_PATTERN.sub("<IP>", sanitized)
            
        if normalize_identifiers:
            sanitized = cls.UUID_PATTERN.sub("<UUID>", sanitized)
            sanitized = cls.HEX_ADDR_PATTERN.sub("<ADDR>", sanitized)
            
        return sanitized

    @classmethod
    def audit_leaks(cls, text: str) -> Dict[str, Any]:
        """
        Inspect text and return report of detected secret types without revealing secret values.
        """
        findings = []
        for name, pattern, _ in cls.PATTERNS:
            matches = pattern.findall(text)
            if matches:
                findings.append({"pattern": name, "count": len(matches)})
        return {
            "clean": len(findings) == 0,
            "leak_count": sum(f["count"] for f in findings),
            "findings": findings
        }
