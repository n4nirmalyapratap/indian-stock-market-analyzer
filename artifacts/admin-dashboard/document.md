# Admin Frontend Index

This file is a quick index for the admin React app in `artifacts/admin-dashboard`.

## Purpose

- Serves the admin dashboard at `/admin`
- Uses session-based admin authentication
- Manages users, logs, jobs, secrets, bugs, audits, and bot operations

## Markdown Sources Reviewed

- Root `SETUP.md`
- Root `README.md`
- Root `replit.md`
- Root `DOCUMENTATION_INDEX.md`

## Main Entry Points

| File | Role |
|---|---|
| `src/main.tsx` | React bootstrap |
| `src/App.tsx` | Admin shell, nav, route switch, and login gate |
| `src/lib/api.ts` | Admin API client and session token helpers |
| `src/index.css` | Shared styling entry |

## Auth Model

- Login posts to `/api/admin/login`
- Returned admin token is stored in `sessionStorage`
- Authenticated requests send `X-Admin-Token`
- A 401 response clears the session and returns the user to the login screen

## Routed Pages

These routes are wired in `src/App.tsx`.

| Route | File | Main responsibility |
|---|---|---|
| `/` | `src/pages/AppStatus.tsx` | Backend status, uptime, endpoint count, and configuration health |
| `/jobs` | `src/pages/JobsPage.tsx` | View and trigger admin jobs |
| `/users` | `src/pages/UsersPage.tsx` | Create, list, and delete app users |
| `/whatsapp` | `src/pages/WhatsAppBot.tsx` | WhatsApp bot status and test messaging |
| `/telegram` | `src/pages/TelegramBot.tsx` | Telegram bot status, history, and testing |
| `/logs` | `src/pages/LogsPage.tsx` | Structured live log viewer |
| `/bugs` | `src/pages/BugReportsPage.tsx` | Bug list, edit flow, delete flow, and AI bug analyser |
| `/sebi` | `src/pages/SebiAuditPage.tsx` | Run SEBI audits and browse generated reports |
| `/secrets` | `src/pages/SecretsPage.tsx` | Manage stored secrets and validation |

## Supporting Pages

- `src/pages/LoginPage.tsx` handles admin sign-in before the route shell renders
- `src/pages/not-found.tsx` is the fallback route

## API Touchpoints

The admin frontend mainly uses `src/lib/api.ts` plus direct `fetchAdmin(...)` calls inside some pages.

| Backend area | Used by |
|---|---|
| `/admin/login` | `LoginPage.tsx` |
| `/admin/status` | `AppStatus.tsx` |
| `/admin/users/app`, `/admin/users/create`, `/admin/users/app/{id}` | `UsersPage.tsx` |
| `/admin/logs` | `LogsPage.tsx` |
| `/admin/jobs`, `/admin/jobs/{job_id}/run` | `JobsPage.tsx` |
| `/admin/bugs*` | `BugReportsPage.tsx` |
| `/admin/secrets*` | `SecretsPage.tsx` |
| `/options/sebi-audit`, `/options/sebi-reports` | `SebiAuditPage.tsx` |
| `/telegram/*` | `TelegramBot.tsx` |
| `/whatsapp/*` | `WhatsAppBot.tsx` |

## Navigation Summary

The admin sidebar is defined directly in `src/App.tsx`:

- App Status
- Jobs
- Users
- WhatsApp Bot
- Telegram Bot
- Logs
- Bug Tracker
- SEBI Audit
- Secrets

## Shared UI Structure

| Path | What is there |
|---|---|
| `src/components/ui/` | Shared UI primitives used across admin pages |
| `src/hooks/` | Small shared hooks like mobile/toast helpers |
| `src/lib/utils.ts` | Local utility helpers |

## Related Repo Docs

- Root `SETUP.md` for `/admin` routing, credentials, and Docker setup
- Root `README.md` for overall project architecture
- Root `replit.md` for admin feature and workflow context
- Root `DOCUMENTATION_INDEX.md` for the markdown-level doc map
