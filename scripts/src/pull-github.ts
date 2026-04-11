/**
 * pull-github.ts
 * Download the FULL GitHub repo tree to the local workspace.
 *
 * Use when the workspace is out of sync with GitHub — e.g. after a Replit
 * environment reset, or when a file on GitHub is missing locally.
 *
 * Run: pnpm --filter @workspace/scripts run pull-github
 *
 * Behaviour:
 *   • Downloads every blob from the GitHub main branch tree.
 *   • Creates directories as needed.
 *   • Overwrites local files if they differ from GitHub.
 *   • Skips binary extensions (images, fonts, audio, etc.).
 *   • Never deletes local files that don't exist on GitHub.
 *   • Prints a summary of restored / up-to-date / skipped files.
 */

import { ReplitConnectors } from "@replit/connectors-sdk";
import * as fs from "fs";
import * as path from "path";

const OWNER  = "n4nirmalyapratap";
const REPO   = "indian-stock-market-analyzer";
const BRANCH = "main";
const ROOT   = path.resolve(import.meta.dirname, "../..");

// File extensions to skip when downloading (binary assets)
const SKIP_EXTS = new Set([
  ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico",
  ".woff", ".woff2", ".ttf", ".otf", ".eot",
  ".mp4", ".mp3", ".wav", ".pdf", ".zip",
  ".db",                            // runtime databases
  ".pyc", ".pyo", ".pyd",           // compiled Python
]);

// Directories to never write into locally (they are runtime-generated or ignored)
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
  const ext  = path.extname(ghPath).toLowerCase();
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
  retries = 3,
): Promise<GHResp> {
  let delay = 1000;
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      return await api(c, endpoint);
    } catch (err) {
      const msg = (err as Error).message ?? "";
      if (msg.startsWith("HTTP_429") && attempt < retries) {
        await new Promise(r => setTimeout(r, delay));
        delay = Math.min(delay * 2, 8000);
        continue;
      }
      throw err;
    }
  }
  throw new Error("unreachable");
}

async function downloadBlob(
  c: InstanceType<typeof ReplitConnectors>,
  ghPath: string,
  blobSha: string,
): Promise<"restored" | "up-to-date" | "skipped"> {
  if (shouldSkip(ghPath)) return "skipped";

  const localPath = path.join(ROOT, ghPath);

  // Fetch raw content from GitHub blob endpoint
  const blob = await apiWithRetry(
    c,
    `/repos/${OWNER}/${REPO}/git/blobs/${blobSha}`,
  ) as { content: string; encoding: string };

  if (blob.encoding !== "base64" || !blob.content) return "skipped";

  const content = Buffer.from(blob.content, "base64");
  const text    = content.toString("utf8");

  // Check if local file already matches
  if (fs.existsSync(localPath)) {
    const localText = fs.readFileSync(localPath, "utf8");
    if (localText === text) return "up-to-date";
  }

  // Write (create dirs if needed)
  fs.mkdirSync(path.dirname(localPath), { recursive: true });
  fs.writeFileSync(localPath, text, "utf8");
  return "restored";
}

async function main() {
  console.log(`\n📥  Pulling full GitHub tree → workspace\n`);
  console.log(`    Repo  : ${OWNER}/${REPO}@${BRANCH}`);
  console.log(`    Target: ${ROOT}\n`);

  const connectors = new ReplitConnectors();

  // Get current HEAD
  const refData = await apiWithRetry(
    connectors,
    `/repos/${OWNER}/${REPO}/git/ref/heads/${BRANCH}`,
  ) as { object: { sha: string } };
  const headSha = refData.object.sha;
  console.log(`🔖  GitHub HEAD: ${headSha.slice(0, 7)}\n`);

  // Fetch the full recursive tree
  console.log(`🌲  Fetching repository tree…`);
  const tree = await apiWithRetry(
    connectors,
    `/repos/${OWNER}/${REPO}/git/trees/${headSha}?recursive=1`,
  ) as { tree: { path: string; type: string; sha: string }[] };

  const blobs = tree.tree.filter(e => e.type === "blob");
  console.log(`    ${blobs.length} files in GitHub tree\n`);

  // Download in parallel with concurrency cap
  const CONCURRENCY = 4;
  let restored = 0, upToDate = 0, skipped = 0, errors = 0;
  const restoredFiles: string[] = [];

  const queue = [...blobs];
  let done = 0;

  async function worker() {
    while (queue.length > 0) {
      const entry = queue.shift()!;
      try {
        const result = await downloadBlob(connectors, entry.path, entry.sha);
        if (result === "restored")    { restored++;   restoredFiles.push(entry.path); }
        if (result === "up-to-date")  { upToDate++;  }
        if (result === "skipped")     { skipped++;   }
      } catch (err) {
        console.error(`  ❌  ${entry.path}: ${(err as Error).message?.slice(0, 80)}`);
        errors++;
      }
      done++;
      if (done % 20 === 0) process.stdout.write(`  ${done}/${blobs.length} files…\r`);
    }
  }

  await Promise.all(Array.from({ length: CONCURRENCY }, worker));
  process.stdout.write(`  ${done}/${blobs.length} files processed.  \n\n`);

  // Summary
  console.log(`✅  Pull complete!`);
  console.log(`    Restored   : ${restored} file(s)`);
  console.log(`    Up-to-date : ${upToDate} file(s)`);
  console.log(`    Skipped    : ${skipped} file(s) (binary / generated)`);
  if (errors > 0) console.log(`    Errors     : ${errors} file(s)`);

  if (restoredFiles.length > 0) {
    console.log(`\n📝  Files restored from GitHub:`);
    for (const f of restoredFiles) console.log(`    + ${f}`);
  } else {
    console.log(`\n💡  Workspace is already in sync with GitHub.`);
  }
}

main().catch(err => {
  console.error("\n❌  Pull failed:", (err as Error).message ?? err);
  process.exit(1);
});
