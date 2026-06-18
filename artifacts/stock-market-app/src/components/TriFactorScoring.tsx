import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import {
  Activity, BarChart2, Newspaper, TrendingUp, TrendingDown,
  Minus, RefreshCw, AlertCircle, ChevronDown, ChevronRight, Info, Users,
} from "lucide-react";

interface TriFactorData {
  symbol: string;
  scores: { technical: number; fundamental: number; sentiment: number; ownership: number };
  factors: {
    technical: {
      price: number | null; ema50: number | null; ema200: number | null;
      rsi14: number | null; trend_score: number; momentum_score: number; score: number;
      // Optional diagnostics the backend includes (adaptive long-EMA window,
      // bar count, and a human-readable data-completeness note).
      ema_long_window?: number; bars?: number; data_note?: string | null;
    };
    fundamental: {
      pe: number | null; sector_pe: number; sector: string | null;
      eps_growth_pct: number | null; debt_to_equity: number | null;
      valuation_score: number; health_score: number;
    };
    sentiment: {
      bullish: number; bearish: number; neutral: number;
      total: number; headlines: Array<{ title: string; sentiment: string }>;
    };
    ownership: {
      promoter_pct: number | null; promoter_pledge_pct: number | null;
      promoter_change: number | null; institutional_change: number | null;
      fii_pct: number | null; dii_pct: number | null;
      pledge_score: number; promoter_trend_score: number; institutional_trend_score: number;
      as_on: string | null; data_note: string | null;
    };
  };
}

const CX = 110, CY = 95, R = 78;
// BUY/SELL thresholds — with 1/3 equal weights and each factor capped at ±1,
// two factors strongly aligned yields ~0.33; use ±0.25 so the model signals
const BUY_THRESH  =  0.25;
const SELL_THRESH = -0.25;

function scoreToDeg(s: number) {
  // score -1 → 180°, 0 → 90°, +1 → 0°
  return 180 - ((s + 1) / 2) * 180;
}

function degToXY(deg: number) {
  const rad = deg * (Math.PI / 180);
  return { x: CX + R * Math.cos(rad), y: CY - R * Math.sin(rad) };
}

