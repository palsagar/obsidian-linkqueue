# Architecture — Link Capture & Triage

Terms per [CONTEXT.md](../CONTEXT.md). Decisions per [ADR 0001](adr/0001-obsidian-sync-sole-vault-sync.md) (Obsidian Sync is the sole vault sync; Agent runs on a laptop) and [ADR 0002](adr/0002-queue-lives-outside-the-vault.md) (Queue lives on the VPS, outside the Vault).

## Overview

```mermaid
flowchart LR
    subgraph clients["iPhone / laptops"]
        S["iOS/macOS Shortcut<br/>'Queue it'"]
        H["Human<br/>(dashboard view / paste)"]
    end

    subgraph vps["VPS — Coolify, Hetzner — behind Cloudflare Access"]
        Q["Queue API (FastAPI)"]
        DB[("SQLite — links")]
        DASH["Dashboard<br/>(Jinja + HTMX)"]
        Q --- DB
        Q --- DASH
    end

    subgraph laptop["Agent laptop(s)"]
        T["Triage Agent (Python)<br/>fetch_url: plain GET, no scrape/download<br/>LLM via OpenRouter (Pydantic AI)"]
        V[("Vault — local copy")]
        G["nightly one-way git push<br/>(backup only)"]
    end

    D["all devices<br/>(read notes)"]

    S -- "POST /links — HTTPS" --> Q
    H -- "browser" --> DASH
    T -- "claim — HTTPS" --> Q
    T -- "writes notes" --> V
    V -- "Obsidian Sync" --> D
    V --> G
```

Flow: Capture appends a Link to the Queue → Triage (periodic, on a laptop) claims pending Links, takes a brief look at each (plain GET, no scraping or downloads), writes one note per Link into the Vault and updates `_Index.md` files → Obsidian Sync propagates to all devices.

## Flow sequence

```mermaid
sequenceDiagram
    actor U as User
    participant S as Shortcut ('Queue it')
    participant Q as Queue API (VPS)
    participant T as Triage Agent (laptop)
    participant V as Vault (filesystem)
    participant O as Obsidian Sync

    U->>S: Share → Queue it
    S->>Q: POST /links {url, source}
    Q-->>S: 201 pending (200 if already queued)
    Note over Q: Link waits durably —<br/>laptop may be asleep

    loop launchd: nightly + on-demand
        T->>Q: POST /links/claim {limit, lease_seconds}
        Q-->>T: Links → processing (leased)
        T->>T: fetch_url — plain GET<br/>(title, metadata, readable text)
        T->>T: LLM via OpenRouter:<br/>summarize + classify
        alt triage succeeds
            T->>V: write note, update _Index.md
            T->>Q: PATCH /links/{id} {done, note_path}
        else hard error (dead URL, API failure)
            T->>Q: PATCH /links/{id} {failed, error}
            Note over Q: visible in dashboard —<br/>retry sets it back to pending
        end
    end

    V->>O: local change detected
    O->>U: note appears on every device
    Note over T,Q: Agent crash? Lease expires →<br/>Link becomes claimable again
```

## Components

### 1. Queue API — FastAPI on the VPS

Single small service, Docker image deployed via Coolify, SQLite file on a persistent volume.

Endpoints (JSON):

| Endpoint | Purpose |
|---|---|
| `POST /links` | Capture. Body: `url`, optional `note`, optional `source` (device). Dedups on normalized URL (returns the existing Link instead of a duplicate). |
| `GET /links?status=` | List Links (Agent polling + dashboard). |
| `POST /links/claim` | Atomically claim up to N `pending` Links → `processing` with a lease expiry (`UPDATE … WHERE status='pending' RETURNING`). Expired leases revert to `pending`, so a crashed run self-heals and two laptops never double-process. |
| `PATCH /links/{id}` | Agent reports outcome: `done` (+ `note_path`, the vault-relative path of the created note) or `failed` (+ error). Dashboard uses it for retry (`failed → pending`) and delete. |

`links` table: `id`, `url`, `url_normalized` (unique), `note`, `source`, `status` (`pending|processing|done|failed`), `lease_expires_at`, `note_path`, `error`, `created_at`, `updated_at`.

### 2. Dashboard — served by the same FastAPI app

Jinja + HTMX, no build step. Lists Links by status, paste-a-link form (desktop capture fallback), retry/delete on failures, and per-Link outcome (which note it became). This is also the debugging window into Triage.

### 3. Auth — Cloudflare Access

