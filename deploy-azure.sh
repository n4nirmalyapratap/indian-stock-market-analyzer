#!/bin/bash
# ── Build Script for Azure Static Web Apps ────────────────────────────────────

# 1. Install dependencies
pnpm install

# 2. Build User Frontend (/)
pnpm --filter @workspace/stock-market-app run build

# 3. Build Admin Dashboard (/admin)
pnpm --filter @workspace/admin-dashboard run build

# 4. Merge them into one folder for Azure
mkdir -p deploy-dist/admin
cp -r artifacts/stock-market-app/dist/public/* deploy-dist/
cp -r artifacts/admin-dashboard/dist/public/* deploy-dist/admin/

# 5. Add the Azure config
cp staticwebapp.config.json deploy-dist/

echo "Done! Your combined frontend is in 'deploy-dist/'"
echo "You can now deploy the contents of 'deploy-dist/' to Azure Static Web Apps."
