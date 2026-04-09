# GitHub Push — How It Works & What to Avoid

## How to push

```bash
pnpm --filter @workspace/scripts run push-github
```

If it times out, run the same command again immediately — it will finish in seconds.
See [Why it sometimes needs two runs](#why-it-sometimes-needs-two-runs) below.

---

## How the script works

The project uses a custom push script (`scripts/src/push-github.ts`) instead of regular
`git push`, because Replit's environment cannot authenticate with GitHub via SSH or PAT —
it uses a Replit OAuth proxy instead.

The script:
1. Walks the **entire workspace** from the root
2. Skips any file or directory listed in `.gitignore` (see skip rules below)
3. Uploads each remaining file to GitHub as an individual API blob
4. Assembles all blobs into a single tree → commit → updates the branch ref

> `.gitignore` is the **single source of truth** for what gets excluded.  
> The `SKIP_DIRS` / `SKIP_FILES` / `SKIP_EXTS` constants inside the script
> mirror `.gitignore` exactly — if you add something to `.gitignore`, add it
> to the matching constant in the script too.

---

## Why it sometimes needs two runs

Each file requires a separate HTTPS round-trip to the GitHub API (~0.4–0.6 s per file).
With ~166 source files that takes **70–100 seconds** total — longer than the default
60-second shell timeout used by the Replit agent.

The script is **idempotent**: blobs already uploaded are cached by GitHub (content-addressed),
so the second run only uploads the remaining files and finishes in **10–20 seconds**.

The GitHub commit is only created once **all** blobs are uploaded, so a timed-out first
run never creates a broken or partial commit on GitHub.

---

## What to avoid

### Never add these to INCLUDE_PATHS (there is no whitelist now)

The old script used a hand-maintained `INCLUDE_PATHS` whitelist. That is gone.
The script now walks from root and skips via `.gitignore` rules. **No whitelist to maintain.**

### Keep the file count low

The more source files synced, the longer each push takes.

| Do NOT add to source | Why |
|---|---|
| `node_modules/` | Hundreds of MB, already in `.gitignore` |
| `dist/` / `build/` | Generated — rebuild from source |
| `.pythonlibs/` | Replit's pip cache, not source |
| `market_cache/` | Runtime data written by the app |
| `artifacts/python-backend/pandas_ta/` | Vendored shim, not real source |
| Large static assets (images, fonts) | Host on CDN; script skips >400 KB anyway |

Keeping the count under **~100 files** makes the push reliably finish in one run.

### Keep `.gitignore` and the script in sync

If you add a new large/generated directory, add it to **both**:

1. `.gitignore` (so local git and editors also ignore it)
2. `SKIP_DIRS` in `scripts/src/push-github.ts` (so the push script ignores it)

---

## Current file count & timings

| Metric | Value |
|---|---|
| Source files synced | ~320 |
| Parallel workers | 4 (stays ≤ 8 RPS, under the 10 RPS proxy limit) |
| Typical run time | 40–50 s (completes in **one run**) |
| Blob upload rate | ~0.4–0.6 s / file sequential; ÷4 with parallelism |
| 429 rate-limit handling | Automatic exponential backoff + retry (up to 4×) |

---

## Adding a new source directory

Just create your directory and files. The next push will pick them up automatically
as long as the directory isn't listed in `.gitignore` or `SKIP_DIRS`.

You **do not** need to update any whitelist.
