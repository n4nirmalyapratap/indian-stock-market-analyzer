# Documentation Index

This file indexes the repo's markdown documentation by product area so it is easier to find the right doc for the frontend, backend, and admin frontend.

## Markdown Files Found

| File | Main theme |
|---|---|
| `README.md` | High-level architecture, project structure, core API surface, deployment overview |
| `SETUP.md` | Local/Docker/Replit setup, auth model, routing, operations |
| `replit.md` | Replit-oriented architecture notes, hard rules, feature notes, agent memory |
| `GITHUB_PUSH.md` | Custom GitHub push workflow and safety rules |
| `artifacts/python-backend/reports/sebi_audit_2026-04-12.md` | Generated compliance report example |

## Frontend

### Most relevant markdown docs

| File | Why it matters for the user app |
|---|---|
| `README.md` | Identifies `artifacts/stock-market-app/` as the main React/Vite frontend and explains `/api` proxying |
| `SETUP.md` | Documents production routing for `/`, `/api/*`, and `/admin/*` plus user auth flow |
| `replit.md` | Captures Replit workflow ports, frontend hard rules, and product feature notes |

### Best starting order

1. `README.md`
2. `SETUP.md`
3. `replit.md`
4. `artifacts/stock-market-app/document.md`

### What these docs tell you

- The user app lives in `artifacts/stock-market-app`
- It is a React/Vite app using `wouter`, not `react-router`
- It talks to the backend through relative `/api/*` calls
- In production, nginx serves `/` and proxies `/api/*`

## Backend

### Most relevant markdown docs

| File | Why it matters for the backend |
|---|---|
| `README.md` | Describes the Python FastAPI backend, route groups, and deployment model |
| `SETUP.md` | Explains auth, Docker topology, API paths, and troubleshooting |
| `replit.md` | Contains backend hard rules, startup commands, feature notes, and service-specific guidance |
| `GITHUB_PUSH.md` | Important for backend-safe pushes because of protected Docker and shim files |

### Best starting order

1. `README.md`
2. `SETUP.md`
3. `replit.md`
4. `artifacts/python-backend/document.md`
5. `GITHUB_PUSH.md`

### What these docs tell you

- The active backend is `artifacts/python-backend`
- `run.py` starts the server and `main.py` mounts the app
- `/api` is the single backend surface for both user and admin clients
- `pandas_ta` must stay local in-repo and must not be installed from PyPI

## Admin Frontend

### Most relevant markdown docs

| File | Why it matters for the admin app |
|---|---|
| `SETUP.md` | Best doc for `/admin` routing, login flow, and admin feature overview |
| `replit.md` | Lists the admin dashboard as a first-class app and summarizes admin features |
| `README.md` | Helpful for overall architecture, but it under-describes the admin frontend compared with `SETUP.md` |

### Best starting order

1. `SETUP.md`
2. `replit.md`
3. `artifacts/admin-dashboard/document.md`
4. `README.md`

### What these docs tell you

- The admin app lives in `artifacts/admin-dashboard`
- It is served at `/admin`
- It uses an admin token in the `X-Admin-Token` header for backend access
- It manages status, users, logs, bots, bugs, jobs, secrets, and SEBI audit workflows

## Shared And Ops Docs

| File | Use when |
|---|---|
| `GITHUB_PUSH.md` | You need to publish changes through the custom push script |
| `SETUP.md` | You need Docker, env, auth, routing, or troubleshooting help |
| `README.md` | You need a repo-level architecture summary |
| `replit.md` | You need Replit workflow, port, or project-rule context |

## Generated Markdown

| File | Notes |
|---|---|
| `artifacts/python-backend/reports/sebi_audit_2026-04-12.md` | Example output from the backend's SEBI audit workflow, not a source-of-truth architecture doc |

## Doc Drift Notes

These markdown files are useful, but they are not perfectly aligned with the current codebase.

- `README.md` focuses on the user frontend and backend and gives little coverage to `artifacts/admin-dashboard`
- `SETUP.md` still mentions Clerk and Google-user admin flows in places, while the current codebase is centered on custom auth
- `replit.md` is valuable for rules and feature notes, but some operational details should be verified against code before treating them as current source of truth

## Local Code Indexes

These were added to give code-first indexes next to each app:

- `artifacts/stock-market-app/document.md`
- `artifacts/python-backend/document.md`
- `artifacts/admin-dashboard/document.md`
