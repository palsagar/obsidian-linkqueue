"""Clipping triage: classify full pages staged in the Vault's Clippings
folder and file them into the Taxonomy.

No fetching or summarizing — the content already exists. The model picks
folder/title/tags/section; Python moves the file (frontmatter merged, body
untouched) and updates the Index Note like any other triaged note.
"""

from datetime import date
from pathlib import Path

import yaml

from agent import judgment, vault
from agent.fetch import TEXT_LIMIT, Page
from agent.run import update_indexes


def split_note(text: str) -> tuple[dict, str]:
    """Split a note into (frontmatter dict, body). Empty dict when absent."""
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            fm = yaml.safe_load(text[4:end]) or {}
            return fm, text[end + 5 :].lstrip("\n")
    return {}, text


def merge_frontmatter(fm: dict, triaged: str, tags: list[str]) -> dict:
    """Add the triaged date and topical tags, keeping all original keys."""
    merged = dict(fm)
    merged["triaged"] = triaged
    existing = merged.get("tags") or []
    if isinstance(existing, str):
        existing = [existing]
    merged["tags"] = existing + [t for t in tags if t not in existing]
    return merged


def render_note(fm: dict, body: str) -> str:
    front = yaml.safe_dump(fm, sort_keys=False, allow_unicode=True)
    return f"---\n{front}---\n\n{body}"


def list_clippings(vault_path: Path) -> list[Path]:
    clippings_dir = vault_path / "Clippings"
    if not clippings_dir.is_dir():
        return []
    return sorted(p for p in clippings_dir.glob("*.md") if p.name != "_Index.md")


def triage_clippings(vault_path: Path, model) -> dict:
    stats = {"done": 0, "failed": 0}
    for path in list_clippings(vault_path):
        try:
            _triage_clipping(path, vault_path, model)
            stats["done"] += 1
        except Exception as e:  # leave the file in place for the next run
            print(f"clipping '{path.name}' failed: {e}")
            stats["failed"] += 1
    return stats


def _triage_clipping(path: Path, vault_path: Path, model) -> None:
    fm, body = split_note(path.read_text())
    root_index = (vault_path / "_Index.md").read_text()

    result = judgment.classify(
        model,
        url=fm.get("source") or f"vault clipping: {path.name}",
        note=None,
        page=Page(
            title=fm.get("title") or path.stem,
            description=fm.get("description"),
            text=body[:TEXT_LIMIT],
        ),
        taxonomy=vault.taxonomy(root_index),
        root_index=root_index,
    )

    update_indexes(vault_path, result, model)

    folder_dir = vault.safe_folder_dir(vault_path, result.folder)
    target = vault.unique_note_path(folder_dir, vault.safe_filename(result.note_title))
    merged = merge_frontmatter(fm, triaged=date.today().isoformat(), tags=result.tags)
    target.write_text(render_note(merged, body))
    path.unlink()
