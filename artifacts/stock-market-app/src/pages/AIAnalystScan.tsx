import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import { Link, useSearch } from "wouter";
import {
  Microscope, Loader2, AlertCircle, ListChecks, RotateCw,
  TrendingUp, TrendingDown, Minus, ArrowUpDown, Check, Clock, Ban,
  Bookmark,
} from "lucide-react";
import { useCustomAuth } from "@/context/CustomAuthContext";

type Verdict = "BUY" | "HOLD" | "SELL";
type Confidence = "LOW" | "MEDIUM" | "HIGH";
type RowStatus = "queued" | "analyzing" | "cached" | "saved" | "analyzed" | "skipped" | "error";

interface ScanReport {
  ticker: string;
  name?: string;
  verdict?: Verdict;
  confidence?: Confidence;
  headline?: string;
  priceTarget?: string;
  horizon?: string;
}

interface Row {
  ticker: string;
  status: RowStatus;
  report?: ScanReport;
  error?: string;
  reason?: string;
  savedAt?: string;
}

interface Watchlist {
  id: string;
  name: string;
  symbols: string[];
}

const STORAGE_KEY = "tv_watchlists_v3";

function loadWatchlists(): Watchlist[] {
  try {
    const s = localStorage.getItem(STORAGE_KEY);
    if (s) return JSON.parse(s);
    const old = localStorage.getItem("tv_watchlists_v2");
    if (old) return JSON.parse(old);
  } catch {}
  return [
    { id: "default", name: "Nifty 50",
      symbols: ["RELIANCE","TCS","HDFCBANK","INFY","ICICIBANK","SBIN","BHARTIARTL","KOTAKBANK","BAJFINANCE","AXISBANK"] },
  ];
}

const VERDICT_RANK: Record<Verdict, number> = { BUY: 0, HOLD: 1, SELL: 2 };
const CONF_RANK: Record<Confidence, number> = { HIGH: 0, MEDIUM: 1, LOW: 2 };

