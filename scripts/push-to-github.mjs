#!/usr/bin/env node
/**
 * Push latest commits to GitHub using the Replit GitHub connector.
 * Run this from the workspace root: node scripts/push-to-github.mjs
 *
 * Requires: GitHub integration connected in Replit
 */

import { execSync } from "child_process";
import { ReplitConnectors } from "@replit/connectors-sdk";

const connectors = new ReplitConnectors();

async function main() {
  // Get fresh OAuth token from Replit GitHub connector
  const response = await connectors.proxy("github", "/user", { method: "GET" });
  const user = await response.json();
  console.log(`Authenticated as GitHub user: ${user.login}`);

  // Get access token from environment (injected by connectors SDK)
  const tokenResponse = await connectors.proxy("github", "/user", { method: "GET" });
  const rawToken = tokenResponse.headers?.get?.("x-oauth-token") ?? process.env.GITHUB_TOKEN;

  // Use settings approach: list connections via API directly
  const { createRequire } = await import("module");
  const require = createRequire(import.meta.url);

  // Update remote URL with fresh token
  const repoUrl = "https://github.com/n4nirmalyapratap/indian-stock-market-analyzer.git";
  console.log("Updating remote origin...");

  // Set remote using env token if available
  if (process.env.GITHUB_ACCESS_TOKEN) {
    execSync(
      `git remote set-url origin https://x-access-token:${process.env.GITHUB_ACCESS_TOKEN}@github.com/n4nirmalyapratap/indian-stock-market-analyzer.git`,
      { stdio: "inherit" }
    );
  }

  // Push
  console.log("Pushing to GitHub...");
  execSync("git push origin main", { stdio: "inherit" });
  console.log("Done! Pushed to https://github.com/n4nirmalyapratap/indian-stock-market-analyzer");
}

main().catch((err) => {
  console.error("Push failed:", err.message);
  process.exit(1);
});
