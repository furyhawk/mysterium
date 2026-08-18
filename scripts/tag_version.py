#!/usr/bin/env python3
"""Create and publish the git release tag for the current Mysterium version.

Reads the version from ``pyproject.toml``, validates it matches
``mysterium/__init__.py``, then creates an *annotated* tag ``v<version>``
(message "Mysterium v<version>") and pushes it to ``origin``.

Usage::

    scripts/tag_version.py             # validate + create + push
    scripts/tag_version.py --no-push   # validate + create locally only
    scripts/tag_version.py --dry-run   # validate + show planned actions, no changes

Guards (each fails unless overridden with ``--force``):

* A tag for the current version already exists.
* The version is not an uptick (it is <= the highest existing ``v*`` tag).
* The version-bearing files (``pyproject.toml``, ``mysterium/__init__.py``,
  ``uv.lock``) have uncommitted changes — commit the bump before tagging.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"
INIT = ROOT / "mysterium" / "__init__.py"
TAG_PREFIX = "v"
# Files that encode the release version and should be committed with the bump.
VERSION_FILES = (r"pyproject\.toml", r"mysterium/__init__\.py", r"uv\.lock")


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd, cwd=ROOT, capture_output=True, text=True, check=False
    )


def git(args: list[str]) -> str:
    """Run a git command; exit on failure, return stdout (stripped)."""
    res = run(["git", *args])
    if res.returncode != 0:
        sys.exit(f"error: `git {' '.join(args)}` failed:\n{res.stderr.strip()}")
    return res.stdout.strip()


def read_pyproject_version() -> str:
    import tomllib  # Python 3.11+

    with open(PYPROJECT, "rb") as fh:
        data = tomllib.load(fh)
    return data["project"]["version"]


def read_init_version() -> str:
    match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', INIT.read_text())
    if not match:
        sys.exit(f"error: cannot find `__version__` in {INIT}")
    return match.group(1)


def version_key(value: str) -> tuple[int, ...]:
    """Numeric sort key for a version string, e.g. 'v0.2.0' -> (0, 2, 0)."""
    return tuple(int(part) for part in re.findall(r"\d+", value))


def existing_version_tags() -> list[str]:
    tags = git(["tag", "-l", f"{TAG_PREFIX}*"])
    pattern = re.compile(rf"{TAG_PREFIX}\d+(?:\.\d+)*$")
    return [t for t in tags.splitlines() if pattern.fullmatch(t)]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Tag the current Mysterium version and push it to origin."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="override guards (existing tag, non-uptick, uncommitted version files)",
    )
    parser.add_argument(
        "--no-push",
        action="store_true",
        help="create the tag locally but do not push it",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate and print planned actions without changing anything",
    )
    args = parser.parse_args()

    # ── Read the version ────────────────────────────────────────────
    version = read_pyproject_version()
    init_version = read_init_version()
    if version != init_version:
        print(
            f"error: version mismatch — pyproject.toml={version}, "
            f"mysterium/__init__.py={init_version}"
        )
        return 1

    tag = f"{TAG_PREFIX}{version}"

    # ── Guard: tag already exists ──────────────────────────────────
    tags = existing_version_tags()
    if tag in tags:
        if not args.force:
            print(f"error: tag {tag!r} already exists")
            return 1
        print(f"warning: tag {tag!r} already exists (overridden by --force)")

    # ── Guard: must be an uptick over the latest tag ───────────────
    if tags:
        latest = max(tags, key=version_key)
        if version_key(version) <= version_key(latest):
            if not args.force:
                print(
                    f"error: version {version} is not an uptick over the "
                    f"latest tag {latest}"
                )
                return 1
            print(
                f"warning: version {version} is not an uptick over the "
                f"latest tag {latest} (overridden by --force)"
            )

    # ── Guard: version bump must be committed ──────────────────────
    dirty = [
        line
        for line in git(["status", "--porcelain"]).splitlines()
        if re.search(rf"(?:{'|'.join(VERSION_FILES)})$", line)
    ]
    if dirty:
        if not args.force:
            print(
                "error: version files have uncommitted changes — commit the "
                "version bump before tagging:"
            )
            for line in dirty:
                print(f"  {line}")
            return 1
        print(
            "warning: version files have uncommitted changes "
            "(overridden by --force):"
        )
        for line in dirty:
            print(f"  {line}")

    # ── Report ──────────────────────────────────────────────────────
    print(f"Mysterium version : {version}")
    print(f"Tag              : {tag}")
    print(f"Message          : Mysterium {version}")
    if args.dry_run:
        print("Dry run — no changes made.")
        return 0

    # ── Create the annotated tag ────────────────────────────────────
    git(["tag", "-a", tag, "-m", f"Mysterium {version}"])
    print(f"Created annotated tag {tag}")

    # ── Push ────────────────────────────────────────────────────────
    if args.no_push:
        print("Skipped push (--no-push).")
    else:
        git(["push", "origin", tag])
        print(f"Pushed {tag} to origin")

    return 0


if __name__ == "__main__":
    sys.exit(main())
