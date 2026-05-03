import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import { useParams, Link } from "wouter";
import {
  Microscope, Loader2, AlertCircle, Sparkles, TrendingUp,
  TrendingDown, Minus, ChevronDown, ChevronUp, RotateCw,
  Newspaper, BarChart3, Activity, Building2,
  Zap, Shield,
} from "lucide-react";
import { useCustomAuth } from "@/context/CustomAuthContext";
import {
  RadialBarChart, RadialBar, PolarAngleAxis,
} from "recharts";

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
  debate: { bull: string; bear: string };
  snapshot: { lastPrice?: number; pChange?: number; marketState?: string; asOfIst?: string };
  modelsUsed: string[];
  sourcesUsed: string[];
  disclaimer: string;
  cached?: boolean;
  cachedAt?: string;
  wallClockMs?: number;
}

interface PhaseEvent {
  phase: string;
  agent?: string;
  status?: string;
  partialText?: string;
  ts?: string;
  report?: Report;
  error?: string;
  quota?: { used: number; limit: number; remaining: number };
}

const VERDICT_STYLE: Record<Verdict, { bg: string; fg: string; icon: any; label: string }> = {
  BUY:  { bg: "bg-green-100 dark:bg-green-500/20", fg: "text-green-700 dark:text-green-300",
          icon: TrendingUp,   label: "Bullish research view" },
  HOLD: { bg: "bg-amber-100 dark:bg-amber-500/20", fg: "text-amber-700 dark:text-amber-300",
          icon: Minus,        label: "Neutral / wait-and-watch view" },
  SELL: { bg: "bg-red-100 dark:bg-red-500/20",     fg: "text-red-700 dark:text-red-300",
          icon: TrendingDown, label: "Bearish research view" },
};

const ANALYSTS = [
  { key: "fundamentals", label: "Fundamentals analyst", icon: Building2 },
  { key: "news",         label: "News & sentiment analyst", icon: Newspaper },
  { key: "technicals",   label: "Technicals analyst", icon: BarChart3 },
  { key: "macro",        label: "Macro & flow analyst", icon: Activity },
];

function StatusPill({ status }: { status?: string }) {
  if (status === "done")
    return <span className="text-[10px] uppercase tracking-wide text-green-600 dark:text-green-400 font-semibold">Done</span>;
  if (status === "running")
    return <span className="text-[10px] uppercase tracking-wide text-indigo-600 dark:text-indigo-400 font-semibold flex items-center gap-1">
      <Loader2 className="w-3 h-3 animate-spin" /> Running
    </span>;
  return <span className="text-[10px] uppercase tracking-wide text-gray-400 font-semibold">Pending</span>;
}

// ── Sentiment heuristic ───────────────────────────────────────────────────────
// Lightweight keyword-count classifier so each analyst section can show a
// bull/neutral/bear chip without needing a structured score from the model.
const BULL_WORDS = [
  "bullish", "positive", "strong", "growth", "upside", "outperform",
  "robust", "healthy", "expansion", "opportunity", "tailwind", "beat",
  "momentum", "improving", "favourable", "favorable", "attractive",
  "undervalued", "buy",
];
const BEAR_WORDS = [
  "bearish", "negative", "weak", "decline", "downside", "underperform",
  "concern", "risk", "headwind", "miss", "deteriorat", "overvalued",
  "expensive", "slowdown", "contraction", "pressure", "stress", "loss",
  "sell", "caution",
];

function analystSignal(text: string): { tone: "bull" | "bear" | "neutral"; score: number } {
  if (!text) return { tone: "neutral", score: 50 };
  const lower = text.toLowerCase();
  let bull = 0, bear = 0;
  for (const w of BULL_WORDS) bull += (lower.match(new RegExp(`\\b${w}`, "g")) || []).length;
  for (const w of BEAR_WORDS) bear += (lower.match(new RegExp(`\\b${w}`, "g")) || []).length;
  const total = bull + bear;
  if (total === 0) return { tone: "neutral", score: 50 };
  const score = Math.round((bull / total) * 100);
  if (score >= 60) return { tone: "bull", score };
  if (score <= 40) return { tone: "bear", score };
  return { tone: "neutral", score };
}

