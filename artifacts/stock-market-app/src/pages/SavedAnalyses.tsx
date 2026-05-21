import { useEffect, useState, useCallback, useMemo } from "react";
import { Link, useLocation } from "wouter";
import {
  Microscope, Search, Trash2, RotateCw, ExternalLink,
  TrendingUp, TrendingDown, Minus, Loader2, AlertCircle,
  Building2, GitCompare, ListChecks,
} from "lucide-react";
import { useCustomAuth } from "@/context/CustomAuthContext";
import { api } from "@/lib/api";

type Scope = "single" | "pair" | "group";
type Verdict = "BUY" | "HOLD" | "SELL";

interface SavedRow {
  id: number;
  scope: Scope;
  scopeKey: string;
  tickers: string[];
  label: string | null;
  verdict: Verdict | null;
  confidence: string | null;
  headline: string | null;
  savedAt: string;
  createdAt: string;
}

const VERDICT_STYLE: Record<Verdict, string> = {
  BUY:  "bg-green-100 text-green-700 dark:bg-green-500/20 dark:text-green-300",
  HOLD: "bg-amber-100 text-amber-700 dark:bg-amber-500/20 dark:text-amber-300",
  SELL: "bg-red-100   text-red-700   dark:bg-red-500/20   dark:text-red-300",
};
const VERDICT_ICON: Record<Verdict, any> = {
  BUY: TrendingUp, HOLD: Minus, SELL: TrendingDown,
};

