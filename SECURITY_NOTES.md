# Security Notes — Manual Action Items

The code-review fixes applied automatically have closed many holes, but a few
items can only be done by you. Work through this list before deploying.

## 1. Rotate every credential that touched `.env`

Treat the following as compromised — they are sitting in `.env` on your
development machine, which means they are in any local backup, IDE-sync
cloud, screenshot share, etc. Rotate at the source, then update `.env`:

| Service | Where to rotate | Replace value of |
|---|---|---|
| OpenRouter (LLM) | https://openrouter.ai → API Keys | `AI_INTEGRATIONS_OPENROUTER_API_KEY` |
| FRED (St Louis Fed) | https://fred.stlouisfed.org/docs/api/api_key.html | `FRED_API_KEY` |
| Admin login | (you choose) | `ADMIN_PASSWORD` |
| GitHub Container Registry PAT | https://github.com/settings/tokens | secret in `containerapp-config.yaml` (now placeholder) |

After rotating, commit nothing. `.env` is correctly listed in `.gitignore`,
but verify with:

```bash
git log --all --full-history -- .env
```

If anything shows up, the keys leaked to the remote — rotate again and
scrub history with `git filter-repo`.

## 2. Set a strong `SESSION_SECRET` before starting the backend

The backend now refuses to start if `SESSION_SECRET` is missing, shorter
than 32 characters, or one of the well-known placeholder strings. Generate
a real value once and store it in your runtime environment:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Then set it via the appropriate channel:

- **Local dev**: edit `.env`, replace `replace_with_a_long_random_secret_here`
  with the generated value.
- **Replit**: open the Secrets tab, add `SESSION_SECRET`.
- **Azure Container Apps**: `az containerapp secret set --name stock-backend
  --resource-group stock-analyzer-rg --secrets session-secret=<generated>`
  then `az containerapp update --set-env-vars SESSION_SECRET=secretref:session-secret`.

Note: rotating `SESSION_SECRET` invalidates every existing JWT, so all logged-in
users will have to sign in again. That's expected and OK.

## 3. Configure webhook secrets if you use Telegram or Twilio

The Telegram and WhatsApp webhook handlers now verify per-provider
signatures. Without the right env vars set, both endpoints respond with
403 Forbidden — including legitimate calls.

### Telegram

1. Generate a webhook secret:
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```
2. Set it in your runtime as `TELEGRAM_WEBHOOK_SECRET`.
3. Re-register the webhook (the backend will auto-pass the secret to
   Telegram when you POST `/api/telegram/set-webhook`).

If you only use the polling-mode bot (the default — `main.py` calls
`delete_webhook` at startup), you can skip this step. The webhook endpoint
will simply return 503 if anyone hits it, which is fine.

### Twilio (WhatsApp)

1. The handler reads `TWILIO_AUTH_TOKEN` (already in `.env.example`) and
   computes the expected `X-Twilio-Signature` to compare against what
   Twilio sent.
2. If your backend is behind a reverse proxy that rewrites the URL,
   set `TWILIO_WEBHOOK_URL` to the public URL Twilio is calling. Otherwise
   it falls back to `request.url` as seen by FastAPI.

If you don't use Twilio at all, leave `TWILIO_AUTH_TOKEN` unset — the
endpoint will reject every request with 403, which is the safe default.

## 4. Pin and lock Python dependencies

`requirements.txt` now has lower AND upper bounds on every package, plus
explicit minimums to fix CVEs in `cryptography`, `lxml`, and
`python-multipart`. For full reproducibility in production, generate a
fully-pinned lock file:

```bash
cd artifacts/python-backend
pip install pip-tools
pip-compile --output-file=requirements.lock requirements.txt
# In Docker:
pip install -r requirements.lock
```

## 5. Production CORS

The backend now reads extra origins from `CORS_ALLOWED_ORIGINS` (comma
separated). Local dev hosts (`localhost:3002/5000/5173/5174/8080`) are
always allowed. When you deploy to Azure / your real domain, set:

```bash
CORS_ALLOWED_ORIGINS="https://stock-frontend.azurestaticapps.net,https://your-custom-domain.com"
```

The string `"*"` is ignored on purpose — wildcard CORS plus token-bearing
fetches lets any third-party site drive your API on the user's behalf.

## 6. The deleted-but-not-deleted dev-login pages

Two files were neutralised but left in the tree because deleting via the
file API isn't supported here:

- `artifacts/stock-market-app/public/_devlogin.html` — replaced with a
  redirect-to-`/sign-in` notice.
- `artifacts/admin-dashboard/public/auto-login.html` — hardened to validate
  the `to` redirect target and the `t` token shape.

If you want them gone entirely, delete them in your shell:

```bash
rm artifacts/stock-market-app/public/_devlogin.html
rm artifacts/admin-dashboard/public/auto-login.html
```

## 7. Containerapp deployment — populate the secrets

`containerapp-config.yaml` now uses `secretRef` placeholders. Before
deploying, populate them:

```bash
RG=stock-analyzer-rg
ADMIN_PWD=$(python -c "import secrets; print(secrets.token_urlsafe(24))")
SESSION_SECRET=$(python -c "import secrets; print(secrets.token_hex(32))")
GHCR_PAT=<paste a fresh GHCR PAT>

az containerapp secret set --name stock-backend --resource-group $RG \
  --secrets ghcr-password=$GHCR_PAT \
            admin-password=$ADMIN_PWD \
            session-secret=$SESSION_SECRET

echo "Save this admin password in your password manager NOW: $ADMIN_PWD"
```

## 8. Optional but recommended — pre-commit secret scanning

Add a pre-commit hook that refuses to commit anything containing
`sk-…`, `ghp_…`, etc.:

```bash
pip install pre-commit detect-secrets
detect-secrets scan > .secrets.baseline
```

Then add a `.pre-commit-config.yaml` and `pre-commit install`. This won't
unbreak anything that's already in git, but it stops the next leak.

---

Generated alongside the automated fixes. See `CODE_REVIEW.md` for the
underlying findings.
