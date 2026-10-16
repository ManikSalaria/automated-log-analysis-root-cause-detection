import sys
import re
from pathlib import Path

raw_dir = Path("backend/data/raw")

# Files included in the repository distribution for demonstration and testing:
repository_files = ["demo_jenkins_build.log", "1130.txt", "jenkins_gist_crash.log"]

# Files explicitly excluded/gitignored from public distribution:
gitignored_files = {"Jenkins_Log_Under_1MB.txt"}

# Discover all candidate raw log files to audit
target_files = list(repository_files)
if raw_dir.exists():
    for f in sorted(raw_dir.iterdir()):
        if f.is_file() and f.suffix in (".log", ".txt") and f.name not in target_files and f.name not in gitignored_files:
            target_files.append(f.name)

print("=" * 80)
print("RAW LOG SECURITY & PRIVACY AUDIT")
print("=" * 80)

scanned_count = 0
violations = []

PRIVATE_IP_PATTERN = re.compile(
    r'\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3})\b'
)
PASSWORD_PATTERN = re.compile(r'(?i)(?:password|passwd|pwd)\s*[:=]\s*["\']?([^"\'\s]+)["\']?')
TOKEN_PATTERN = re.compile(r'(?i)(?:token|api[_-]?key|secret|auth)\s*[:=]\s*["\']?([a-zA-Z0-9_\-\.]{8,})["\']?')
SAFE_REDACTION_SUBSTRINGS = {"<REDACTED", "[REDACTED", "***POTENTIAL_SECRET***", "<SECRET>", "<IP>"}

for fname in target_files:
    fpath = raw_dir / fname
    if not fpath.exists():
        print(f"\n--- File: {fname} (NOT PRESENT ON DISK) ---")
        print("  - Status: File not present in local workspace; skipped.")
        continue

    content = fpath.read_text(encoding="utf-8", errors="replace")
    scanned_count += 1

    # Check private IP addresses
    private_ips = set(PRIVATE_IP_PATTERN.findall(content))

    # Check unredacted passwords
    raw_passwords = set(PASSWORD_PATTERN.findall(content))
    unmasked_passwords = {
        p for p in raw_passwords
        if not any(sub in p for sub in SAFE_REDACTION_SUBSTRINGS)
    }

    # Check unredacted tokens
    raw_tokens = set(TOKEN_PATTERN.findall(content))
    unmasked_tokens = {
        t for t in raw_tokens
        if not any(sub in t for sub in SAFE_REDACTION_SUBSTRINGS)
    }

    # Check internal corporate hostnames
    internal_hosts = set(re.findall(r'[a-zA-Z0-9_\-]+\.(?:internal|corp|local|hpe\.com)', content))

    print(f"\n--- File: {fname} ({len(content)} bytes, {len(content.splitlines())} lines) ---")
    print(f"  - Private IPs Detected:         {len(private_ips)}")
    if private_ips:
        print(f"      Samples: {list(private_ips)[:4]}")
        violations.append((fname, "Private IP Address", list(private_ips)[:3]))

    print(f"  - Plaintext Passwords Detected: {len(unmasked_passwords)}")
    if unmasked_passwords:
        print(f"      Samples: {list(unmasked_passwords)[:4]}")
        violations.append((fname, "Plaintext Password", list(unmasked_passwords)[:3]))

    print(f"  - Plaintext Tokens Detected:    {len(unmasked_tokens)}")
    if unmasked_tokens:
        print(f"      Samples: {list(unmasked_tokens)[:4]}")
        violations.append((fname, "Plaintext Token", list(unmasked_tokens)[:3]))

    print(f"  - Internal Hostnames Detected:  {len(internal_hosts)}")
    if internal_hosts:
        print(f"      Samples: {list(internal_hosts)[:4]}")

if scanned_count == 0:
    print("\n[FAIL] Audit checked 0 files! At least one raw log file must be present and verified.")
    print("=" * 80)
    sys.exit(1)

if violations:
    print(f"\n[FAIL] {len(violations)} privacy/credential violation(s) detected in raw logs:")
    for fn, vtype, samples in violations:
        print(f"  ! {fn}: {vtype} -> {samples}")
    print("=" * 80)
    sys.exit(1)

print("\n" + "=" * 80)
print(f"[PASS] Raw log privacy audit passed! Successfully verified {scanned_count} file(s).")
print("       Zero private IPs, unmasked passwords, or exposed tokens detected.")
print("=" * 80)
sys.exit(0)

