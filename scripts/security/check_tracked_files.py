"""Fail CI if tracked files contain obvious credentials or bulk raw datasets.

This is a lightweight guard, NOT a full Git-history/secret-scanning solution.
Never print credential contents in logs.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

PROHIBITED_PATHS = (
    re.compile(r"(^|/)\.env($|\.)"),
    re.compile(r"(^|/)(id_rsa|id_ed25519|credentials|\.aws/credentials)$", re.I),
    re.compile(r"\.(pem|p12|pfx|key)$", re.I),
)
ALLOW = {".env.example"}
PATTERNS = (
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(rb"(?<![A-Z0-9])(?:AKIA|ASIA)[A-Z0-9]{16}(?![A-Z0-9])"),
    re.compile(rb"(?i)(?:aws_secret_access_key|aws_session_token)\s*[:=]\s*['\"]?[^\s'\"#]{20,}"),
)
MAX_BYTES = 5 * 1024 * 1024


def findings(paths: list[Path]) -> list[str]:
    issues = []
    for path in paths:
        name = path.as_posix()
        if path.name not in ALLOW and any(p.search(name) for p in PROHIBITED_PATHS):
            issues.append(f"{name}: forbidden credential-like filename")
        if not path.exists() or not path.is_file():
            continue
        if path.stat().st_size > MAX_BYTES:
            issues.append(f"{name}: tracked file exceeds 5 MiB")
            continue
        data = path.read_bytes()
        if any(pattern.search(data) for pattern in PATTERNS):
            issues.append(f"{name}: potential credential content")
    return issues


def main() -> int:
    completed = subprocess.run(
        ["git", "ls-files", "-z"], capture_output=True, check=True
    )
    paths = [Path(p.decode("utf-8", "surrogateescape"))
             for p in completed.stdout.split(b"\0") if p]
    problems = findings(paths)
    if problems:
        print("\n".join(problems))
        return 1
    print(f"Tracked file hygiene: PASS ({len(paths)} files examined)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
