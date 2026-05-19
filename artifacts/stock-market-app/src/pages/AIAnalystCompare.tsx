import { useState, useEffect, useRef } from "react";
import { useSearch, Link } from "wouter";
import {
  Microscope, Loader2, AlertCircle, TrendingUp, TrendingDown, Minus,
  Bookmark, RotateCw, Trophy, Target, Clock, ShieldAlert,
  BarChart3, LineChart, Newspaper, Globe2, Sparkles,
} from "lucide-react";
import { useCustomAuth } from "@/context/CustomAuthContext";
import { friendlyError, friendlyMessage, sanitizeTicker } from "@/lib/friendlyError";
import { StockCombobox } from "@/components/StockCombobox";

type Verdict = "BUY" | "HOLD" | "SELL";
type Confidence = "LOW" | "MEDIUM" | "HIGH";

interface Report {
  ticker: string;
  name: string;
  verdict: Verdict;
  confidence: Confidence;
  headline: string;
  priceTarget: string;
  horizon: string;
  keyRisks: string[];
  analysts: { fundamentals: string; news: string; technicals: string; macro: string };
  modelsUsed: string[];
  sourcesUsed: string[];
  disclaimer: string;
  error?: string;
}

const VERDICT_RANK: Record<Verdict, number> = { BUY: 2, HOLD: 1, SELL: 0 };
const CONF_RANK: Record<Confidence, number> = { LOW: 1, MEDIUM: 2, HIGH: 3 };

const VERDICT_THEME: Record<Verdict, {
  badge: string; ring: string; text: string; Icon: any; label: string;
}> = {
  BUY:  { badge: "bg-emerald-500 text-white",
          ring:  "ring-emerald-300 dark:ring-emerald-500/40",
          text:  "text-emerald-700 dark:text-emerald-300",
          Icon:  TrendingUp, label: "Bullish" },
  HOLD: { badge: "bg-amber-500 text-white",
          ring:  "ring-amber-300 dark:ring-amber-500/40",
          text:  "text-amber-700 dark:text-amber-300",
          Icon:  Minus, label: "Neutral" },
  SELL: { badge: "bg-rose-500 text-white",
          ring:  "ring-rose-300 dark:ring-rose-500/40",
          text:  "text-rose-700 dark:text-rose-300",
          Icon:  TrendingDown, label: "Bearish" },
};

const CONF_PCT: Record<Confidence, number> = { LOW: 33, MEDIUM: 66, HIGH: 100 };

function VerdictPill({ v, big = false }: { v: Verdict; big?: boolean }) {
  const t = VERDICT_THEME[v];
  return (
    <span className={`${t.badge} inline-flex items-center gap-1.5 rounded-full font-bold
                      ${big ? "px-4 py-1.5 text-base" : "px-2.5 py-0.5 text-xs"}`}>
      <t.Icon className={big ? "w-4 h-4" : "w-3 h-3"} />
      {v}
    </span>
  );
}

