import { ReplitConnectors } from "@replit/connectors-sdk";
import * as fs from "fs";
import * as path from "path";

const OWNER = "n4nirmalyapratap";
const REPO  = "indian-stock-market-analyzer";
// Use "main" so restore-files always pulls the latest good version from GitHub.
// These files are protected by push-github.ts and will always be on main.
const REF   = "main";

const ROOT = path.resolve(import.meta.dirname, "../..");

// ── Protected files that must always exist in the workspace ──────────────────
// These are critical for Docker builds and production deployments.
// push-github.ts will ABORT if any of these are missing from the workspace.
// Whenever you add a Dockerfile or nginx.conf to a new artifact, add its path
// here too so restore-files can recover it automatically.
const FILES_TO_RESTORE = [
  // Root infra files
  ".dockerignore",
  ".env.example",
  "GITHUB_PUSH.md",
  "README.md",
  "SETUP.md",
  "deploy.sh",
  "docker-compose.yml",
  "scripts/setup-git-hook.sh",
  // Docker / nginx files — PROTECTED, never delete
  "artifacts/stock-market-app/Dockerfile",
  "artifacts/stock-market-app/nginx.conf",
];

async function main() {
  const connectors = new ReplitConnectors();

  for (const file of FILES_TO_RESTORE) {
    const resp = await connectors.proxy(
      "github",
      `/repos/${OWNER}/${REPO}/contents/${file}?ref=${REF}`,
    );
    const data = await resp.json() as { content?: string; size?: number; message?: string };

    if (!data.content) {
      console.log(`❌  ${file}: ${data.message ?? "no content"}`);
      continue;
    }

    const decoded = Buffer.from(data.content, "base64").toString("utf8");
    const dest = path.join(ROOT, file);
    fs.mkdirSync(path.dirname(dest), { recursive: true });
    fs.writeFileSync(dest, decoded, "utf8");
    console.log(`✅  Restored ${file}  (${data.size} bytes)`);
  }

  console.log("\nDone. Re-run push-github to sync to GitHub.");
}

main().catch(err => {
  console.error("❌  Failed:", err.message);
  process.exit(1);
});
