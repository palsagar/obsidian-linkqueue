"""Triage orchestration: claim → fetch → judge → write → report, per Link.

Each Link completes (or fails) fully before the next starts, so a crash
loses at most one; the lease reclaims anything stranded mid-run.
"""

import logging
from datetime import date
from pathlib import Path

import httpx

from agent import judgment, vault
from agent.fetch import fetch
from agent.queue_client import QueueClient

log = logging.getLogger("obs_triage")


def run_triage(
    queue: QueueClient,
    web: httpx.Client,
    vault_path: Path,
    model,
    limit: int = 20,
) -> dict:
    stats = {"done": 0, "failed": 0}
    links = queue.claim(limit=limit)
    log.info("claimed %d links", len(links))
    for i, link in enumerate(links, 1):
        log.info("[%d/%d] %s", i, len(links), link["url"])
        try:
            page = fetch(link["url"], web)
            if page.error:
                queue.failed(link["id"], error=page.error)
                stats["failed"] += 1
                log.info("  failed: %s", page.error)
                continue
            log.info("  fetched: %s", page.title or "(no title)")
            note_path = _triage_one(link, page, vault_path, model)
            queue.done(link["id"], note_path=note_path)
            stats["done"] += 1
            log.info("  done: %s", note_path)
        except Exception as e:  # hard error (model/API): report and keep going
            queue.failed(link["id"], error=str(e))
            stats["failed"] += 1
            log.info("  failed: %s", e)
    return stats


def update_indexes(vault_path: Path, result, model) -> None:
    """File a classified note into the Taxonomy: create a new folder (seeding
    its Index Note and the root entry) or guarded-rewrite the existing folder's
    Index Note (ADR 0004). Shared by Link and Clipping triage."""
    root_index_path = vault_path / "_Index.md"
    root_index = root_index_path.read_text()
    folder_dir = vault.safe_folder_dir(vault_path, result.folder)
    folder_index_path = folder_dir / "_Index.md"

    if result.is_new_folder:
        folder_dir.mkdir(exist_ok=True)
        folder_index_path.write_text(
            f"# {result.folder}\n\n{result.folder_description}\n\n"
            f"## {result.section}\n- [[{result.note_title}]]\n"
        )
        root_entry = (
            f"- [[{result.folder}/_Index|{result.folder}]] — {result.folder_description}"
        )
        root_index_path.write_text(
            vault.append_under_section(root_index, result.root_section, root_entry)
        )
    else:
        current = folder_index_path.read_text()
        rewritten = judgment.rewrite_index(
            model,
            folder=result.folder,
            current_index=current,
            note_title=result.note_title,
        )
        folder_index_path.write_text(
            vault.guarded_rewrite(
                current, rewritten, f"- [[{result.note_title}]]", result.section
            )
        )


def _triage_one(link: dict, page, vault_path: Path, model) -> str:
    root_index = (vault_path / "_Index.md").read_text()

    result = judgment.classify(
        model,
        url=link["url"],
        note=link.get("note"),
        page=page,
        taxonomy=vault.taxonomy(root_index),
        root_index=root_index,
    )

    update_indexes(vault_path, result, model)

    return vault.write_note(
        vault_path,
        folder=result.folder,
        title=result.note_title,
        body=result.note_body,
        source=link["url"],
        captured=date.fromtimestamp(link["created_at"]).isoformat(),
        triaged=date.today().isoformat(),
        tags=result.tags,
    )
