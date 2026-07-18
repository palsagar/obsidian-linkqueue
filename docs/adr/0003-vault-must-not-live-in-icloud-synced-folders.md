# The Vault must not live under an iCloud-synced folder

Investigation revealed "Desktop & Documents in iCloud" is enabled on the Macs, so anything under `~/Documents` — including the vault and its `.git` directory — was being silently synced by iCloud across machines. This was an unrecognized third sync mechanism: it cross-contaminated the two vault copies, produced iCloud "name 2.md"-style duplicate files, and shared one `.git` between two machines' obsidian-git plugins. We decided the canonical Vault lives outside any iCloud-synced path (e.g. `~/Obsidian/`), so Obsidian Sync (ADR 0001) is genuinely the only mechanism syncing vault content.

## Consequences

- During migration the vault moves from `~/Documents/Obsidian Vault` to `~/Obsidian/vault` (done at Obsidian Sync pairing time).
- The one-way git backup repo also leaves iCloud-synced paths, ending the shared-`.git` hazard.
