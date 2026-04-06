#!/usr/bin/env python3
"""Validate datoon skill copies and packaged .skill artifact consistency."""

from __future__ import annotations

import hashlib
import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_SKILL = REPO_ROOT / "skills" / "datoon" / "SKILL.md"
MIRROR_SKILL_PATHS = [
    REPO_ROOT / "SKILL.md",
    REPO_ROOT / "datoon" / "SKILL.md",
    REPO_ROOT / "plugins" / "datoon" / "skills" / "datoon" / "SKILL.md",
]
SKILL_ARCHIVE_PATH = REPO_ROOT / "datoon.skill"
SKILL_ARCHIVE_MEMBER = "datoon/SKILL.md"


def _sha256_bytes(value: bytes) -> str:
    """Compute SHA-256 hash from bytes."""
    return hashlib.sha256(value).hexdigest()


def _read_file(path: Path) -> bytes:
    """Read file bytes with explicit path error context."""
    if not path.exists():
        raise FileNotFoundError(f"Missing required file: {path}")
    return path.read_bytes()


def _read_archive_member(path: Path, member: str) -> bytes:
    """Read a file member from zip archive."""
    if not path.exists():
        raise FileNotFoundError(f"Missing skill archive: {path}")

    with zipfile.ZipFile(path, "r") as archive:
        try:
            return archive.read(member)
        except KeyError as exc:
            raise FileNotFoundError(
                f"Missing '{member}' inside archive: {path}"
            ) from exc


def validate() -> list[str]:
    """Validate mirror files and archive content against source skill."""
    errors: list[str] = []
    source_bytes = _read_file(SOURCE_SKILL)
    source_hash = _sha256_bytes(source_bytes)

    for mirror_path in MIRROR_SKILL_PATHS:
        mirror_bytes = _read_file(mirror_path)
        mirror_hash = _sha256_bytes(mirror_bytes)
        if mirror_hash != source_hash:
            errors.append(
                f"Out-of-sync SKILL.md copy: {mirror_path} "
                f"(expected hash {source_hash}, got {mirror_hash})"
            )

    archived_bytes = _read_archive_member(SKILL_ARCHIVE_PATH, SKILL_ARCHIVE_MEMBER)
    archived_hash = _sha256_bytes(archived_bytes)
    if archived_hash != source_hash:
        errors.append(
            f"Out-of-sync {SKILL_ARCHIVE_PATH}::{SKILL_ARCHIVE_MEMBER} "
            f"(expected hash {source_hash}, got {archived_hash})"
        )

    return errors


def main() -> int:
    """Run validation and return shell-style exit code."""
    try:
        errors = validate()
    except FileNotFoundError as exc:
        print(f"skill-sync check failed: {exc}", file=sys.stderr)
        return 1

    if errors:
        print("skill-sync check failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print("skill-sync check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