function VerdictBadge({ v }: { v: Verdict | null }) {
  if (!v) return null;
  const Icon = VERDICT_ICON[v];
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold ${VERDICT_STYLE[v]}`}>
      <Icon className="w-3 h-3" />
      {v}
    </span>
  );
}

async function _friendlyError(r: Response): Promise<string> {
  let raw = "";
  try { raw = await r.text(); } catch { /* ignore */ }
  let detail = "";
  try {
    const j = JSON.parse(raw);
    detail = String(j?.detail || j?.error || j?.message || "").trim();
  } catch { detail = raw.trim(); }
  if (r.status === 401 || r.status === 403) return "You're signed out. Please sign in again to view your saved analyses.";
  if (r.status === 404) return "We couldn't find that saved analysis — it may have been deleted or re-run.";
  if (r.status === 429) return "You've hit today's limit. Please try again later.";
  if (r.status >= 500) return "Our server hit a snag. Please try again in a moment.";
  if (detail && !/^not found$/i.test(detail)) return detail;
  return `Something went wrong (HTTP ${r.status}). Please try again.`;
}

function _friendlyMessage(e: any): string {
  const m = String(e?.message || e || "").trim();
  if (!m) return "Something went wrong. Please try again.";
  if (/failed to fetch|network|load failed/i.test(m)) {
    return "Can't reach the server right now. Check your connection and try again.";
  }
  // Avoid leaking raw JSON like {"detail":"Not Found"} into the UI.
  if (m.startsWith("{") || m.startsWith("[")) {
    try {
      const j = JSON.parse(m);
      const d = String(j?.detail || j?.error || j?.message || "").trim();
      if (d && !/^not found$/i.test(d)) return d;
    } catch { /* fall through */ }
    return "Something went wrong. Please try again.";
  }
  return m;
}

function fmtDate(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
  } catch {
    return iso;
  }
}

const TABS: { key: Scope; label: string; Icon: any }[] = [
  { key: "single", label: "Stocks", Icon: Building2 },
  { key: "pair",   label: "Pairs",  Icon: GitCompare },
  { key: "group",  label: "Groups", Icon: ListChecks },
];

const EMPTY_COPY: Record<Scope, { title: string; body: string; cta: { href: string; label: string } }> = {
  single: {
    title: "No saved stock analyses yet",
    body:  "Run a Deep AI Analysis on any stock and it'll show up here, kept until you re-run it.",
    cta:   { href: "/ai-analyst", label: "Analyse a stock →" },
  },
  pair: {
    title: "No saved pair comparisons yet",
    body:  "Compare two stocks side-by-side and the result will be saved here.",
    cta:   { href: "/ai-analyst/compare", label: "Compare two stocks →" },
  },
  group: {
    title: "No saved watchlist scans yet",
    body:  "Scan a watchlist with AI Analyst and the whole group will be saved here.",
    cta:   { href: "/ai-analyst/scan", label: "Scan a watchlist →" },
  },
};

export default function SavedAnalyses() {
  const { token } = useCustomAuth();
  const [, navigate] = useLocation();
  const [tab, setTab] = useState<Scope>("single");
  const [q, setQ] = useState("");
  const [items, setItems] = useState<SavedRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  // Bulk-select state. Stored as a Set<number> so toggle is O(1) and the
  // header checkbox can reason about "all visible items selected" without
  // a linear scan on every render.
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [bulkBusy, setBulkBusy] = useState(false);

  const allVisibleIds = useMemo(() => items.map(i => i.id), [items]);
  const allSelected = allVisibleIds.length > 0 &&
                      allVisibleIds.every(id => selected.has(id));
  const toggleOne = (id: number) =>
    setSelected(s => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  const toggleAll = () =>
    setSelected(s =>
      allSelected ? new Set() : new Set(allVisibleIds));

  // Clear selection when the user switches tab/search so they don't
  // accidentally bulk-delete items they can't see anymore.
  useEffect(() => { setSelected(new Set()); }, [tab, q]);

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true); setErr(null);
    try {
      const url = `/api/ai-analyst/saved?scope=${tab}&q=${encodeURIComponent(q)}&limit=100`;
      const r = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
      // 404 from this endpoint means "nothing saved yet" — treat as empty list.
      if (r.status === 404) { setItems([]); return; }
      if (!r.ok) throw new Error(await _friendlyError(r));
      const j = await r.json();
      setItems(j.items || []);
    } catch (e: any) {
      setErr(_friendlyMessage(e));
    } finally {
      setLoading(false);
    }
  }, [tab, q, token]);

  useEffect(() => { void load(); }, [load]);

  const onDelete = async (row: SavedRow) => {
    if (!token) return;
    if (!confirm(`Delete this saved ${row.scope === "single" ? "stock analysis"
                  : row.scope === "pair" ? "pair comparison" : "watchlist scan"}?`)) return;
    setBusyId(row.id);
    try {
      const r = await fetch(`/api/ai-analyst/saved/${row.id}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!r.ok) throw new Error(await _friendlyError(r));
      setItems(prev => prev.filter(x => x.id !== row.id));
      // If this row was in the selection set, drop it.
      setSelected(s => { const n = new Set(s); n.delete(row.id); return n; });
    } catch (e: any) {
      setErr(_friendlyMessage(e));
    } finally {
      setBusyId(null);
    }
  };

  const onDeleteSelected = async () => {
    const ids = Array.from(selected);
    if (ids.length === 0) return;
    if (!confirm(`Delete ${ids.length} saved analyses? This cannot be undone.`)) return;
    setBulkBusy(true);
    setErr(null);
    try {
      const res = await api.deleteSavedAnalysesBulk(ids);
      // Remove every deleted id from the visible list. We rely on the
      // server's `deleted` count for the toast, but optimistically drop
      // all `ids` from the local state — any that weren't actually
      // deleted (e.g. concurrent delete from another tab) will re-appear
      // when the user refreshes or changes scope/search.
      setItems(prev => prev.filter(x => !selected.has(x.id)));
      setSelected(new Set());
      if (res.deleted < ids.length) {
        setErr(`Deleted ${res.deleted} of ${ids.length} — ${ids.length - res.deleted} were already gone.`);
      }
    } catch (e: any) {
      setErr(_friendlyMessage(e));
    } finally {
      setBulkBusy(false);
    }
  };

  const openHref = (row: SavedRow): string => {
    if (row.scope === "single") return `/ai-analyst/${encodeURIComponent(row.tickers[0] || "")}`;
    if (row.scope === "pair") {
      const [a, b] = row.tickers;
      return `/ai-analyst/compare?a=${encodeURIComponent(a || "")}&b=${encodeURIComponent(b || "")}`;
    }
    return `/ai-analyst/scan?tickers=${encodeURIComponent(row.tickers.join(","))}`
         + (row.label ? `&name=${encodeURIComponent(row.label)}` : "");
  };

  const onRerun = (row: SavedRow) => {
    navigate(`${openHref(row)}${openHref(row).includes("?") ? "&" : "?"}rerun=1`);
  };

  const empty = EMPTY_COPY[tab];
  const counts = useMemo(() => {
    const c = { single: 0, pair: 0, group: 0 };
    items.forEach(i => { if (c[i.scope] != null) c[i.scope]++; });
    return c;
  }, [items]);

  return (
    <div className="max-w-5xl mx-auto p-4 space-y-4">
      <div className="flex items-center gap-3 flex-wrap">
        <div className="w-10 h-10 rounded-lg bg-indigo-100 dark:bg-indigo-500/20 flex items-center justify-center">
          <Microscope className="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
        </div>
        <div className="flex-1 min-w-0">
          <h1 className="text-xl font-bold text-gray-900 dark:text-white">Saved Analyses</h1>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            Every Deep AI Analyst run is saved here until you re-run it. Re-runs overwrite the saved copy.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Link href="/ai-analyst"
                className="text-xs px-3 py-1.5 rounded-md border border-gray-200 dark:border-white/10 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/5">
            Single ticker
          </Link>
          <Link href="/ai-analyst/compare"
                className="text-xs px-3 py-1.5 rounded-md border border-gray-200 dark:border-white/10 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/5">
            Compare
          </Link>
          <Link href="/ai-analyst/scan"
                className="text-xs px-3 py-1.5 rounded-md border border-gray-200 dark:border-white/10 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/5">
            Scan
          </Link>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-1 border-b border-gray-200 dark:border-white/10">
        {TABS.map(t => {
          const Icon = t.Icon;
          const active = t.key === tab;
          return (
            <button key={t.key}
                    onClick={() => setTab(t.key)}
                    className={`inline-flex items-center gap-2 px-3 py-2 text-sm font-medium border-b-2 -mb-px ${
                      active
                        ? "border-indigo-600 text-indigo-600 dark:text-indigo-400"
                        : "border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
                    }`}>
              <Icon className="w-4 h-4" />
              {t.label}
              {!loading && active && (
                <span className="text-xs text-gray-400">({counts[t.key]})</span>
              )}
            </button>
          );
        })}
        <div className="ml-auto py-1.5">
          <div className="relative">
            <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              value={q}
              onChange={e => setQ(e.target.value)}
              placeholder="Filter by ticker or group name…"
              className="pl-7 pr-3 py-1.5 text-xs rounded-md border border-gray-200 dark:border-white/10 bg-white dark:bg-gray-950 text-gray-900 dark:text-white w-56"
            />
          </div>
        </div>
      </div>

      {err && (
        <div role="alert" aria-live="polite"
             className="rounded-md border border-red-200 dark:border-red-900/40 bg-red-50 dark:bg-red-900/20 p-3 text-sm text-red-700 dark:text-red-300 flex items-start gap-2">
          <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
          <span className="flex-1">{err}</span>
          <button onClick={() => { setErr(null); void load(); }}
                  className="text-xs font-medium underline hover:no-underline">
            Retry
          </button>
        </div>
      )}

      {loading ? (
        <div className="text-center py-12 text-gray-500 dark:text-gray-400 text-sm flex items-center justify-center gap-2">
          <Loader2 className="w-4 h-4 animate-spin" /> Loading saved analyses…
        </div>
      ) : items.length === 0 ? (
        <div className="text-center py-16 border border-dashed border-gray-200 dark:border-white/10 rounded-xl">
          {q.trim() ? (
            <>
              <p className="text-sm font-medium text-gray-700 dark:text-gray-200">
                No matches for "{q.trim()}"
              </p>
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-1 max-w-md mx-auto">
                Try a different ticker or clear the filter to see all your saved {empty.title.toLowerCase().replace(/^no saved /, "").replace(/ yet$/, "")}.
              </p>
              <button onClick={() => setQ("")}
                      className="inline-block mt-4 text-sm font-medium text-indigo-600 dark:text-indigo-400 hover:underline">
                Clear filter
              </button>
            </>
          ) : (
            <>
              <p className="text-sm font-medium text-gray-700 dark:text-gray-200">{empty.title}</p>
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-1 max-w-md mx-auto">{empty.body}</p>
              <Link href={empty.cta.href}
                    className="inline-block mt-4 text-sm font-medium text-indigo-600 dark:text-indigo-400 hover:underline">
                {empty.cta.label}
              </Link>
            </>
          )}
        </div>
      ) : (
        <>
          {/* Bulk-select toolbar — only shown when there's anything to select.
              Sticky-ish behaviour kept simple (just a small bar at the top
              of the list) so users can see it without scrolling. */}
          <div className="flex items-center gap-3 px-3 py-2 bg-gray-50 dark:bg-gray-800/40 border border-gray-200 dark:border-white/10 rounded-lg text-xs">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={allSelected}
                ref={el => { if (el) el.indeterminate = !allSelected && selected.size > 0; }}
                onChange={toggleAll}
              />
              <span className="font-medium text-gray-700 dark:text-gray-200">
                {selected.size === 0
                  ? "Select all"
                  : `${selected.size} selected`}
              </span>
            </label>
            {selected.size > 0 && (
              <>
                <button
                  onClick={() => setSelected(new Set())}
                  className="text-gray-500 hover:text-gray-800 dark:hover:text-gray-200"
                >
                  Clear
                </button>
                <span className="flex-1" />
                <button
                  onClick={onDeleteSelected}
                  disabled={bulkBusy}
                  className="px-3 py-1 rounded text-white bg-rose-600 hover:bg-rose-700 disabled:opacity-50 inline-flex items-center gap-1"
                >
                  {bulkBusy
                    ? <Loader2 className="w-3 h-3 animate-spin" />
                    : <Trash2 className="w-3 h-3" />}
                  Delete {selected.size}
                </button>
              </>
            )}
          </div>

          <ul className="space-y-2 mt-2">
            {items.map(row => (
              <li key={row.id}
                  className={`bg-white dark:bg-gray-900 border ${selected.has(row.id) ? "border-indigo-300 dark:border-indigo-700" : "border-gray-200 dark:border-white/10"} rounded-lg p-3 sm:p-4`}>
                <div className="flex items-start gap-3 flex-wrap">
                  <input
                    type="checkbox"
                    className="mt-1"
                    checked={selected.has(row.id)}
                    onChange={() => toggleOne(row.id)}
                    aria-label={`Select ${row.scope} analysis ${row.id}`}
                  />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    {row.scope === "single" && (
                      <span className="font-mono font-semibold text-sm text-gray-900 dark:text-white">
                        {row.tickers[0]}
                      </span>
                    )}
                    {row.scope === "pair" && (
                      <span className="font-mono font-semibold text-sm text-gray-900 dark:text-white">
                        {row.tickers[0]} <span className="text-gray-400">vs</span> {row.tickers[1]}
                      </span>
                    )}
                    {row.scope === "group" && (
                      <>
                        <span className="font-semibold text-sm text-gray-900 dark:text-white">
                          {row.label || `${row.tickers.length} stocks`}
                        </span>
                        <span className="text-xs text-gray-400">·</span>
                        <span className="text-xs text-gray-500 dark:text-gray-400">
                          {row.tickers.length} ticker{row.tickers.length === 1 ? "" : "s"}
                        </span>
                      </>
                    )}
                    <VerdictBadge v={row.verdict} />
                    {row.confidence && (
                      <span className="text-[10px] uppercase tracking-wider text-gray-500 dark:text-gray-400 px-1.5 py-0.5 rounded bg-gray-100 dark:bg-white/5">
                        {row.confidence}
                      </span>
                    )}
                  </div>
                  {row.headline && (
                    <p className="text-sm text-gray-700 dark:text-gray-300 mt-1 line-clamp-2">
                      {row.headline}
                    </p>
                  )}
                  {row.scope === "group" && (
                    <div className="mt-1.5 flex flex-wrap gap-1">
                      {row.tickers.slice(0, 12).map(t => (
                        <span key={t} className="font-mono text-[10px] px-1.5 py-0.5 rounded bg-gray-100 dark:bg-white/5 text-gray-700 dark:text-gray-300">
                          {t}
                        </span>
                      ))}
                      {row.tickers.length > 12 && (
                        <span className="text-[10px] text-gray-500 dark:text-gray-400 self-center">
                          +{row.tickers.length - 12} more
                        </span>
                      )}
                    </div>
                  )}
                  <p className="text-[11px] text-gray-500 dark:text-gray-400 mt-1.5">
                    Saved {fmtDate(row.savedAt)}
                  </p>
                </div>
                <div className="flex items-center gap-1.5 flex-shrink-0">
                  <Link href={openHref(row)}
                        className="inline-flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium rounded-md bg-indigo-600 hover:bg-indigo-700 text-white">
                    <ExternalLink className="w-3.5 h-3.5" /> Open
                  </Link>
                  <button onClick={() => onRerun(row)}
                          title="Re-run this analysis (uses quota)"
                          className="inline-flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium rounded-md border border-gray-200 dark:border-white/10 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/5">
                    <RotateCw className="w-3.5 h-3.5" /> Re-run
                  </button>
                  <button onClick={() => onDelete(row)}
                          disabled={busyId === row.id}
                          title="Delete this saved analysis"
                          className="inline-flex items-center gap-1 px-2 py-1.5 text-xs font-medium rounded-md border border-red-200 dark:border-red-900/40 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 disabled:opacity-50">
                    {busyId === row.id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}
                  </button>
                </div>
              </div>
            </li>
          ))}
          </ul>
        </>
      )}
    </div>
  );
}
