# 4. Triage rewrites index notes wholesale, guarded by wikilink preservation

Date: 2026-07-18

## Status

Accepted

## Context

When Triage files a note into a topic folder it must update that folder's
`_Index.md`. Index notes are curated documents — sectioned headings, intro
prose, hand-ordered wikilinks — not append-only lists. Three strategies were
considered: (a) LLM picks a section and Python inserts one line, (b) LLM
returns the full rewritten index, (c) Python appends to a fixed "Recently
Triaged" section. (a) and (c) can never lose content but also can never
reorganize; (b) keeps the index coherent as it grows but makes every Triage
run a chance to silently drop curated entries — and the loss propagates to
all devices via Obsidian Sync before anyone notices.

## Decision

The LLM returns the complete rewritten `_Index.md`. Python accepts the
rewrite only if every wikilink present before the rewrite is still present
after it (reordering and re-sectioning are allowed; deletion is not). If the
guard fails, Python falls back to appending the new entry under the LLM's
chosen section heading, and the Link still completes as `done`.

## Consequences

- Indexes stay curated-looking without manual re-filing; the model may
  restructure sections as a folder grows.
- Curated entries cannot be silently lost; worst case is a suboptimally
  placed new entry.
- Removing an index entry is a human-only operation — the Agent can never
  delete, so intentional pruning happens in Obsidian, not through Triage.
- The guard needs a wikilink parser that matches Obsidian syntax
  (`[[target]]`, `[[target|alias]]`) — target equality, not display text.
