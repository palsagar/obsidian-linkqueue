# The Agent moves to the VPS; headless Obsidian Sync brackets each Triage run

ADR 0001 pinned the Agent to a laptop for exactly one reason: Obsidian Sync had no headless client, so a vault copy could only live on a GUI device. That premise is gone — Obsidian ships an official headless sync client ([`obsidian-headless`](https://github.com/obsidianmd/obsidian-headless), npm, Node 22+) that makes a server a first-class sync participant. We decided the Agent moves to the VPS as a second container alongside the Queue: the vault's automated-write copy lives on a persistent volume, and every Triage run is **bracketed by one-shot `ob sync` calls** — pull before writing, push after. A failed pull **aborts the run**; Links simply stay pending (ADR 0002 makes waiting safe). What survives of ADR 0001: Obsidian Sync remains the *sole* vault sync mechanism and the Agent remains the *single* automated writer — the server is just another synced device.

## Considered Options

- **`ob sync --continuous` daemon** — rejected: it offers no "am I current *right now*?" barrier, so the ADR 0004 index-rewrite guard could run against a stale `_Index.md` and push an index missing a fresh human edit — silent curated-entry loss reintroduced at the sync layer. It is also a long-lived process to supervise, and it pushes half-finished state mid-run.
- **Agent stays on the laptop** — rejected: Triage latency stays bounded by laptop wakefulness, which is the constraint this decision exists to remove.

## Consequences

- Triage latency is bounded by server uptime, not laptop availability. The laptop retires to a plain Obsidian device with zero automated jobs.
- The vault **plaintext**, the `ob` session token, and the E2EE-derived sync state now live on the VPS volume: anyone with root on the box can read the knowledge base. This is inherent to any headless sync participant and is an **accepted trade-off**; Cloudflare Access protects the HTTP surface, not the disk. The Obsidian account password is never stored — login is a one-time interactive `docker exec`.
- ADR 0001's backup rule restates as: *git survives only as a one-way backup pushed from the vault copy the Agent writes to* — now the server's copy, so the backup job moves into the triage container.
- A post-run push failure self-heals: the next run's bidirectional pull-push delivers the notes. Until then `done` can briefly mean "done on the server, not yet on devices".
- The Agent reports each run's outcome to the Queue (`POST /runs`); the dashboard's last-run heartbeat is the liveness signal for a machine nobody is sitting at.
