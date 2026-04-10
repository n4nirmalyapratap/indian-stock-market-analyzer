# ── Stage 1: Build the React/Vite frontend ────────────────────────────────────
#
# Why node:24-slim (Debian/glibc) instead of node:24-alpine (musl):
#   Rollup ships platform-native binaries. The pnpm-workspace.yaml overrides
#   exclude the musl variant (@rollup/rollup-linux-x64-musl) to keep the
#   Replit environment lean. On Alpine (musl), that binary is missing and the
#   build fails. Debian slim uses glibc — the gnu variant is available. ✓
#
FROM node:24-slim AS builder

WORKDIR /workspace

# Install pnpm globally
RUN npm install -g pnpm

# ── Workspace manifests — cached layer ─────────────────────────────────────────
# Copied before source so pnpm install is cached unless these files change.
COPY package.json pnpm-workspace.yaml ./

# tsconfig.base.json is extended by the frontend's own tsconfig.json via
# "../../tsconfig.base.json". Root tsconfig.json is also copied so the
# TypeScript compiler can resolve project references at build time.
COPY tsconfig.json tsconfig.base.json ./

# ── Frontend source ─────────────────────────────────────────────────────────────
# Only the stock-market-app artifact is copied — the frontend has no workspace
# dependencies on any lib/* package (verified: package.json has no workspace:
# entries). Omitting lib/ keeps the build context lean and avoids unnecessary
# re-installs when unrelated lib code changes.
COPY artifacts/stock-market-app/ ./artifacts/stock-market-app/

# ── Install dependencies ────────────────────────────────────────────────────────
# --no-frozen-lockfile is required because pnpm-lock.yaml is not committed to
# the repository (excluded from GitHub push script). pnpm will resolve versions
# from npm and build a fresh lock internally.
RUN pnpm install --no-frozen-lockfile

# ── Build ───────────────────────────────────────────────────────────────────────
# VITE_CLERK_PUBLISHABLE_KEY must be passed as a build-time ARG so Vite can
# embed it into the compiled JS bundle. It is not needed at nginx serve time.
ARG VITE_CLERK_PUBLISHABLE_KEY
ENV PORT=3000 BASE_PATH=/ NODE_ENV=production \
    VITE_CLERK_PUBLISHABLE_KEY=${VITE_CLERK_PUBLISHABLE_KEY}

RUN pnpm --filter @workspace/stock-market-app run build

# ── Stage 2: Serve with nginx ──────────────────────────────────────────────────
FROM nginx:alpine

# vite.config.ts sets outDir to dist/public (relative to the artifact root).
# Full path inside the builder stage: /workspace/artifacts/stock-market-app/dist/public
COPY --from=builder /workspace/artifacts/stock-market-app/dist/public /usr/share/nginx/html

# nginx config: serves the SPA at / and proxies /api/* to the backend container.
# Build context is the workspace root, so the path is relative to there.
COPY artifacts/stock-market-app/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