function ScoreGauge({ score, color }: { score: number; color: string }) {
  const TOTAL_LEN = Math.PI * R;
  // fillLen goes from 0 (score=-1) to TOTAL_LEN (score=+1)
  const fillLen = Math.max(0, Math.min(TOTAL_LEN, ((score + 1) / 2) * TOTAL_LEN));
  const needle  = degToXY(scoreToDeg(score));

  const signal   = score >= BUY_THRESH ? "BUY" : score <= SELL_THRESH ? "SELL" : "HOLD";
  const sigColor = score >= BUY_THRESH ? "#10b981" : score <= SELL_THRESH ? "#ef4444" : "#94a3b8";

  // Threshold tick positions
  const buyTick  = degToXY(scoreToDeg(BUY_THRESH));
  const sellTick = degToXY(scoreToDeg(SELL_THRESH));

  const W = CX * 2;   // 220
  const H = CY + 20;  // 115

  return (
    <div className="flex flex-col items-center select-none">
      <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`}>
        {/* ── Background track ──────────────────────────────── */}
        {/* sweep-flag=1 = clockwise in SVG = goes UPWARD through top ✓ */}
        <path
          d={`M ${CX - R} ${CY} A ${R} ${R} 0 0 1 ${CX + R} ${CY}`}
          fill="none" stroke="currentColor" strokeWidth="10" strokeLinecap="round"
          className="text-gray-200 dark:text-slate-700"
        />

        {/* ── Colored fill (left → needle, clockwise through top) ─ */}
        {fillLen > 0.5 && (
          <path
            d={`M ${CX - R} ${CY} A ${R} ${R} 0 0 1 ${CX + R} ${CY}`}
            fill="none" stroke={color} strokeWidth="10" strokeLinecap="round"
            strokeDasharray={`${fillLen} ${TOTAL_LEN + 1}`}
          />
        )}

        {/* ── BUY/SELL threshold ticks ─────────────────────── */}
        <circle cx={buyTick.x}  cy={buyTick.y}  r="3" fill="#10b981" opacity="0.7" />
        <circle cx={sellTick.x} cy={sellTick.y} r="3" fill="#ef4444" opacity="0.7" />

        {/* ── Needle ───────────────────────────────────────── */}
        <line
          x1={CX} y1={CY}
          x2={needle.x} y2={needle.y}
          stroke={color} strokeWidth="2.5" strokeLinecap="round"
        />
        <circle cx={CX} cy={CY} r="5" fill={color} />

        {/* ── Signal label (inside the arc) ────────────────── */}
        <text x={CX} y={CY - 30} textAnchor="middle" fontSize="19" fontWeight="bold" fill={sigColor}>
          {signal}
        </text>
        <text x={CX} y={CY - 12} textAnchor="middle" fontSize="11" fill={sigColor} fontFamily="monospace">
          {score >= 0 ? "+" : ""}{score.toFixed(3)}
        </text>

        {/* ── Scale labels ─────────────────────────────────── */}
        <text x={CX - R - 4} y={CY + 16} textAnchor="middle" fontSize="9" fill="#94a3b8">−1</text>
        <text x={CX + R + 4} y={CY + 16} textAnchor="middle" fontSize="9" fill="#94a3b8">+1</text>
        <text x={CX}         y={CY - R - 8} textAnchor="middle" fontSize="8" fill="#94a3b8">0</text>
      </svg>
    </div>
  );
}

function ScoreBar({ score, showLabel = true }: { score: number; showLabel?: boolean }) {
  const pct = Math.round(((score + 1) / 2) * 100);
  const color =
    score >= BUY_THRESH ? "bg-emerald-500" : score <= SELL_THRESH ? "bg-red-500" : "bg-gray-400";
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 rounded-full bg-gray-100 dark:bg-slate-700 overflow-hidden">
        <div
          className={`h-full rounded-full transition-all ${color}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      {showLabel && (
        <span className="text-[10px] font-mono w-12 text-right text-gray-500 dark:text-slate-400 shrink-0">
          {score >= 0 ? "+" : ""}{score.toFixed(2)}
        </span>
      )}
    </div>
  );
}

function SubScore({ label, score }: { label: string; score: number | null | undefined }) {
  const s = score ?? 0;
  const color =
    s > 0 ? "text-emerald-600 dark:text-emerald-400"
    : s < 0 ? "text-red-500"
    : "text-gray-400";
  return (
    <div className="flex items-center justify-between text-[11px]">
      <span className="text-gray-500 dark:text-slate-400">{label}</span>
      {score == null
        ? <span className="font-mono text-gray-300 dark:text-slate-600">—</span>
        : <span className={`font-mono font-semibold ${color}`}>
            {s > 0 ? "+" : ""}{s.toFixed(1)}
          </span>
      }
    </div>
  );
}

