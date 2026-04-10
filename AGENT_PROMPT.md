Set up the Indian Stock Market Analyzer on Replit with the following exact specifications.
Read every section in full before writing any code or running any commands.

─────────────────────────────────────────────
PART 1 — SOURCE & REPOSITORY
─────────────────────────────────────────────
Source: https://github.com/n4nirmalyapratap/indian-stock-market-analyzer
Branch: main

GitHub is connected via the Replit GitHub integration (OAuth — no personal access
token needed). Push using the custom script — NOT git push:

  pnpm --filter @workspace/scripts run push-github

After every meaningful change: push and share the commit URL with the user.

─────────────────────────────────────────────
PART 2 — MONOREPO STRUCTURE
─────────────────────────────────────────────
This is a pnpm workspace. pnpm-workspace.yaml includes:
  packages: [artifacts/*, lib/*, lib/integrations/*, scripts]

Active artifacts:
  artifacts/python-backend/   ← FastAPI backend (port 8090)
  artifacts/stock-market-app/ ← React/Vite frontend

DEPRECATED — never touch these:
  artifacts/nestjs-backend/   ← old Node.js backend, reference only
  artifacts/api-server/       ← repurposed artifact shell; actual code is python-backend

─────────────────────────────────────────────
PART 3 — PYTHON BACKEND SETUP
─────────────────────────────────────────────
Runtime: Python 3.11 (must be explicit — default Python may be 3.x generic)
Framework: FastAPI + uvicorn

requirements.txt (exact versions that work):
  fastapi>=0.110.0
  uvicorn[standard]>=0.27.0
  httpx>=0.27.0
  pandas>=2.0.0
  numpy>=1.26.0
  ta>=0.11.0
  spacy>=3.8.0
  python-multipart>=0.0.9
  openpyxl>=3.1.0
  yfinance>=0.2.48
  scipy>=1.11.0

Install with: pip3.11 install -r requirements.txt

Workflow command (use exactly this):
  bash -c 'cd /home/runner/workspace/artifacts/python-backend && PORT=8090 python run.py'

run.py MUST contain:
  1. A spaCy model self-heal block (before uvicorn starts):
       try:
           import spacy; spacy.load("en_core_web_sm")
       except OSError:
           subprocess.run([sys.executable, "-m", "spacy", "download",
                          "en_core_web_sm", "--break-system-packages"])
  2. uvicorn bound to host="0.0.0.0" (NOT localhost/127.0.0.1)
  3. Port read from env: int(os.environ.get("PORT", 8090))

FastAPI main.py MUST have CORSMiddleware allowing all origins for dev.

Health check to verify backend is live:
  curl http://localhost:8090/api/healthz

─────────────────────────────────────────────
PART 4 — FRONTEND SETUP
─────────────────────────────────────────────
Runtime: Node.js 24, pnpm
Framework: React 18 + Vite + TypeScript + TailwindCSS + TanStack Query
Router: wouter (NOT react-router)
UI: shadcn/ui

Workflow command (use exactly this — both env vars are REQUIRED):
  pnpm --filter @workspace/stock-market-app run dev

The workflow must set: PORT=<assigned port> and BASE_PATH=/

⚠️  CRITICAL — Vite will throw a hard error if PORT or BASE_PATH are not set:
  "PORT environment variable is required but was not provided."
  "BASE_PATH environment variable is required but was not provided."
  These are intentional checks in vite.config.ts — do not remove them.

vite.config.ts MUST contain:
  server: {
    port,                      ← from PORT env var
    host: "0.0.0.0",           ← required for Replit proxy
    allowedHosts: true,        ← required — Replit proxies from a different hostname
    proxy: {
      "/api": {
        target: "http://localhost:8090",
        changeOrigin: true,    ← proxies all /api/* to the Python backend
      },
    },
  },
  resolve: {
    dedupe: ["react", "react-dom"],  ← prevents duplicate React instance errors
  }

Verify full proxy routing works:
  curl http://localhost:80/api/sectors/rotation

─────────────────────────────────────────────
PART 5 — KNOWN SETUP ISSUES & SOLUTIONS
─────────────────────────────────────────────

ISSUE 1: spaCy model missing on first run
  Symptom: "Can't find model 'en_core_web_sm'" error at startup
  Fix: run.py auto-downloads it before uvicorn starts (see Part 3).
       If you set up run.py from scratch, include that self-heal block.
       On newer pip: add --break-system-packages to the download command.

ISSUE 2: GlobalAssistant location hook fails silently
  Symptom: useLocation() always returns "/" regardless of actual page
  Root cause: GlobalAssistant was placed OUTSIDE <WouterRouter> in App.tsx
  Fix: Place <GlobalAssistant /> INSIDE <WouterRouter>, after <Router />:
    <WouterRouter base={...}>
      <Router />
      <GlobalAssistant />   ← must be here, not outside WouterRouter
    </WouterRouter>

ISSUE 3: Vite dev server unreachable in preview pane
  Symptom: Blank preview or "connection refused"
  Fix: Ensure server.host="0.0.0.0" and server.allowedHosts=true in vite.config.ts
  Also check: the workflow is passing PORT as an env var, not hardcoded

ISSUE 4: Glass/transparent UI invisible in light mode
  Symptom: Floating buttons, badges, overlays disappear when switching to light mode
  Root cause: bg-white/10 + text-white is invisible on light backgrounds
  Fix: Always pair — solid color for light, glass for dark:
    bg-indigo-600 dark:bg-white/10   ← never use transparency alone

ISSUE 5: Python backend not reachable from frontend
  Symptom: /api/* requests return 404 or connection errors
  Fix: uvicorn must bind to 0.0.0.0 (not localhost). Check run.py host parameter.
  Also verify: vite proxy target is http://localhost:8090 with changeOrigin: true

ISSUE 6: Duplicate React instance runtime errors
  Symptom: "Invalid hook call" or context not working across packages
  Fix: Add resolve.dedupe: ["react", "react-dom"] in vite.config.ts

ISSUE 7: pnpm refuses to install a newly released package
  Symptom: "Package X does not meet the minimum release age requirement (1440 min)"
  Root cause: pnpm-workspace.yaml enforces a 1-day minimum age for packages
              (supply-chain attack protection — do NOT disable this setting)
  Fix: Add the package name to minimumReleaseAgeExclude in pnpm-workspace.yaml,
       only for trusted publishers, and remove it once the package is >1 day old

ISSUE 8: GitHub push fails with authentication error
  Symptom: Push script errors on auth
  Fix: Ensure the Replit GitHub integration is connected (OAuth, not PAT).
       The push script at scripts/src/push-github.ts uses the Replit connector.
       Run: pnpm --filter @workspace/scripts run push-github

ISSUE 9: yfinance returns None or empty data for Indian stocks
  Symptom: Stock data endpoints return empty arrays or NaN values
  Root cause: yfinance uses NSE/BSE tickers with .NS or .BO suffix
  Fix: All Indian stock symbols must be passed as "RELIANCE.NS", "TCS.NS" etc.
       The backend services handle this — do not change ticker formatting.

ISSUE 10: Learn tab visible on Chart Studio, blocking chart tools
  Symptom: The floating Learn tab overlaps the drawing toolbar on /trading
  Fix: GlobalAssistant checks the route and returns null on /trading and /chart/*:
    const isChartStudio = loc.startsWith("/trading") || loc.startsWith("/chart");
    if (isChartStudio) return null;

─────────────────────────────────────────────
PART 6 — APP PAGES
─────────────────────────────────────────────
  /           → Market Dashboard
  /trading    → Chart Studio (full candlestick chart — Learn tab hidden here)
  /sectors    → Market Sectors & rotation
  /stocks     → Stock Lookup
  /patterns   → Candlestick pattern detection
  /scanners   → Custom stock scanners
  /hydra      → AI Analyzer (NLP queries)
  /options    → Options Strategy Tester
  /settings   → Settings (WhatsApp/Telegram bot config)

─────────────────────────────────────────────
PART 7 — GLOBAL LEARNING ASSISTANT
─────────────────────────────────────────────
File: artifacts/stock-market-app/src/components/GlobalAssistant.tsx

A "peek tab" anchored to the right edge of the viewport (vertically centered):
- 28px wide vertical pill, flush to right edge, rounded on left side only
- Indigo→violet gradient, shows GraduationCap icon + vertical "LEARN" text + ChevronLeft
- On hover: expands to 44px, chevron shifts left
- First visit only: tooltip "Learn market concepts →" slides out after 1.2s,
  retracts after 5.2s, localStorage key "learn-hint-shown" prevents repeat
- Click → opens full-height right-side drawer with translucent backdrop
- Escape or backdrop click → closes drawer
- HIDDEN on /trading and /chart/* (Chart Studio)
- Uses useLocation() from wouter — MUST be inside WouterRouter in App.tsx
- Purely educational, client-side only, no API calls

─────────────────────────────────────────────
PART 8 — CHART STUDIO DEEP-LINK PATTERN
─────────────────────────────────────────────
ChartButton component: artifacts/stock-market-app/src/components/ChartButton.tsx

A subtle LineChart icon placed next to stock/sector names. Clicking it opens
Chart Studio (/trading?symbol=SYMBOLNAME) with that symbol pre-loaded.

Key rules:
- Strips .NS / .BO suffixes automatically (RELIANCE.NS → RELIANCE)
- Default opacity 30%, fades to 100% on hover with indigo highlight
- Works in both dark and light mode (uses dark: variants)
- TradingPlatform.tsx reads ?symbol= via useSearch() hook
- Back button in Chart Studio: cameFromLink.current ref — true when ?symbol= param
  was present on arrival. Back button renders at top-left of toolbar.

Usage:
  <ChartButton symbol="RELIANCE.NS" />   // stock (strips .NS)
  <ChartButton symbol="NIFTY BANK" />    // sector index

Currently placed:
  SectorDetail.tsx → sector header (data.symbol)
  SectorDetail.tsx → Constituents tab → every stock row

─────────────────────────────────────────────
PART 9 — DEVELOPMENT RULES
─────────────────────────────────────────────
1. Push to GitHub and share the commit link after every meaningful change.
2. Never mock data — always use the live Python backend.
3. Never hardcode colors — use Tailwind semantic classes + dark: variants.
4. Glass/transparent elements: solid color in light + glass in dark (see Issue 4).
5. Every UI change must work in both dark AND light mode — test both mentally.
6. Never place floating elements over data — use edge-anchored or sidebar patterns.
7. After code changes: restart the affected workflow and verify with a screenshot.
8. Never touch artifacts/nestjs-backend/ or artifacts/api-server/ source code.
9. Update replit.md whenever architecture or structure changes are made.
10. The Learn tab must never appear on /trading or /chart/* — it breaks the chart UX.
11. yfinance thread-safety: ALWAYS use yf.Ticker(ticker).history() NOT yf.download()
    when fetching multiple tickers concurrently.
12. Sectors with no Yahoo Finance history (^CNXOILGAS, ^CNXHEALTH, ^CNXFIN):
    use _synthetic_history() fallback in sector_analytics_service.py.

─────────────────────────────────────────────
PART 10 — SOURCE, REPOSITORY & GITHUB PUSH
─────────────────────────────────────────────
Source: https://github.com/n4nirmalyapratap/indian-stock-market-analyzer
Branch: main

GitHub is connected via the Replit GitHub integration (OAuth — no personal access
token needed). Push using the custom script — NOT git push:

  pnpm --filter @workspace/scripts run push-github

After every meaningful change: push and share the commit URL with the user.

See GITHUB_PUSH.md at the repo root for full documentation on the push script,
skip rules, rate limiting, and retry behaviour.

─── FIRST-TIME AUTHORIZATION (required once per workspace) ─────────────────────

The very first time the push script runs in a fresh Replit workspace, the GitHub
OAuth integration must be authorized by a human. The agent cannot do this.

When setting up a new workspace, the agent MUST stop and say:

  "Before I can push to GitHub, I need you to authorize the GitHub integration.
   Please open Tools → Integrations in the Replit sidebar, find GitHub, click
   Connect, and complete the authorization popup. Let me know when it's done."

Steps for the user:
  1. Replit sidebar → Tools → Integrations (plug icon)
  2. Find GitHub → click Connect
  3. GitHub OAuth popup opens — sign in if needed → click Authorize Replit
  4. Popup closes, status shows Connected
  5. Tell the agent "GitHub is authorized" — agent then runs the push script

Symptoms of missing authorization:
  - Push script errors with: HTTP_401: Bad credentials
  - Push script errors with: Cannot proxy request — no connection found
  Do NOT attempt to fix this in code — it requires the OAuth popup above.

─── SUBSEQUENT PUSHES ──────────────────────────────────────────────────────────

Once authorized, just run:
  pnpm --filter @workspace/scripts run push-github

No further human interaction needed. Output will include a commit URL like:
  https://github.com/n4nirmalyapratap/indian-stock-market-analyzer/commit/<sha>
