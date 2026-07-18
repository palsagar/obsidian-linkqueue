# Next steps — things only you can do

Automated migration is done: vaults snapshotted, git settled and pushed, vault copies reconciled, obsidian-git plugin and artifacts removed. What remains needs you in the Obsidian/Cloudflare/Coolify UIs.

## 1. Move the vault out of iCloud and pair Obsidian Sync (this Mac)

"Desktop & Documents in iCloud" is ON, so `~/Documents` is iCloud-synced across your Macs (ADR 0003). The vault must leave it.

1. Quit Obsidian on **all** devices.
2. Move the vault: `mkdir -p ~/Obsidian && mv ~/Documents/"Obsidian Vault" ~/Obsidian/vault`
3. Open Obsidian → remove the old vault from the vault switcher → "Open folder as vault" → `~/Obsidian/vault`.
4. Settings → Sync → log in → **create a new remote vault** (delete the old remote `sagar's vault` in the same screen if it exists — check what it was connected to while you're there). Enable "Sync all other types" so images sync too.

## 2. Reconnect the iPhone

Remove/disconnect the existing vault in Obsidian mobile, then connect to the new remote vault fresh. From now on the iPhone only reads/edits via Obsidian Sync — no queue page.

## 3. Reconnect laptop 2

Laptop 2's `~/Documents` mirrors this Mac's via iCloud, so the vault's disappearance from Documents will propagate there — expected. On laptop 2: remove old vault entries from Obsidian, create `~/Obsidian/`, and connect to the remote vault into `~/Obsidian/vault`. Never open a vault from `~/Documents` again. Also check which vault laptop 2's Obsidian was opening — that's almost certainly the writer behind `sagar's vault`.

## 4. Verify, then archive vault 2

Edit a test note on each device and watch it propagate. Once verified: `mv ~/Documents/"sagar's vault" ~/Documents/vault-snapshots-2026-07-18/sagars-vault-retired`. Snapshots of both vaults already exist in `~/Documents/vault-snapshots-2026-07-18/`.

## 5. Cloudflare Zero Trust

1. Zero Trust dashboard → Access → Applications → add a self-hosted app for `queue.<your-domain>`.
2. Policy: allow your email (SSO / email OTP).
3. Access → Service Auth → create a **service token** ("linkqueue-clients"); save the Client ID/Secret.
4. Add a policy allowing that service token on the application.
5. Note the **team domain** (`<team>.cloudflareaccess.com`) and the app's **Audience (AUD) tag** → these become `CF_TEAM_DOMAIN` / `CF_POLICY_AUD`.

## 6. Deploy on Coolify

Push this repo to GitHub (ask Claude to commit first), create the app in Coolify from it (Dockerfile build), attach a volume at `/data`, set the env vars from the README, point the domain, deploy.

## 7. iOS Shortcut

Build "Queue it" per the README recipe with the service-token headers. Add to share sheet. Test from X/Safari/YouTube.

## 8. Drain the old queue page

Once the API is live: the links still in `Processing Queue - Links dump.md` get POSTed to `/links` (Claude can script this), then the page is deleted from the vault. The page also contains stray pasted notes (Coolify migration steps, an rsync command, a slash-command prompt) — copy anything you still want into a real note first.

## 9. Then: build the Triage Agent

Next project phase (see ARCHITECTURE.md §5): Python worker, Pydantic AI over OpenRouter, `fetch_url` tool, launchd schedule, plus the nightly one-way git backup job from `~/Obsidian/vault`.
