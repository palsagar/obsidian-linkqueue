# Obsidian Sync is the sole vault sync; the Agent runs on a laptop, not the VPS

> **Superseded by [ADR 0005](0005-agent-moves-to-vps-with-headless-sync.md)**: Obsidian now ships an official headless sync client, so the Agent runs on the VPS. "Obsidian Sync is the sole vault sync mechanism" survives unchanged.

The vault was synced by two mechanisms at once (obsidian-git on desktop + Obsidian Sync on iPhone), which produced repeated merge conflicts and two diverged vault copies. We decided Obsidian Sync is the only sync mechanism for the Vault. Because Obsidian Sync has no headless/server API, the Triage Agent cannot run on the VPS — it runs on a laptop with direct filesystem access to the local vault, and Obsidian Sync propagates its output. The VPS hosts only the Queue API, so Links captured while the laptop is asleep wait durably and are never lost.

## Considered Options

- **Git canonical + VPS agent + one bridge laptop running both mechanisms** — rejected: keeps the git↔Obsidian Sync overlap that caused the conflicts, just confined to one machine.
- **Git only, everywhere (drop Obsidian Sync)** — rejected: git on iOS is the clunky experience being escaped, and the iPhone is 80% of usage.

## Consequences

- obsidian-git must be removed from the write path on all devices; git may survive only as a one-way backup pushed from the same laptop that runs the Agent.
- Triage latency is bounded by laptop availability, not server uptime. This is acceptable because Triage is periodic, not real-time.
