# ─────────────────────────────────────────────────────────────────────────────
# Indian Stock Market Analyzer — Combined Frontend Dockerfile
#
# Builds BOTH React apps in a single image and serves them from one nginx:
#   /          →  User frontend  (stock-market-app)
#   /admin/    →  Admin dashboard (admin-dashboard)
#   /api/*     →  Proxied to Python backend container (backend:8090)
#
# Why node:24-slim (Debian/glibc) instead of node:24-alpine (musl):
#   Rollup ships platform-native binaries. pnpm-workspace.yaml excludes the
#   musl variant (@rollup/rollup-linux-x64-musl). Alpine (musl) causes build
#   failure. Debian slim uses glibc — the gnu variant is present. ✓
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 1: Build user frontend ─────────────────────────────────────────────
FROM node:24-slim AS builder-user

WORKDIR /workspace

RUN npm install -g pnpm

# Workspace manifests — cached as long as these don't change
COPY package.json pnpm-workspace.yaml ./
COPY tsconfig.json tsconfig.base.json ./

# Only copy the user frontend — no workspace:* deps on lib/
COPY artifacts/stock-market-app/ ./artifacts/stock-market-app/

RUN pnpm install --no-frozen-lockfile

ENV PORT=3000 BASE_PATH=/ NODE_ENV=production

RUN pnpm --filter @workspace/stock-market-app run build


# ── Stage 2: Build admin dashboard ───────────────────────────────────────────
FROM node:24-slim AS builder-admin

WORKDIR /workspace

RUN npm install -g pnpm

COPY package.json pnpm-workspace.yaml ./
COPY tsconfig.json tsconfig.base.json ./

# Only copy the admin dashboard
COPY artifacts/admin-dashboard/ ./artifacts/admin-dashboard/

RUN pnpm install --no-frozen-lockfile

ENV PORT=3001 BASE_PATH=/admin NODE_ENV=production

RUN pnpm --filter @workspace/admin-dashboard run build


# ── Stage 3: Serve with nginx ─────────────────────────────────────────────────
FROM nginx:alpine

# User frontend → served at /
COPY --from=builder-user  /workspace/artifacts/stock-market-app/dist/public  /usr/share/nginx/html

# Admin dashboard → served at /admin/
# vite.config.ts sets outDir to dist/public relative to the artifact root
COPY --from=builder-admin /workspace/artifacts/admin-dashboard/dist/public  /usr/share/nginx/admin

# nginx config handles all three routes: /api, /admin, /
COPY artifacts/stock-market-app/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
