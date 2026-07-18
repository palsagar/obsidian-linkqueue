"""Vault file operations: taxonomy, guarded index rewrites, note writing.

All Vault writes happen here — the LLM only ever produces data (ADR 0004).
"""

import re
from pathlib import Path

WIKILINK = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]")

# Characters Obsidian forbids or mangles in note filenames
UNSAFE_FILENAME_CHARS = re.compile(r'[:"\[\]#|?/\\^]')


def wikilink_targets(text: str) -> set[str]:
    return {m.group(1).strip() for m in WIKILINK.finditer(text)}


def taxonomy(root_index_text: str) -> list[str]:
    """Topic folders declared in the root Index Note, in document order."""
    folders = []
    for m in WIKILINK.finditer(root_index_text):
        target = m.group(1).strip()
        if target.endswith("/_Index"):
            folders.append(target.removesuffix("/_Index"))
    return folders


def guarded_rewrite(current: str, rewritten: str, fallback_line: str, section: str) -> str:
    """Accept a full index rewrite only if no pre-existing wikilink was lost;
    otherwise fall back to appending `fallback_line` under `section` (ADR 0004)."""
    if wikilink_targets(current) <= wikilink_targets(rewritten):
        return rewritten
    return append_under_section(current, section, fallback_line)


def append_under_section(text: str, section: str, line: str) -> str:
    lines = text.splitlines()
    heading = f"## {section}"
    if heading not in lines:
        return text.rstrip("\n") + f"\n\n{heading}\n{line}\n"
    start = lines.index(heading)
    # insert after the last non-blank line before the next heading (or EOF)
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if lines[i].startswith("## "):
            end = i
            break
    insert_at = end
    while insert_at > start + 1 and not lines[insert_at - 1].strip():
        insert_at -= 1
    lines.insert(insert_at, line)
    return "\n".join(lines) + "\n"


def safe_folder_dir(vault_path: Path, folder: str) -> Path:
    """Resolve a model-chosen folder name, refusing anything that escapes the
    Vault or lands on its root (model output is untrusted — fetched pages can
    prompt-inject it)."""
    resolved = (vault_path / folder).resolve()
    root = vault_path.resolve()
    if resolved == root or not resolved.is_relative_to(root):
        raise ValueError(f"unsafe folder name: {folder!r}")
    return resolved


def safe_filename(title: str) -> str:
    cleaned = UNSAFE_FILENAME_CHARS.sub("", title)
    return re.sub(r"\s+", " ", cleaned).strip()


def write_note(
    vault_path: Path,
    folder: str,
    title: str,
    body: str,
    source: str,
    captured: str,
    triaged: str,
    tags: list[str],
) -> str:
    """Write the note, deduping filename collisions. Returns the vault-relative path."""
    folder_dir = safe_folder_dir(vault_path, folder)
    name = safe_filename(title)
    target = folder_dir / f"{name}.md"
    n = 2
    while target.exists():
        target = folder_dir / f"{name} {n}.md"
        n += 1
    tag_lines = "".join(f"\n  - {t}" for t in tags)
    frontmatter = (
        f"---\n"
        f'source: "{source}"\n'
        f"captured: {captured}\n"
        f"triaged: {triaged}\n"
        f"tags:{tag_lines or ' []'}\n"
        f"---\n"
    )
    target.write_text(f"{frontmatter}\n{body.strip()}\n")
    return str(target.relative_to(vault_path.resolve()))