const TONE_STYLE = {
  bull:    { dot: "bg-green-500",  label: "Bullish lean",  text: "text-green-700 dark:text-green-300",  bg: "bg-green-50 dark:bg-green-500/10",  ring: "ring-green-500/30" },
  bear:    { dot: "bg-red-500",    label: "Bearish lean",  text: "text-red-700 dark:text-red-300",      bg: "bg-red-50 dark:bg-red-500/10",      ring: "ring-red-500/30" },
  neutral: { dot: "bg-gray-400",   label: "Mixed / neutral", text: "text-gray-700 dark:text-gray-300", bg: "bg-gray-50 dark:bg-gray-500/10",    ring: "ring-gray-400/30" },
} as const;

// Simple markdown-ish renderer: turn lines starting with "- " or "* " into a
// bulleted list, and render **bold** segments inline. Keeps the rest as
// paragraphs separated by blank lines. No external dependency.
function PrettyText({ text }: { text: string }) {
  if (!text || !text.trim()) {
    return <p className="text-sm italic text-gray-400 dark:text-gray-500">(no content)</p>;
  }
  const blocks: { type: "para" | "list"; lines: string[] }[] = [];
  const raw = text.replace(/\r\n/g, "\n").split("\n");
  let cur: { type: "para" | "list"; lines: string[] } | null = null;
  for (const ln of raw) {
    const t = ln.trim();
    if (!t) { if (cur) { blocks.push(cur); cur = null; } continue; }
    const isBullet = /^[-*•]\s+/.test(t);
    const wantType = isBullet ? "list" : "para";
    if (!cur || cur.type !== wantType) {
      if (cur) blocks.push(cur);
      cur = { type: wantType, lines: [] };
    }
    cur.lines.push(isBullet ? t.replace(/^[-*•]\s+/, "") : t);
  }
  if (cur) blocks.push(cur);

  const renderInline = (s: string) => {
    // bold via **…**
    const parts = s.split(/(\*\*[^*]+\*\*)/g);
    return parts.map((p, i) =>
      p.startsWith("**") && p.endsWith("**")
        ? <strong key={i} className="font-semibold text-gray-900 dark:text-white">{p.slice(2, -2)}</strong>
        : <span key={i}>{p}</span>
    );
  };

  return (
    <div className="space-y-2 text-sm text-gray-700 dark:text-gray-300 leading-relaxed">
      {blocks.map((b, i) =>
        b.type === "list" ? (
          <ul key={i} className="list-disc pl-5 space-y-1">
            {b.lines.map((ln, j) => <li key={j}>{renderInline(ln)}</li>)}
          </ul>
        ) : (
          <p key={i}>{b.lines.map((ln, j) => <span key={j}>{renderInline(ln)}{j < b.lines.length - 1 ? " " : ""}</span>)}</p>
        )
      )}
    </div>
  );
}

