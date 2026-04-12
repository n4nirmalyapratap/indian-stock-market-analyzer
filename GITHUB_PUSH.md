# GitHub Push — How It Works

This project pushes to GitHub using a custom TypeScript script that talks to the
Replit GitHub connector. There is no `git push` involved — no PAT, no SSH key.

---

## Quick Reference

```bash
pnpm --filter @workspace/scripts run push-github
```

Run after every meaningful change. It will print a commit URL on success.

---

## Pulling from GitHub (only when something looks wrong)

**Do not pull before every push.** It is unnecessary and wastes API quota.

Pull only in these situations:

| Situation | What to do |
|---|---|
| Fresh Replit environment / workspace wipe | Run pull to restore missing files |
| Push pre-flight warns a file will be unexpectedly deleted | Run pull to check, then push |
| You know a file was deleted locally by accident | Run pull to get it back |

```bash
cd scripts && node_modules/.bin/tsx ./src/pull-github.ts
```

### How the pull script works (smart — minimal API calls)

1. **ONE** API call to get the current GitHub HEAD SHA.
2. **ONE** API call to fetch the full recursive file tree (paths + SHAs).
3. **Zero API calls** to check which files are present — just reads the local filesystem.
4. Downloads blob content **only for files that are truly missing** locally.
   In a healthy workspace this means 0 extra API calls and instant completion.
5. Never overwrites files that already exist locally — your edits are always safe.

---

## First-Time Setup — Agent Must Trigger the Popup (NOT the user)

When the push script fails with `HTTP_401` or "No connection found", the GitHub
OAuth integration needs to be authorized. **The agent must handle this automatically
by calling `proposeIntegration` in the code_execution sandbox — do NOT ask the user
to navigate the Replit sidebar manually.**

### Correct agent flow (do this, in order):

```javascript
// Step 1 — Search for the GitHub integration
const results = await searchIntegrations("GitHub");
console.log(results);
// Look for either a connector (not_setup) or connection (not_added / added)

// Step 2a — If status is "not_setup" (never authorized):
//   Call proposeIntegration to trigger the OAuth popup for the user automatically.
//   This exits the agent loop and waits for the user to complete the popup.
await proposeIntegration("connector:ccfg_github_<ID>");

// Step 2b — On the next agent loop after the user authorizes:
//   searchIntegrations will now return a connection instead of a connector.
//   Wire it to this project:
await addIntegration("connection:conn_github_<ID>");

// Step 3 — Run the push script
// pnpm --filter @workspace/scripts run push-github
```

### What NOT to do

- Do NOT tell the user to open Tools → Integrations in the sidebar
- Do NOT tell the user to click Connect manually
- Do NOT ask the user to do anything — call proposeIntegration and the popup appears automatically
- Do NOT attempt to use a PAT or SSH key

### What the user sees

When `proposeIntegration` is called, Replit automatically shows a GitHub OAuth
popup in the user's browser. The user just clicks "Authorize Replit" and the
popup closes. That's it — no sidebar navigation required.

---

## How the Script Works

The script (`scripts/src/push-github.ts`) uses the Replit Connectors SDK to
call the GitHub API through Replit's proxy. No token is stored in the code.

Flow:
1. Authenticate via `GET /user` — confirms the connector is authorized
2. Get current GitHub `HEAD` SHA for the branch
3. Walk the entire workspace (respecting `.gitignore` skip rules)
4. Upload all files as Git blobs via `POST /repos/.../git/blobs`
5. Create a **complete new Git tree** from those blobs (no `base_tree`)
6. Create a new commit with that tree
7. Update the branch ref to point to the new commit

### ⚠️ Critical: `base_tree` must NOT be used

The GitHub trees API accepts an optional `base_tree` parameter. **Do not add it.**

If `base_tree` is set, GitHub inherits every file from the previous commit's tree
and only adds/updates the provided entries. This means **deleted files are never
removed from GitHub** — they silently persist across all future commits.

By omitting `base_tree`, the new tree is built exclusively from the files uploaded
in the current run, which exactly mirrors the workspace state including deletions.

---

## Skip Rules

The following are **never pushed** (mirrors `.gitignore`):

| Category | Skipped |
|---|---|
| Directories | `node_modules`, `dist`, `build`, `.git`, `__pycache__`, `.pythonlibs`, `market_cache`, `.agents`, `.local` |
| Files | `pnpm-lock.yaml`, `hydra_prices.db`, `.DS_Store`, `.tsbuildinfo` |
| Extensions | `.png`, `.jpg`, `.gif`, `.webp`, `.ico`, `.woff`, `.ttf`, `.mp4`, `.pdf`, `.zip` |
| Size | Files larger than 400 KB are skipped with a warning |

### 🛡️ Hard-coded protected files — NEVER deletable

The following file types trigger an **immediate push abort** if they are missing
from the workspace (detected by `isProtected()` in `push-github.ts`):

| Protected pattern | Why |
|---|---|
| `Dockerfile` (any path) | Required for Docker builds in every artifact |
| `docker-compose.yml` | Orchestrates the multi-container production stack |
| `nginx.conf` (any path) | Reverse proxy config served inside the Docker image |
| `.dockerignore` | Controls what goes into the Docker build context |

If the push prints `🚨 PUSH ABORTED — PROTECTED FILES MISSING FROM WORKSPACE`,
run `restore-files` and re-push. The `restore-files` script automatically
includes all these files in its recovery list.

**Never remove `Dockerfile`, `nginx.conf`, or `docker-compose.yml` from the
workspace before pushing. The push script will refuse and tell you exactly
which files to restore.**

---

### ⚠️ pandas_ta must NOT be in SKIP_DIRS

`artifacts/python-backend/pandas_ta/` is a local package shim that must be in the
GitHub repo so Docker builds can include it via `COPY . .`.

It was incorrectly added to `SKIP_DIRS` in April 2026 (labelled "Vendored shim — not real source").
This caused three Docker build failures because cloned repos had no `pandas_ta/` shim, and
Python threw `ModuleNotFoundError: No module named 'pandas_ta'` at container startup.

**Never add `"pandas_ta"` back to `SKIP_DIRS` in `push-github.ts`.**

---

## Rate Limiting & Retries

- The script uploads blobs with 4 concurrent workers to stay under GitHub's
  rate limit (Replit proxy allows ~10 requests/second).
- On HTTP 429 (rate limited), the script automatically retries up to 4 times
  with exponential back-off (1s → 2s → 4s → 8s).
- If the push times out or fails partway through, just run it again — blob
  uploads are idempotent.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `HTTP_401: Bad credentials` or `No connection found` | GitHub not authorized for this workspace | Agent calls `searchIntegrations("GitHub")` then `proposeIntegration(connectorId)` — popup appears automatically |
| `HTTP_404: Not Found` | Wrong owner/repo in the script | Check `OWNER`, `REPO`, `BRANCH` constants in `scripts/src/push-github.ts` |
| `HTTP_429: rate limit` | Too many requests | Script retries automatically; wait and retry if it still fails |
| `Cannot find module '@replit/connectors-sdk'` | pnpm packages not installed | Run `pnpm install` first |
| Push hangs with no output | Network issue in Replit | Restart the shell and try again |
| `non-JSON response` | GitHub API error or proxy issue | Wait 30 seconds and retry |

---

## Configuration

Edit these three constants at the top of `scripts/src/push-github.ts` if the
repository changes:

```typescript
const OWNER  = "n4nirmalyapratap";
const REPO   = "indian-stock-market-analyzer";
const BRANCH = "main";
```
