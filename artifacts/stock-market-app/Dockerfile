# ─────────────────────────────────────────────────────────────────────────────
# Indian Stock Market Analyzer — Combined Frontend Dockerfile
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 1: Build user frontend ─────────────────────────────────────────────
FROM node:24-slim AS builder-user
WORKDIR /workspace
RUN npm install -g pnpm

COPY package.json pnpm-workspace.yaml ./
COPY tsconfig.json tsconfig.base.json ./
COPY artifacts/stock-market-app/ ./artifacts/stock-market-app/

RUN pnpm install --no-frozen-lockfile --dangerously-allow-all-builds
ENV PORT=3000 BASE_PATH=/ NODE_ENV=production
RUN pnpm --filter @workspace/stock-market-app run build


# ── Stage 2: Build admin dashboard ───────────────────────────────────────────
FROM node:24-slim AS builder-admin
WORKDIR /workspace
RUN npm install -g pnpm

COPY package.json pnpm-workspace.yaml ./
COPY tsconfig.json tsconfig.base.json ./
COPY artifacts/admin-dashboard/ ./artifacts/admin-dashboard/

RUN pnpm install --no-frozen-lockfile --dangerously-allow-all-builds
ENV PORT=3001 BASE_PATH=/admin NODE_ENV=production
RUN pnpm --filter @workspace/admin-dashboard run build


# ── Stage 3: Serve with nginx ────────────────────────────────────────────────
FROM nginx:alpine
COPY --from=builder-user  /workspace/artifacts/stock-market-app/dist/public  /usr/share/nginx/html
COPY --from=builder-admin /workspace/artifacts/admin-dashboard/dist/public  /usr/share/nginx/admin
COPY artifacts/stock-market-app/nginx.conf /etc/nginx/conf.d/default.conf

# Copy entrypoint script for dynamic environment injection
COPY artifacts/stock-market-app/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 80

ENTRYPOINT ["/entrypoint.sh"]
CMD ["nginx", "-g", "daemon off;"]