function CollapsibleSection({ title, icon: Icon, body, defaultOpen = false, signal }:
    { title: string; icon: any; body: string; defaultOpen?: boolean;
      signal?: { tone: "bull" | "bear" | "neutral"; score: number } }) {
  const [open, setOpen] = useState(defaultOpen);
  const tone = signal ? TONE_STYLE[signal.tone] : null;
  return (
    <div className="border border-gray-200 dark:border-white/10 rounded-lg overflow-hidden bg-white dark:bg-gray-900">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center gap-2 px-3 py-3 hover:bg-gray-50 dark:hover:bg-gray-900/50"
      >
        <Icon className="w-4 h-4 text-indigo-600 dark:text-indigo-400" />
        <span className="text-sm font-medium text-gray-900 dark:text-white flex-1 text-left">{title}</span>
        {tone && (
          <span className={`hidden sm:inline-flex items-center gap-1.5 text-[10px] uppercase tracking-wide font-semibold px-2 py-0.5 rounded-full ${tone.bg} ${tone.text}`}>
            <span className={`w-1.5 h-1.5 rounded-full ${tone.dot}`} />
            {tone.label}
          </span>
        )}
        {open ? <ChevronUp className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
      </button>
      {open && (
        <div className="px-4 py-3 bg-gray-50 dark:bg-gray-900/40 border-t border-gray-200 dark:border-white/10">
          <PrettyText text={body} />
        </div>
      )}
    </div>
  );
}

// Circular confidence gauge using recharts RadialBar
function ConfidenceGauge({ confidence, verdict }: { confidence: Confidence; verdict: Verdict }) {
  const pct = confidence === "HIGH" ? 92 : confidence === "MEDIUM" ? 62 : 32;
  const color = verdict === "BUY" ? "#22c55e" : verdict === "SELL" ? "#ef4444" : "#f59e0b";
  const data = [{ name: "c", value: pct, fill: color }];
  return (
    <div className="relative w-[140px] h-[140px] flex-shrink-0">
      <RadialBarChart
        width={140} height={140}
        innerRadius={56} outerRadius={68}
        data={data} startAngle={90} endAngle={-270}
      >
        <PolarAngleAxis type="number" domain={[0, 100]} angleAxisId={0} tick={false} />
        <RadialBar background={{ fill: "rgba(148,163,184,0.18)" }} dataKey="value" cornerRadius={20} />
      </RadialBarChart>
      <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
        <span className="text-2xl font-bold" style={{ color }}>{pct}%</span>
        <span className="text-[10px] uppercase tracking-wider text-gray-500 dark:text-gray-400">
          {confidence}
        </span>
      </div>
    </div>
  );
}

// Horizontal bull-vs-bear strength bar based on argument length
function DebateBar({ bull, bear }: { bull: string; bear: string }) {
  const bL = (bull || "").trim().length;
  const rL = (bear || "").trim().length;
  const total = Math.max(1, bL + rL);
  const bullPct = Math.round((bL / total) * 100);
  const bearPct = 100 - bullPct;
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between text-[11px] font-semibold">
        <span className="text-green-600 dark:text-green-400 flex items-center gap-1">
          <TrendingUp className="w-3 h-3" /> Bull case · {bullPct}%
        </span>
        <span className="text-red-600 dark:text-red-400 flex items-center gap-1">
          {bearPct}% · Bear case <TrendingDown className="w-3 h-3" />
        </span>
      </div>
      <div className="flex h-2.5 rounded-full overflow-hidden bg-gray-100 dark:bg-gray-800">
        <div className="bg-gradient-to-r from-green-400 to-green-600" style={{ width: `${bullPct}%` }} />
        <div className="bg-gradient-to-r from-red-600 to-red-400" style={{ width: `${bearPct}%` }} />
      </div>
    </div>
  );
}

// KPI tile for the snapshot ribbon
function KPI({ label, value, hint, tone }:
    { label: string; value: React.ReactNode; hint?: string; tone?: "up" | "down" | "neutral" }) {
  const toneClass = tone === "up" ? "text-green-600 dark:text-green-400"
                   : tone === "down" ? "text-red-600 dark:text-red-400"
                   : "text-gray-900 dark:text-white";
  return (
    <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-white/10 rounded-lg px-3 py-2.5">
      <p className="text-[10px] uppercase tracking-wider text-gray-500 dark:text-gray-400 font-semibold">
        {label}
      </p>
      <p className={`text-base font-bold mt-0.5 ${toneClass}`}>{value}</p>
      {hint && <p className="text-[10px] text-gray-500 dark:text-gray-400 mt-0.5">{hint}</p>}
    </div>
  );
}


