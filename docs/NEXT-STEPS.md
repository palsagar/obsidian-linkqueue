# Next steps — server-side Triage cutover (ADR 0005)

Hard cutover, in this order. Rollback at any point: `launchctl load ~/Library/LaunchAgents/com.linkqueue.triage.plist` on the laptop (the installed plists stay there until step 6).

## 1. Retire the laptop jobs first

No overlap window — captures keep queueing durably while nothing processes them.

```bash
launchctl unload ~/Library/LaunchAgents/com.linkqueue.triage.plist
launchctl unload ~/Library/LaunchAgents/com.linkqueue.backup.plist
```

## 2. Have the E2EE passphrase in hand

`ob sync-setup` will ask for the remote vault's end-to-end encryption password. Dig it up **before** starting the bootstrap.

## 3. Create the triage app in Coolify

- Same project as the queue app, build from `Dockerfile.triage`.
- Persistent volume mounted at `/data`.
- Env vars: `OPENROUTER_API_KEY`, `QUEUE_URL`, `CF_ACCESS_CLIENT_ID`, `CF_ACCESS_CLIENT_SECRET` (the existing service token works). `VAULT_PATH=/data/vault` and `TZ=Europe/Paris` are image defaults.
- No domain/ports needed — it makes only outbound calls.
- Deploy. supercronic starts on schedule; runs will fail until the bootstrap below, which is fine (Links just stay pending).

## 4. One-time bootstrap (`docker exec -it <triage-container> bash`)

Everything lands under `/data` (the container's `HOME`), so it survives redeploys.

```bash
# a) Obsidian Sync: interactive login (email/password/2FA — token persisted, password not stored)
ob login
ob sync-list-remote                       # find the vault name
ob sync-setup --vault "<name>" --path /data/vault   # prompts for the E2EE passphrase
ob sync --path /data/vault                # first full pull — verify it completes

# b) git backup: reuse the existing backup repo's history
mkdir -p /data/.ssh && chmod 700 /data/.ssh   # ssh-keygen won't create the dir itself
ssh-keygen -t ed25519 -f /data/.ssh/id_ed25519 -N ""
cat /data/.ssh/id_ed25519.pub             # → add as a write-access deploy key on the backup repo
ssh-keyscan github.com >> /data/.ssh/known_hosts   # verify the printed key against GitHub's published fingerprints (docs.github.com → "GitHub's SSH key fingerprints") before trusting it
git config --global user.name "vault-backup"
git config --global user.email "vault-backup@localhost"
# ssh resolves ~ from /etc/passwd (/root), not $HOME=/data — pin key + known_hosts by absolute path
SSHCMD="ssh -i /data/.ssh/id_ed25519 -o IdentitiesOnly=yes -o UserKnownHostsFile=/data/.ssh/known_hosts"
GIT_SSH_COMMAND="$SSHCMD" git clone --no-checkout git@github.com:<you>/<backup-repo>.git /tmp/bk
mv /tmp/bk/.git /data/vault/.git          # existing vault files become the working tree
git -C /data/vault config core.sshCommand "$SSHCMD"   # scheduled backups use the same pinned key
git -C /data/vault reset -q               # --no-checkout leaves an empty index; rebuild it from HEAD
git -C /data/vault checkout -- .gitignore # root dotfiles don't sync; restore the repo's ignore rules
```

(Obsidian Sync ignores dot-directories, so `.git` inside the vault never syncs to devices.)

## 5. Verify end-to-end

1. Queue a link from the iPhone Shortcut.
2. In the container: `cd /srv && uv run --no-dev obs_triage run --sync` — watch it claim, triage, push.
3. The note appears on the iPhone via Obsidian Sync; the dashboard shows the run heartbeat.
4. `uv run --no-dev obs_triage backup` — confirm the backup repo gets a commit.
5. Leave it alone for a day; check the dashboard heartbeat advances on schedule.

## 6. Laptop cleanup (after a few clean days)

```bash
rm ~/Library/LaunchAgents/com.linkqueue.triage.plist ~/Library/LaunchAgents/com.linkqueue.backup.plist
```

Optional: remove `~/Obsidian/vault/.git` on the laptop — the backup now runs from the server copy, and a second git actor is exactly what ADR 0001/0005 retired. The laptop is now a plain Obsidian device.
