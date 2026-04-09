/**
 * push-github.ts
 * Push source changes to GitHub using the Replit GitHub connector.
 * No PAT needed — uses Replit OAuth (repo permissions).
 *
 * Run: pnpm --filter @workspace/scripts run push-github
 *
 * Strategy: whitelist only source directories (avoids node_modules,
 * .pythonlibs, .cache, dist, __pycache__, and other generated dirs).
 */

import { ReplitConnectors } from "@replit/connectors-sdk";
import { execSync } from "child_process";
import * as fs from "fs";
import * as path from "path";

const OWNER  = "n4nirmalyapratap";
const REPO   = "indian-stock-market-analyzer";
const BRANCH = "main";
const ROOT   = path.resolve(import.meta.dirname, "../..");

// ── Whitelist: only these paths are synced to GitHub ─────────────────────────
// Paths are relative to workspace root. Directories are walked recursively
// (with the SKIP_INSIDE dirs excluded).
const INCLUDE_PATHS = [
  // Root config files
  "package.json",
  "pnpm-workspace.yaml",
  "tsconfig.json",
  "tsconfig.base.json",
  "replit.md",
  ".replit",
  ".gitignore",
  ".replitignore",
  ".npmrc",
  "main.py",
  "pyproject.toml",
  // Python backend (all source)
  "artifacts/python-backend",
  // React frontend source
  "artifacts/nestjs-backend-placeholder/src",
  "artifacts/nestjs-backend-placeholder/public",
  "artifacts/nestjs-backend-placeholder/package.json",
  "artifacts/nestjs-backend-placeholder/vite.config.ts",
  "artifacts/nestjs-backend-placeholder/tsconfig.json",
  "artifacts/nestjs-backend-placeholder/index.html",
  "artifacts/nestjs-backend-placeholder/components.json",
  // Artifact routing configs
  "artifacts/stock-market-app/.replit-artifact/artifact.toml",
  "artifacts/api-server/.replit-artifact/artifact.toml",
  // Scripts
  "scripts/src",
  "scripts/package.json",
  "scripts/tsconfig.json",
  // Shared libs
  "lib/api-spec",
  "lib/api-zod/src",
  "lib/api-zod/package.json",
  "lib/api-client-react/src",
  "lib/api-client-react/package.json",
  "lib/db/src",
  "lib/db/package.json",
  "lib/db/drizzle.config.ts",
];