function FactorCard({
  icon: Icon, label, score, color, children, defaultOpen = false,
}: {
  icon: React.FC<any>; label: string; score: number;
  color: string; children: React.ReactNode; defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const sigText = score >= BUY_THRESH ? "Bullish" : score <= SELL_THRESH ? "Bearish" : "Neutral";
  const sigColor =
    score >= BUY_THRESH ? "text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-900/20"
    : score <= SELL_THRESH ? "text-red-500 bg-red-50 dark:bg-red-900/20"
    : "text-gray-500 bg-gray-50 dark:bg-slate-700";

  return (
    <div className="rounded-xl border border-gray-100 dark:border-slate-700 bg-white dark:bg-slate-800 overflow-hidden">
      <button
        onClick={() => setOpen(p => !p)}
        className="w-full flex items-center gap-3 px-4 py-3 hover:bg-gray-50 dark:hover:bg-slate-700/40 transition text-left"
      >
        <div className={`w-7 h-7 rounded-lg flex items-center justify-center shrink-0 ${color}`}>
          <Icon className="w-3.5 h-3.5" />
        </div>
        <span className="flex-1 text-sm font-semibold text-gray-800 dark:text-slate-200">{label}</span>
        <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full shrink-0 ${sigColor}`}>
          {sigText}
        </span>
        <span className="font-mono text-xs font-bold text-gray-600 dark:text-slate-300 shrink-0 w-10 text-right">
          {score >= 0 ? "+" : ""}{score.toFixed(2)}
        </span>
        {open ? <ChevronDown className="w-3.5 h-3.5 text-gray-400 shrink-0" /> : <ChevronRight className="w-3.5 h-3.5 text-gray-400 shrink-0" />}
      </button>
      <div className="px-4 pb-1">
        <ScoreBar score={score} showLabel={false} />
      </div>
      {open && <div className="px-4 pt-2 pb-3 border-t border-gray-50 dark:border-slate-700 mt-1">{children}</div>}
    </div>
  );
}

function WeightSlider({
  label, icon: Icon, value, onChange, color,
}: {
  label: string; icon: React.FC<any>; value: number;
  onChange: (v: number) => void; color: string;
}) {
  return (
    <div className="flex items-center gap-3">
      <div className={`w-6 h-6 rounded-md flex items-center justify-center shrink-0 ${color}`}>
        <Icon className="w-3 h-3" />
      </div>
      <span className="text-xs text-gray-600 dark:text-slate-400 w-24 shrink-0">{label}</span>
      <input
        type="range" min={0} max={100} value={Math.round(value * 100)}
        onChange={e => onChange(Number(e.target.value) / 100)}
        className="flex-1 accent-indigo-500 h-1.5"
      />
      <span className="text-xs font-mono w-9 text-right text-gray-700 dark:text-slate-300 shrink-0">
        {Math.round(value * 100)}%
      </span>
    </div>
  );
}

function SentimentIcon({ s }: { s: string }) {
  if (s === "bullish") return <TrendingUp className="w-3 h-3 text-emerald-500 shrink-0" />;
  if (s === "bearish") return <TrendingDown className="w-3 h-3 text-red-500 shrink-0" />;
  return <Minus className="w-3 h-3 text-gray-400 shrink-0" />;
}

interface Props { symbol: string }

export default function TriFactorScoring({ symbol }: Props) {
  const { data, isLoading, error, refetch, isFetching } = useQuery<TriFactorData>({
    queryKey: ["tri-factor", symbol],
    queryFn: () => api.stockTriFactor(symbol),
    staleTime: 5 * 60 * 1000,
    enabled: !!symbol,
  });

  const [weights, setWeights] = useState({ t: 0.25, f: 0.25, s: 0.25, o: 0.25 });

  function handleWeight(key: "t" | "f" | "s" | "o", val: number) {
    const clamped = Math.max(0, Math.min(1, val));
    const others = (["t", "f", "s", "o"] as const).filter(k => k !== key);
    const rem = 1 - clamped;
    const sum = others.reduce((a, k) => a + weights[k], 0);
    const newWeights = { ...weights, [key]: clamped };
    if (sum > 0) {
      for (const k of others) newWeights[k] = (weights[k] / sum) * rem;
    } else {
      for (const k of others) newWeights[k] = rem / others.length;
    }
    setWeights(newWeights);
  }

  const composite = useMemo(() => {
    if (!data) return 0;
    const { technical, fundamental, sentiment, ownership } = data.scores;
    return Math.max(-1, Math.min(1,
      technical * weights.t + fundamental * weights.f
        + sentiment * weights.s + (ownership ?? 0) * weights.o
    ));
  }, [data, weights]);

  const gaugeColor =
    composite >= BUY_THRESH ? "#10b981" : composite <= SELL_THRESH ? "#ef4444" : "#6b7280";

  if (isLoading) {
    return (
      <div className="space-y-3">
        {[...Array(5)].map((_, i) => (
          <div key={i} className="h-16 bg-gray-100 dark:bg-slate-800 animate-pulse rounded-xl" />
        ))}
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="flex items-center gap-2 p-4 rounded-xl bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-sm text-red-600 dark:text-red-400">
        <AlertCircle className="w-4 h-4 shrink-0" />
        <span>{(error as Error)?.message || "Failed to load scoring data"}</span>
        <button onClick={() => refetch()} className="ml-auto text-xs underline">Retry</button>
      </div>
    );
  }

  const { factors } = data;
  const tech = factors.technical;
  const fund = factors.fundamental;
  const sent = factors.sentiment;
  const own  = factors.ownership;

  return (
    <div className="space-y-4">
      {/* Top row: Gauge + Weights */}
      <div className="bg-white dark:bg-slate-800 rounded-xl border border-gray-100 dark:border-slate-700 p-5">
        <div className="flex items-start justify-between mb-1">
          <div>
            <h3 className="text-sm font-semibold text-gray-800 dark:text-slate-200">
              Composite Score
            </h3>
            <p className="text-[11px] text-gray-400 dark:text-slate-500 mt-0.5">
              Technical × Fundamental × Sentiment × Ownership — adjust weights below
            </p>
          </div>
          <button
            onClick={() => refetch()}
            disabled={isFetching}
            title="Refresh"
            className="p-1.5 rounded-lg text-gray-400 hover:text-indigo-600 hover:bg-indigo-50 dark:hover:bg-indigo-900/30 transition"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isFetching ? "animate-spin text-indigo-500" : ""}`} />
          </button>
        </div>

        <div className="flex flex-col sm:flex-row gap-6 items-center mt-2">
          <div className="shrink-0">
            <ScoreGauge score={composite} color={gaugeColor} />
          </div>
          <div className="flex-1 w-full space-y-3">
            <WeightSlider
              label="Technical" icon={Activity} value={weights.t}
              onChange={v => handleWeight("t", v)}
              color="bg-sky-100 text-sky-600 dark:bg-sky-900/40 dark:text-sky-400"
            />
            <WeightSlider
              label="Fundamental" icon={BarChart2} value={weights.f}
              onChange={v => handleWeight("f", v)}
              color="bg-violet-100 text-violet-600 dark:bg-violet-900/40 dark:text-violet-400"
            />
            <WeightSlider
              label="Sentiment" icon={Newspaper} value={weights.s}
              onChange={v => handleWeight("s", v)}
              color="bg-amber-100 text-amber-600 dark:bg-amber-900/40 dark:text-amber-400"
            />
            <WeightSlider
              label="Ownership" icon={Users} value={weights.o}
              onChange={v => handleWeight("o", v)}
              color="bg-rose-100 text-rose-600 dark:bg-rose-900/40 dark:text-rose-400"
            />
            <div className="text-[10px] text-gray-400 dark:text-slate-600 flex items-center gap-1">
              <Info className="w-2.5 h-2.5" />
              Sliders auto-balance to 100%
            </div>
          </div>
        </div>
      </div>

      {/* Score breakdown cards */}
      <FactorCard
        icon={Activity} label="Technical Analysis" score={data.scores.technical}
        color="bg-sky-100 text-sky-600 dark:bg-sky-900/40 dark:text-sky-400"
        defaultOpen
      >
        <div className="space-y-2">
          {/* Adaptive EMA note — info tone, not a warning */}
          {tech.data_note && (
            <div className="flex items-start gap-1.5 text-[10px] text-sky-600 dark:text-sky-400 bg-sky-50 dark:bg-sky-900/20 rounded-lg px-2.5 py-1.5">
              <span className="mt-px shrink-0">ℹ</span>
              <span>{tech.data_note}</span>
            </div>
          )}
          <SubScore label="Trend sub-score" score={tech.trend_score ?? null} />
          <SubScore label="Momentum sub-score" score={tech.momentum_score ?? null} />
          <div className="border-t border-gray-100 dark:border-slate-700 pt-2 mt-1 grid grid-cols-2 gap-x-6 gap-y-1.5">
            {[
              ["Current Price", tech.price != null ? `₹${tech.price.toLocaleString("en-IN")}` : "—"],
              ["EMA 50",        tech.ema50  != null ? `₹${tech.ema50.toLocaleString("en-IN")}` : "—"],
              // Label dynamically: "EMA 200" for full history, "EMA N" for adaptive
              [`EMA ${tech.ema_long_window ?? 200}`,
                                tech.ema200 != null ? `₹${tech.ema200.toLocaleString("en-IN")}` : "—"],
              ["RSI (14)",      tech.rsi14  != null ? (tech.rsi14 as number).toFixed(1) : "—"],
              ...(tech.bars != null ? [["Price bars", String(tech.bars)]] : []),
            ].map(([k, v]) => (
              <div key={k as string} className="flex justify-between text-[11px]">
                <span className="text-gray-400 dark:text-slate-500">{k}</span>
                <span className="font-mono text-gray-700 dark:text-slate-300">{v}</span>
              </div>
            ))}
          </div>
          <p className="text-[10px] text-gray-400 dark:text-slate-600 mt-1">
            Trend: ±0.5 (price&gt;EMA50&gt;EMA<em>{tech.ema_long_window ?? 200}</em>) or ±0.25 (EMA50 only &lt;100 bars) &nbsp;·&nbsp; Momentum: RSI linear ±0.5 around 50
          </p>
        </div>
      </FactorCard>

      <FactorCard
        icon={BarChart2} label="Fundamental Analysis" score={data.scores.fundamental}
        color="bg-violet-100 text-violet-600 dark:bg-violet-900/40 dark:text-violet-400"
      >
        <div className="space-y-2">
          <SubScore label="Valuation sub-score" score={fund.valuation_score} />
          <SubScore label="Health sub-score" score={fund.health_score} />
          <div className="border-t border-gray-100 dark:border-slate-700 pt-2 mt-1 grid grid-cols-2 gap-x-6 gap-y-1.5">
            {[
              ["Trailing P/E", fund.pe != null ? fund.pe.toFixed(1) : "—"],
              [`${fund.sector || "Sector"} P/E`, fund.sector_pe.toFixed(1)],
              ["EPS Growth (TTM)", fund.eps_growth_pct != null ? `${fund.eps_growth_pct >= 0 ? "+" : ""}${fund.eps_growth_pct}%` : "—"],
              ["Debt / Equity", fund.debt_to_equity != null ? fund.debt_to_equity.toFixed(2) : "—"],
            ].map(([k, v]) => (
              <div key={k as string} className="flex justify-between text-[11px]">
                <span className="text-gray-400 dark:text-slate-500 truncate mr-1">{k}</span>
                <span className="font-mono text-gray-700 dark:text-slate-300 shrink-0">{v}</span>
              </div>
            ))}
          </div>
          <p className="text-[10px] text-gray-400 dark:text-slate-600 mt-1">
            Valuation: P/E vs sector &nbsp;·&nbsp; Health: EPS growth &amp; D/E
          </p>
        </div>
      </FactorCard>

      <FactorCard
        icon={Newspaper} label="News Sentiment" score={data.scores.sentiment}
        color="bg-amber-100 text-amber-600 dark:bg-amber-900/40 dark:text-amber-400"
      >
        <div className="space-y-2">
          {sent.total > 0 ? (
            <>
              <div className="flex gap-4 text-[11px]">
                {[
                  { label: "Bullish", val: sent.bullish, cls: "text-emerald-600 dark:text-emerald-400" },
                  { label: "Bearish", val: sent.bearish, cls: "text-red-500" },
                  { label: "Neutral", val: sent.neutral, cls: "text-gray-400" },
                ].map(({ label, val, cls }) => (
                  <div key={label} className="flex flex-col items-center">
                    <span className={`text-base font-bold ${cls}`}>{val}</span>
                    <span className="text-gray-400 dark:text-slate-500">{label}</span>
                  </div>
                ))}
                <div className="flex flex-col items-center ml-auto">
                  <span className="text-base font-bold text-gray-600 dark:text-slate-300">{sent.total}</span>
                  <span className="text-gray-400 dark:text-slate-500">Articles</span>
                </div>
              </div>

              {/* Mini bar */}
              <div className="flex h-1.5 rounded-full overflow-hidden gap-px">
                {sent.bullish > 0 && (
                  <div className="bg-emerald-400" style={{ flex: sent.bullish }} />
                )}
                {sent.neutral > 0 && (
                  <div className="bg-gray-300 dark:bg-slate-600" style={{ flex: sent.neutral }} />
                )}
                {sent.bearish > 0 && (
                  <div className="bg-red-400" style={{ flex: sent.bearish }} />
                )}
              </div>

              {sent.headlines.length > 0 && (
                <div className="mt-2 space-y-1.5">
                  {sent.headlines.map((h, i) => (
                    <div key={i} className="flex items-start gap-1.5">
                      <SentimentIcon s={h.sentiment} />
                      <p className="text-[11px] text-gray-600 dark:text-slate-400 leading-snug line-clamp-2">
                        {h.title}
                      </p>
                    </div>
                  ))}
                </div>
              )}
            </>
          ) : (
            <p className="text-[11px] text-gray-400 dark:text-slate-500 italic">
              No recent news available for sentiment analysis.
            </p>
          )}
          <p className="text-[10px] text-gray-400 dark:text-slate-600 mt-1">
            Score = (Bullish − Bearish) ÷ Total — powered by VADER NLP
          </p>
        </div>
      </FactorCard>

      <FactorCard
        icon={Users} label="Ownership & Conviction" score={data.scores.ownership ?? 0}
        color="bg-rose-100 text-rose-600 dark:bg-rose-900/40 dark:text-rose-400"
      >
        <div className="space-y-2">
          {own.data_note && (
            <div className="flex items-start gap-1.5 text-[10px] text-rose-600 dark:text-rose-400 bg-rose-50 dark:bg-rose-900/20 rounded-lg px-2.5 py-1.5">
              <span className="mt-px shrink-0">ℹ</span>
              <span>{own.data_note}</span>
            </div>
          )}
          <SubScore label="Promoter pledge (risk)" score={own.pledge_score ?? null} />
          <SubScore label="Promoter stake trend (QoQ)" score={own.promoter_trend_score ?? null} />
          <SubScore label="Institutional FII+DII trend (QoQ)" score={own.institutional_trend_score ?? null} />
          <div className="border-t border-gray-100 dark:border-slate-700 pt-2 mt-1 grid grid-cols-2 gap-x-6 gap-y-1.5">
            {[
              ["Promoter holding", own.promoter_pct != null ? `${own.promoter_pct.toFixed(2)}%` : "—"],
              ["Promoter pledge",  own.promoter_pledge_pct != null ? `${own.promoter_pledge_pct.toFixed(2)}%` : "—"],
              ["Promoter Δ QoQ",   own.promoter_change != null ? `${own.promoter_change >= 0 ? "+" : ""}${own.promoter_change}%` : "—"],
              ["FII+DII Δ QoQ",    own.institutional_change != null ? `${own.institutional_change >= 0 ? "+" : ""}${own.institutional_change}%` : "—"],
              ["FII / DII",        (own.fii_pct != null || own.dii_pct != null)
                                     ? `${own.fii_pct != null ? own.fii_pct.toFixed(1) : "—"} / ${own.dii_pct != null ? own.dii_pct.toFixed(1) : "—"}%`
                                     : "—"],
              ...(own.as_on ? [["As of", own.as_on]] : []),
            ].map(([k, v]) => (
              <div key={k as string} className="flex justify-between text-[11px]">
                <span className="text-gray-400 dark:text-slate-500 truncate mr-1">{k}</span>
                <span className="font-mono text-gray-700 dark:text-slate-300 shrink-0">{v}</span>
              </div>
            ))}
          </div>
          <p className="text-[10px] text-gray-400 dark:text-slate-600 mt-1">
            Pledge penalty (−0.15 to −0.6) · promoter &amp; institutional stake trend (±0.25 QoQ) — from SEBI shareholding filings
          </p>
        </div>
      </FactorCard>

      {/* Signal legend */}
      <div className="flex flex-wrap items-center gap-3 text-[10px] text-gray-400 dark:text-slate-500 px-1">
        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-emerald-500 inline-block" /> BUY ≥ +{BUY_THRESH}</span>
        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-gray-400 inline-block" /> HOLD {SELL_THRESH} to +{BUY_THRESH}</span>
        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-red-500 inline-block" /> SELL ≤ {SELL_THRESH}</span>
        <span className="ml-auto italic">For educational use only — not investment advice</span>
      </div>
    </div>
  );
}
