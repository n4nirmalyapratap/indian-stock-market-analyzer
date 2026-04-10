import { ReplitConnectors } from "@replit/connectors-sdk";
import * as fs from "fs";
import * as path from "path";

const OWNER = "n4nirmalyapratap";
const REPO  = "indian-stock-market-analyzer";
const REF   = "b658374"; // commit SHA before our push

const ROOT = path.resolve(import.meta.dirname, "../..");

const FILES_TO_RESTORE = [
  ".dockerignore",
  ".env.example",
  "GITHUB_PUSH.md",
  "README.md",
  "SETUP.md",
  "deploy.sh",
  "docker-compose.yml",
  "scripts/setup-git-hook.sh",
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
