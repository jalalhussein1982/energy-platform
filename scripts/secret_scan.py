"""Fail if any git-tracked (or staged) file contains a credential-looking string.

Deliberately small and dependency-free (Phase 0). Replace with gitleaks via ADR if needed; keep
the Make target name `secret-scan` so CI wrappers do not change (ADR-015).
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

PATTERNS: dict[str, re.Pattern[str]] = {
    "AWS access key id": re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b"),
    "private key block": re.compile(r"-----BEGIN (RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----"),
    "bearer token": re.compile(r"(?i)\bbearer\s+[a-z0-9._\-]{24,}"),
    "rancher token": re.compile(r"\b(token|kubeconfig)-[a-z0-9]{5}:[a-z0-9]{40,}\b"),
    "openstack app-cred secret": re.compile(r"OS_APPLICATION_CREDENTIAL_SECRET\s*=\s*\S{8,}"),
    "generic assignment": re.compile(
        r"(?i)\b(aws_secret_access_key|secret_key|api[_-]?key|access[_-]?token|password|passwd)"
        r"\s*[:=]\s*['\"]?[A-Za-z0-9/+_\-]{16,}['\"]?"
    ),
    "github token": re.compile(r"\b(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}\b"),
    "slack token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
}

# Placeholders used in docs and templates that must not trip the scan.
ALLOW_LINE = re.compile(
    r"(?i)(<redacted>|<token>|example|placeholder|REPLACE-WITH|\$\{?[A-Z_]+\}?$)"
)
SKIP_SUFFIXES = {".lock", ".png", ".jpg", ".gif", ".pdf", ".xlsx", ".woff", ".woff2"}
SKIP_PATHS = {"scripts/secret_scan.py"}


def tracked_files() -> list[Path]:
    git = shutil.which("git") or "/usr/bin/git"
    out = subprocess.run(  # noqa: S603 — fixed argv, resolved git path, no user input
        [git, "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        check=True,
        capture_output=True,
    ).stdout
    return [Path(p) for p in out.decode().split("\0") if p]


def scan(paths: list[Path]) -> list[str]:
    findings: list[str] = []
    for path in paths:
        if path.suffix in SKIP_SUFFIXES or str(path) in SKIP_PATHS or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if ALLOW_LINE.search(line):
                continue
            for name, pat in PATTERNS.items():
                if pat.search(line):
                    findings.append(f"{path}:{lineno}: {name}")
    return findings


def main() -> int:
    findings = scan(tracked_files())
    if findings:
        print("secret-scan: credential-looking strings found:")
        for f in findings:
            print(f"  {f}")
        return 1
    print("secret-scan: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
