/**
 * push-github.ts
 * Sync workspace ↔ GitHub — pull first, then push.
 *
 * PRIMARY   — Replit GitHub OAuth connector
 * FALLBACK  — GITHUB_PAT secret (Personal Access Token, repo scope)
 *
 * WORKFLOW
 * ────────
 * 1. PULL  — fetch the GitHub tree and compare to workspace.
 *            • Files that exist ONLY on GitHub        → downloaded to workspace.
 *            • Files that differ on BOTH sides         → workspace wins (NOT overwritten).
 *            • Files unchanged on both sides           → skipped.
 *
 * 2. PUSH  — diff-based upload (git blob SHA comparison).
 *            Only files whose content changed since the last push are uploaded.
 *            Unchanged files reuse their existing GitHub blob SHA (zero API calls).
 *            This makes incremental pushes take seconds instead of minutes.
 *
 * Run: pnpm --filter @workspace/scripts run push-github
 *
 * See GITHUB_PUSH.md for full setup instructions and troubleshooting.
 */

import { ReplitConnectors } from "@replit/connectors-sdk";
import { createHash }       from "crypto";
import { execSync }         from "child_process";
import * as fs              from "fs";
import * as path            from "path";

const OWNER  = "n4nirmalyapratap";
const REPO   = "indian-stock-market-analyzer";
const BRANCH = "main";
const ROOT   = path.resolve(import.meta.dirname, "../..");
const PAT    = process.env.GITHUB_PAT ?? "";

// ── Skip rules ────────────────────────────────────────────────────────────────

const SKIP_DIRS = new Set([
  ".git",
  "node_modules", "dist", "build", "tmp", "out-tsc", ".cache",
  "__pycache__", ".pythonlibs", ".pnpm-store", ".upm", ".venv",
  "venv", "env", ".tox", ".eggs",
  ".agents", ".local", ".replit-artifact",
  "market_cache",
  ".expo", ".expo-shared",
  ".idea", ".vscode", "coverage", "typings",
]);

const SKIP_FILES = new Set([
  "pnpm-lock.yaml", "uv.lock", "package-lock.json", "yarn.lock",
  "hydra_prices.db",
  ".DS_Store", "Thumbs.db",
  ".tsbuildinfo",
]);

const SKIP_NAME_SUFFIXES = [".pyc", ".pyo", ".pyd", ".egg-info", ".db"];

const SKIP_EXTS = new Set([
  ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico",
  ".woff", ".woff2", ".ttf", ".otf", ".eot",
  ".mp4", ".mp3", ".wav", ".pdf", ".zip",
]);

const MAX_FILE_BYTES = 400 * 1024;

const PROTECTED_FILENAMES = new Set([
  "Dockerfile", "nginx.conf", "docker-compose.yml", ".dockerignore",
]);

const PROTECTED_PATH_SUBSTRINGS = [
  "Dockerfile", "docker-compose", "nginx.conf", ".dockerignore",
];

function isProtected(filePath: string): boolean {
  const name = path.basename(filePath);
  if (PROTECTED_FILENAMES.has(name)) return true;
  return PROTECTED_PATH_SUBSTRINGS.some(s => filePath.includes(s));
}

// ── File walker ───────────────────────────────────────────────────────────────

function shouldSkipFile(name: string): boolean {
  if (SKIP_FILES.has(name)) return true;
  const ext = path.extname(name).toLowerCase();
  if (SKIP_EXTS.has(ext)) return true;
  if (SKIP_NAME_SUFFIXES.some(s => name.endsWith(s))) return true;
  return false;
}

function shouldSkipPath(relPath: string): boolean {
  const parts = relPath.split(path.sep);
  for (const part of parts) {
    if ((part.startsWith(".") && SKIP_DIRS.has(part)) || SKIP_DIRS.has(part)) return true;
  }
  return shouldSkipFile(path.basename(relPath));
}

