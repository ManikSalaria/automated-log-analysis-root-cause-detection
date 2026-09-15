import os
import re
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

findings = []
for dirpath, dirnames, filenames in os.walk(root):
    dirnames[:] = [d for d in dirnames if d not in IGNORED_DIRS]
    for f in filenames:
        p = Path(dirpath) / f
        try:
            content = p.read_text(encoding="utf-8", errors="ignore")
            for pat, desc in SECRET_PATTERNS:
                matches = re.findall(pat, content)
                if matches:
                    findings.append((str(p.relative_to(root)), desc, len(matches), matches[:3]))
        except Exception:
            pass

print("=" * 80)
print("REPOSITORY SECURITY & CREDENTIAL SCAN REPORT")
print("=" * 80)
if not findings:
    print("Zero secrets detected.")
else:
    for path, desc, count, samples in findings:
        print(f"File: {path:<50} | Type: {desc:<22} | Count: {count}")
        for s in samples:
            print(f"    Match snippet: {str(s)[:80]}")

print("\nScan completed.")
