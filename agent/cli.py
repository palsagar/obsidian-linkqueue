"""`obs_triage run` — the Agent's entry point (interactive and launchd)."""

import argparse
import sys
from pathlib import Path

import httpx

from agent.clippings import triage_clippings
from agent.config import DEFAULT_PATH, load_config
from agent.judgment import build_model
from agent.queue_client import QueueClient, build_http_client
from agent.run import run_triage


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="obs_triage")
    sub = parser.add_subparsers(dest="command", required=True)
    run_p = sub.add_parser("run", help="claim pending Links and triage them")
    run_p.add_argument("--config", default=str(DEFAULT_PATH))
    run_p.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)

    try:
        cfg = load_config(Path(args.config))
    except (FileNotFoundError, ValueError) as e:
        print(e, file=sys.stderr)
        return 1

    queue = QueueClient(
        build_http_client(cfg.queue_url, cfg.cf_access_client_id, cfg.cf_access_client_secret)
    )
    model = build_model(cfg.openrouter_api_key, cfg.model, cfg.fallback_model)

    try:
        with httpx.Client() as web:
            stats = run_triage(
                queue, web, cfg.vault_path, model, limit=args.limit or cfg.limit
            )
    except httpx.HTTPError as e:
        # offline or queue unreachable — a normal nightly condition, not an error
        print(f"queue unreachable ({e.__class__.__name__}) — skipping this run")
        return 0

    clip_stats = triage_clippings(cfg.vault_path, model)

    print(
        f"triage: {stats['done']} done, {stats['failed']} failed (links); "
        f"{clip_stats['done']} filed, {clip_stats['failed']} failed (clippings)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