function VerdictBadge({ v }: { v?: Verdict }) {
  if (!v) return <span className="text-xs text-gray-400">—</span>;
  const map = {
    BUY:  { bg: "bg-green-100 text-green-700 dark:bg-green-500/20 dark:text-green-300", Icon: TrendingUp },
    HOLD: { bg: "bg-amber-100 text-amber-700 dark:bg-amber-500/20 dark:text-amber-300", Icon: Minus },
    SELL: { bg: "bg-red-100 text-red-700 dark:bg-red-500/20 dark:text-red-300", Icon: TrendingDown },
  } as const;
  const { bg, Icon } = map[v];
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold ${bg}`}>
      <Icon className="w-3 h-3" />
      {v}
    </span>
  );
}

function StatusCell({ row }: { row: Row }) {
  switch (row.status) {
    case "queued":
      return <span className="text-xs text-gray-400 inline-flex items-center gap-1"><Clock className="w-3 h-3" />Queued</span>;
    case "analyzing":
      return <span className="text-xs text-indigo-600 dark:text-indigo-400 inline-flex items-center gap-1"><Loader2 className="w-3 h-3 animate-spin" />Analyzing</span>;
    case "cached":
    case "saved":
      return (
        <span
          className="text-xs text-emerald-600 dark:text-emerald-400 inline-flex items-center gap-1"
          title={row.savedAt
            ? `Saved on ${new Date(row.savedAt).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })}`
            : "Loaded from your saved analyses"}
        >
          <Bookmark className="w-3 h-3" />Saved
        </span>
      );
    case "analyzed":
      return <span className="text-xs text-emerald-600 dark:text-emerald-400 inline-flex items-center gap-1"><Check className="w-3 h-3" />Fresh</span>;
    case "skipped":
      return <span className="text-xs text-amber-600 dark:text-amber-400 inline-flex items-center gap-1" title={row.reason || ""}><Ban className="w-3 h-3" />Skipped</span>;
    case "error":
      return <span className="text-xs text-red-600 dark:text-red-400 inline-flex items-center gap-1" title={row.error || ""}><AlertCircle className="w-3 h-3" />Error</span>;
  }
}

type SortKey = "ticker" | "verdict" | "confidence" | "status";

export default function AIAnalystScan() {
  const { token } = useCustomAuth();
  const search = useSearch();
  const queryParams = useMemo(() => new URLSearchParams(search || ""), [search]);

  // Ad-hoc tickers passed via `?tickers=A,B,C` (e.g. when re-opening a saved
  // group from Saved Analyses) take precedence over the local watchlist
  // picker and run as their own group. `?name=...` sets an optional label,
  // `?rerun=1` immediately forces a fresh re-scan that overwrites the saved
  // entry instead of loading it from the saved store.
  const adhocTickers = useMemo(() => {
    const raw = queryParams.get("tickers") || "";
    return raw.split(",").map(s => s.trim().toUpperCase()).filter(Boolean);
  }, [queryParams]);

  const [watchlists] = useState<Watchlist[]>(loadWatchlists);
  const [activeId, setActiveId] = useState<string>(watchlists[0]?.id || "");
  const [groupName, setGroupName] = useState<string>(queryParams.get("name") || "");
  const [rows, setRows] = useState<Row[]>([]);
  const [running, setRunning] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [quota, setQuota] = useState<{ used: number; limit: number; remaining: number } | null>(null);
  const [summary, setSummary] = useState<{ cached: number; analyzed: number; skipped: number; errors: number } | null>(null);
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>("verdict");
  const [sortAsc, setSortAsc] = useState(true);
  const abortRef = useRef<AbortController | null>(null);
  // Tracks which symbol-set we've already attempted to auto-load from the
  // saved store, so switching the watchlist re-runs the lookup but the
  // same selection doesn't re-fetch on every render.
  const autoLoadedKeyRef = useRef<string>("");
  // Monotonic scan id — only the most recent scan is allowed to mutate
  // shared state (running / rows / summary). Stale callbacks from an
  // aborted previous scan compare their captured id against this ref and
  // bail out, preventing the stop-then-restart race that would otherwise
  // flip `running` back to false while the new scan is still active.
  const scanIdRef = useRef(0);

  const active = watchlists.find(w => w.id === activeId) || watchlists[0];
  // Effective symbols for the next scan: if the URL provided ad-hoc tickers,
  // they win; otherwise we use whichever watchlist is selected.
  const effectiveSymbols = adhocTickers.length > 0
    ? adhocTickers
    : (active?.symbols || []).map(s => s.toUpperCase());

  useEffect(() => {
    if (!token) return;
    fetch("/api/ai-analyst/quota", { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.ok ? r.json() : null).then(q => q && setQuota(q)).catch(() => {});
  }, [token]);

  // Abort any in-flight SSE on unmount
  useEffect(() => () => abortRef.current?.abort(), []);

  const upsertRow = useCallback((ticker: string, patch: Partial<Row>) => {
    setRows(prev => {
      const idx = prev.findIndex(r => r.ticker === ticker);
      if (idx === -1) return [...prev, { ticker, status: "queued", ...patch } as Row];
      const next = prev.slice();
      next[idx] = { ...next[idx], ...patch };
      return next;
    });
  }, []);

  const start = useCallback(async (force = false) => {
    if (!token || running) return;
    if (effectiveSymbols.length === 0) return;
    abortRef.current?.abort();
    const ctl = new AbortController();
    abortRef.current = ctl;
    const myScanId = ++scanIdRef.current;
    const isCurrent = () => scanIdRef.current === myScanId;

    // Backend caps a single scan at 50 tickers — slice the symbols list and
    // surface a note instead of failing the whole request.
    const MAX_PER_SCAN = 50;
    const allSymbols = effectiveSymbols;
    const symbols = allSymbols.slice(0, MAX_PER_SCAN);
    const trimmedNote = allSymbols.length > MAX_PER_SCAN
      ? `Group has ${allSymbols.length} tickers — scanning the first ${MAX_PER_SCAN}. Run again for the rest tomorrow.`
      : null;

    setRunning(true);
    setErr(trimmedNote);
    setSummary(null);
    setSavedAt(null);
    setRows(symbols.map(s => ({ ticker: s, status: "queued" })));

    try {
      const resp = await fetch("/api/ai-analyst/scan", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          tickers: symbols,
          force,
          ...(groupName.trim() ? { name: groupName.trim() } : {}),
        }),
        signal: ctl.signal,
      });
      if (!isCurrent()) return; // superseded between fetch start and headers
      if (!resp.ok || !resp.body) {
        let msg = `HTTP ${resp.status}`;
        try { const j = await resp.json(); msg = j.detail || j.error || msg; } catch {}
        throw new Error(msg);
      }

      const reader = resp.body.getReader();
      const dec = new TextDecoder();
      let buf = "";
      while (true) {
        const { value, done } = await reader.read();
        if (!isCurrent()) return; // superseded mid-stream; let new scan own state
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const frames = buf.split("\n\n");
        buf = frames.pop() || "";
        for (const f of frames) {
          const line = f.split("\n").find(l => l.startsWith("data: "));
          if (!line) continue;
          let ev: any; try { ev = JSON.parse(line.slice(6)); } catch { continue; }
          if (ev.phase === "item") {
            const isPersisted = ev.status === "saved" || ev.status === "cached";
            upsertRow(ev.ticker, { status: isPersisted ? "saved" : "analyzing" });
          } else if (ev.phase === "result") {
            // Backend now emits status="saved" instead of "cached"; tolerate both.
            const raw = ev.status as string;
            const status: RowStatus = raw === "cached" ? "saved" : (raw as RowStatus);
            upsertRow(ev.ticker, {
              status,
              report: ev.report ? {
                ticker: ev.report.ticker,
                name: ev.report.name,
                verdict: ev.report.verdict,
                confidence: ev.report.confidence,
                headline: ev.report.headline,
                priceTarget: ev.report.priceTarget,
                horizon: ev.report.horizon,
              } : undefined,
              error: ev.error,
              reason: ev.reason,
              savedAt: ev.report?.cachedAt || ev.report?.savedAt,
            });
          } else if (ev.phase === "done") {
            // Backend `done` event fields:
            //   cached  — number of items served from the saved store
            //   analyzed/skipped/errors — numeric counters
            //   saved   — metadata object for the persisted group entry
            //             ({id, scopeKey, ...}) — NEVER a number
            setSummary({
              cached: Number(ev.cached) || 0,
              analyzed: Number(ev.analyzed) || 0,
              skipped: Number(ev.skipped) || 0,
              errors: Number(ev.errors) || 0,
            });
            if (ev.quota) setQuota(ev.quota);
            // The group entry was just persisted — surface the timestamp so
            // the saved banner appears immediately without a page reload.
            setSavedAt(new Date().toISOString());
          }
        }
      }
    } catch (e: any) {
      if (isCurrent() && e?.name !== "AbortError") setErr(e?.message || "Scan failed");
    } finally {
      // Only the current scan is allowed to flip `running` back off, so an
      // aborted earlier scan can't race the new one's button state.
      if (isCurrent()) setRunning(false);
    }
  }, [token, running, upsertRow, effectiveSymbols, groupName]);

  // Auto-load the saved group entry (if any) for whatever symbol-set is
  // currently selected — both for ad-hoc tickers from the URL and for the
  // normal watchlist picker. This means re-opening the page with the same
  // watchlist instantly shows the previously saved scan with a banner +
  // Re-run button, no manual Scan press required.
  //
  // ?rerun=1 (only meaningful when the URL also carries ad-hoc tickers,
  // e.g. from Saved Analyses) bypasses the saved load and forces a fresh
  // scan that overwrites the saved entry.
  useEffect(() => {
    if (!token) return;
    if (running) return;
    if (effectiveSymbols.length === 0) return;
    const key = effectiveSymbols.join(",");
    if (autoLoadedKeyRef.current === key) return;
    autoLoadedKeyRef.current = key;

    const wantRerun = adhocTickers.length > 0 && queryParams.get("rerun") === "1";
    if (wantRerun) {
      void start(true);
      return;
    }

    let cancelled = false;
    (async () => {
      try {
        const r = await fetch(
          `/api/ai-analyst/saved/group?tickers=${encodeURIComponent(effectiveSymbols.join(","))}`,
          { headers: { Authorization: `Bearer ${token}` } });
        if (cancelled) return;
        if (!r.ok) {
          // No saved entry for this watchlist yet — leave the empty state up
          // so the user can press Scan when they're ready. We never auto-run
          // a fresh scan from a watchlist switch (that would silently burn
          // quota).
          setRows([]); setSummary(null); setSavedAt(null);
          return;
        }
        const j = await r.json();
        const items = (j?.report?.items || []) as any[];
        if (items.length === 0) {
          setRows([]); setSummary(null); setSavedAt(null);
          return;
        }
        setSavedAt(j.savedAt || null);
        if (j?.report?.name && !groupName) setGroupName(j.report.name);
        setRows(items.map((it: any) => ({
          ticker: it.ticker,
          status: (it.status === "cached" ? "saved" : it.status) as RowStatus,
          report: it.report ? {
            ticker: it.report.ticker,
            name: it.report.name,
            verdict: it.report.verdict,
            confidence: it.report.confidence,
            headline: it.report.headline,
            priceTarget: it.report.priceTarget,
            horizon: it.report.horizon,
          } : undefined,
          error: it.error,
          reason: it.reason,
          savedAt: j.savedAt,
        })));
        const counts = j?.report?.counts || {};
        setSummary({
          cached: counts.saved ?? counts.cached ?? items.filter(i => i.status === "saved" || i.status === "cached").length,
          analyzed: counts.analyzed ?? items.filter(i => i.status === "analyzed").length,
          skipped: counts.skipped ?? items.filter(i => i.status === "skipped").length,
          errors: counts.errors ?? items.filter(i => i.status === "error").length,
        });
      } catch {
        // Network blip — leave the page in its empty state; the user can
        // still press Scan manually.
      }
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, effectiveSymbols.join(",")]);

  const stop = useCallback(() => {
    // Bump the scan id so any in-flight callbacks bail out on isCurrent().
    scanIdRef.current++;
    abortRef.current?.abort();
    setRunning(false);
  }, []);

  const sortedRows = useMemo(() => {
    const arr = rows.slice();
    arr.sort((a, b) => {
      let cmp = 0;
      if (sortKey === "ticker") cmp = a.ticker.localeCompare(b.ticker);
      else if (sortKey === "verdict") {
        const av = a.report?.verdict ? VERDICT_RANK[a.report.verdict] : 99;
        const bv = b.report?.verdict ? VERDICT_RANK[b.report.verdict] : 99;
        cmp = av - bv;
      } else if (sortKey === "confidence") {
        const av = a.report?.confidence ? CONF_RANK[a.report.confidence] : 99;
        const bv = b.report?.confidence ? CONF_RANK[b.report.confidence] : 99;
        cmp = av - bv;
      } else if (sortKey === "status") {
        cmp = a.status.localeCompare(b.status);
      }
      return sortAsc ? cmp : -cmp;
    });
    return arr;
  }, [rows, sortKey, sortAsc]);

  const toggleSort = (k: SortKey) => {
    if (sortKey === k) setSortAsc(a => !a);
    else { setSortKey(k); setSortAsc(true); }
  };

  return (
    <div className="max-w-6xl mx-auto p-4 space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
            <Microscope className="w-5 h-5 text-indigo-600" />
            Scan watchlist with AI Analyst
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Run the deep analyst across every stock in a watchlist. Saved
            reports are free; fresh analyses respect your daily quota.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Link href="/ai-analyst"
                className="text-xs px-3 py-1.5 rounded-md border border-gray-200 dark:border-white/10 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/5">
            Single ticker
          </Link>
          <Link href="/ai-analyst/compare"
                className="text-xs px-3 py-1.5 rounded-md border border-gray-200 dark:border-white/10 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/5">
            Compare two
          </Link>
          <Link href="/ai-analyst/saved"
                className="text-xs px-3 py-1.5 rounded-md border border-gray-200 dark:border-white/10 text-indigo-600 dark:text-indigo-400 hover:bg-gray-50 dark:hover:bg-white/5 inline-flex items-center gap-1.5">
            <Bookmark className="w-3.5 h-3.5" /> Saved analyses
          </Link>
        </div>
      </div>

      {savedAt && rows.length > 0 && !running && (
        <div className="rounded-md border border-indigo-200 dark:border-indigo-500/30 bg-indigo-50 dark:bg-indigo-500/10 p-3 flex items-center gap-3 flex-wrap">
          <Bookmark className="w-4 h-4 text-indigo-600 dark:text-indigo-400 flex-shrink-0" />
          <p className="text-xs text-indigo-900 dark:text-indigo-100 flex-1 min-w-0">
            {groupName ? <><strong>{groupName}</strong> · </> : null}
            Saved on{" "}
            <strong>
              {new Date(savedAt).toLocaleDateString("en-IN", {
                day: "numeric", month: "short", year: "numeric",
              })}
            </strong>{" "}
            · Re-run to refresh every stock in this group.
          </p>
          <button
            onClick={() => start(true)}
            disabled={running}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-xs font-semibold"
          >
            <RotateCw className="w-3.5 h-3.5" /> Re-run
          </button>
        </div>
      )}

      {/* Controls */}
      <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-white/10 rounded-xl p-4 flex flex-wrap items-end gap-3">
        {adhocTickers.length === 0 ? (
          <div className="flex-1 min-w-[200px]">
            <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Watchlist</label>
            <select
              value={activeId}
              onChange={e => setActiveId(e.target.value)}
              disabled={running}
              className="w-full px-3 py-2 rounded-md border border-gray-200 dark:border-white/10 bg-white dark:bg-gray-950 text-sm text-gray-900 dark:text-white"
            >
              {watchlists.map(w => (
                <option key={w.id} value={w.id}>{w.name} ({w.symbols.length})</option>
              ))}
            </select>
          </div>
        ) : (
          <div className="flex-1 min-w-[200px]">
            <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Group ({adhocTickers.length} tickers)</label>
            <div className="px-3 py-2 rounded-md border border-gray-200 dark:border-white/10 bg-gray-50 dark:bg-gray-950 text-xs text-gray-700 dark:text-gray-300 truncate">
              {adhocTickers.join(", ")}
            </div>
          </div>
        )}
        <div className="min-w-[180px]">
          <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Group name (optional)</label>
          <input
            value={groupName}
            onChange={e => setGroupName(e.target.value)}
            disabled={running}
            placeholder="e.g. My banks"
            className="w-full px-3 py-2 rounded-md border border-gray-200 dark:border-white/10 bg-white dark:bg-gray-950 text-sm text-gray-900 dark:text-white placeholder:text-gray-400"
          />
        </div>
        <div className="text-xs text-gray-500 dark:text-gray-400">
          Quota: <span className="font-semibold text-gray-900 dark:text-white">{quota ? `${quota.remaining}/${quota.limit}` : "—"}</span> fresh runs left today
        </div>
        {!running ? (
          <button
            onClick={() => start(false)}
            disabled={effectiveSymbols.length === 0 || !token}
            title={quota?.remaining === 0
              ? "Daily quota exhausted — saved reports will still be shown; un-saved tickers will be marked skipped."
              : undefined}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-md bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-sm font-medium"
          >
            <ListChecks className="w-4 h-4" />
            Scan {effectiveSymbols.length} stocks
          </button>
        ) : (
          <button onClick={stop}
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-md bg-gray-200 dark:bg-white/10 text-gray-900 dark:text-white text-sm font-medium">
            <RotateCw className="w-4 h-4" /> Stop
          </button>
        )}
      </div>

      {err && (
        <div className="rounded-md border border-red-200 dark:border-red-900/40 bg-red-50 dark:bg-red-900/20 p-3 text-sm text-red-700 dark:text-red-300 flex items-start gap-2">
          <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
          <span>{err}</span>
        </div>
      )}

      {summary && (
        <div className="rounded-md border border-gray-200 dark:border-white/10 bg-gray-50 dark:bg-gray-900/40 p-3 text-sm text-gray-700 dark:text-gray-300 flex flex-wrap gap-x-4 gap-y-1">
          <span><strong className="text-emerald-700 dark:text-emerald-400">{summary.cached}</strong> from saved</span>
          <span><strong className="text-emerald-700 dark:text-emerald-400">{summary.analyzed}</strong> freshly analyzed</span>
          {summary.skipped > 0 && (
            <span><strong className="text-amber-700 dark:text-amber-400">{summary.skipped}</strong> skipped (quota)</span>
          )}
          {summary.errors > 0 && (
            <span><strong className="text-red-700 dark:text-red-400">{summary.errors}</strong> failed</span>
          )}
          {summary.skipped > 0 && (
            <span className="text-gray-500 dark:text-gray-400">
              Daily quota exhausted — try the skipped tickers tomorrow, or open them individually if you have a fresh slot.
            </span>
          )}
        </div>
      )}

      {/* Results table */}
      {rows.length > 0 && (
        <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-white/10 rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 dark:bg-gray-900/60 text-xs uppercase tracking-wide text-gray-500 dark:text-gray-400">
              <tr>
                <th className="text-left px-3 py-2 cursor-pointer" onClick={() => toggleSort("ticker")}>
                  <span className="inline-flex items-center gap-1">Ticker <ArrowUpDown className="w-3 h-3" /></span>
                </th>
                <th className="text-left px-3 py-2 cursor-pointer" onClick={() => toggleSort("verdict")}>
                  <span className="inline-flex items-center gap-1">Verdict <ArrowUpDown className="w-3 h-3" /></span>
                </th>
                <th className="text-left px-3 py-2 cursor-pointer" onClick={() => toggleSort("confidence")}>
                  <span className="inline-flex items-center gap-1">Confidence <ArrowUpDown className="w-3 h-3" /></span>
                </th>
                <th className="text-left px-3 py-2">Headline</th>
                <th className="text-left px-3 py-2 cursor-pointer" onClick={() => toggleSort("status")}>
                  <span className="inline-flex items-center gap-1">Status <ArrowUpDown className="w-3 h-3" /></span>
                </th>
                <th className="text-left px-3 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {sortedRows.map(row => (
                <tr key={row.ticker} className="border-t border-gray-100 dark:border-white/5 align-top">
                  <td className="px-3 py-2 font-mono font-semibold text-gray-900 dark:text-white">{row.ticker}</td>
                  <td className="px-3 py-2"><VerdictBadge v={row.report?.verdict} /></td>
                  <td className="px-3 py-2 text-gray-700 dark:text-gray-300">
                    {row.report?.confidence
                      ? <span className="text-xs px-1.5 py-0.5 rounded bg-gray-100 dark:bg-white/5">{row.report.confidence}</span>
                      : <span className="text-xs text-gray-400">—</span>}
                  </td>
                  <td className="px-3 py-2 text-gray-700 dark:text-gray-300 max-w-md">
                    <div className="line-clamp-2">{row.report?.headline || row.error || row.reason || "—"}</div>
                  </td>
                  <td className="px-3 py-2"><StatusCell row={row} /></td>
                  <td className="px-3 py-2">
                    <Link href={`/ai-analyst/${encodeURIComponent(row.ticker)}`}
                          className="text-xs text-indigo-600 dark:text-indigo-400 hover:underline">
                      Open →
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {rows.length === 0 && !running && (
        <div className="text-center text-sm text-gray-500 dark:text-gray-400 py-12">
          Pick a watchlist above and hit <strong>Scan</strong> to run the AI Analyst across every stock in it.
        </div>
      )}
    </div>
  );
}