function ConfidenceBar({ c }: { c: Confidence }) {
  const pct = CONF_PCT[c] ?? 0;
  const tone = c === "HIGH" ? "bg-emerald-500"
            : c === "MEDIUM" ? "bg-amber-500"
            : "bg-rose-500";
  return (
    <div>
      <div className="flex items-center justify-between text-[10px] uppercase tracking-wide text-gray-500 dark:text-gray-400 mb-1">
        <span>Confidence</span>
        <span className="font-semibold text-gray-700 dark:text-gray-200">{c}</span>
      </div>
      <div className="h-1.5 rounded-full bg-gray-200 dark:bg-white/10 overflow-hidden">
        <div className={`h-full ${tone} transition-all`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function MetricBox({ Icon, label, value }: { Icon: any; label: string; value: string }) {
  return (
    <div className="rounded-lg border border-gray-200 dark:border-white/10 bg-gray-50 dark:bg-white/5 p-2.5">
      <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wide text-gray-500 dark:text-gray-400">
        <Icon className="w-3 h-3" />
        {label}
      </div>
      <div className="mt-1 text-sm font-semibold text-gray-900 dark:text-white truncate">
        {value || "—"}
      </div>
    </div>
  );
}

const ANALYST_META: Record<keyof Report["analysts"], { Icon: any; label: string; tone: string }> = {
  fundamentals: { Icon: BarChart3,  label: "Fundamentals", tone: "text-indigo-600 dark:text-indigo-400" },
  technicals:   { Icon: LineChart,  label: "Charts",       tone: "text-sky-600 dark:text-sky-400" },
  news:         { Icon: Newspaper,  label: "News flow",    tone: "text-violet-600 dark:text-violet-400" },
  macro:        { Icon: Globe2,     label: "Macro",        tone: "text-teal-600 dark:text-teal-400" },
};

function AnalystRow({ k, text }: { k: keyof Report["analysts"]; text: string }) {
  const m = ANALYST_META[k];
  if (!text) return null;
  return (
    <div className="flex gap-2.5">
      <m.Icon className={`w-4 h-4 mt-0.5 flex-shrink-0 ${m.tone}`} />
      <div className="min-w-0">
        <div className="text-[11px] font-semibold uppercase tracking-wide text-gray-600 dark:text-gray-400">
          {m.label}
        </div>
        <p className="text-xs text-gray-700 dark:text-gray-200 leading-relaxed">{text}</p>
      </div>
    </div>
  );
}

function ReportCard({ r, isWinner }: { r: Report | null; isWinner: boolean }) {
  if (!r) return null;
  if (r.error) {
    return (
      <div className="border border-rose-200 dark:border-rose-800 rounded-xl p-4 bg-rose-50 dark:bg-rose-900/20 flex items-start gap-2">
        <AlertCircle className="w-4 h-4 mt-0.5 text-rose-600 dark:text-rose-400 flex-shrink-0" />
        <div>
          <p className="text-sm font-semibold text-rose-700 dark:text-rose-300">{r.ticker}</p>
          <p className="text-xs text-rose-600 dark:text-rose-300/80 mt-0.5">{r.error}</p>
        </div>
      </div>
    );
  }
  const t = VERDICT_THEME[r.verdict];
  return (
    <div className={`relative rounded-2xl border bg-white dark:bg-gray-900 border-gray-200 dark:border-white/10
                     ring-2 ${t.ring} p-4 sm:p-5 flex flex-col gap-4`}>
      {isWinner && (
        <div role="status" aria-label="Stronger pick"
             className="absolute -top-3 left-4 inline-flex items-center gap-1 px-2.5 py-0.5
                        rounded-full bg-amber-400 text-amber-950 text-[10px] font-bold uppercase tracking-wide shadow">
          <Trophy className="w-3 h-3" aria-hidden="true" /> Stronger pick
        </div>
      )}

      {/* Header */}
      <div className="flex items-start gap-3">
        <div className="flex-1 min-w-0">
          <div className="text-[10px] uppercase tracking-wide text-gray-500 dark:text-gray-400">
            {t.label} call
          </div>
          <p className="font-bold text-gray-900 dark:text-white truncate text-base">
            {r.name || r.ticker}
          </p>
          <p className="text-xs font-mono text-gray-500 dark:text-gray-400">{r.ticker}</p>
        </div>
        <VerdictPill v={r.verdict} big />
      </div>

      {/* Headline */}
      <p className="text-sm text-gray-800 dark:text-gray-100 leading-relaxed border-l-2 border-gray-200 dark:border-white/10 pl-3 italic">
        "{r.headline}"
      </p>

      {/* Confidence + metrics grid */}
      <ConfidenceBar c={r.confidence} />
      <div className="grid grid-cols-2 gap-2">
        <MetricBox Icon={Target} label="Price target" value={r.priceTarget} />
        <MetricBox Icon={Clock}  label="Horizon"      value={r.horizon} />
      </div>

      {/* Analyst breakdown */}
      <div className="space-y-2.5 pt-1 border-t border-gray-100 dark:border-white/5">
        <AnalystRow k="fundamentals" text={r.analysts?.fundamentals} />
        <AnalystRow k="technicals"   text={r.analysts?.technicals} />
        <AnalystRow k="news"         text={r.analysts?.news} />
        <AnalystRow k="macro"        text={r.analysts?.macro} />
      </div>

      {/* Risks */}
      {r.keyRisks?.length > 0 && (
        <div className="pt-1 border-t border-gray-100 dark:border-white/5">
          <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-gray-600 dark:text-gray-400 mb-1.5">
            <ShieldAlert className="w-3.5 h-3.5 text-rose-500" />
            Key risks
          </div>
          <ul className="flex flex-wrap gap-1.5">
            {r.keyRisks.slice(0, 6).map((risk, i) => (
              <li key={i}
                  className="text-[11px] px-2 py-0.5 rounded-full bg-rose-50 dark:bg-rose-500/10
                             text-rose-700 dark:text-rose-300 border border-rose-200/50 dark:border-rose-500/20">
                {risk}
              </li>
            ))}
          </ul>
        </div>
      )}

      <Link href={`/ai-analyst/${encodeURIComponent(r.ticker)}`}
            className="text-xs font-medium text-indigo-600 dark:text-indigo-400 hover:underline self-start">
        Open full analysis →
      </Link>
    </div>
  );
}

function Showdown({ a, b }: { a: Report; b: Report }) {
  const aRank = (VERDICT_RANK[a.verdict] ?? 0) * 10 + (CONF_RANK[a.confidence] ?? 0);
  const bRank = (VERDICT_RANK[b.verdict] ?? 0) * 10 + (CONF_RANK[b.confidence] ?? 0);
  const winner = aRank > bRank ? "a" : bRank > aRank ? "b" : null;
  const aT = VERDICT_THEME[a.verdict];
  const bT = VERDICT_THEME[b.verdict];

  return (
    <div className="rounded-2xl border border-gray-200 dark:border-white/10 bg-gradient-to-br from-indigo-50/60 to-violet-50/60 dark:from-indigo-500/10 dark:to-violet-500/10 p-4 sm:p-5">
      <div className="flex items-center justify-center gap-2 text-[10px] uppercase tracking-widest text-gray-500 dark:text-gray-400 mb-3">
        <Sparkles className="w-3 h-3" /> AI Verdict Showdown
      </div>
      <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-2 sm:gap-3 min-w-0">
        {/* Left */}
        <div className="text-center">
          <p className="font-mono text-xs text-gray-500 dark:text-gray-400 mb-1">{a.ticker}</p>
          <p className={`font-bold text-lg ${aT.text}`}>{a.verdict}</p>
          <p className="text-[10px] text-gray-500 dark:text-gray-400 mt-0.5">{a.confidence} conf</p>
          {winner === "a" && (
            <div className="mt-2 inline-flex items-center gap-1 text-[10px] font-bold text-amber-700 dark:text-amber-400">
              <Trophy className="w-3 h-3" /> Winner
            </div>
          )}
        </div>
        {/* Middle */}
        <div className="text-gray-400 text-xs font-bold">VS</div>
        {/* Right */}
        <div className="text-center">
          <p className="font-mono text-xs text-gray-500 dark:text-gray-400 mb-1">{b.ticker}</p>
          <p className={`font-bold text-lg ${bT.text}`}>{b.verdict}</p>
          <p className="text-[10px] text-gray-500 dark:text-gray-400 mt-0.5">{b.confidence} conf</p>
          {winner === "b" && (
            <div className="mt-2 inline-flex items-center gap-1 text-[10px] font-bold text-amber-700 dark:text-amber-400">
              <Trophy className="w-3 h-3" /> Winner
            </div>
          )}
        </div>
      </div>
      {!winner && (
        <p className="text-center text-[11px] text-gray-500 dark:text-gray-400 mt-3">
          Too close to call — both stocks rank evenly on verdict + confidence.
        </p>
      )}
    </div>
  );
}

export default function AIAnalystCompare() {
  const search = useSearch();
  const params = new URLSearchParams(search);
  const [a, setA] = useState((params.get("a") || "").toUpperCase());
  const [b, setB] = useState((params.get("b") || "").toUpperCase());
  const { token } = useCustomAuth();
  const [running, setRunning] = useState(false);
  const [error, setError]     = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const runIdRef = useRef(0);
  useEffect(() => () => { abortRef.current?.abort(); }, []);
  const [data,  setData]      = useState<{ a: Report; b: Report } | null>(null);
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const initRef = useRef(false);

  // On mount: if we have both tickers, try to load the saved pair first.
  // If found, render it instantly with a banner. Otherwise run the analysis.
  // ?rerun=1 forces a fresh re-run that overwrites the saved pair.
  useEffect(() => {
    if (initRef.current) return;
    if (!token) return;
    if (!a || !b) return;
    initRef.current = true;
    const wantRerun = (params.get("rerun") === "1");
    (async () => {
      if (!wantRerun) {
        try {
          const r = await fetch(
            `/api/ai-analyst/saved/pair?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`,
            { headers: { Authorization: `Bearer ${token}` } });
          if (r.ok) {
            const j = await r.json();
            if (j?.report?.a && j?.report?.b) {
              setData({ a: j.report.a, b: j.report.b });
              setSavedAt(j.savedAt || null);
              return;
            }
          }
        } catch { /* fall through to a fresh run */ }
      }
      void run(wantRerun);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const run = async (force = false) => {
    const ca = sanitizeTicker(a);
    const cb = sanitizeTicker(b);
    if (!ca || !cb) { setError("Enter two valid tickers (letters, digits, '.', '-')"); return; }
    if (ca === cb)  { setError("Pick two different tickers"); return; }
    if (!token)     { setError("Please sign in"); return; }
    abortRef.current?.abort();
    abortRef.current = new AbortController();
    const myId = ++runIdRef.current;
    setError(null); setData(null); setSavedAt(null); setRunning(true);
    try {
      const res = await fetch(
        `/api/ai-analyst/compare?a=${encodeURIComponent(ca)}&b=${encodeURIComponent(cb)}&force=${force}`,
        {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
          signal: abortRef.current.signal,
        });
      if (runIdRef.current !== myId) return;  // stale — newer run started
      if (!res.ok) throw new Error(await friendlyError(res));
      const j = await res.json();
      if (runIdRef.current !== myId) return;
      setData({ a: j.a, b: j.b });
      // Newly persisted — surface the freshly-saved timestamp so the banner
      // shows immediately on the next compare load (or page refresh).
      if (j.saved) setSavedAt(new Date().toISOString());
    } catch (e: any) {
      if (runIdRef.current !== myId) return;
      if (e?.name === "AbortError") return;
      setError(friendlyMessage(e));
    } finally {
      if (runIdRef.current === myId) setRunning(false);
    }
  };

  // Pick the "winner" by verdict then confidence rank — only when both
  // sides actually produced a clean report (no errors).
  const winner: "a" | "b" | null = (() => {
    if (!data || data.a?.error || data.b?.error) return null;
    const ar = (VERDICT_RANK[data.a.verdict] ?? 0) * 10 + (CONF_RANK[data.a.confidence] ?? 0);
    const br = (VERDICT_RANK[data.b.verdict] ?? 0) * 10 + (CONF_RANK[data.b.confidence] ?? 0);
    return ar > br ? "a" : br > ar ? "b" : null;
  })();

  return (
    <div className="max-w-5xl mx-auto p-4 space-y-5">
      {/* Title bar */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="w-10 h-10 rounded-lg bg-indigo-100 dark:bg-indigo-500/20 flex items-center justify-center">
          <Microscope className="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
        </div>
        <div className="flex-1 min-w-0">
          <h1 className="text-xl font-bold text-gray-900 dark:text-white">Compare two stocks</h1>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            Side-by-side AI verdicts with charts, fundamentals, news flow & macro.
          </p>
        </div>
        <Link href="/ai-analyst/saved"
              className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-md border border-gray-200 dark:border-white/10 text-indigo-600 dark:text-indigo-400 hover:bg-gray-50 dark:hover:bg-white/5">
          <Bookmark className="w-3.5 h-3.5" /> Saved analyses
        </Link>
      </div>

      {/* Saved banner */}
      {savedAt && data && !running && (
        <div className="rounded-md border border-indigo-200 dark:border-indigo-500/30 bg-indigo-50 dark:bg-indigo-500/10 p-3 flex items-center gap-3 flex-wrap">
          <Bookmark className="w-4 h-4 text-indigo-600 dark:text-indigo-400 flex-shrink-0" />
          <p className="text-xs text-indigo-900 dark:text-indigo-100 flex-1 min-w-0">
            Saved on{" "}
            <strong>
              {new Date(savedAt).toLocaleDateString("en-IN", {
                day: "numeric", month: "short", year: "numeric",
              })}
            </strong>{" "}
            · Re-run to refresh both stocks with the latest market data.
          </p>
          <button
            onClick={() => run(true)}
            disabled={running}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-xs font-semibold"
          >
            <RotateCw className="w-3.5 h-3.5" /> Re-run
          </button>
        </div>
      )}

      {/* Input bar — grid on mobile (no overflow at 320px), flex on >=sm */}
      <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-white/10 rounded-xl p-3 sm:p-4 grid grid-cols-[1fr_auto_1fr] sm:flex sm:flex-wrap items-center gap-2">
        <div className="min-w-0 sm:flex-1 sm:min-w-[140px]">
          <StockCombobox value={a} onChange={(v) => setA(v.slice(0, 20))}
                         onSelect={(s) => setA(s.symbol)}
                         onSubmit={() => run()}
                         placeholder="Ticker A" />
        </div>
        <span className="text-gray-400 text-xs font-bold px-1" aria-hidden="true">VS</span>
        <div className="min-w-0 sm:flex-1 sm:min-w-[140px]">
          <StockCombobox value={b} onChange={(v) => setB(v.slice(0, 20))}
                         onSelect={(s) => setB(s.symbol)}
                         onSubmit={() => run()}
                         placeholder="Ticker B" />
        </div>
        <button onClick={() => run()} disabled={running}
                className="col-span-3 sm:col-auto px-4 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-sm font-medium rounded-lg flex items-center justify-center gap-2">
          {running ? <Loader2 className="w-4 h-4 animate-spin" /> : <Microscope className="w-4 h-4" />}
          {running ? "Analysing…" : "Compare"}
        </button>
      </div>

      {/* Loading state */}
      {running && (
        <div role="status" aria-live="polite" aria-busy="true"
             aria-label="Running AI analysis on both stocks"
             className="grid md:grid-cols-2 gap-4">
          {[0, 1].map(i => (
            <div key={i} className="rounded-2xl border border-gray-200 dark:border-white/10 bg-white dark:bg-gray-900 p-5 space-y-3 animate-pulse">
              <div className="flex items-center justify-between">
                <div className="h-4 w-24 bg-gray-200 dark:bg-white/10 rounded" />
                <div className="h-7 w-16 bg-gray-200 dark:bg-white/10 rounded-full" />
              </div>
              <div className="h-3 w-full bg-gray-200 dark:bg-white/10 rounded" />
              <div className="h-3 w-5/6 bg-gray-200 dark:bg-white/10 rounded" />
              <div className="h-1.5 w-full bg-gray-200 dark:bg-white/10 rounded-full" />
              <div className="grid grid-cols-2 gap-2">
                <div className="h-12 bg-gray-200 dark:bg-white/10 rounded-lg" />
                <div className="h-12 bg-gray-200 dark:bg-white/10 rounded-lg" />
              </div>
              <div className="h-3 w-full bg-gray-200 dark:bg-white/10 rounded" />
              <div className="h-3 w-4/6 bg-gray-200 dark:bg-white/10 rounded" />
            </div>
          ))}
        </div>
      )}
      {running && (
        <p className="text-center text-xs text-gray-500 dark:text-gray-400 -mt-2">
          Running two parallel multi-agent analyses — this can take 30–90 seconds…
        </p>
      )}

      {/* Error */}
      {error && (
        <div className="bg-rose-50 dark:bg-rose-900/20 border border-rose-200 dark:border-rose-800 rounded-lg p-3 flex items-start gap-2">
          <AlertCircle className="w-4 h-4 mt-0.5 text-rose-600 dark:text-rose-400 flex-shrink-0" />
          <p className="text-sm text-rose-700 dark:text-rose-300">{error}</p>
        </div>
      )}

      {/* Showdown + cards */}
      {data && !running && (
        <>
          {!data.a?.error && !data.b?.error && (
            <Showdown a={data.a} b={data.b} />
          )}
          <div className="grid md:grid-cols-2 gap-4">
            <ReportCard r={data.a} isWinner={winner === "a"} />
            <ReportCard r={data.b} isWinner={winner === "b"} />
          </div>
          <div className="bg-amber-50 dark:bg-amber-900/10 border border-amber-200 dark:border-amber-900/30 rounded-lg p-3 text-[11px] text-amber-900 dark:text-amber-200">
            AI-generated research only — not investment advice. Outputs may be inaccurate.
            Consult a SEBI-registered advisor before acting.
          </div>
        </>
      )}
    </div>
  );
}