// Dirs to skip when walking a whitelisted directory
const SKIP_INSIDE = new Set([
  "node_modules", "__pycache__", ".pnpm-store", "market_cache",
  "dist", ".cache", ".pythonlibs", ".upm", ".agents", ".local",
  ".replit-artifact", "pandas_ta", ".venv", "venv", "env",
  ".tox", "build", "eggs", "*.egg-info",
]);
const SKIP_FILES = new Set([
  "hydra_prices.db", "pnpm-lock.yaml", "uv.lock", ".DS_Store",
  "package-lock.json", "yarn.lock",
]);
const MAX_FILE_BYTES = 400 * 1024; // skip files > 400 KB (proxy limit)
// Skip binary asset extensions that are large or not useful in source sync
const SKIP_EXTS = new Set([".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".woff", ".woff2", ".ttf", ".otf", ".eot", ".mp4", ".mp3", ".wav", ".pdf", ".zip"]);

function walkDir(dir: string, base: string): string[] {
  const out: string[] = [];
  for (const name of fs.readdirSync(dir)) {
    if (SKIP_INSIDE.has(name) || SKIP_FILES.has(name)) continue;
    const full = path.join(dir, name);
    const stat = fs.statSync(full);
    if (stat.isDirectory()) {
      out.push(...walkDir(full, base));
    } else if (!SKIP_EXTS.has(path.extname(name).toLowerCase())) {
      out.push(path.relative(base, full));
    }
  }
  return out;
}

function collectFiles(): string[] {
  const results: string[] = [];
  for (const rel of INCLUDE_PATHS) {
    const abs = path.join(ROOT, rel);
    if (!fs.existsSync(abs)) continue;
    const stat = fs.statSync(abs);
    if (stat.isDirectory()) {
      results.push(...walkDir(abs, ROOT));
    } else {
      if (!SKIP_FILES.has(path.basename(rel))) results.push(rel);
    }
  }
  return [...new Set(results)]; // dedupe
}

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
  try {
    return JSON.parse(text) as GHResp;
  } catch {
    throw new Error(`GitHub API returned non-JSON: ${text.slice(0, 200)}`);
  }
}

async function main() {
  const connectors = new ReplitConnectors();

  // Verify auth
  const user = await api(connectors, "/user") as { login: string };
  console.log(`\n🔗  Authenticated as: ${user.login}`);

  // Get GitHub HEAD sha
  const refData = await api(
    connectors,
    `/repos/${OWNER}/${REPO}/git/ref/heads/${BRANCH}`,
  ) as { object: { sha: string } };
  const githubSha = (refData.object as { sha: string }).sha;
  console.log(`📌  GitHub HEAD:  ${githubSha.slice(0, 7)}`);

  // Get local HEAD sha
  const localSha = execSync("git rev-parse HEAD", { cwd: ROOT }).toString().trim();
  console.log(`📌  Local HEAD:   ${localSha.slice(0, 7)}`);

  // Collect whitelisted source files
  const files = collectFiles();
  console.log(`📁  Syncing ${files.length} source files…\n`);

  // Get GitHub's current base tree
  const commitInfo = await api(
    connectors,
    `/repos/${OWNER}/${REPO}/git/commits/${githubSha}`,
  ) as { tree: { sha: string } };
  const baseTreeSha = (commitInfo.tree as { sha: string }).sha;

  // Create blobs for all whitelisted files
  const treeEntries: { path: string; mode: string; type: string; sha: string }[] = [];
  let done = 0;
  for (const rel of files) {
    const abs = path.join(ROOT, rel);
    let content: string;
    try {
      const stat = fs.statSync(abs);
      if (stat.size > MAX_FILE_BYTES) {
        console.log(`  ⚠️  Skipping large file (${(stat.size / 1024 / 1024).toFixed(1)} MB): ${rel}`);
        continue;
      }
      content = fs.readFileSync(abs).toString("base64");
    } catch {
      continue;
    }
    const blob = await api(
      connectors,
      `/repos/${OWNER}/${REPO}/git/blobs`,
      { method: "POST", body: { content, encoding: "base64" } },
    ) as { sha: string };
    treeEntries.push({ path: rel, mode: "100644", type: "blob", sha: blob.sha });
    done++;
    if (done % 5 === 0) process.stdout.write(`  ${done}/${files.length} blobs created…\r`);
  }
  process.stdout.write(`  ${done}/${files.length} blobs created.  \n`);

  // Build commit message
  let msg = "chore: periodic sync from Replit";
  try {
    const subject = execSync("git log -1 --pretty=format:%s", { cwd: ROOT }).toString().trim();
    const body    = execSync("git log -1 --pretty=format:%b", { cwd: ROOT }).toString().trim();
    msg = body ? `${subject}\n\n${body}` : subject;
  } catch { /* use default */ }

  // Create tree (inherits untouched files from GitHub's base tree)
  const newTree = await api(
    connectors,
    `/repos/${OWNER}/${REPO}/git/trees`,
    { method: "POST", body: { base_tree: baseTreeSha, tree: treeEntries } },
  ) as { sha: string };

  // Create commit
  const newCommit = await api(
    connectors,
    `/repos/${OWNER}/${REPO}/git/commits`,
    { method: "POST", body: { message: msg, tree: newTree.sha, parents: [githubSha] } },
  ) as { sha: string };

  // Update branch ref (force allows pushing on top of diverged history)
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