function walkDir(dir: string): string[] {
  const out: string[] = [];
  let entries: string[];
  try { entries = fs.readdirSync(dir); } catch { return out; }

  for (const name of entries) {
    if ((name.startsWith(".") && SKIP_DIRS.has(name)) || SKIP_DIRS.has(name)) continue;

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

// ── Git blob SHA (same as `git hash-object`) ──────────────────────────────────
// SHA1("blob <byte-length>\0<content>")
function gitBlobSha(content: Buffer): string {
  const header = `blob ${content.length}\0`;
  return createHash("sha1")
    .update(Buffer.concat([Buffer.from(header), content]))
    .digest("hex");
}

// ── GitHub API helpers ────────────────────────────────────────────────────────

type GHResp = Record<string, unknown>;
type ApiOpts = { method?: string; body?: unknown };

async function callOAuth(
  connectors: InstanceType<typeof ReplitConnectors>,
  endpoint: string,
  opts: ApiOpts = {},
): Promise<GHResp> {
  const resp = await connectors.proxy("github", endpoint, {
    method: opts.method ?? "GET",
    ...(opts.body
      ? { body: JSON.stringify(opts.body), headers: { "Content-Type": "application/json" } }
      : {}),
  });
  const text = await resp.text() as string;
  let json: GHResp;
  try { json = JSON.parse(text) as GHResp; } catch {
    throw new Error(`GitHub API ${opts.method ?? "GET"} ${endpoint} → non-JSON (HTTP ${resp.status}): ${text.slice(0, 300)}`);
  }
  if (resp.status >= 400) {
    const msg    = (json.message as string) ?? text.slice(0, 300);
    const errors = json.errors ? `\n  Errors: ${JSON.stringify(json.errors)}` : "";
    throw new Error(`HTTP_${resp.status}: ${msg}${errors}`);
  }
  return json;
}

async function callPAT(endpoint: string, opts: ApiOpts = {}): Promise<GHResp> {
  const resp = await fetch(`https://api.github.com${endpoint}`, {
    method: opts.method ?? "GET",
    headers: {
      "Authorization": `Bearer ${PAT}`,
      "Accept": "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      ...(opts.body ? { "Content-Type": "application/json" } : {}),
    },
    ...(opts.body ? { body: JSON.stringify(opts.body) } : {}),
  });
  const text = await resp.text();
  let json: GHResp;
  try { json = JSON.parse(text) as GHResp; } catch {
    throw new Error(`GitHub API ${opts.method ?? "GET"} ${endpoint} → non-JSON (HTTP ${resp.status}): ${text.slice(0, 300)}`);
  }
  if (resp.status >= 400) {
    const msg    = (json.message as string) ?? text.slice(0, 300);
    const errors = json.errors ? `\n  Errors: ${JSON.stringify(json.errors)}` : "";
    throw new Error(`HTTP_${resp.status}: ${msg}${errors}`);
  }
  return json;
}

let api: (endpoint: string, opts?: ApiOpts) => Promise<GHResp>;

async function apiWithRetry(
  endpoint: string,
  opts: ApiOpts = {},
  retries = 4,
): Promise<GHResp> {
  let delay = 1000;
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      return await api(endpoint, opts);
    } catch (err) {
      const msg = (err as Error).message ?? "";
      if ((msg.startsWith("HTTP_429") || msg.startsWith("HTTP_403")) && attempt < retries) {
        const wait = delay;
        process.stdout.write(`  ⏳  Rate limited — waiting ${wait / 1000}s before retry…\r`);
        await new Promise(r => setTimeout(r, wait));
        delay = Math.min(delay * 2, 16000);
        continue;
      }
      throw err;
    }
  }
  throw new Error("unreachable");
}

// ── Download a single blob from GitHub into the workspace ─────────────────────
async function downloadBlob(relPath: string, blobSha: string): Promise<void> {
  const blobData = await api(
    `/repos/${OWNER}/${REPO}/git/blobs/${blobSha}`,
  ) as { content: string; encoding: string };

  const content = blobData.encoding === "base64"
    ? Buffer.from(blobData.content.replace(/\n/g, ""), "base64")
    : Buffer.from(blobData.content as string);

  const abs = path.join(ROOT, relPath);
  fs.mkdirSync(path.dirname(abs), { recursive: true });
  fs.writeFileSync(abs, content);
}

