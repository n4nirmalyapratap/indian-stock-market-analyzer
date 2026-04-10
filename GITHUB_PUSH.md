# GitHub Push — How It Works

This project pushes to GitHub using a custom TypeScript script that talks to the
Replit GitHub connector. There is no `git push` involved — no PAT, no SSH key.

---

## Quick Reference

```bash
pnpm --filter @workspace/scripts run push-github
```

Run this after every meaningful change. It will print a commit URL on success.

---

## 🚨 CRITICAL: Every Push is a Full Workspace Sync

**This is the most important thing to understand before running a push.**

The push script creates a **completely fresh Git tree** from the files currently
in the Replit workspace. There is no incremental diff. This means:

> **Any file that exists on GitHub but is NOT present in the Replit workspace
> will be permanently deleted from GitHub when you push.**

### Why this design exists

The script intentionally omits `base_tree` (see technical section below). Using
`base_tree` would cause the opposite problem: files deleted from the workspace
would silently persist on GitHub forever. Both choices have a trade-off. We
chose "workspace is the source of truth" — but that means the workspace must
always contain ALL files you want on GitHub.

### How to prevent accidental deletions (agent checklist)

Before running a push for the first time on a new Replit workspace, the agent MUST:

1. **Check what is currently on GitHub** — fetch the repo tree:
   ```
   GET /repos/{owner}/{repo}/git/trees/HEAD?recursive=1
   ```
2. **Compare to the workspace** — identify any file on GitHub that is not in
   the local workspace. The push script now prints this list automatically (see
   "Pre-flight deletion report" below).
3. **Restore any missing files** before pushing:
   ```bash
   pnpm --filter @workspace/scripts run restore-files
   ```
   Or copy the specific files manually using the GitHub contents API.
4. Only then run the push.

### What happened on 2026-04-10 (post-mortem)

When this project was set up in Replit, only the `artifacts/` directories were
copied from the original GitHub repo. Root-level files like `docker-compose.yml`,
`README.md`, `SETUP.md`, `deploy.sh`, `.dockerignore`, `.env.example`,
`GITHUB_PUSH.md`, and `scripts/setup-git-hook.sh` were never brought into the
workspace. The first push then deleted all of them from GitHub because they did
not exist locally. They were recovered using the `restore-files` script.

**Rule: always run `restore-files` before the very first push on any fresh workspace.**

---

## Pre-flight Deletion Report (built into the push script)

The push script now automatically fetches the current GitHub file list before
pushing and prints every file that **will be deleted** from GitHub as a result
of the push. Look for this block in the output:

```
⚠️  Files on GitHub that WILL BE DELETED by this push (not in workspace):
     deploy.sh
     docker-compose.yml
     README.md
```

If you see unexpected files in that list, **stop** — do not proceed. Instead:
1. Fetch those files back from the previous GitHub commit using the GitHub
   contents API or the `restore-files` script.
2. Re-run the push once the workspace contains those files.

---

## Restore Script

If files were accidentally deleted by a push, run:

```bash
pnpm --filter @workspace/scripts run restore-files
```

`scripts/src/restore-files.ts` is pre-configured with the list of root-level
project files that should always exist. After restoring, re-run the push.

To recover a specific file from a specific commit SHA, edit the `REF` constant
in `restore-files.ts` to point to the commit before the deletion.

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
3. **Fetch the full file tree from GitHub HEAD** — builds deletion report
4. Walk the entire workspace (respecting skip rules)
5. **Print any files that will be deleted** (on GitHub but not in workspace)
6. Upload all files as Git blobs via `POST /repos/.../git/blobs`
7. Create a **complete new Git tree** from those blobs (no `base_tree`)
8. Create a new commit with that tree
9. Update the branch ref to point to the new commit

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
| Files deleted from GitHub after push | Workspace was missing files | Run `restore-files` script, then push again |

---

## Configuration

Edit these three constants at the top of `scripts/src/push-github.ts` if the
repository changes:

```typescript
const OWNER  = "n4nirmalyapratap";
const REPO   = "indian-stock-market-analyzer";
const BRANCH = "main";
```
