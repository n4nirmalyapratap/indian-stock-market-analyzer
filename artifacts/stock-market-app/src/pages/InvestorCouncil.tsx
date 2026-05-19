import { useState, useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { useRoute, useLocation } from "wouter";
import { api } from "@/lib/api";
import {
  Search, ArrowLeft, CheckCircle2, XCircle, MinusCircle, Sparkles,
  TrendingUp, TrendingDown, Loader2, Quote, LayoutGrid, Grid3x3,
} from "lucide-react";

// ─── Types — re-exported from shared api types so they stay in sync ──────────

import type { AgentVerdict as Verdict, ChecklistItem, PersonaResult, CouncilResponse, PersonaRegion } from "@/lib/api";
import { StockCombobox } from "@/components/StockCombobox";
export type { Verdict, ChecklistItem, PersonaResult, CouncilResponse };

// Fallback region map by persona id (backend already emits `region`, but this
// keeps the UI safe if a payload is missing the field).
const PERSONA_REGION_FALLBACK: Record<string, PersonaRegion> = {
  buffett: "Global", graham: "Global", lynch: "Global", munger: "Global",
  klarman: "Global", marks: "Global", dalio: "Global", burry: "Global",
  jhunjhunwala: "India", damani_rk: "India", agrawal: "India", kedia: "India",
  veliyath: "India", damani_ramesh: "India", kacholia: "India", khanna: "India",
};

function regionOf(p: { id: string; region?: PersonaRegion }): PersonaRegion {
  return p.region ?? PERSONA_REGION_FALLBACK[p.id] ?? "Global";
}

type RegionFilter = "all" | "Global" | "India";

function RegionBadge({ region }: { region: PersonaRegion }) {
  const isIndia = region === "India";
  return (
    <span
      className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold tracking-wider ${
        isIndia
          ? "bg-orange-100 dark:bg-orange-500/20 text-orange-700 dark:text-orange-300"
          : "bg-sky-100 dark:bg-sky-500/20 text-sky-700 dark:text-sky-300"
      }`}
      title={isIndia ? "Indian investor" : "Global investor"}
    >
      {isIndia ? "IN" : "GL"}
    </span>
  );
}

function RegionToggle({ value, onChange, counts }: {
  value: RegionFilter;
  onChange: (v: RegionFilter) => void;
  counts: { all: number; Global: number; India: number };
}) {
  const opts: { key: RegionFilter; label: string }[] = [
    { key: "all",    label: `All (${counts.all})` },
    { key: "Global", label: `Global (${counts.Global})` },
    { key: "India",  label: `India (${counts.India})` },
  ];
  return (
    <div className="flex items-center gap-1 bg-gray-100 dark:bg-gray-800 rounded-lg p-1 w-fit">
      {opts.map(o => (
        <button
          key={o.key}
          onClick={() => onChange(o.key)}
          className={`px-3 py-1.5 rounded-md text-xs font-medium transition ${
            value === o.key
              ? "bg-white dark:bg-gray-900 text-indigo-700 dark:text-indigo-300 shadow-sm"
              : "text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

// ─── Visual helpers ───────────────────────────────────────────────────────────

const VERDICT_STYLE: Record<Verdict, { bg: string; text: string; label: string }> = {
  STRONG_BUY:   { bg: "bg-emerald-100 dark:bg-emerald-500/20", text: "text-emerald-700 dark:text-emerald-300", label: "Strong Buy" },
  BUY:          { bg: "bg-green-100 dark:bg-green-500/20",     text: "text-green-700 dark:text-green-300",     label: "Buy" },
  HOLD:         { bg: "bg-amber-100 dark:bg-amber-500/20",     text: "text-amber-700 dark:text-amber-300",     label: "Hold" },
  AVOID:        { bg: "bg-orange-100 dark:bg-orange-500/20",   text: "text-orange-700 dark:text-orange-300",   label: "Avoid" },
  STRONG_AVOID: { bg: "bg-red-100 dark:bg-red-500/20",         text: "text-red-700 dark:text-red-300",         label: "Strong Avoid" },
};

const PERSONA_TINT: Record<string, string> = {
  // Global legends
  buffett:        "from-amber-500 to-orange-500",
  graham:         "from-slate-500 to-gray-700",
  lynch:          "from-emerald-500 to-teal-600",
  munger:         "from-yellow-500 to-amber-600",
  klarman:        "from-blue-500 to-indigo-600",
  marks:          "from-purple-500 to-violet-600",
  dalio:          "from-cyan-500 to-blue-600",
  burry:          "from-rose-500 to-red-600",
  // Indian legends — saffron / green / blue palette nodding to the tricolour
  jhunjhunwala:   "from-orange-500 to-red-500",
  damani_rk:      "from-emerald-600 to-green-700",
  agrawal:        "from-blue-600 to-indigo-700",
  kedia:          "from-pink-500 to-rose-600",
  veliyath:       "from-fuchsia-500 to-purple-600",
  damani_ramesh:  "from-teal-500 to-emerald-600",
  kacholia:       "from-yellow-500 to-orange-600",
  khanna:         "from-lime-500 to-green-600",
};

function VerdictBadge({ verdict }: { verdict: Verdict }) {
  const s = VERDICT_STYLE[verdict];
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-bold ${s.bg} ${s.text}`}>
      {(verdict === "BUY" || verdict === "STRONG_BUY") && <TrendingUp className="w-3 h-3" />}
      {(verdict === "AVOID" || verdict === "STRONG_AVOID") && <TrendingDown className="w-3 h-3" />}
      {verdict === "HOLD" && <MinusCircle className="w-3 h-3" />}
      {s.label}
    </span>
  );
}

function ScoreBar({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  const color =
    pct >= 65 ? "bg-emerald-500" :
    pct >= 45 ? "bg-amber-500" :
                "bg-red-500";
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 bg-gray-200 dark:bg-gray-800 rounded overflow-hidden">
        <div className={`h-full ${color} transition-all duration-300`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs font-bold text-gray-700 dark:text-gray-300 w-8 text-right">{pct}%</span>
    </div>
  );
}

function fmtThreshold(op: string, threshold: number | number[]): string {
  if (op === "between" && Array.isArray(threshold)) {
    return `${threshold[0]} – ${threshold[1]}`;
  }
  return `${op} ${threshold}`;
}

// ─── Persona card ─────────────────────────────────────────────────────────────

function PersonaCard({ persona, onOpen }: { persona: PersonaResult; onOpen: (id: string) => void }) {
  const tint = PERSONA_TINT[persona.id] || "from-gray-500 to-gray-700";
  const passed = persona.checklist.filter(c => c.passed).length;
  const total  = persona.checklist.length;

  return (
    <div className="bg-white dark:bg-gray-900 border border-gray-100 dark:border-white/10 rounded-xl overflow-hidden hover:shadow-md transition">
      <div className={`h-1.5 bg-gradient-to-r ${tint}`} />
      <div className="p-4 space-y-3">
        <div className="flex items-start justify-between gap-2">
          <div>
            <div className="flex items-center gap-1.5">
              <h3 className="font-bold text-gray-900 dark:text-white text-sm">{persona.name}</h3>
              <RegionBadge region={regionOf(persona)} />
            </div>
            <p className="text-[11px] text-gray-500 dark:text-gray-400">{persona.firm}</p>
          </div>
          <VerdictBadge verdict={persona.verdict} />
        </div>

        <p className="text-xs text-gray-600 dark:text-gray-400 italic line-clamp-2">
          {persona.philosophy}
        </p>

        <div>
          <div className="flex items-center justify-between text-[11px] text-gray-500 dark:text-gray-400 mb-1">
            <span>{passed}/{total} checks passed</span>
          </div>
          <ScoreBar score={persona.score} />
        </div>

        <ul className="space-y-1 max-h-40 overflow-y-auto pr-1">
          {persona.checklist.map((c, i) => (
            <li key={i} className="flex items-start gap-1.5 text-[11px] leading-tight">
              {c.passed
                ? <CheckCircle2 className="w-3 h-3 text-emerald-500 mt-0.5 flex-shrink-0" />
                : <XCircle      className="w-3 h-3 text-red-400      mt-0.5 flex-shrink-0" />}
              <span className={c.passed ? "text-gray-700 dark:text-gray-300" : "text-gray-500 dark:text-gray-500 line-through decoration-1"}>
                {c.label}
                <span className="text-gray-400 dark:text-gray-600 ml-1">
                  {c.value !== null ? `(${c.value})` : "(n/a)"}
                </span>
              </span>
            </li>
          ))}
        </ul>

        <button
          onClick={() => onOpen(persona.id)}
          className="w-full text-xs font-medium text-indigo-600 dark:text-indigo-400 hover:text-indigo-700 dark:hover:text-indigo-300 py-1.5 border-t border-gray-100 dark:border-white/10 mt-2 -mb-1 flex items-center justify-center gap-1"
        >
          <Sparkles className="w-3 h-3" />
          Read AI thesis
        </button>
      </div>
    </div>
  );
}

// ─── Persona detail modal ─────────────────────────────────────────────────────

function PersonaThesisModal({ symbol, personaId, onClose }: {
  symbol: string; personaId: string; onClose: () => void;
}) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["agent-thesis", symbol, personaId],
    queryFn:  () => api.agentPersona(symbol, personaId),
    enabled:  !!symbol && !!personaId,
    staleTime: 5 * 60 * 1000,
  });

  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4" onClick={onClose}>
      <div
        className="bg-white dark:bg-gray-900 rounded-2xl shadow-2xl max-w-2xl w-full max-h-[85vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className={`h-2 bg-gradient-to-r ${PERSONA_TINT[personaId] || "from-gray-500 to-gray-700"}`} />
        <div className="p-6 space-y-4">
          {isLoading && (
            <div className="flex items-center justify-center py-12 text-gray-500">
              <Loader2 className="w-5 h-5 animate-spin mr-2" />
              Asking {personaId}…
            </div>
          )}

          {error && (
            <p className="text-sm text-red-500">Failed to load thesis: {(error as Error).message}</p>
          )}

          {data && (
            <>
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h2 className="text-xl font-bold text-gray-900 dark:text-white">{data.name}</h2>
                  <p className="text-xs text-gray-500 dark:text-gray-400">{data.firm} • {data.era}</p>
                </div>
                <VerdictBadge verdict={data.verdict as Verdict} />
              </div>

              <blockquote className="border-l-4 border-indigo-400 pl-3 py-1 text-sm italic text-gray-600 dark:text-gray-400">
                <Quote className="inline w-3 h-3 mr-1 text-indigo-400" />
                {data.signature}
              </blockquote>

              <div>
                <h3 className="text-xs font-bold uppercase tracking-wider text-gray-400 mb-1">Score</h3>
                <ScoreBar score={data.score} />
              </div>

              <div>
                <h3 className="text-xs font-bold uppercase tracking-wider text-gray-400 mb-2">Verdict thesis</h3>
                <div className="text-sm text-gray-800 dark:text-gray-200 whitespace-pre-line leading-relaxed">
                  {data.thesis}
                </div>
              </div>

              <div>
                <h3 className="text-xs font-bold uppercase tracking-wider text-gray-400 mb-2">Checklist detail</h3>
                <ul className="space-y-1.5">
                  {data.checklist.map((c: ChecklistItem, i: number) => (
                    <li key={i} className="flex items-start gap-2 text-xs">
                      {c.passed
                        ? <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 mt-0.5 flex-shrink-0" />
                        : <XCircle      className="w-3.5 h-3.5 text-red-400      mt-0.5 flex-shrink-0" />}
                      <div className="flex-1">
                        <p className="text-gray-800 dark:text-gray-200 font-medium">
                          {c.label}{" "}
                          <span className="text-gray-400">— target {fmtThreshold(c.op, c.threshold)}, got {c.value !== null ? c.value : "n/a"}</span>
                        </p>
                        {c.detail && <p className="text-gray-500 dark:text-gray-500 italic mt-0.5">{c.detail}</p>}
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            </>
          )}

          <button onClick={onClose} className="w-full mt-4 py-2 text-sm font-medium text-gray-600 dark:text-gray-400 border border-gray-200 dark:border-white/10 rounded hover:bg-gray-50 dark:hover:bg-gray-800">
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Search landing (when no symbol) ──────────────────────────────────────────

function SearchLanding({ onSelect }: { onSelect: (sym: string) => void }) {
  const [input, setInput] = useState("");
  const popular = ["RELIANCE","TCS","HDFCBANK","INFY","ICICIBANK","ITC","SBIN","BAJFINANCE","HINDUNILVR","MARUTI","WIPRO","ASIANPAINT"];

  return (
    <div className="max-w-2xl mx-auto space-y-6 py-6">
      <div className="text-center space-y-2">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-indigo-50 dark:bg-indigo-500/20 text-indigo-700 dark:text-indigo-300 text-xs font-medium">
          <Sparkles className="w-3.5 h-3.5" /> AI Investor Council
        </div>
        <h1 className="text-3xl font-bold text-gray-900 dark:text-white">
          Ask the legends about any Indian stock
        </h1>
        <p className="text-sm text-gray-500 dark:text-gray-400 max-w-lg mx-auto">
          Sixteen famous investors — eight global legends (Buffett, Graham, Lynch, Munger, Klarman, Marks, Dalio, Burry) plus eight Indian icons (Jhunjhunwala, Damani, Agrawal, Kedia, Veliyath, Ramesh Damani, Kacholia, Khanna) — run their documented checklists on any NSE stock and write a short AI thesis in their own voice.
        </p>
      </div>

      <form
        onSubmit={(e) => { e.preventDefault(); if (input.trim()) onSelect(input.trim().toUpperCase()); }}
        className="bg-white dark:bg-gray-900 border border-gray-100 dark:border-white/10 rounded-xl p-4 flex gap-2"
      >
        <div className="flex-1">
          <StockCombobox
            autoFocus
            value={input}
            onChange={setInput}
            onSelect={(s) => onSelect(s.symbol)}
            onSubmit={() => input.trim() && onSelect(input.trim().toUpperCase())}
            placeholder="Enter NSE symbol or company name (e.g. RELIANCE)…"
          />
        </div>
        <button type="submit" className="px-4 py-1.5 bg-indigo-600 text-white rounded text-sm font-medium hover:bg-indigo-700">
          Ask the Council
        </button>
      </form>

      <div>
        <p className="text-xs text-gray-400 uppercase tracking-wider mb-2">Popular stocks</p>
        <div className="flex flex-wrap gap-2">
          {popular.map((s) => (
            <button
              key={s}
              onClick={() => onSelect(s)}
              className="px-3 py-1 text-xs font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-900 border border-gray-200 dark:border-white/10 rounded-full hover:border-indigo-400 hover:text-indigo-600 dark:hover:text-indigo-400 transition"
            >
              {s}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function InvestorCouncil() {
  const [, params]  = useRoute("/agents/:symbol");
  const [, navigate] = useLocation();
  const symbol = params?.symbol?.toUpperCase() || "";
  const cameFromLink = useRef(document.referrer !== "" || window.history.length > 1);

  const [openPersona, setOpenPersona] = useState<string | null>(null);
  const [view, setView] = useState<"cards" | "matrix">("cards");
  const [region, setRegion] = useState<RegionFilter>("all");

  const { data, isLoading, error } = useQuery({
    queryKey: ["agent-council", symbol],
    queryFn:  () => api.agentCouncil(symbol),
    enabled:  !!symbol,
    staleTime: 5 * 60 * 1000,
  });

  // Reset modal when symbol changes
  useEffect(() => { setOpenPersona(null); }, [symbol]);

  if (!symbol) {
    return <SearchLanding onSelect={(s) => navigate(`/agents/${encodeURIComponent(s)}`)} />;
  }

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-3">
          {cameFromLink.current ? (
            <button
              onClick={() => window.history.back()}
              title="Go back"
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-sm font-medium text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 hover:text-gray-900 dark:hover:text-white transition-colors flex-shrink-0"
            >
              <ArrowLeft className="w-4 h-4" />
              Back
            </button>
          ) : (
            <button
              onClick={() => navigate("/agents")}
              className="text-xs text-gray-500 hover:text-indigo-600 dark:hover:text-indigo-400 flex items-center gap-1"
            >
              <ArrowLeft className="w-3 h-3" /> Different stock
            </button>
          )}
        </div>
        <button
          onClick={() => navigate(`/stocks?symbol=${encodeURIComponent(symbol)}`)}
          className="text-xs text-indigo-600 dark:text-indigo-400 hover:underline"
        >
          See full stock analysis →
        </button>
      </div>

      {isLoading && (
        <div className="flex items-center justify-center py-20 text-gray-500">
          <Loader2 className="w-5 h-5 animate-spin mr-2" />
          Convening the council for {symbol}…
        </div>
      )}

      {error && (
        <div className="bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/30 rounded-xl p-4 text-sm text-red-700 dark:text-red-300">
          Could not load council for <strong>{symbol}</strong>: {(error as Error).message}
        </div>
      )}

      {data && (
        <CouncilContent
          data={data}
          symbol={symbol}
          view={view}
          onChangeView={setView}
          region={region}
          onChangeRegion={setRegion}
          onOpenPersona={setOpenPersona}
        />
      )}

      {openPersona && symbol && (
        <PersonaThesisModal
          symbol={symbol}
          personaId={openPersona}
          onClose={() => setOpenPersona(null)}
        />
      )}
    </div>
  );
}

function deriveCouncilStats(personas: PersonaResult[]) {
  const buyCount   = personas.filter(p => p.verdict === "BUY"   || p.verdict === "STRONG_BUY").length;
  const avoidCount = personas.filter(p => p.verdict === "AVOID" || p.verdict === "STRONG_AVOID").length;
  const holdCount  = personas.filter(p => p.verdict === "HOLD").length;
  const avgScore   = personas.length
    ? personas.reduce((s, p) => s + p.score, 0) / personas.length
    : 0;
  let verdict: Verdict = "HOLD";
  if (personas.length > 0) {
    if (buyCount > avoidCount && avgScore >= 0.65)      verdict = "STRONG_BUY";
    else if (buyCount > avoidCount)                      verdict = "BUY";
    else if (avoidCount > buyCount && avgScore < 0.35)   verdict = "STRONG_AVOID";
    else if (avoidCount > buyCount)                      verdict = "AVOID";
  }
  return { buyCount, avoidCount, holdCount, avgScore, verdict };
}

function CouncilContent({ data, symbol, view, onChangeView, region, onChangeRegion, onOpenPersona }: {
  data: CouncilResponse;
  symbol: string;
  view: "cards" | "matrix";
  onChangeView: (v: "cards" | "matrix") => void;
  region: RegionFilter;
  onChangeRegion: (r: RegionFilter) => void;
  onOpenPersona: (id: string) => void;
}) {
  const counts = {
    all:    data.personas.length,
    Global: data.personas.filter(p => regionOf(p) === "Global").length,
    India:  data.personas.filter(p => regionOf(p) === "India").length,
  };

  const filteredPersonas = region === "all"
    ? data.personas
    : data.personas.filter(p => regionOf(p) === region);

  // When showing all personas, prefer the council stats already computed by the
  // backend (it may apply weighting). For region-filtered subsets, recompute
  // locally so the header reflects the visible voices.
  const stats = region === "all"
    ? {
        buyCount:   data.council.buyCount,
        holdCount:  data.council.holdCount,
        avoidCount: data.council.avoidCount,
        avgScore:   data.council.avgScore,
        verdict:    data.council.verdict,
      }
    : deriveCouncilStats(filteredPersonas);

  const verdictStyle = VERDICT_STYLE[stats.verdict];

  return (
    <>
      <div className="bg-gradient-to-br from-indigo-50 to-violet-50 dark:from-indigo-500/10 dark:to-violet-500/10 border border-indigo-100 dark:border-indigo-500/20 rounded-2xl p-6">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <p className="text-xs uppercase tracking-wider text-indigo-600 dark:text-indigo-400 font-bold mb-1">
              Investor Council Verdict
              {region !== "all" && (
                <span className="ml-2 normal-case tracking-normal text-[11px] text-gray-500 dark:text-gray-400 font-medium">
                  · {region} voices only
                </span>
              )}
            </p>
            <h1 className="text-3xl font-bold text-gray-900 dark:text-white">
              {data.name || symbol}{" "}
              <span className="text-base font-normal text-gray-400">({symbol})</span>
            </h1>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
              {data.sector || "—"} {data.lastPrice ? ` • ₹${data.lastPrice.toLocaleString()}` : ""}
            </p>
          </div>
          <div className="text-right space-y-1">
            <div className={`inline-block px-4 py-1.5 rounded-full text-base font-bold ${verdictStyle.bg} ${verdictStyle.text}`}>
              {verdictStyle.label}
            </div>
            <p className="text-xs text-gray-500 dark:text-gray-400">
              Avg score {Math.round(stats.avgScore * 100)}% across {filteredPersonas.length} personas
            </p>
          </div>
        </div>

        <div className="mt-4 flex gap-3 text-xs">
          <span className="px-2 py-1 rounded bg-emerald-100 dark:bg-emerald-500/20 text-emerald-700 dark:text-emerald-300 font-medium">
            {stats.buyCount} buy
          </span>
          <span className="px-2 py-1 rounded bg-amber-100 dark:bg-amber-500/20 text-amber-700 dark:text-amber-300 font-medium">
            {stats.holdCount} hold
          </span>
          <span className="px-2 py-1 rounded bg-red-100 dark:bg-red-500/20 text-red-700 dark:text-red-300 font-medium">
            {stats.avoidCount} avoid
          </span>
        </div>
      </div>

      <div className="flex items-center gap-3 flex-wrap">
        <RegionToggle value={region} onChange={onChangeRegion} counts={counts} />
        <div className="flex items-center gap-1 bg-gray-100 dark:bg-gray-800 rounded-lg p-1 w-fit">
          <button
            onClick={() => onChangeView("cards")}
            className={`flex items-center gap-1.5 px-4 py-1.5 rounded-md text-xs font-medium transition ${view === "cards" ? "bg-white dark:bg-gray-900 text-indigo-700 dark:text-indigo-300 shadow-sm" : "text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"}`}
          >
            <LayoutGrid className="w-3.5 h-3.5" /> Persona Cards
          </button>
          <button
            onClick={() => onChangeView("matrix")}
            className={`flex items-center gap-1.5 px-4 py-1.5 rounded-md text-xs font-medium transition ${view === "matrix" ? "bg-white dark:bg-gray-900 text-indigo-700 dark:text-indigo-300 shadow-sm" : "text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"}`}
          >
            <Grid3x3 className="w-3.5 h-3.5" /> Council View
          </button>
        </div>
      </div>

      {filteredPersonas.length === 0 && (
        <div className="text-sm text-gray-500 dark:text-gray-400 bg-gray-50 dark:bg-gray-900 border border-gray-100 dark:border-white/10 rounded-xl p-6 text-center">
          No {region} personas in this council.
        </div>
      )}

      {filteredPersonas.length > 0 && view === "cards" && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {filteredPersonas.map((p) => (
            <PersonaCard key={p.id} persona={p} onOpen={onOpenPersona} />
          ))}
        </div>
      )}

      {filteredPersonas.length > 0 && view === "matrix" && (
        <CouncilMatrix personas={filteredPersonas} onOpen={onOpenPersona} />
      )}

      <div className="text-xs text-gray-400 dark:text-gray-600 text-center max-w-2xl mx-auto pt-2">
        Each persona's verdict is computed deterministically from public investor checklists; the AI
        thesis is generated by a free language model and is for educational purposes only — not
        personalised investment advice.
      </div>
    </>
  );
}

// ─── Council View — verdict heatmap matrix (consensus vs disagreement at a glance) ─

const VERDICT_HEAT: Record<Verdict, string> = {
  STRONG_BUY:   "bg-emerald-500 text-white",
  BUY:          "bg-emerald-300 text-emerald-950 dark:bg-emerald-500/70 dark:text-white",
  HOLD:         "bg-amber-200 text-amber-900 dark:bg-amber-500/40 dark:text-amber-100",
  AVOID:        "bg-orange-300 text-orange-950 dark:bg-orange-500/70 dark:text-white",
  STRONG_AVOID: "bg-red-500 text-white",
};

function CouncilMatrix({ personas, onOpen }: {
  personas: PersonaResult[]; onOpen: (id: string) => void;
}) {
  // Group all checklist labels into one union, ordered by frequency, so we can
  // build a persona × check matrix.
  const allChecks: string[] = [];
  const seen = new Set<string>();
  personas.forEach(p => p.checklist.forEach(c => {
    if (!seen.has(c.label)) { seen.add(c.label); allChecks.push(c.label); }
  }));

  return (
    <div className="space-y-4">
      {/* Verdict consensus row */}
      <div className="bg-white dark:bg-gray-900 border border-gray-100 dark:border-white/10 rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-100 dark:border-white/10 flex items-center justify-between">
          <div>
            <h3 className="font-bold text-sm text-gray-900 dark:text-white">Council View — verdict consensus</h3>
            <p className="text-[11px] text-gray-500 dark:text-gray-400">All {personas.length} personas side-by-side. Click any cell for the AI thesis.</p>
          </div>
          <div className="hidden md:flex items-center gap-2 text-[10px] text-gray-500">
            {(["STRONG_BUY","BUY","HOLD","AVOID","STRONG_AVOID"] as Verdict[]).map(v => (
              <span key={v} className={`inline-block w-3 h-3 rounded ${VERDICT_HEAT[v]}`} title={VERDICT_STYLE[v].label} />
            ))}
            <span>Strong Buy → Strong Avoid</span>
          </div>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-px bg-gray-100 dark:bg-white/10">
          {personas.map((p) => {
            const heat = VERDICT_HEAT[p.verdict];
            const tint = PERSONA_TINT[p.id] || "from-gray-500 to-gray-700";
            return (
              <button
                key={p.id}
                onClick={() => onOpen(p.id)}
                className="bg-white dark:bg-gray-900 p-3 text-left hover:ring-2 hover:ring-indigo-400 transition flex flex-col gap-2"
                title={`${p.name} — ${VERDICT_STYLE[p.verdict].label} (${Math.round(p.score * 100)}%)`}
              >
                <div className={`h-1 rounded bg-gradient-to-r ${tint}`} />
                <div className="text-[11px] font-bold text-gray-900 dark:text-white truncate">{p.name.split(" ").slice(-1)[0]}</div>
                <div className={`text-[10px] font-bold rounded px-1.5 py-1 text-center ${heat}`}>
                  {VERDICT_STYLE[p.verdict].label}
                </div>
                <div className="text-[10px] text-gray-500 dark:text-gray-400 text-center">{Math.round(p.score * 100)}%</div>
              </button>
            );
          })}
        </div>
      </div>

      {/* Checklist matrix — persona × check */}
      <div className="bg-white dark:bg-gray-900 border border-gray-100 dark:border-white/10 rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-100 dark:border-white/10">
          <h3 className="font-bold text-sm text-gray-900 dark:text-white">Checklist matrix</h3>
          <p className="text-[11px] text-gray-500 dark:text-gray-400">Green = passed • red = failed • blank = not in this persona's checklist</p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-[11px]">
            <thead className="bg-gray-50 dark:bg-gray-800/50">
              <tr>
                <th className="text-left px-3 py-2 font-medium text-gray-500 dark:text-gray-400 sticky left-0 bg-gray-50 dark:bg-gray-800/50 z-10 min-w-[180px]">Check</th>
                {personas.map(p => (
                  <th key={p.id} className="px-2 py-2 font-medium text-gray-500 dark:text-gray-400 text-center min-w-[64px]">
                    {p.name.split(" ").slice(-1)[0]}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {allChecks.map((label) => (
                <tr key={label} className="border-t border-gray-100 dark:border-white/5">
                  <td className="px-3 py-1.5 text-gray-700 dark:text-gray-300 sticky left-0 bg-white dark:bg-gray-900 z-10">
                    {label}
                  </td>
                  {personas.map(p => {
                    const c = p.checklist.find(x => x.label === label);
                    if (!c) {
                      return <td key={p.id} className="px-2 py-1.5 text-center text-gray-300 dark:text-gray-700">·</td>;
                    }
                    return (
                      <td key={p.id} className="px-2 py-1.5 text-center" title={`${p.name}: ${label} ${c.passed ? "✓" : "✗"} (value ${c.value ?? "n/a"})`}>
                        {c.passed
                          ? <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 inline" />
                          : <XCircle      className="w-3.5 h-3.5 text-red-400      inline" />}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
