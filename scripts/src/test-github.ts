import { ReplitConnectors } from "@replit/connectors-sdk";

const c = new ReplitConnectors();

const u = await c.proxy("github", "/user");
const user = await u.json() as { login: string };
console.log("Login:", user.login);

const r = await c.proxy("github", "/repos/n4nirmalyapratap/indian-stock-market-analyzer");
const repo = await r.json() as { full_name: string; permissions: Record<string, boolean>; owner: { login: string } };
console.log("Full name:", repo.full_name);
console.log("Permissions:", JSON.stringify(repo.permissions));
console.log("Owner:", repo.owner?.login);

// Try creating a test blob
const blobResp = await c.proxy("github", "/repos/n4nirmalyapratap/indian-stock-market-analyzer/git/blobs", {
  method: "POST",
  body: JSON.stringify({ content: "dGVzdA==", encoding: "base64" }),
  headers: { "Content-Type": "application/json" },
});
console.log("Blob status:", blobResp.status);
const blobBody = await blobResp.text();
console.log("Blob body:", blobBody.slice(0, 200));
