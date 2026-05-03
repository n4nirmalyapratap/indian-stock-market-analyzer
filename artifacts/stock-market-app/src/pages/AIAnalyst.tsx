import { useState, useEffect, useRef, useCallback } from "react";
import { useParams, Link } from "wouter";
import {
  Brain, Loader2, AlertCircle, Sparkles, TrendingUp,
  TrendingDown, Minus, ChevronDown, ChevronUp, RotateCw,
  Newspaper, BarChart3, Activity, Building2,
} from "lucide-react";
import { useCustomAuth } from "@/context/CustomAuthContext";

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

function CollapsibleSection({ title, icon: Icon, body, defaultOpen = false }:
    { title: string; icon: any; body: string; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border border-gray-200 dark:border-white/10 rounded-lg overflow-hidden">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center gap-2 px-3 py-2.5 hover:bg-gray-50 dark:hover:bg-gray-900/50"
      >
        <Icon className="w-4 h-4 text-indigo-600 dark:text-indigo-400" />
        <span className="text-sm font-medium text-gray-900 dark:text-white flex-1 text-left">{title}</span>
        {open ? <ChevronUp className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
      </button>
      {open && (
        <div className="px-3 py-3 bg-gray-50 dark:bg-gray-900/40 border-t border-gray-200 dark:border-white/10">
          <p className="text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap leading-relaxed">{body || "(no content)"}</p>
        </div>
      )}
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

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-lg bg-indigo-100 dark:bg-indigo-500/20 flex items-center justify-center">
          <Brain className="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
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
          {/* Verdict card */}
          <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-white/10 rounded-xl overflow-hidden">
            <div className={`px-5 py-4 ${Vstyle.bg} flex items-center gap-3`}>
              <VIcon className={`w-7 h-7 ${Vstyle.fg}`} />
              <div className="flex-1">
                <p className="text-xs uppercase tracking-wider text-gray-600 dark:text-gray-300 font-semibold">
                  {Vstyle.label} · {report.confidence} confidence · horizon {report.horizon}
                </p>
                <p className={`text-2xl font-bold ${Vstyle.fg}`}>
                  {report.verdict}
                  {report.priceTarget && report.priceTarget !== "N/A" && (
                    <span className="text-base font-medium ml-3 text-gray-700 dark:text-gray-200">
                      Target: {report.priceTarget}
                    </span>
                  )}
                </p>
              </div>
              {report.cached && (
                <span className="text-[10px] uppercase tracking-wider bg-white/70 dark:bg-black/30 text-gray-700 dark:text-gray-200 px-2 py-1 rounded">
                  Cached {report.cachedAt ? new Date(report.cachedAt).toLocaleTimeString() : ""}
                </span>
              )}
            </div>
            <div className="px-5 py-4">
              <p className="text-sm text-gray-700 dark:text-gray-200 leading-relaxed">
                <span className="font-semibold text-gray-900 dark:text-white">{report.name}</span> — {report.headline}
              </p>
              {report.keyRisks?.length > 0 && (
                <div className="mt-3">
                  <p className="text-[10px] uppercase tracking-wider text-gray-500 dark:text-gray-400 font-semibold mb-1">
                    Key risks
                  </p>
                  <ul className="text-xs text-gray-600 dark:text-gray-300 list-disc pl-5 space-y-0.5">
                    {report.keyRisks.map((r, i) => <li key={i}>{r}</li>)}
                  </ul>
                </div>
              )}
            </div>
          </div>

          {/* Analyst sections */}
          <div className="grid gap-3">
            <CollapsibleSection title="What the fundamentals say"
                                icon={Building2} body={report.analysts.fundamentals} defaultOpen />
            <CollapsibleSection title="What the news & sentiment say"
                                icon={Newspaper}  body={report.analysts.news} />
            <CollapsibleSection title="What the charts say"
                                icon={BarChart3}  body={report.analysts.technicals} />
            <CollapsibleSection title="What the macro & flows say"
                                icon={Activity}   body={report.analysts.macro} />
          </div>

          {/* Debate */}
          <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-white/10 rounded-xl">
            <button onClick={() => setShowDebate(s => !s)}
                    className="w-full flex items-center gap-2 px-4 py-3 hover:bg-gray-50 dark:hover:bg-gray-900/60">
              <Sparkles className="w-4 h-4 text-indigo-600 dark:text-indigo-400" />
              <span className="text-sm font-medium text-gray-900 dark:text-white flex-1 text-left">
                Show the full Bull-vs-Bear debate transcript
              </span>
              {showDebate ? <ChevronUp className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
            </button>
            {showDebate && (
              <div className="px-4 pb-4 grid md:grid-cols-2 gap-4 border-t border-gray-200 dark:border-white/10 pt-4">
                <div>
                  <p className="text-xs font-bold text-green-600 dark:text-green-400 uppercase tracking-wider mb-2">
                    Bull researcher
                  </p>
                  <p className="text-xs text-gray-700 dark:text-gray-300 whitespace-pre-wrap leading-relaxed">
                    {report.debate.bull}
                  </p>
                </div>
                <div>
                  <p className="text-xs font-bold text-red-600 dark:text-red-400 uppercase tracking-wider mb-2">
                    Bear researcher
                  </p>
                  <p className="text-xs text-gray-700 dark:text-gray-300 whitespace-pre-wrap leading-relaxed">
                    {report.debate.bear}
                  </p>
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
