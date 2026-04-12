/**
 * pull-github.ts
 * Restores files that are MISSING from the workspace by fetching them from GitHub.
 *
 * Use only when you suspect the workspace is incomplete — e.g. after a Replit
 * environment reset, or when the push pre-flight warns about unexpected deletions.
 * Do NOT run before every push; it is unnecessary in a healthy workspace.
 *
 * Run: cd scripts && node_modules/.bin/tsx ./src/pull-github.ts
 *
 * How it works (smart / minimal API calls):
 *   1. ONE call to get the current HEAD SHA.
 *   2. ONE call to fetch the full recursive file tree (paths + SHAs).
 *   3. Check each path against the LOCAL filesystem — zero API calls for
 *      files that already exist locally.
 *   4. Only fetch blob content for files that are TRULY MISSING locally.
 *      In a healthy workspace this is 0 extra API calls.
 *   5. Never overwrites files that already exist — local edits are safe.
 *   6. Never deletes local files that aren't on GitHub.
 */

import { ReplitConnectors } from "@replit/connectors-sdk";
import * as fs from "fs";
import * as path from "path";

const OWNER  = "n4nirmalyapratap";
const REPO   = "indian-stock-market-analyzer";
const BRANCH = "main";
const ROOT   = path.resolve(import.meta.dirname, "../..");

// Binary / generated extensions — skip downloading these
const SKIP_EXTS = new Set([
  ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico",
  ".woff", ".woff2", ".ttf", ".otf", ".eot",
  ".mp4", ".mp3", ".wav", ".pdf", ".zip",
  ".db", ".pyc", ".pyo", ".pyd",
]);

// Directory prefixes to never write into locally
const SKIP_DIRS_PREFIX = [
  "node_modules/",
  "__pycache__/",
  ".git/",
  ".local/",
  "market_cache/",
  ".expo/",
  ".pnpm-store/",
];

function shouldSkip(ghPath: string): boolean {
  const ext = path.extname(ghPath).toLowerCase();
  if (SKIP_EXTS.has(ext)) return true;
  if (SKIP_DIRS_PREFIX.some(d => ghPath.startsWith(d) || ghPath.includes("/" + d))) return true;
  return false;
}

type GHResp = Record<string, unknown>;

async function api(
  c: InstanceType<typeof ReplitConnectors>,
  endpoint: string,
): Promise<GHResp> {
  const resp = await c.proxy("github", endpoint, { method: "GET" });
  const text = await resp.text() as string;
  let json: GHResp;
  try {
    json = JSON.parse(text) as GHResp;
  } catch {
    throw new Error(`GitHub API GET ${endpoint} returned non-JSON (HTTP ${resp.status}): ${text.slice(0, 200)}`);
  }
  if (resp.status >= 400) {
    throw new Error(`HTTP_${resp.status}: ${(json.message as string) ?? text.slice(0, 200)}`);
  }
  return json;
}

/** api() with retry on 429 rate limit */
async function apiWithRetry(
  c: InstanceType<typeof ReplitConnectors>,
  endpoint: string,
  retries = 4,
): Promise<GHResp> {
  let delay = 1000;
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      return await api(c, endpoint);
    } catch (err) {
      const msg = (err as Error).message ?? "";
      if ((msg.startsWith("HTTP_429") || msg.startsWith("HTTP_403")) && attempt < retries) {
        console.warn(`  ⏳  Rate limited — retrying in ${delay / 1000}s…`);
        await new Promise(r => setTimeout(r, delay));
        delay = Math.min(delay * 2, 16000);
        continue;
      }
      throw err;
    }
  }
  throw new Error("unreachable");
}

async function fetchMissingBlob(
  c: InstanceType<typeof ReplitConnectors>,
  ghPath: string,
  blobSha: string,
): Promise<void> {
  const blob = await apiWithRetry(
    c,
    `/repos/${OWNER}/${REPO}/git/blobs/${blobSha}`,
  ) as { content: string; encoding: string };

  if (blob.encoding !== "base64" || !blob.content) return;

  const localPath = path.join(ROOT, ghPath);
  const content   = Buffer.from(blob.content, "base64");
  fs.mkdirSync(path.dirname(localPath), { recursive: true });
  fs.writeFileSync(localPath, content);
}

async function main() {
  console.log(`\n📥  Checking workspace against GitHub…\n`);
  console.log(`    Repo  : ${OWNER}/${REPO}@${BRANCH}`);
  console.log(`    Target: ${ROOT}\n`);

  const connectors = new ReplitConnectors();

  // ── Step 1: one API call for HEAD SHA ─────────────────────────────────────
  const refData = await apiWithRetry(
    connectors,
    `/repos/${OWNER}/${REPO}/git/ref/heads/${BRANCH}`,
  ) as { object: { sha: string } };
  const headSha = refData.object.sha;
  console.log(`🔖  GitHub HEAD : ${headSha.slice(0, 7)}`);

  // ── Step 2: one API call for full recursive tree ───────────────────────────
  console.log(`🌲  Fetching repository tree…`);
  const treeResp = await apiWithRetry(
    connectors,
    `/repos/${OWNER}/${REPO}/git/trees/${headSha}?recursive=1`,
  ) as { tree: { path: string; type: string; sha: string }[]; truncated?: boolean };

  const blobs = treeResp.tree.filter(e => e.type === "blob");
  console.log(`    ${blobs.length} files in GitHub tree\n`);

  if (treeResp.truncated) {
    console.warn(`⚠️   Tree was truncated by GitHub — some files may not appear above.\n`);
  }

  // ── Step 3: local existence check (zero API calls) ─────────────────────────
  const missing: { path: string; sha: string }[] = [];
  let skipped = 0;
  let present = 0;

  for (const entry of blobs) {
    if (shouldSkip(entry.path)) { skipped++; continue; }
    const localPath = path.join(ROOT, entry.path);
    if (fs.existsSync(localPath)) { present++; }
    else { missing.push({ path: entry.path, sha: entry.sha }); }
  }

  console.log(`    ${present} files already present locally`);
  console.log(`    ${skipped} files skipped (binary / generated)`);
  console.log(`    ${missing.length} files MISSING — will restore\n`);

  if (missing.length === 0) {
    console.log(`✅  Workspace is complete — nothing to restore.`);
    return;
  }

  // ── Step 4: fetch blobs only for missing files ─────────────────────────────
  console.log(`📦  Restoring ${missing.length} missing file(s)…\n`);

  const CONCURRENCY = 4;
  let restored = 0;
  let errors   = 0;
  const restoredFiles: string[] = [];

  const queue = [...missing];

  async function worker() {
    while (queue.length > 0) {
      const entry = queue.shift()!;
      try {
        await fetchMissingBlob(connectors, entry.path, entry.sha);
        restored++;
        restoredFiles.push(entry.path);
        console.log(`    ✔ ${entry.path}`);
      } catch (err) {
        console.error(`    ✘ ${entry.path}: ${(err as Error).message?.slice(0, 100)}`);
        errors++;
      }
    }
  }

  await Promise.all(Array.from({ length: CONCURRENCY }, worker));

  console.log(`\n✅  Done!`);
  console.log(`    Restored : ${restored} file(s)`);
  if (errors > 0) console.log(`    Errors   : ${errors} file(s) — check output above`);
}

main().catch(err => {
  console.error("\n❌  Pull failed:", (err as Error).message ?? err);
  process.exit(1);
});