// ── Main ──────────────────────────────────────────────────────────────────────

async function main() {
  let connectors: InstanceType<typeof ReplitConnectors> | null = null;

  // ── 1. Choose transport: OAuth primary, PAT fallback ──────────────────────
  let usingOAuth = false;
  try {
    connectors = new ReplitConnectors();
    const testResp = await connectors.proxy("github", "/user", { method: "GET" });
    const testText = await testResp.text() as string;
    const testJson = JSON.parse(testText) as GHResp;
    if (testResp.status >= 400 || !testJson.login) throw new Error("OAuth probe failed");
    api       = (endpoint, opts) => callOAuth(connectors!, endpoint, opts);
    usingOAuth = true;
    console.log(`\n🔐  Auth method: GitHub OAuth (primary)`);
  } catch {
    if (!PAT) {
      console.error("\n❌  No auth: OAuth not connected AND GITHUB_PAT not set.");
      console.error("    → Connect GitHub in Replit Integrations, or add GITHUB_PAT to Secrets.");
      process.exit(1);
    }
    console.log(`\n🔑  Auth method: Personal Access Token (fallback — OAuth not available)`);
    api = (endpoint, opts) => callPAT(endpoint, opts);
  }

  // ── 2. Auth check ──────────────────────────────────────────────────────────
  const user = await api("/user") as { login: string };
  console.log(`🔗  Authenticated as: ${user.login}`);

  if (usingOAuth) {
    const repoInfo = await api(`/repos/${OWNER}/${REPO}`) as {
      permissions?: { push: boolean };
      owner?: { login: string };
    };
    if (!(repoInfo.permissions?.push ?? false)) {
      if (PAT) {
        console.log(`⚠️   OAuth account lacks push access → falling back to PAT…`);
        api       = (endpoint, opts) => callPAT(endpoint, opts);
        usingOAuth = false;
      } else {
        console.error(`\n❌  OAuth account "${user.login}" cannot push to ${OWNER}/${REPO}.`);
        process.exit(1);
      }
    }
  }

  // ── 3. Fetch GitHub HEAD and tree ──────────────────────────────────────────
  const refData = await api(
    `/repos/${OWNER}/${REPO}/git/ref/heads/${BRANCH}`,
  ) as { object: { sha: string } };
  const githubSha = refData.object.sha;

  const localSha = execSync("git rev-parse HEAD", { cwd: ROOT }).toString().trim();

  console.log(`\n📌  GitHub HEAD : ${githubSha.slice(0, 7)}`);
  console.log(`📌  Local HEAD  : ${localSha.slice(0, 7)}`);

  console.log(`\n🔍  Fetching GitHub file tree…`);
  const ghTree = await api(
    `/repos/${OWNER}/${REPO}/git/trees/${githubSha}?recursive=1`,
  ) as { tree: { path: string; type: string; sha: string }[] };

  const ghBlobMap = new Map<string, string>(
    ghTree.tree.filter(e => e.type === "blob").map(e => [e.path, e.sha]),
  );

  // ── 4. PULL — sync GitHub-only changes into workspace ─────────────────────
  //
  // Rules:
  //   • File ONLY on GitHub (not in workspace)      → download to workspace
  //   • File on BOTH sides, GitHub SHA ≠ local SHA  → WORKSPACE WINS (skip download)
  //   • File unchanged                              → nothing to do
  //   • Skippable paths (node_modules, etc.)        → always skip

  const localFiles  = collectFiles();
  const workspaceSet = new Set(localFiles);

  const onlyOnGitHub:   string[] = []; // new on GitHub → will pull
  const bothDiffer:     string[] = []; // edited in both → workspace wins
  const skippedOnPull:  string[] = []; // should-skip paths from GitHub

  for (const [ghPath, ghSha] of ghBlobMap) {
    if (shouldSkipPath(ghPath)) { skippedOnPull.push(ghPath); continue; }

    if (!workspaceSet.has(ghPath)) {
      onlyOnGitHub.push(ghPath);
    } else {
      // Compare local SHA to GitHub SHA
      const abs = path.join(ROOT, ghPath);
      let localRaw: Buffer | null = null;
      try { localRaw = fs.readFileSync(abs); } catch { /* file vanished */ }
      if (localRaw !== null && gitBlobSha(localRaw) !== ghSha) {
        bothDiffer.push(ghPath);
      }
    }
  }

  if (onlyOnGitHub.length === 0 && bothDiffer.length === 0) {
    console.log(`   ✅  Workspace already has all GitHub changes — no pull needed.\n`);
  } else {
    if (onlyOnGitHub.length > 0) {
      console.log(`\n⬇️   PULLING ${onlyOnGitHub.length} file(s) that exist on GitHub but not in workspace:`);
      for (const f of onlyOnGitHub) console.log(`     + ${f}`);
      let pulled = 0;
      for (const f of onlyOnGitHub) {
        await downloadBlob(f, ghBlobMap.get(f)!);
        pulled++;
        process.stdout.write(`  ${pulled}/${onlyOnGitHub.length} pulled…\r`);
      }
      process.stdout.write(`  ${pulled}/${onlyOnGitHub.length} file(s) pulled into workspace.   \n`);
    }

    if (bothDiffer.length > 0) {
      console.log(`\n⚡  ${bothDiffer.length} file(s) differ on BOTH sides — workspace version kept (will be pushed):`);
      for (const f of bothDiffer.slice(0, 10)) console.log(`     ~ ${f}`);
      if (bothDiffer.length > 10) console.log(`     … and ${bothDiffer.length - 10} more`);
    }
  }

  // Re-collect after pull (new files may have been downloaded)
  const files = collectFiles();
  const workspaceSetFinal = new Set(files);

  // ── 5. Pre-flight: detect files that would be deleted from GitHub ──────────
  const willBeDeleted = ghTree.tree
    .filter(e => e.type === "blob")
    .map(e => e.path)
    .filter(p => !workspaceSetFinal.has(p));

  const protectedViolations = willBeDeleted.filter(isProtected);
  if (protectedViolations.length > 0) {
    console.log(`\n🚨  PUSH ABORTED — PROTECTED FILES MISSING FROM WORKSPACE:`);
    for (const f of protectedViolations) console.log(`     🛡  ${f}`);
    console.log(`\n   Restore with: pnpm --filter @workspace/scripts run restore-files\n`);
    process.exit(1);
  }

  if (willBeDeleted.length > 0) {
    console.log(`\n⚠️   FILES ON GITHUB THAT WILL BE DELETED BY THIS PUSH:`);
    for (const f of willBeDeleted) console.log(`     🗑  ${f}`);
    console.log(`\n   To keep them, run: pnpm --filter @workspace/scripts run restore-files`);
    console.log(`   then re-run push.\n`);
  } else {
    console.log(`\n   ✅  No unexpected deletions.\n`);
  }

  // ── 6. PUSH — diff-based upload (only changed files) ─────────────────────
  //
  // Recompute the ghBlobMap after pull (pulled files are now identical to GitHub)
  const ghBlobMapFinal = new Map<string, string>(
    ghTree.tree.filter(e => e.type === "blob").map(e => [e.path, e.sha]),
  );

  const treeEntries: { path: string; mode: string; type: string; sha: string }[] = [];
  const toUpload: string[] = [];
  let reused = 0;

  for (const rel of files) {
    const abs = path.join(ROOT, rel);
    let raw: Buffer;
    try {
      const stat = fs.statSync(abs);
      if (stat.size > MAX_FILE_BYTES) {
        console.log(`  ⚠️  Skipping large file (${(stat.size / 1024 / 1024).toFixed(1)} MB): ${rel}`);
        continue;
      }
      raw = fs.readFileSync(abs);
    } catch { continue; }

    const localBlobSha  = gitBlobSha(raw);
    const remoteBlobSha = ghBlobMapFinal.get(rel);

    if (remoteBlobSha && remoteBlobSha === localBlobSha) {
      // Unchanged — reuse existing SHA, zero API calls
      treeEntries.push({ path: rel, mode: "100644", type: "blob", sha: localBlobSha });
      reused++;
    } else {
      toUpload.push(rel);
    }
  }

  console.log(`📊  ${files.length} files — ${reused} unchanged (reused), ${toUpload.length} to upload`);

  if (toUpload.length === 0 && willBeDeleted.length === 0) {
    console.log(`\n✅  Nothing to push — GitHub is already up to date!`);
    return;
  }

  if (toUpload.length > 0) {
    console.log(`\n📤  Uploading ${toUpload.length} changed file(s)…\n`);
  }

  const CONCURRENCY   = 5;
  const BLOB_DELAY_MS = 150;
  let done = 0;

  async function uploadBlob(rel: string): Promise<void> {
    const abs = path.join(ROOT, rel);
    let raw: Buffer;
    try { raw = fs.readFileSync(abs); } catch { return; }

    const content = raw.toString("base64");
    const blob = await apiWithRetry(
      `/repos/${OWNER}/${REPO}/git/blobs`,
      { method: "POST", body: { content, encoding: "base64" } },
    ) as { sha: string };
    treeEntries.push({ path: rel, mode: "100644", type: "blob", sha: blob.sha });
    done++;
    process.stdout.write(`  ${done}/${toUpload.length} uploaded…\r`);
    await new Promise(r => setTimeout(r, BLOB_DELAY_MS));
  }

  const queue = [...toUpload];
  async function worker() {
    while (queue.length > 0) {
      const rel = queue.shift()!;
      await uploadBlob(rel);
    }
  }
  await Promise.all(Array.from({ length: Math.min(CONCURRENCY, toUpload.length || 1) }, worker));
  if (toUpload.length > 0) process.stdout.write(`  ${done}/${toUpload.length} uploaded.   \n`);

  // ── 7. Commit + update ref ─────────────────────────────────────────────────
  let msg = "chore: sync from Replit";
  try {
    const subject = execSync("git log -1 --pretty=format:%s", { cwd: ROOT }).toString().trim();
    const body    = execSync("git log -1 --pretty=format:%b", { cwd: ROOT }).toString().trim();
    msg = body ? `${subject}\n\n${body}` : subject;
  } catch { /* use default */ }

  const newTree = await api(
    `/repos/${OWNER}/${REPO}/git/trees`,
    { method: "POST", body: { tree: treeEntries } },
  ) as { sha: string };

  const newCommit = await api(
    `/repos/${OWNER}/${REPO}/git/commits`,
    { method: "POST", body: { message: msg, tree: newTree.sha, parents: [githubSha] } },
  ) as { sha: string };

  await api(
    `/repos/${OWNER}/${REPO}/git/refs/heads/${BRANCH}`,
    { method: "PATCH", body: { sha: newCommit.sha, force: true } },
  );

  const commitSha = newCommit.sha as string;
  const authLabel = usingOAuth ? "OAuth" : "PAT";
  console.log(`\n✅  Pushed to GitHub! (via ${authLabel})`);
  console.log(`    Commit   : ${commitSha.slice(0, 7)}`);
  console.log(`    Branch   : ${BRANCH}`);
  console.log(`    URL      : https://github.com/${OWNER}/${REPO}/commit/${commitSha}`);
  console.log(`    Summary  : ${toUpload.length} uploaded, ${reused} reused, ${onlyOnGitHub.length} pulled in`);
}

main().catch((err: Error) => {
  console.error("\n❌  Push failed:", err.message ?? err);
  process.exit(1);
});
