#!/usr/bin/env python3
"""Check that every artifact a subagent claimed to produce actually exists.

Reads a manifest of one path per line (blank lines and ``#`` comments ignored),
prints one PASS/FAIL row per path, and exits 1 when any path is missing or is
an empty file. Exits 2 on a usage error.

The point is to stop a delegated task from being reported as done on the
strength of the child's own summary: this checks the filesystem, not the prose.

Usage:
    python3 verify_artifacts.py <manifest.txt> [more manifests...]
"""

from __future__ import annotations

import sys
from pathlib import Path


def parse_manifest(text: str) -> list[str]:
    """Manifest lines → artifact paths. Blank lines and ``#`` comments dropped."""
    paths = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        paths.append(line)
    return paths


def check(path_str: str) -> tuple[str, str, bool]:
    """Return (path, status, ok). A path is ok when it exists and is not an empty file."""
    p = Path(path_str).expanduser()
    if not p.exists():
        return path_str, "FAIL (missing)", False
    if p.is_file() and p.stat().st_size == 0:
        return path_str, "FAIL (empty file)", False
    if p.is_dir():
        return path_str, "FAIL (directory, not a file)", False
    return path_str, "PASS", True


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: verify_artifacts.py <manifest.txt> [more manifests...]", file=sys.stderr)
        return 2

    total = 0
    failures = 0
    for manifest in argv[1:]:
        mpath = Path(manifest).expanduser()
        if not mpath.is_file():
            print(f"FAIL (manifest missing) {manifest}")
            failures += 1
            total += 1
            continue
        for artifact in parse_manifest(mpath.read_text(encoding="utf-8")):
            path_str, status, ok = check(artifact)
            total += 1
            if not ok:
                failures += 1
            print(f"{status} {path_str}")

    print(f"\n{total - failures}/{total} artifacts present")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
