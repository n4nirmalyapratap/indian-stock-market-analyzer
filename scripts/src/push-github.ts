/**
 * push-github.ts
 * Push source changes to GitHub using the Replit GitHub connector.
 * No PAT needed — uses Replit OAuth (repo permissions).
 *
 * Run: pnpm --filter @workspace/scripts run push-github
 *
 * Strategy: walk the ENTIRE workspace root and skip anything that matches
 * the patterns in .gitignore (maintained in SKIP_DIRS, SKIP_FILES, SKIP_EXTS
 * below — keep these in sync with /.gitignore so there is one source of truth).
 *
 * See GITHUB_PUSH.md for timeout behaviour and retry notes.
 */

import { ReplitConnectors } from "@replit/connectors-sdk";
import { execSync } from "child_process";
import * as fs from "fs";
import * as path from "path";

const OWNER  = "n4nirmalyapratap";
const REPO   = "indian-stock-market-analyzer";
const BRANCH = "main";
const ROOT   = path.resolve(import.meta.dirname, "../..");

// ── Skip rules — mirror /.gitignore exactly so there is one source of truth ──
//
// SKIP_DIRS   : directory names that are never descended into
// SKIP_FILES  : exact filenames that are skipped wherever they appear
// SKIP_EXTS   : file extensions that are always skipped
// MAX_FILE_BYTES : hard cap — files larger than this are skipped with a warning

const SKIP_DIRS = new Set([
  // Git internal objects — never push these
  ".git",
  // JS / TS tooling
  "node_modules", "dist", "build", "tmp", "out-tsc", ".cache",
  // Python tooling / venvs
  "__pycache__", ".pythonlibs", ".pnpm-store", ".upm", ".venv",
  "venv", "env", ".tox", ".eggs",
  // Replit platform
  ".agents", ".local", ".replit-artifact",
  // App-generated data
  "market_cache",
  // Expo / React Native
  ".expo", ".expo-shared",
  // Misc
  ".idea", ".vscode", "coverage", "typings",
]);

const SKIP_FILES = new Set([
  // Lock files — generated, not human-maintained
  "pnpm-lock.yaml", "uv.lock", "package-lock.json", "yarn.lock",
  // Databases written at runtime
  "hydra_prices.db",
  // System
  ".DS_Store", "Thumbs.db",
  // Large build artefacts
  ".tsbuildinfo",
]);

// Also skip any file whose name ends in these suffixes (gitignore glob patterns)
const SKIP_NAME_SUFFIXES = [".pyc", ".pyo", ".pyd", ".egg-info", ".db"];

const SKIP_EXTS = new Set([
  // Binary assets — host on a CDN instead
  ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico",
  ".woff", ".woff2", ".ttf", ".otf", ".eot",
  ".mp4", ".mp3", ".wav", ".pdf", ".zip",
]);

const MAX_FILE_BYTES = 400 * 1024; // 400 KB hard cap (GitHub API proxy limit)

// ── File walker ───────────────────────────────────────────────────────────────

function shouldSkipFile(name: string): boolean {
  if (SKIP_FILES.has(name)) return true;
  const ext = path.extname(name).toLowerCase();
  if (SKIP_EXTS.has(ext)) return true;
  if (SKIP_NAME_SUFFIXES.some(s => name.endsWith(s))) return true;
  return false;
}

function walkDir(dir: string): string[] {
  const out: string[] = [];
  let entries: string[];
  try { entries = fs.readdirSync(dir); } catch { return out; }

  for (const name of entries) {
    if (name.startsWith(".") && SKIP_DIRS.has(name)) continue; // hidden dirs
    if (SKIP_DIRS.has(name)) continue;

    const full = path.join(dir, name);
    let stat: fs.Stats;
    try { stat = fs.statSync(full); } catch { continue; }

    if (stat.isDirectory()) {
      out.push(...walkDir(full));
    } else if (!shouldSkipFile(name)) {
      out.push(path.relative(ROOT, full));
    }
  }
  return out;
}

function collectFiles(): string[] {
  return [...new Set(walkDir(ROOT))];
}

// ── GitHub API helper ─────────────────────────────────────────────────────────

type GHResp = Record<string, unknown>;

async function api(
  c: InstanceType<typeof ReplitConnectors>,
  endpoint: string,
  opts: { method?: string; body?: unknown } = {},
): Promise<GHResp> {
  const resp = await c.proxy("github", endpoint, {
    method: opts.method ?? "GET",
    ...(opts.body
      ? { body: JSON.stringify(opts.body), headers: { "Content-Type": "application/json" } }
      : {}),
  });
  const text = await resp.text() as string;
  let json: GHResp;
  try {
    json = JSON.parse(text) as GHResp;
  } catch {
    throw new Error(`GitHub API ${opts.method ?? "GET"} ${endpoint} returned non-JSON (HTTP ${resp.status}): ${text.slice(0, 300)}`);
  }
  // GitHub returns error details in a "message" field on 4xx/5xx responses
  if (resp.status >= 400) {
    const msg = (json.message as string) ?? text.slice(0, 300);
    const errors = json.errors ? `\n  Errors: ${JSON.stringify(json.errors)}` : "";
    throw new Error(`HTTP_${resp.status}: ${msg}${errors}`);
  }
  return json;
}

