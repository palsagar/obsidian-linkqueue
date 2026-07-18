# Link Capture & Triage

A system that captures links from any device into a server-side queue and periodically integrates them into an Obsidian-based knowledge base via an LLM agent.

## Language

**Link**:
A captured URL, optionally with a note from the user. The unit of work in the Queue.
_Avoid_: bookmark, item, entry

**Capture**:
The act of adding a Link to the Queue from any device, in as few taps as possible.
_Avoid_: dumping, sharing, saving

**Queue**:
The server-side, append-only list of Links awaiting Triage. Lives outside the Vault; devices write to it only through the Capture API.
_Avoid_: processing queue page, links dump, inbox

**Triage**:
The periodic LLM-driven run that consumes pending Links from the Queue, derives content from them, and integrates notes into the Knowledge Base.
_Avoid_: processing, sorting, ingestion

**Agent**:
The program that performs Triage. It is the only automated writer to the Vault.
_Avoid_: bot, worker, LLM

**Vault**:
The Obsidian directory of markdown files. Synced across devices by exactly one mechanism.
_Avoid_: repo, notes folder

**Knowledge Base**:
The curated, classified content inside the Vault (topic folders, index notes). What Triage maintains and the user reads.
_Avoid_: KB, wiki

## Flagged ambiguities

- "Processing Queue" previously named a markdown page *inside* the Vault. That page is deprecated; **Queue** now always means the server-side queue.
- "Sync" previously meant either git or Obsidian Sync, running simultaneously. It now means Obsidian Sync only; git is not a sync mechanism in this system.

## Example dialogue

> **Dev:** When I share an article from my iPhone, does that write to the Vault?
> **Expert:** No — Capture only ever appends a Link to the Queue. Nothing touches the Vault until Triage runs.
> **Dev:** And Triage runs on the server?
> **Expert:** No, the Agent runs where the Vault physically exists. It pulls pending Links from the Queue, writes notes into the Knowledge Base, and Obsidian Sync propagates them to every device.
