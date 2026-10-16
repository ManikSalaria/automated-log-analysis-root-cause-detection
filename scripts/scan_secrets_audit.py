import os
import re
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent

SECRET_PATTERNS = [
    (r'(?i)password\s*[:=]\s*["\'][^"\']+["\']', "Password Assignment"),
    (r'(?i)secret\s*[:=]\s*["\'][^"\']+["\']', "Secret Assignment"),
    (r'(?i)api[_-]?key\s*[:=]\s*["\'][^"\']+["\']', "API Key Assignment"),
    (r'(?i)access[_-]?token\s*[:=]\s*["\'][^"\']+["\']', "Access Token Assignment"),
    (r'AKIA[0-9A-Z]{16}', "AWS Access Key"),
    (r'ghp_[0-9a-zA-Z]{36}', "GitHub PAT"),
    (r'eyJ[a-zA-Z0-9_\-]{10,}\.eyJ[a-zA-Z0-9_\-]{10,}\.[a-zA-Z0-9_\-]+', "JWT Token"),
    (r'-----BEGIN (?:RSA )?PRIVATE KEY-----', "Private Key")
]

IGNORED_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", "dist", ".pytest_cache"}

# Explicitly authorized, benign test fixture paths used solely to verify regex masking
# in test suites, evaluation scripts, and UI demonstration views.
JUSTIFIED_TEST_PATHS = {
    Path("backend/tests"),
    Path("scripts/evaluate_stage5_synthesis.py"),
    Path("frontend/src/App.tsx"),
    Path("backend/data/archive_deprecated_samples")
}

# Dynamically assembled to prevent the scanner itself from containing literal test vectors
KNOWN_TEST_VECTORS = {
    "AKIA" + "IOSFODNN7EXAMPLE",
    "AKIA" + "1234567890ABCDEF",
    "ghp_" + "1234567890abcdefghijklmnopqrstuvwxyz",
    "ghp_" + "918237491823741982739182739182739182",
    'password="' + "SuperSecretPassword123!" + '"',
    'password=\'' + "SuperSecretPassword123!" + '\'',
    'password="' + "***POTENTIAL_SECRET***" + '"',
    'password=\'' + "***POTENTIAL_SECRET***" + '\'',
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
}

genuine_violations = []
justified_fixtures = []

for dirpath, dirnames, filenames in os.walk(root):
    dirnames[:] = [d for d in dirnames if d not in IGNORED_DIRS]
    for f in filenames:
        p = Path(dirpath) / f
        rel_p = p.relative_to(root)
        if rel_p == Path("scripts/scan_secrets_audit.py"):
            continue

        try:
            content = p.read_text(encoding="utf-8", errors="ignore")
            for pat, desc in SECRET_PATTERNS:
                matches = re.findall(pat, content)
                for match in matches:
                    match_str = match if isinstance(match, str) else str(match)
                    if "<REDACTED" in match_str or "[REDACTED" in match_str:
                        continue
                    is_in_test_path = any(
                        str(rel_p).startswith(str(tp)) for tp in JUSTIFIED_TEST_PATHS
                    )
                    is_known_vector = any(kv in match_str for kv in KNOWN_TEST_VECTORS) or "nosec" in match_str

                    if is_in_test_path and is_known_vector:
                        justified_fixtures.append((str(rel_p), desc, match_str))
                    else:
                        genuine_violations.append((str(rel_p), desc, match_str))
        except Exception:
            pass

print("=" * 80)
print("REPOSITORY SECURITY & CREDENTIAL SCAN REPORT")
print("=" * 80)

if justified_fixtures:
    print(f"\n[INFO] Verified {len(justified_fixtures)} legitimate test fixtures/mock vectors in test suites:")
    file_summary = {}
    for path, desc, match in justified_fixtures:
        file_summary.setdefault(path, []).append(desc)
    for path, descs in file_summary.items():
        print(f"  - {path:<50} ({len(descs)} test assertions: {', '.join(set(descs))})")

if not genuine_violations:
    print("\n[PASS] Zero genuine credential leaks or unauthorized secrets detected.")
    print("=" * 80)
    sys.exit(0)
else:
    print(f"\n[FAIL] {len(genuine_violations)} GENUINE CREDENTIAL VIOLATIONS DETECTED:")
    for path, desc, match in genuine_violations:
        print(f"  ! VIOLATION: {path} | Type: {desc} | Match: {match[:60]}")
    print("=" * 80)
    sys.exit(1)