/** api() with automatic retry on 429 (rate limit) */
async function apiWithRetry(
  c: InstanceType<typeof ReplitConnectors>,
  endpoint: string,
  opts: { method?: string; body?: unknown } = {},
  retries = 4,
): Promise<GHResp> {
  let delay = 1000; // ms
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      return await api(c, endpoint, opts);
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

// ── Main ──────────────────────────────────────────────────────────────────────

async function main() {
  const connectors = new ReplitConnectors();

  const user = await api(connectors, "/user") as { login: string };
  console.log(`\n🔗  Authenticated as: ${user.login}`);

  const refData = await api(
    connectors,
    `/repos/${OWNER}/${REPO}/git/ref/heads/${BRANCH}`,
  ) as { object: { sha: string } };
  const githubSha = (refData.object as { sha: string }).sha;
  console.log(`📌  GitHub HEAD:  ${githubSha.slice(0, 7)}`);

  const localSha = execSync("git rev-parse HEAD", { cwd: ROOT }).toString().trim();
  console.log(`📌  Local HEAD:   ${localSha.slice(0, 7)}`);

  const files = collectFiles();
  console.log(`📁  Syncing ${files.length} source files…\n`);

  const treeEntries: { path: string; mode: string; type: string; sha: string }[] = [];
  let done = 0;

  // Upload blobs in parallel with a concurrency cap.
  // Replit's GitHub proxy allows max 10 RPS; 4 workers × ~0.5 s/req ≈ 8 RPS.
  const CONCURRENCY = 4;

  async function uploadBlob(rel: string): Promise<void> {
    const abs = path.join(ROOT, rel);
    let content: string;
    try {
      const stat = fs.statSync(abs);
      if (stat.size > MAX_FILE_BYTES) {
        console.log(`  ⚠️  Skipping large file (${(stat.size / 1024 / 1024).toFixed(1)} MB): ${rel}`);
        return;
      }
      content = fs.readFileSync(abs).toString("base64");
    } catch {
      return;
    }
    const blob = await apiWithRetry(
      connectors,
      `/repos/${OWNER}/${REPO}/git/blobs`,
      { method: "POST", body: { content, encoding: "base64" } },
    ) as { sha: string };
    treeEntries.push({ path: rel, mode: "100644", type: "blob", sha: blob.sha });
    done++;
    if (done % 10 === 0) process.stdout.write(`  ${done}/${files.length} blobs…\r`);
  }

  // Simple concurrency pool
  const queue = [...files];
  async function worker() {
    while (queue.length > 0) {
      const rel = queue.shift()!;
      await uploadBlob(rel);
    }
  }
  await Promise.all(Array.from({ length: CONCURRENCY }, worker));
  process.stdout.write(`  ${done}/${files.length} blobs created.  \n`);

  let msg = "chore: periodic sync from Replit";
  try {
    const subject = execSync("git log -1 --pretty=format:%s", { cwd: ROOT }).toString().trim();
    const body    = execSync("git log -1 --pretty=format:%b", { cwd: ROOT }).toString().trim();
    msg = body ? `${subject}\n\n${body}` : subject;
  } catch { /* use default */ }

  // NOTE: base_tree is intentionally omitted here.
  // Using base_tree would inherit all files from the previous commit's tree,
  // meaning deleted files would NOT be removed from GitHub.
  // Without base_tree, GitHub creates a completely fresh tree from only the
  // files we've uploaded — correctly reflecting the current workspace state.
  const newTree = await api(
    connectors,
    `/repos/${OWNER}/${REPO}/git/trees`,
    { method: "POST", body: { tree: treeEntries } },
  ) as { sha: string };

  const newCommit = await api(
    connectors,
    `/repos/${OWNER}/${REPO}/git/commits`,
    { method: "POST", body: { message: msg, tree: newTree.sha, parents: [githubSha] } },
  ) as { sha: string };

  await api(
    connectors,
    `/repos/${OWNER}/${REPO}/git/refs/heads/${BRANCH}`,
    { method: "PATCH", body: { sha: newCommit.sha, force: true } },
  );

  const commitSha = newCommit.sha as string;
  console.log(`\n✅  Pushed to GitHub!`);
  console.log(`    Commit ID : ${commitSha}`);
  console.log(`    Short SHA : ${commitSha.slice(0, 7)}`);
  console.log(`    Branch    : ${BRANCH}`);
  console.log(`    URL       : https://github.com/${OWNER}/${REPO}/commit/${commitSha}`);
}

main().catch((err: Error) => {
  console.error("\n❌  Push failed:", err.message ?? err);
  process.exit(1);
});
