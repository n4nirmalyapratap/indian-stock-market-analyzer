# GitHub Push — How It Works

This project pushes to GitHub using a custom TypeScript script
(`scripts/src/push-github.ts`). There is no `git push` involved.

The script supports **two auth methods**, tried in order:

| Priority | Method | How it works |
|---|---|---|
| **1 — Primary** | Personal Access Token (`GITHUB_PAT` secret) | Direct GitHub API via `fetch()` — fast, reliable, no OAuth dependency |
| **2 — Fallback** | Replit GitHub OAuth connector | Replit proxy via `ReplitConnectors` — used automatically if no PAT is set |

---

## Quick Reference

```bash
pnpm --filter @workspace/scripts run push-github
```

Run after every meaningful change. It prints a commit URL on success.

---

## Primary Method — Personal Access Token (PAT)

### Setup (one time)

1. Go to `https://github.com/settings/tokens` on the **`n4nirmalyapratap`** account
2. Click **Generate new token (classic)**
3. Give it a name (e.g. `replit-push`) and tick the **`repo`** scope
4. Copy the token
5. In Replit → open the **Secrets** panel → add key `GITHUB_PAT`, paste the token

The push script reads `process.env.GITHUB_PAT` automatically. No code changes needed.

### Why PAT is preferred

- Always authenticates as the repo owner — no permission mismatch possible
- Direct HTTPS to `api.github.com` — no Replit proxy layer
- Token is stored securely in Replit Secrets and never appears in code
- Works even if the Replit GitHub OAuth connector is connected to a different account

---

## Fallback Method — Replit GitHub OAuth Connector

Used automatically when `GITHUB_PAT` is **not set**. The script will print a
warning and continue via the OAuth connector.

### ⚠️ Permission check built in

Before uploading anything, the script calls `GET /repos/{owner}/{repo}` and
checks `permissions.push`. If the connected OAuth account does **not** have
push access (e.g. it belongs to a different GitHub user than the repo owner),
the push **aborts immediately** with a clear error message rather than
failing silently with cryptic 404 errors on blob upload.

### Setting up the OAuth connector (agent flow)

When the push script fails with `HTTP_401` or "No connection found", the
OAuth integration needs to be authorized. The agent handles this automatically:

```javascript
// Step 1 — Find the GitHub integration
const results = await searchIntegrations("GitHub");
// Look for connector (not_setup) or connection (not_added / added)

// Step 2a — Never authorized before (status: not_setup):
await proposeIntegration("connector:ccfg_github_<ID>");
// Exits the agent loop; user completes the OAuth popup

// Step 2b — On next agent loop after user authorizes:
await addIntegration("connection:conn_github_<ID>");

// Step 3 — Re-run the push
// pnpm --filter @workspace/scripts run push-github
```

**What the user sees:** A GitHub OAuth popup appears automatically in the
browser. The user clicks "Authorize Replit" and it closes. No sidebar
navigation required.

### Common OAuth pitfall — wrong GitHub account

If `proposeIntegration` connects a GitHub account that is **not** the repo
owner and is **not** a collaborator with write access, the script will
detect this and print:

```
❌  OAuth account "other-user" does not have push access to n4nirmalyapratap/...
    Fix options:
    1. (Recommended) Set the GITHUB_PAT secret to a token from "n4nirmalyapratap".
    2. Or add "other-user" as a collaborator with Write access on GitHub.
```

The recommended fix is always to set `GITHUB_PAT` (primary method).

---

## How the Script Works

Flow (same for both auth methods):

1. Authenticate via `GET /user` — confirms credentials are valid
2. *(OAuth only)* Check `permissions.push` on the repo — abort if no write access
3. Get current GitHub `HEAD` SHA for the branch
4. Walk the entire workspace (respecting skip rules below)
5. Pre-flight: compare workspace files vs GitHub tree — warn about deletions
6. Upload all files as Git blobs via `POST /repos/.../git/blobs`
7. Create a **complete new Git tree** from those blobs (no `base_tree`)
8. Create a new commit with that tree
9. Update the branch ref to point to the new commit

### ⚠️ Critical: `base_tree` must NOT be used

