# ── Stage 1: Build the React/Vite frontend ────────────────────────────────────
# Use Debian slim (glibc) — NOT alpine (musl).
# Rollup ships platform-native binaries; the musl variant is missing on alpine
# when pnpm resolves optional deps from a glibc-built lockfile.
FROM node:24-slim AS builder

WORKDIR /workspace

# Install pnpm
RUN npm install -g pnpm

# Copy workspace manifests first (better layer caching)
COPY package.json pnpm-workspace.yaml ./
COPY tsconfig.json tsconfig.base.json ./

# Copy lib packages (shared workspace libraries)
COPY lib/ ./lib/

# Copy the frontend artifact
COPY artifacts/stock-market-app/ ./artifacts/stock-market-app/

# Install all workspace dependencies
# --no-frozen-lockfile because lockfile is excluded from .dockerignore
RUN pnpm install --no-frozen-lockfile

# Build the frontend
# PORT is required by vite.config.ts at config-parse time (not used at runtime)
# BASE_PATH=/ means the app is served from the root
ENV PORT=3000 BASE_PATH=/ NODE_ENV=production

RUN pnpm --filter @workspace/stock-market-app run build

# ── Stage 2: Serve with nginx ──────────────────────────────────────────────────
FROM nginx:alpine

# Copy the built static files
# vite.config.ts outputs to dist/public inside the artifact directory
COPY --from=builder /workspace/artifacts/stock-market-app/dist/public /usr/share/nginx/html

# Copy nginx config (proxies /api/* to backend container + serves SPA)
COPY artifacts/stock-market-app/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
