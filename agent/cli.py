"""`obs_triage run` / `obs_triage backup` — the Agent's entry points
(interactive and scheduled)."""

import argparse
import logging
import subprocess
import sys
import time
from pathlib import Path

import httpx

from agent.backup import run_backup
from agent.clippings import triage_clippings
from agent.config import DEFAULT_PATH, load_config
from agent.judgment import build_model
from agent.queue_client import QueueClient, build_http_client
from agent.run import run_triage
from agent.sync import SyncError, ob_sync


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="obs_triage")
    sub = parser.add_subparsers(dest="command", required=True)
    run_p = sub.add_parser("run", help="claim pending Links and triage them")
    run_p.add_argument("--config", default=str(DEFAULT_PATH))
    run_p.add_argument("--limit", type=int, default=None)
    run_p.add_argument(
        "--sync",
        action="store_true",
        help="bracket the run with one-shot `ob sync` pull/push (ADR 0005)",
    )
    backup_p = sub.add_parser("backup", help="one-way git backup of the Vault")
    backup_p.add_argument("--config", default=str(DEFAULT_PATH))
    args = parser.parse_args(argv)

    # per-link progress on stdout — visible interactively and in launchd logs
    # (scoped to our logger so httpx/httpcore chatter stays out)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    progress_log = logging.getLogger("obs_triage")
    progress_log.addHandler(handler)
    progress_log.setLevel(logging.INFO)

    try:
        cfg = load_config(Path(args.config))
    except ValueError as e:
        print(e, file=sys.stderr)
        return 1

    if args.command == "backup":
        try:
            print(f"backup: {run_backup(cfg.vault_path)}")
        except ValueError as e:
            print(e, file=sys.stderr)
            return 1
        except subprocess.CalledProcessError as e:
            print(f"backup failed: {e.stderr.strip() or e}", file=sys.stderr)
            return 1
        return 0

    queue = QueueClient(
        build_http_client(cfg.queue_url, cfg.cf_access_client_id, cfg.cf_access_client_secret)
    )

    started = time.time()

    def heartbeat(outcome: str, done: int = 0, failed: int = 0, error: str | None = None):
        # best-effort: an unreachable queue must not mask the run's own outcome
        try:
            queue.report_run(started, time.time(), outcome, done=done, failed=failed, error=error)
        except httpx.HTTPError:
            pass

    if args.sync:
        try:
            ob_sync(cfg.vault_path)
        except SyncError as e:
            # never write into a vault we can't confirm is current (ADR 0005)
            heartbeat("sync_failed", error=str(e))
            print(f"pre-run sync failed, aborting: {e}", file=sys.stderr)
            return 1

    model = build_model(cfg.openrouter_api_key, cfg.model, cfg.fallback_model)

    try:
        with httpx.Client() as web:
            stats = run_triage(
                queue, web, cfg.vault_path, model, limit=args.limit or cfg.limit
            )
    except httpx.HTTPError as e:
        # offline or queue unreachable — a normal scheduled condition, not an error
        print(f"queue unreachable ({e.__class__.__name__}) — skipping this run")
        return 0

    clip_stats = triage_clippings(cfg.vault_path, model)
    done = stats["done"] + clip_stats["done"]
    failed = stats["failed"] + clip_stats["failed"]

    if args.sync:
        try:
            ob_sync(cfg.vault_path)
        except SyncError as e:
            # notes are written locally; the next run's pull-push self-heals (ADR 0005)
            heartbeat("push_failed", done=done, failed=failed, error=str(e))
            print(f"post-run sync failed: {e}", file=sys.stderr)
            return 1

    heartbeat("ok", done=done, failed=failed)
    print(
        f"triage: {stats['done']} done, {stats['failed']} failed (links); "
        f"{clip_stats['done']} filed, {clip_stats['failed']} failed (clippings)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
