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

## First-Time Setup — Authorization Required

The very first time you run the push script in a new Replit workspace, GitHub
OAuth authorization is required. The agent cannot do this for you — it needs a
human to click the popup.

### Step-by-step

1. In the Replit sidebar, open **Tools → Integrations** (or click the plug icon).
2. Find **GitHub** in the integrations list and click **Connect**.
3. A GitHub OAuth popup will open in your browser.
4. Sign in to GitHub (if not already signed in) and click **Authorize Replit**.
5. The popup closes. The integration status changes to **Connected**.
6. Now run the push script — it will work without any further auth.

> **Important:** Tell the agent "I have authorized GitHub" once you complete
> step 4-5. The agent will then run the push script for you.

### What the agent should say to prompt authorization

When setting up a fresh workspace, the agent should pause and say:

> "Before I can push to GitHub, I need you to authorize the GitHub integration.
> Please open **Tools → Integrations** in the Replit sidebar, find GitHub,
> click Connect, and complete the OAuth popup. Let me know when it's done."

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
| `HTTP_401: Bad credentials` | GitHub not authorized | Complete the OAuth flow (see First-Time Setup above) |
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