- Domain proxied through Cloudflare; Access application in front of it.
- Humans: SSO (email OTP / Google) for the dashboard.
- Machines (Shortcut, Agent): Access **service tokens** via `CF-Access-Client-Id`/`CF-Access-Client-Secret` headers.
- FastAPI middleware verifies the Cloudflare-signed `Cf-Access-Jwt-Assertion` JWT so the origin rejects traffic that didn't pass Access (covers direct-to-IP hits).

### 4. Capture clients

- **iOS/macOS Shortcut** ("Queue it"): share-sheet target; grabs the shared URL, POSTs to `/links` with service-token headers. One tap after Share. Same Shortcut syncs to the Macs via iCloud.
- **Dashboard form**: paste fallback on any browser.
- Anything else later (bookmarklet, Raycast, CLI) is just another caller of `POST /links`.

### 5. Triage Agent — Python worker on the laptop(s)

Runs where the Vault is (ADR 0001). Installed on this Mac first; the second laptop can be added later unchanged thanks to claim semantics.

- **Trigger**: launchd, nightly + on-demand (`triage run`). Skips silently if offline or no pending Links.
- **No deterministic fetch pipeline** (no trafilatura/yt-dlp/X-syndication). The agent has one lightweight `fetch_url` tool: a plain HTTP GET returning page title, OG/meta description, and readable text when the page serves it. Articles and blog posts usually serve their content this way and get a real summary. X and YouTube links are deliberately **not** scraped or downloaded — the agent takes a brief look at the URL plus whatever metadata the page exposes, writes a tiny summary (grounded in that metadata, not full content), and sorts the Link accordingly.
- **Judgment (LLM via OpenRouter)**: Pydantic AI agent (OpenRouter provider, model configurable — e.g. Claude via OpenRouter). Given the fetched context + the Vault's folder taxonomy and index files, it: writes one note per Link (depth follows what the link yielded — full summary for articles, tiny summary for X/YouTube), chooses the topic folder, updates that folder's `_Index.md` (and root `_Index.md` if a new folder is warranted), adds wikilinks to related existing notes. Only hard errors (URL dead, model/API failure) mark a Link `failed`; thin metadata does not.
- **Note format**: frontmatter with `source` (URL), `captured`/`triaged` dates, `tags`, `triaged: true` — so recent arrivals are queryable from within Obsidian (Bases/Dataview) for post-hoc review (auto-write policy).
- **Reporting**: PATCHes each Link `done`/`failed`; optionally appends a one-line entry to a "Triage Log" note in the Vault.

### 6. Backup job — one-way git push

launchd job on the Agent laptop: nightly `git add -A && git commit && git push` to the private GitHub repo. Never pulls, never runs on other devices; the obsidian-git plugin is removed everywhere. Pure offsite history.

## Migration plan (one-time cleanup)

Order matters; do this before building anything that touches the Vault.

1. **Snapshot both vaults** (zip or Time Machine checkpoint) — everything below becomes reversible.
2. **Settle vault 1's git**: resolve the open merge conflict in `Processing Queue - Links dump.md` (keep both link lists), commit everything including untracked notes, push. This is the "final state" backup of the git era.
3. **Reconcile the two vault copies**: diff `Obsidian Vault` vs `sagar's vault`; copy anything unique in vault 2 into vault 1. (They're near-identical; expect a handful of files.)
4. **Make vault 1 the one Vault**: first move it out of iCloud's reach — `~/Documents` is synced by "Desktop & Documents in iCloud" ([ADR 0003](adr/0003-vault-must-not-live-in-icloud-synced-folders.md)) — to `~/Obsidian/vault`, and open it from there in Obsidian. Then connect it to Obsidian Sync — overwrite/replace the remote vault. Remove the obsidian-git plugin. Delete the `.obsidian-git-bridge/` folders and `conflict-files-obsidian-git*.md` artifacts.
5. **Reconnect iPhone + second laptop** to the remote vault fresh (delete their local copies first to avoid re-merging stale state).
6. **Archive `sagar's vault`** (move out of `~/Documents`, keep the snapshot) once sync is verified on all three devices.
7. **Drain the old queue page**: the links still in `Processing Queue - Links dump.md` become the first `POST /links` batch; then delete the page (ADR 0002).

## Build order

1. Queue API + SQLite + auth middleware, deployed on Coolify behind Cloudflare Access. *(Capture works via curl from day one.)*
2. iOS Shortcut. *(The iPhone friction — 80% of the problem — is now solved, before any LLM work.)*
3. Dashboard.
4. Triage Agent: `fetch_url` tool → note-writing agent → launchd schedule.
5. Backup job + vault migration finalization.