export default function AIAnalyst() {
  const params = useParams<{ ticker?: string }>();
  const [ticker, setTicker] = useState((params.ticker || "").toUpperCase());
  const { token } = useCustomAuth();
  const [events, setEvents] = useState<PhaseEvent[]>([]);
  const [report, setReport]   = useState<Report | null>(null);
  const [error,  setError]    = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [quota,   setQuota]   = useState<{ used: number; limit: number; remaining: number } | null>(null);
  const [showDebate, setShowDebate] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  // Quota fetch on mount
  useEffect(() => {
    if (!token) return;
    fetch("/api/ai-analyst/quota", { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.ok ? r.json() : null)
      .then(q => q && setQuota(q))
      .catch(() => {});
  }, [token]);

  // Abort any in-flight SSE stream when the page unmounts so we don't leak
  // a fetch reader into the background.
  useEffect(() => {
    return () => { abortRef.current?.abort(); };
  }, []);

  const start = useCallback(async (force = false) => {
    if (!ticker.trim()) { setError("Enter a ticker"); return; }
    if (!token)         { setError("Please sign in"); return; }

    abortRef.current?.abort();
    abortRef.current = new AbortController();
    setEvents([]); setReport(null); setError(null); setRunning(true);

    try {
      const res = await fetch(`/api/ai-analyst/run/${encodeURIComponent(ticker)}?force=${force}`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, Accept: "text/event-stream" },
        signal: abortRef.current.signal,
      });
      if (!res.ok || !res.body) {
        const body = await res.text().catch(() => "");
        throw new Error(body || `HTTP ${res.status}`);
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const frames = buf.split("\n\n");
        buf = frames.pop() || "";
        for (const frame of frames) {
          const line = frame.split("\n").find(l => l.startsWith("data: "));
          if (!line) continue;
          try {
            const ev: PhaseEvent = JSON.parse(line.slice(6));
            setEvents(prev => [...prev, ev]);
            if (ev.phase === "done" && ev.report) {
              setReport(ev.report);
              if (ev.quota) setQuota(ev.quota);
            } else if (ev.phase === "error") {
              setError(ev.error || "Unknown error");
              if (ev.quota) setQuota(ev.quota);
            }
          } catch { /* ignore malformed frame */ }
        }
      }
    } catch (e: any) {
      if (e.name !== "AbortError") setError(e.message || String(e));
    } finally {
      setRunning(false);
    }
  }, [ticker, token]);

  // Helpers to read live phase status from the event stream
  const phaseStatus = (phase: string, agent?: string): string | undefined => {
    const list = events.filter(e => e.phase === phase && (!agent || e.agent === agent));
    return list.length ? list[list.length - 1].status : undefined;
  };

  const verdict = report?.verdict ?? "HOLD";
  const Vstyle  = VERDICT_STYLE[verdict];
  const VIcon   = Vstyle.icon;

  // Compute per-analyst sentiment chips once per report
  const signals = useMemo(() => ({
    fundamentals: analystSignal(report?.analysts.fundamentals || ""),
    news:         analystSignal(report?.analysts.news || ""),
    technicals:   analystSignal(report?.analysts.technicals || ""),
    macro:        analystSignal(report?.analysts.macro || ""),
  }), [report]);

  const fmtPrice = (p?: number) =>
    p == null ? "—" : `₹${p.toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
  const pctTone = (p?: number): "up" | "down" | "neutral" =>
    p == null ? "neutral" : p > 0 ? "up" : p < 0 ? "down" : "neutral";

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-lg bg-indigo-100 dark:bg-indigo-500/20 flex items-center justify-center">
          <Microscope className="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
        </div>
        <div className="flex-1">
          <h1 className="text-xl font-bold text-gray-900 dark:text-white">Deep AI Analyst</h1>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            Multi-agent equity research powered by free open-source LLMs.{" "}
            <span className="text-amber-600 dark:text-amber-400">Educational research only — not investment advice.</span>
          </p>
        </div>
        {quota && (
          <div className="text-xs text-gray-500 dark:text-gray-400 bg-gray-100 dark:bg-gray-900 px-3 py-1.5 rounded-lg">
            <span className="font-semibold text-gray-900 dark:text-white">{quota.used}</span>
            <span> / {quota.limit} runs today</span>
          </div>
        )}
      </div>

      {/* Input row */}
      <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-white/10 rounded-xl p-4 flex flex-wrap items-center gap-2">
        <input
          value={ticker}
          onChange={e => setTicker(e.target.value.toUpperCase())}
          onKeyDown={e => e.key === "Enter" && !running && start(false)}
          placeholder="NSE ticker (e.g. RELIANCE, TCS, INFY)"
          className="flex-1 min-w-[200px] px-3 py-2 text-sm bg-gray-50 dark:bg-gray-950 border border-gray-200 dark:border-white/10 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500"
          disabled={running}
        />
        <button
          onClick={() => start(false)}
          disabled={running || !ticker.trim()}
          className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg flex items-center gap-2"
        >
          {running ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
          {running ? "Analysing…" : "Run Deep AI Analysis"}
        </button>
        {report && !running && (
          <button
            onClick={() => start(true)}
            disabled={quota?.remaining === 0}
            title="Force refresh (uses one quota slot)"
            className="px-3 py-2 text-sm border border-gray-200 dark:border-white/10 hover:bg-gray-50 dark:hover:bg-gray-800 rounded-lg flex items-center gap-2 text-gray-600 dark:text-gray-300"
          >
            <RotateCw className="w-3.5 h-3.5" /> Re-run
          </button>
        )}
        <Link href={`/ai-analyst/compare?a=${ticker}&b=`}
              className="px-3 py-2 text-sm border border-gray-200 dark:border-white/10 hover:bg-gray-50 dark:hover:bg-gray-800 rounded-lg text-gray-600 dark:text-gray-300">
          Compare two stocks →
        </Link>
        <Link href="/ai-analyst/scan"
              className="px-3 py-2 text-sm border border-gray-200 dark:border-white/10 hover:bg-gray-50 dark:hover:bg-gray-800 rounded-lg text-gray-600 dark:text-gray-300">
          Scan a watchlist →
        </Link>
      </div>

      {/* Error */}
      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4 flex items-start gap-2">
          <AlertCircle className="w-5 h-5 text-red-600 dark:text-red-400 flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-medium text-red-700 dark:text-red-300">{error}</p>
            {error === "quota_exceeded" && (
              <p className="text-xs text-red-600 dark:text-red-400 mt-1">
                You've used your 3 free analyses for today. The quota resets at midnight IST.
              </p>
            )}
          </div>
        </div>
      )}

      {/* Live progress */}
      {(running || (events.length > 0 && !report)) && (
        <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-white/10 rounded-xl p-4">
          <p className="text-xs uppercase tracking-wider text-gray-500 dark:text-gray-400 font-semibold mb-3">
            Research desk in progress
          </p>
          <div className="space-y-1.5">
            <div className="flex items-center justify-between text-sm">
              <span className="text-gray-700 dark:text-gray-300">Gathering market data, news & flows</span>
              <StatusPill status={phaseStatus("context")} />
            </div>
            {ANALYSTS.map(a => (
              <div key={a.key} className="flex items-center justify-between text-sm">
                <span className="flex items-center gap-2 text-gray-700 dark:text-gray-300">
                  <a.icon className="w-3.5 h-3.5 text-gray-400" />{a.label}
                </span>
                <StatusPill status={phaseStatus("analyst", a.key)} />
              </div>
            ))}
            <div className="flex items-center justify-between text-sm">
              <span className="text-gray-700 dark:text-gray-300">Bull researcher arguing the upside</span>
              <StatusPill status={phaseStatus("debate", "bull")} />
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-gray-700 dark:text-gray-300">Bear researcher arguing the downside</span>
              <StatusPill status={phaseStatus("debate", "bear")} />
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-gray-700 dark:text-gray-300">Trader synthesising the verdict</span>
              <StatusPill status={phaseStatus("trader")} />
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-gray-700 dark:text-gray-300">Compliance & risk gate</span>
              <StatusPill status={phaseStatus("risk")} />
            </div>
          </div>
        </div>
      )}

      {/* Final report */}
      {report && (
        <div className="space-y-4">
          {/* Hero verdict card with confidence gauge */}
          <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-white/10 rounded-xl overflow-hidden">
            <div className={`px-5 py-5 ${Vstyle.bg} flex flex-col sm:flex-row items-start sm:items-center gap-4`}>
              <ConfidenceGauge confidence={report.confidence} verdict={report.verdict} />
              <div className="flex-1 min-w-0">
                <p className="text-[11px] uppercase tracking-wider text-gray-600 dark:text-gray-300 font-semibold">
                  {Vstyle.label}
                </p>
                <div className="flex items-baseline gap-3 flex-wrap">
                  <span className={`text-4xl font-extrabold tracking-tight ${Vstyle.fg} flex items-center gap-2`}>
                    <VIcon className="w-8 h-8" />
                    {report.verdict}
                  </span>
                  <span className="text-lg font-semibold text-gray-900 dark:text-white">{report.name}</span>
                  <span className="text-xs text-gray-500 dark:text-gray-400">{report.ticker}</span>
                </div>
                <p className="text-sm text-gray-700 dark:text-gray-200 leading-relaxed mt-2">
                  {report.headline}
                </p>
              </div>
              {report.cached && (
                <span className="text-[10px] uppercase tracking-wider bg-white/70 dark:bg-black/30 text-gray-700 dark:text-gray-200 px-2 py-1 rounded self-start">
                  Cached {report.cachedAt ? new Date(report.cachedAt).toLocaleTimeString() : ""}
                </span>
              )}
            </div>

            {/* KPI ribbon */}
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2 p-3 border-t border-gray-200 dark:border-white/10 bg-gray-50/50 dark:bg-gray-950/40">
              <KPI label="Last price"
                   value={fmtPrice(report.snapshot.lastPrice)}
                   tone={pctTone(report.snapshot.pChange)} />
              <KPI label="Day change"
                   value={report.snapshot.pChange != null
                     ? `${report.snapshot.pChange > 0 ? "+" : ""}${report.snapshot.pChange.toFixed(2)}%`
                     : "—"}
                   tone={pctTone(report.snapshot.pChange)} />
              <KPI label="Target" value={report.priceTarget || "—"} hint="research view" />
              <KPI label="Horizon" value={report.horizon || "—"} />
              <KPI label="Market"
                   value={report.snapshot.marketState || "—"}
                   hint={report.snapshot.asOfIst ? new Date(report.snapshot.asOfIst).toLocaleTimeString("en-IN") : undefined} />
              <KPI label="Generated in"
                   value={report.wallClockMs ? `${(report.wallClockMs / 1000).toFixed(1)}s` : "—"}
                   hint={`${report.modelsUsed.length} model${report.modelsUsed.length === 1 ? "" : "s"}`} />
            </div>

            {/* Key risks */}
            {report.keyRisks?.length > 0 && (
              <div className="px-5 py-4 border-t border-gray-200 dark:border-white/10">
                <p className="text-[10px] uppercase tracking-wider text-gray-500 dark:text-gray-400 font-semibold mb-2 flex items-center gap-1.5">
                  <Shield className="w-3 h-3" /> Key risks the analyst flagged
                </p>
                <ul className="grid sm:grid-cols-2 gap-x-6 gap-y-1 text-xs text-gray-700 dark:text-gray-300 list-disc pl-5">
                  {report.keyRisks.map((r, i) => <li key={i}>{r}</li>)}
                </ul>
              </div>
            )}
          </div>

          {/* Bull vs Bear strength bar */}
          <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-white/10 rounded-xl p-4">
            <p className="text-[10px] uppercase tracking-wider text-gray-500 dark:text-gray-400 font-semibold mb-3 flex items-center gap-1.5">
              <Zap className="w-3 h-3" /> Bull vs Bear · argument balance
            </p>
            <DebateBar bull={report.debate.bull} bear={report.debate.bear} />
          </div>

          {/* Analyst sections with sentiment chips */}
          <div className="grid gap-3">
            <CollapsibleSection title="What the fundamentals say"
                                icon={Building2} body={report.analysts.fundamentals}
                                signal={signals.fundamentals} defaultOpen />
            <CollapsibleSection title="What the news & sentiment say"
                                icon={Newspaper}  body={report.analysts.news}
                                signal={signals.news} />
            <CollapsibleSection title="What the charts say"
                                icon={BarChart3}  body={report.analysts.technicals}
                                signal={signals.technicals} />
            <CollapsibleSection title="What the macro & flows say"
                                icon={Activity}   body={report.analysts.macro}
                                signal={signals.macro} />
          </div>

          {/* Full debate transcript */}
          <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-white/10 rounded-xl">
            <button onClick={() => setShowDebate(s => !s)}
                    className="w-full flex items-center gap-2 px-4 py-3 hover:bg-gray-50 dark:hover:bg-gray-900/60">
              <Sparkles className="w-4 h-4 text-indigo-600 dark:text-indigo-400" />
              <span className="text-sm font-medium text-gray-900 dark:text-white flex-1 text-left">
                Read the full Bull-vs-Bear debate
              </span>
              {showDebate ? <ChevronUp className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
            </button>
            {showDebate && (
              <div className="px-4 pb-4 grid md:grid-cols-2 gap-4 border-t border-gray-200 dark:border-white/10 pt-4">
                <div className="rounded-lg border border-green-200 dark:border-green-900/40 bg-green-50/40 dark:bg-green-500/5 p-3">
                  <p className="text-xs font-bold text-green-700 dark:text-green-300 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                    <TrendingUp className="w-3.5 h-3.5" /> Bull researcher
                  </p>
                  <PrettyText text={report.debate.bull} />
                </div>
                <div className="rounded-lg border border-red-200 dark:border-red-900/40 bg-red-50/40 dark:bg-red-500/5 p-3">
                  <p className="text-xs font-bold text-red-700 dark:text-red-300 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                    <TrendingDown className="w-3.5 h-3.5" /> Bear researcher
                  </p>
                  <PrettyText text={report.debate.bear} />
                </div>
              </div>
            )}
          </div>

          {/* Disclaimer footer */}
          <div className="bg-amber-50 dark:bg-amber-900/10 border border-amber-200 dark:border-amber-900/30 rounded-lg p-4 text-xs text-amber-900 dark:text-amber-200">
            <p className="font-semibold mb-1">Disclosure & disclaimer</p>
            <p>{report.disclaimer}</p>
            <p className="mt-2">
              This report is AI-generated educational content, not investment
              advice or a recommendation under SEBI (Investment Advisers)
              Regulations, 2013. Always consult a SEBI-registered investment
              adviser before making investment decisions. Learn more at the{" "}
              <a
                href="https://investor.sebi.gov.in/"
                target="_blank"
                rel="noopener noreferrer"
                className="underline font-medium hover:text-amber-950 dark:hover:text-amber-100"
              >
                SEBI Investor Awareness portal
              </a>.
            </p>
            <p className="mt-2 text-[10px] text-amber-800/80 dark:text-amber-300/70">
              <span className="font-semibold">Models used:</span> {report.modelsUsed.join(", ") || "—"}<br />
              <span className="font-semibold">Data sources:</span> {report.sourcesUsed.join(", ") || "—"}<br />
              <span className="font-semibold">Generated:</span> {report.snapshot.asOfIst || "—"}
              {report.wallClockMs ? ` · in ${(report.wallClockMs / 1000).toFixed(1)}s` : ""}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
