"""One-way vault backup: add, commit, push. Never fetches or pulls —
git is a backup target, not a sync mechanism (ADR 0001)."""

import subprocess
from datetime import datetime
from pathlib import Path


def _git(vault_path: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(vault_path), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def run_backup(vault_path: Path) -> str:
    if not (vault_path / ".git").is_dir():
        raise ValueError(f"not a git repo: {vault_path}")

    changes = _git(vault_path, "status", "--porcelain")
    if not changes:
        return "no changes"

    n_files = len(changes.splitlines())
    _git(vault_path, "add", "-A")
    stamp = datetime.now().isoformat(sep=" ", timespec="minutes")
    _git(vault_path, "commit", "-m", f"vault backup {stamp}")
    _git(vault_path, "push", "origin", "HEAD")
    return f"backed up {n_files} files"
