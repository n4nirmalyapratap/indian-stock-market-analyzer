#!/bin/bash
set -e
# --ignore-scripts skips the preinstall guard which checks npm_config_user_agent
# (that env var is not set in the post-merge runner context).
# Dependencies are already installed; this just ensures lockfile sync.
pnpm install --frozen-lockfile --ignore-scripts

# NOTE: DB schema migrations are NOT run automatically here.
# drizzle-kit push requires an interactive TTY (to confirm destructive changes)
# and must be run manually by an admin when schema changes are intentional:
#   pnpm --filter db push
