# ── Stage 1: Build the React/Vite frontend ────────────────────────────────────
FROM node:24-alpine AS builder

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
RUN pnpm install --no-frozen-lockfile

# Build the frontend
# PORT is required by vite.config.ts at config-parse time (not used in production)
# BASE_PATH=/ means the app is served from the root
ENV PORT=3000 BASE_PATH=/ NODE_ENV=production

RUN pnpm --filter @workspace/stock-market-app run build

# ── Stage 2: Serve with nginx ──────────────────────────────────────────────────
FROM nginx:alpine

# Copy the built static files
# vite.config.ts outputs to dist/public inside the artifact directory
COPY --from=builder /workspace/artifacts/stock-market-app/dist/public /usr/share/nginx/html

# Copy nginx config
COPY artifacts/stock-market-app/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
