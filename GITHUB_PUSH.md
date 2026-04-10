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
5. Create a new Git tree from those blobs
6. Create a new commit with that tree
7. Update the branch ref to point to the new commit

---

## Skip Rules

The following are **never pushed** (mirrors `.gitignore`):

| Category | Skipped |
|---|---|
| Directories | `node_modules`, `dist`, `build`, `.git`, `__pycache__`, `.pythonlibs`, `market_cache`, `.agents`, `.local` |
| Files | `pnpm-lock.yaml`, `hydra_prices.db`, `.DS_Store`, `.tsbuildinfo` |
| Extensions | `.png`, `.jpg`, `.gif`, `.webp`, `.ico`, `.woff`, `.ttf`, `.mp4`, `.pdf`, `.zip` |
| Size | Files larger than 400 KB are skipped with a warning |

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
