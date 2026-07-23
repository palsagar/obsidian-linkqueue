"""One-shot headless Obsidian Sync (`ob sync`) bracketing a Triage run:
pull before writing so the index-rewrite guard (ADR 0004) sees current
indexes, push after so devices see results immediately. Never continuous
(ADR 0005)."""

import subprocess
from pathlib import Path


class SyncError(Exception):
    """`ob sync` failed, timed out, or the `ob` binary is missing."""


def ob_sync(vault_path: Path, timeout: int = 600) -> None:
    try:
        subprocess.run(
            ["ob", "sync", "--path", str(vault_path)],
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as e:
        raise SyncError("`ob` binary not found on PATH") from e
    except subprocess.TimeoutExpired as e:
        raise SyncError(f"ob sync timed out after {timeout}s") from e
    except subprocess.CalledProcessError as e:
        detail = (e.stderr or e.stdout or "").strip()
        raise SyncError(f"ob sync failed: {detail or e}") from e
