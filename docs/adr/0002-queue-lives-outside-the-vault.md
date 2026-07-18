# The Queue lives on the VPS, outside the Vault

Capturing links by appending to a markdown page inside the synced vault made every device a concurrent writer to one file — the direct cause of recurring merge conflicts, and it coupled capture availability to vault sync health. We decided the Queue is a server-side store (SQLite behind a FastAPI service on the VPS): devices Capture via an append-only API and never write to the Vault; the Triage Agent is the only automated Vault writer. The old "Processing Queue - Links dump" page is deprecated.

## Consequences

- Capture works from any device regardless of vault sync state, and Links survive laptop downtime.
- The Vault's automated write path narrows to a single writer (the Agent), which is what makes "Obsidian Sync only" (ADR 0001) conflict-free in practice.
- The Queue must expose atomic claim semantics (`pending → processing` with a lease) because the Agent may eventually run on more than one laptop.