The GitHub trees API accepts an optional `base_tree` parameter. **Do not add it.**

With `base_tree`, GitHub inherits every file from the previous commit so
**deleted files silently persist** across all future commits.

Without `base_tree`, the new tree is built exclusively from uploaded files,
which exactly mirrors the workspace state including deletions.

---

## Pulling from GitHub (only when something looks wrong)

**Do not pull before every push.** It is unnecessary and wastes API quota.

Pull only in these situations:

| Situation | What to do |
|---|---|
| Fresh Replit environment / workspace wipe | Run pull to restore missing files |
| Push pre-flight warns a file will be unexpectedly deleted | Run pull to check, then push |
| A file was deleted locally by accident | Run pull to get it back |

```bash
pnpm --filter @workspace/scripts run restore-files
```

---

## Skip Rules

The following are **never pushed** (mirrors `.gitignore`):

| Category | Skipped |
|---|---|
| Directories | `node_modules`, `dist`, `build`, `.git`, `__pycache__`, `.pythonlibs`, `market_cache`, `.agents`, `.local` |
| Files | `pnpm-lock.yaml`, `hydra_prices.db`, `.DS_Store`, `.tsbuildinfo` |
| Extensions | `.png`, `.jpg`, `.gif`, `.webp`, `.ico`, `.woff`, `.ttf`, `.mp4`, `.pdf`, `.zip` |
| Size | Files larger than 400 KB are skipped with a warning |

### 🛡️ Protected files — NEVER deletable

These trigger an **immediate push abort** if missing from the workspace:

| Protected pattern | Why |
|---|---|
| `Dockerfile` (any path) | Required for Docker builds in every artifact |
| `docker-compose.yml` | Orchestrates the multi-container production stack |
| `nginx.conf` (any path) | Reverse proxy config served inside the Docker image |
| `.dockerignore` | Controls what goes into the Docker build context |

If the push prints `🚨 PUSH ABORTED — PROTECTED FILES MISSING FROM WORKSPACE`,
run `restore-files` then re-push.

### ⚠️ pandas_ta must NOT be in SKIP_DIRS

`artifacts/python-backend/pandas_ta/` is a local package shim that must be
in the repo so Docker builds include it. Never add `"pandas_ta"` to `SKIP_DIRS`.

---

## Rate Limiting & Retries

- Blobs are uploaded with **2 concurrent workers** and a **500 ms delay** per
  blob (≈ 4 req/s) — well under GitHub's secondary rate limit.
- On HTTP 429 or 403 (rate limited), the script retries up to 4 times with
  exponential back-off (1 s → 2 s → 4 s → 8 s → 16 s).
- If the push fails partway through, re-run — blob uploads are idempotent.
- If you hit the secondary rate limit, wait **2 minutes** before retrying.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `🔑 Auth method: Personal Access Token` then success | PAT working correctly | Nothing to do |
| `⚠️ GITHUB_PAT secret not set` | PAT missing, using OAuth fallback | Add `GITHUB_PAT` to Replit Secrets |
| `❌ OAuth account "X" does not have push access` | Wrong GitHub account connected | Set `GITHUB_PAT` from the `n4nirmalyapratap` account |
| `HTTP_401: Bad credentials` | PAT expired or invalid | Regenerate token at github.com/settings/tokens and update the secret |
| `HTTP_401` or `No connection found` (OAuth) | OAuth not authorized | Agent calls `searchIntegrations("GitHub")` then `proposeIntegration(id)` |
| `HTTP_403: secondary rate limit` | Uploading too fast | Script retries automatically; wait 2 min if it persists |
| `HTTP_404: Not Found` | Wrong owner/repo constant | Check `OWNER`, `REPO`, `BRANCH` at top of `push-github.ts` |
| `Cannot find module '@replit/connectors-sdk'` | Packages not installed | Run `pnpm install` first |
| Push hangs with no output | Network issue | Restart the shell and try again |

---

## Configuration

Edit these constants at the top of `scripts/src/push-github.ts` if the
repository changes:

```typescript
const OWNER  = "n4nirmalyapratap";
const REPO   = "indian-stock-market-analyzer";
const BRANCH = "main";
```
