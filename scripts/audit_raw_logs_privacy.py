import re
from pathlib import Path

raw_dir = Path("backend/data/raw")

files = ["1130.txt", "Jenkins_Log_Under_1MB.txt", "jenkins_gist_crash.log"]

print("=" * 80)
print("RAW LOG SECURITY & PRIVACY AUDIT")
print("=" * 80)

for fname in files:
    fpath = raw_dir / fname
    content = fpath.read_text(encoding="utf-8", errors="replace")
    
    # Check IP addresses
    ips = set(re.findall(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', content))
    
    # Check passwords
    passwords = set(re.findall(r'(?i)(?:password|passwd|pwd)\s*[:=]\s*(\S+)', content))
    
    # Check tokens / keys
    tokens = set(re.findall(r'(?i)(?:token|key|secret|auth)\s*[:=]\s*([a-zA-Z0-9_\-\.]{8,})', content))
    
    # Check email / hostnames
    internal_hosts = set(re.findall(r'[a-zA-Z0-9_\-]+\.(?:internal|corp|local|hpe\.com)', content))

    print(f"\n--- File: {fname} ({len(content)} bytes, {len(content.splitlines())} lines) ---")
    print(f"  - IP Addresses Detected:        {len(ips)} distinct IPs")
    if ips:
        print(f"      Samples: {list(ips)[:4]}")
    print(f"  - Password Patterns Detected:   {len(passwords)} patterns")
    if passwords:
        print(f"      Samples: {list(passwords)[:4]}")
    print(f"  - Tokens/Keys Patterns Detected:{len(tokens)} patterns")
    if tokens:
        print(f"      Samples: {list(tokens)[:4]}")
    print(f"  - Internal Hostnames Detected:  {len(internal_hosts)} hostnames")
    if internal_hosts:
        print(f"      Samples: {list(internal_hosts)[:4]}")

print("\nAudit completed.")
