#!/usr/bin/env python3
"""Pre-commit guard: block rawdata, crawl intermediates, and secrets."""
from __future__ import annotations

import subprocess
import sys

BLOCKED_PREFIXES = (
    "rawdata/",
    "rawdata\\",
    "data/crawl/",
    "data\\crawl\\",
)

BLOCKED_BASENAMES = {
    ".env",
    ".env.local",
    ".envrc",
}

BLOCKED_SUFFIXES = (
    ".pem",
    ".key",
)

ENV_ALLOWLIST = {".env.example"}


def _blocked_reason(path: str) -> str | None:
    normalized = path.replace("\\", "/")
    basename = normalized.rsplit("/", 1)[-1]

    if basename in BLOCKED_BASENAMES:
        return "secret env file"
    if basename.startswith(".env.") and basename not in ENV_ALLOWLIST:
        return "secret env file"
    if any(normalized.endswith(suffix) for suffix in BLOCKED_SUFFIXES):
        return "private key material"
    if any(normalized.startswith(prefix.replace("\\", "/")) for prefix in BLOCKED_PREFIXES):
        return "local-only data pipeline artifact"

    return None


def staged_paths() -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
        check=True,
        capture_output=True,
        text=True,
    )
    return [line for line in result.stdout.splitlines() if line.strip()]


def main() -> int:
    violations: list[tuple[str, str]] = []
    for path in staged_paths():
        reason = _blocked_reason(path)
        if reason:
            violations.append((path, reason))

    if not violations:
        return 0

    print("Commit blocked — the following paths must not be pushed:", file=sys.stderr)
    for path, reason in violations:
        print(f"  - {path} ({reason})", file=sys.stderr)
    print(file=sys.stderr)
    print("Remove them from the index, keep them gitignored, and retry.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
