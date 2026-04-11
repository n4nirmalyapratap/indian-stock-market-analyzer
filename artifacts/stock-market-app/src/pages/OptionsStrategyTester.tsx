import { useState, useCallback, useEffect, useRef } from "react";
import { fetchApi } from "@/lib/api";
import { fmtINR, pct, fmt, clr, bg, computeHeatBars, QUICK_STRATEGIES } from "@/lib/options-utils";
import { useTheme } from "@/context/ThemeContext";
import {
  TrendingUp, TrendingDown, Plus, Trash2, Play, BarChart2,
  AlertTriangle, RefreshCw, ChevronDown, Target, Activity,
  Shield, Zap, Info, X, Sparkles, BookOpen
} from "lucide-react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ReferenceLine, ResponsiveContainer, BarChart, Bar, Cell
} from "recharts";

// ── API helpers ───────────────────────────────────────────────────────────────
const J = { "Content-Type": "application/json" };
function post<T = any>(path: string, body: unknown) {
  return fetchApi<T>(path, { method: "POST", headers: J, body: JSON.stringify(body) });
}
function get<T = any>(path: string) { return fetchApi<T>(path); }

// ── Types ─────────────────────────────────────────────────────────────────────
interface Leg {
  id:          string;
  action:      "buy" | "sell";
  option_type: "call" | "put";
  strike:      number;
  premium:     number;
  lots:        number;
  lot_size:    number;
  iv:          number;
}

interface SpotInfo { spot: number; hv30: number; hv30_pct: number; lot_size: number; atm: number; }
interface Greeks   { delta: number; gamma: number; theta: number; vega: number; rho: number; }

// ── Preset strategies ─────────────────────────────────────────────────────────
const PRESETS = [
  "long_call","long_put","short_call","short_put",
  "straddle","short_straddle","strangle","short_strangle",
  "bull_call_spread","bear_put_spread","iron_condor","butterfly",
];

const PRESET_LABELS: Record<string, string> = {
  long_call: "Long Call", long_put: "Long Put",
  short_call: "Short Call", short_put: "Short Put",
  straddle: "Long Straddle", short_straddle: "Short Straddle",
  strangle: "Long Strangle", short_strangle: "Short Strangle",
  bull_call_spread: "Bull Call Spread", bear_put_spread: "Bear Put Spread",
  iron_condor: "Iron Condor", butterfly: "Butterfly",
};

// otmMult: offset = step×3 × mult  (e.g. 1 = 1 OTM wing)
// spreadMult: offset = step × mult  (finer control, for butterfly wings)
type QuickLeg = Partial<Leg> & { otmMult?: number; spreadMult?: number };

type Outlook = "bullish" | "bearish" | "neutral" | "volatile";
const OUTLOOK_CHIP: Record<Outlook, string> = {
  bullish:  "text-emerald-700 bg-emerald-50  border-emerald-200 hover:bg-emerald-100",
  bearish:  "text-rose-700   bg-rose-50    border-rose-200   hover:bg-rose-100",
  neutral:  "text-indigo-700 bg-indigo-50  border-indigo-200 hover:bg-indigo-100",
  volatile: "text-amber-700  bg-amber-50   border-amber-200  hover:bg-amber-100",
};
const OUTLOOK_DOT: Record<Outlook, string> = {
  bullish:  "bg-emerald-400",
  bearish:  "bg-rose-400",
  neutral:  "bg-indigo-400",
  volatile: "bg-amber-400",
};

const STRATEGY_GROUPS = [
  { label: "Directional", items: QUICK_STRATEGIES.filter(s => s.category === "Directional") },
  { label: "Volatility",  items: QUICK_STRATEGIES.filter(s => s.category === "Volatility") },
  { label: "Spreads",     items: QUICK_STRATEGIES.filter(s => s.category === "Spreads") },
  { label: "Multi-leg",   items: QUICK_STRATEGIES.filter(s => s.category === "Multi-leg") },
];

// ── Components ────────────────────────────────────────────────────────────────
function Loader() {
  return (
    <div className="flex items-center gap-2 text-indigo-500 text-sm">
      <RefreshCw className="w-4 h-4 animate-spin" />
      <span>Loading…</span>
    </div>
  );
}

function Pill({ label, value, color = "gray" }: { label: string; value: string; color?: string }) {
  return (
    <div className="bg-white border border-gray-200 rounded-xl p-3 shadow-sm">
      <p className="text-xs text-gray-500 uppercase tracking-wide mb-1">{label}</p>
      <p className={`text-lg font-bold text-${color}-700`}>{value}</p>
    </div>
  );
}

function GreeksBar({ g }: { g: Greeks }) {
  const items = [
    { sym: "Δ", label: "Delta", val: g.delta, tip: "Price sensitivity per ₹1 move" },
    { sym: "Γ", label: "Gamma", val: g.gamma, tip: "Rate of change of Delta" },
    { sym: "Θ", label: "Theta", val: g.theta, tip: "Daily time decay (₹)" },
    { sym: "ν", label: "Vega",  val: g.vega,  tip: "Sensitivity to 1% IV change" },
    { sym: "ρ", label: "Rho",   val: g.rho,   tip: "Sensitivity to 1% rate change" },
  ];
  return (
    <div className="grid grid-cols-2 gap-1.5">
      {items.map(({ sym, label, val, tip }) => (
        <div key={label} title={tip}
             className="flex items-center justify-between bg-white rounded-lg px-2.5 py-1.5 border border-gray-100 cursor-help">
          <span className="text-[10px] text-gray-500">
            <span className="font-bold">{sym}</span>
            <span className="ml-1 text-gray-400">{label}</span>
          </span>
          <span className={`text-xs font-bold font-mono ml-2 ${clr(val)}`}>{fmt(val, 3)}</span>
        </div>
      ))}
    </div>
  );
}

// ── P&L Heatmap ───────────────────────────────────────────────────────────────
function PnlHeatmap({ spots, payoffs, currentSpot }: {
  spots: number[]; payoffs: number[]; currentSpot?: number;
}) {
  const bars = computeHeatBars(spots, payoffs);

  // Find spot bar nearest to currentSpot
  const nearestIdx = currentSpot
    ? bars.reduce((best, b, i) =>
        Math.abs(b.s - currentSpot) < Math.abs(bars[best].s - currentSpot) ? i : best, 0)
    : -1;

  return (
    <div className="mt-2">
      <div className="flex items-center justify-between mb-1">
        <span className="text-[10px] text-gray-400 font-medium uppercase tracking-wide">P&L Heatmap at Expiry</span>
        <div className="flex items-center gap-3 text-[10px] text-gray-400">
          <span className="flex items-center gap-1"><span className="w-3 h-2 rounded-sm inline-block bg-red-500 opacity-70" /> Loss</span>
          <span className="flex items-center gap-1"><span className="w-3 h-2 rounded-sm inline-block bg-green-600 opacity-70" /> Profit</span>
        </div>
      </div>
      <div className="flex h-8 rounded-lg overflow-hidden border border-gray-100">
        {bars.map((b, i) => (
          <div
            key={i}
            className="flex-1 relative group cursor-default transition-opacity"
            style={{ background: b.color }}
            title={`₹${b.s.toLocaleString("en-IN")} → ${b.pnl >= 0 ? "+" : ""}${b.pnl.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`}
          >
            {i === nearestIdx && (
              <div className="absolute inset-y-0 left-1/2 w-0.5 bg-orange-500 opacity-90" />
            )}
          </div>
        ))}
      </div>
      <div className="flex justify-between text-[9px] text-gray-400 mt-0.5 font-mono">
        <span>₹{bars[0]?.s.toLocaleString("en-IN", { maximumFractionDigits: 0 })}</span>
        {currentSpot && <span className="text-orange-500">↑ Spot</span>}
        <span>₹{bars[bars.length - 1]?.s.toLocaleString("en-IN", { maximumFractionDigits: 0 })}</span>
      </div>
    </div>
  );
}

// ── Strategy Insight Card ──────────────────────────────────────────────────────

const STRATEGY_INFO: Record<string, {
  tagline: string;
  when: string;
  risk: string;
  reward: string;
  outlook: "bullish" | "bearish" | "neutral" | "volatile";
}> = {
  "Long Call":        { tagline: "Unlimited upside with defined risk",         when: "Strong bullish view; expect a sharp rally",          risk: "Limited (premium paid)",  reward: "Unlimited",          outlook: "bullish"  },
  "Short Put":        { tagline: "Collect premium on mild bullish view",        when: "Mildly bullish or neutral; happy to buy at lower level", risk: "High (if market crashes)", reward: "Limited (premium)", outlook: "bullish"  },
  "Long Put":         { tagline: "Unlimited downside profit with defined risk", when: "Strong bearish view or need portfolio hedge",          risk: "Limited (premium paid)",  reward: "Unlimited",          outlook: "bearish"  },
  "Short Call":       { tagline: "Collect premium expecting market to stagnate or fall", when: "Bearish to neutral; expecting sideways or decline",  risk: "Unlimited (if market rallies)", reward: "Limited (premium)", outlook: "bearish" },
  "Long Straddle":    { tagline: "Profit from any big move — direction unknown", when: "High-impact event (budget, earnings) ahead",          risk: "Limited (total premium)", reward: "Unlimited both ways", outlook: "volatile" },
  "Long Strangle":    { tagline: "Cheaper than straddle; needs bigger move",    when: "Expecting large move but want lower cost",            risk: "Limited (total premium)", reward: "Unlimited both ways", outlook: "volatile" },
  "Short Straddle":   { tagline: "Profit from time decay and low volatility",   when: "Range-bound market; IV rich before event",            risk: "Unlimited (gap risk)",    reward: "Limited (net credit)", outlook: "neutral" },
  "Short Strangle":   { tagline: "Wider profit zone than short straddle",       when: "Sideways market with some buffer on both sides",      risk: "Unlimited (gap risk)",    reward: "Limited (net credit)", outlook: "neutral" },
  "Bull Call Spread":  { tagline: "Defined risk, defined reward bullish play",  when: "Moderate bullish view; lower cost than long call",    risk: "Limited (net debit)",     reward: "Limited (spread width − debit)", outlook: "bullish" },
  "Bear Put Spread":   { tagline: "Defined risk, defined reward bearish play",  when: "Moderate bearish view; lower cost than long put",     risk: "Limited (net debit)",     reward: "Limited (spread width − debit)", outlook: "bearish" },
  "Iron Condor":      { tagline: "Collect premium in a defined range",          when: "Low-volatility sideways market; IV is high",          risk: "Limited (net of spreads)",reward: "Limited (net credit)", outlook: "neutral" },
  "Butterfly":        { tagline: "Max profit if spot pins to centre strike",    when: "Expect very small move; approaching expiry",          risk: "Limited (net debit)",     reward: "Limited (highest near centre)", outlook: "neutral" },
};

type OutlookKey = "bullish" | "bearish" | "neutral" | "volatile";

function getOutlookTheme(outlook: OutlookKey, isDark: boolean) {
  const themes: Record<OutlookKey, { light: string; dark: string; border: string; text: string; subtext: string; dot: string; label: string; inner: string }> = {
    bullish:  {
      light:   "bg-emerald-50",   dark:  "bg-emerald-900/20",
      border:  isDark ? "border-emerald-700/50" : "border-emerald-200",
      text:    isDark ? "text-emerald-300"       : "text-emerald-800",
      subtext: isDark ? "text-emerald-400/80"    : "text-emerald-700",
      dot:     "bg-emerald-500",  label: "Bullish",
      inner:   isDark ? "bg-slate-700/60"        : "bg-white/70",
    },
    bearish:  {
      light:   "bg-red-50",       dark:  "bg-red-900/20",
      border:  isDark ? "border-red-700/50"      : "border-red-200",
      text:    isDark ? "text-red-300"            : "text-red-800",
      subtext: isDark ? "text-red-400/80"         : "text-red-700",
      dot:     "bg-red-500",      label: "Bearish",
      inner:   isDark ? "bg-slate-700/60"        : "bg-white/70",
    },
    neutral:  {
      light:   "bg-blue-50",      dark:  "bg-blue-900/20",
      border:  isDark ? "border-blue-700/50"     : "border-blue-200",
      text:    isDark ? "text-blue-300"           : "text-blue-800",
      subtext: isDark ? "text-blue-400/80"        : "text-blue-700",
      dot:     "bg-blue-500",     label: "Neutral",
      inner:   isDark ? "bg-slate-700/60"        : "bg-white/70",
    },
    volatile: {
      light:   "bg-violet-50",    dark:  "bg-violet-900/20",
      border:  isDark ? "border-violet-700/50"   : "border-violet-200",
      text:    isDark ? "text-violet-300"         : "text-violet-800",
      subtext: isDark ? "text-violet-400/80"      : "text-violet-700",
      dot:     "bg-violet-500",   label: "Volatile",
      inner:   isDark ? "bg-slate-700/60"        : "bg-white/70",
    },
  };
  const t = themes[outlook];
  return { ...t, bg: isDark ? t.dark : t.light };
}

function detectStrategy(legs: Array<{ action: string; option_type: string; lots: number; strike: number }>): string | null {
  const bc = legs.filter(l => l.action === "buy"  && l.option_type === "call");
  const sc = legs.filter(l => l.action === "sell" && l.option_type === "call");
  const bp = legs.filter(l => l.action === "buy"  && l.option_type === "put");
  const sp = legs.filter(l => l.action === "sell" && l.option_type === "put");
  const n  = legs.length;
  if (n === 1) {
    if (bc.length === 1) return "Long Call";
    if (sc.length === 1) return "Short Call";
    if (bp.length === 1) return "Long Put";
    if (sp.length === 1) return "Short Put";
  }
  if (n === 2) {
    if (bc.length === 1 && sc.length === 1) return "Bull Call Spread";
    if (bp.length === 1 && sp.length === 1) return "Bear Put Spread";
    if (bc.length === 1 && bp.length === 1) {
      return bc[0].strike === bp[0].strike ? "Long Straddle" : "Long Strangle";
    }
    if (sc.length === 1 && sp.length === 1) {
      return sc[0].strike === sp[0].strike ? "Short Straddle" : "Short Strangle";
    }
  }
  if (n === 3 && bc.length === 2 && sc.length === 1) return "Butterfly";
  if (n === 4 && bc.length === 1 && sc.length === 1 && bp.length === 1 && sp.length === 1) return "Iron Condor";
  return null;
}

// ── Market-fit scoring ────────────────────────────────────────────────────────

type StrategyCategory = "buy_vol" | "sell_vol" | "buy_dir" | "sell_dir" | "spread" | "pin";
type FitVerdict       = "recommended" | "caution" | "avoid";

interface FitSignal {
  label:  string;
  value:  string;
  status: "good" | "warn" | "bad";
}

interface MarketFit {
  verdict:  FitVerdict;
  score:    number;   // 0–100
  signals:  FitSignal[];
  headline: string;
}

const STRATEGY_CATEGORY: Record<string, StrategyCategory> = {
  "Long Call":        "buy_dir",
  "Long Put":         "buy_dir",
  "Short Call":       "sell_dir",
  "Short Put":        "sell_dir",
  "Long Straddle":    "buy_vol",
  "Long Strangle":    "buy_vol",
  "Short Straddle":   "sell_vol",
  "Short Strangle":   "sell_vol",
  "Bull Call Spread": "spread",
  "Bear Put Spread":  "spread",
  "Iron Condor":      "sell_vol",
  "Butterfly":        "pin",
};

function computeMarketFit(
  name: string | null,
  spotInfo: SpotInfo,
  payoff: any,
  greeks: any,
): MarketFit | null {
  if (!name || !spotInfo) return null;
  const cat    = STRATEGY_CATEGORY[name];
  if (!cat) return null;

  const hvPct  = spotInfo.hv30_pct;          // 0–100 percentile
  const hv     = +(spotInfo.hv30 * 100).toFixed(1); // annualised %
  const spot   = spotInfo.spot;
  const maxP   = payoff?.max_profit  as number | null;
  const maxL   = payoff?.max_loss    as number | null;
  const bes    = (payoff?.breakevens ?? []) as number[];
  const theta  = greeks?.theta  ?? 0;
  const vega   = greeks?.vega   ?? 0;

  const rr     = (maxP != null && maxL != null && maxL !== 0)
    ? Math.abs(maxP / maxL)
    : null;
  const beGapPct = bes.length >= 1
    ? Math.min(...bes.map(b => Math.abs(b - spot) / spot * 100))
    : null;

  const signals: FitSignal[] = [];
  let score = 50;

  // ── Vol-regime signal (universal) ─────────────────────────────────────────
  const volLabel = hvPct < 30 ? "Low"
    : hvPct < 55 ? "Moderate"
    : hvPct < 75 ? "High"
    : "Very High";

  if (cat === "buy_vol" || cat === "buy_dir") {
    const ok = hvPct < 40 ? "good" : hvPct < 60 ? "warn" : "bad";
    signals.push({
      label: "Vol Regime",
      value: `HV ${hv}% (${hvPct}th pct) — ${volLabel}`,
      status: ok,
    });
    score += hvPct < 35 ? +30 : hvPct < 50 ? +10 : hvPct < 65 ? -10 : -30;
  } else if (cat === "sell_vol" || cat === "sell_dir") {
    const ok = hvPct > 60 ? "good" : hvPct > 40 ? "warn" : "bad";
    signals.push({
      label: "Vol Regime",
      value: `HV ${hv}% (${hvPct}th pct) — ${hvPct > 60 ? "premium rich ✓" : hvPct > 40 ? "fair" : "premium thin ✗"}`,
      status: ok,
    });
    score += hvPct > 65 ? +30 : hvPct > 50 ? +10 : hvPct > 40 ? -10 : -30;
  } else if (cat === "spread") {
    const ok = hvPct > 30 && hvPct < 70 ? "good" : "warn";
    signals.push({
      label: "Vol Regime",
      value: `HV ${hv}% (${hvPct}th pct) — ${ok === "good" ? "moderate, ideal for spreads" : "extreme vol, less favourable"}`,
      status: ok,
    });
    score += ok === "good" ? +15 : -10;
  } else {  // pin (butterfly)
    const ok = hvPct < 35 ? "good" : hvPct < 50 ? "warn" : "bad";
    signals.push({
      label: "Vol Regime",
      value: `HV ${hv}% (${hvPct}th pct) — ${hvPct < 35 ? "calm, pin play viable" : hvPct < 50 ? "moderate, marginal" : "too volatile for pin"}`,
      status: ok,
    });
    score += hvPct < 30 ? +30 : hvPct < 45 ? +10 : hvPct < 60 ? -15 : -30;
  }

  // ── Breakeven distance ────────────────────────────────────────────────────
  if (beGapPct !== null) {
    if (cat === "sell_vol") {
      // For sell-vol: wider BEs = safer → high gap = good
      const ok = beGapPct > 5 ? "good" : beGapPct > 2.5 ? "warn" : "bad";
      signals.push({
        label: "Buffer to BE",
        value: `${beGapPct.toFixed(1)}% from spot ${ok === "good" ? "— wide safety zone" : ok === "warn" ? "— moderate" : "— tight, gap risk"}`,
        status: ok,
      });
      score += beGapPct > 5 ? +15 : beGapPct > 2.5 ? +5 : -10;
    } else {
      // For buy/spread: smaller gap = easier to reach profit
      const ok = beGapPct < 3 ? "good" : beGapPct < 6 ? "warn" : "bad";
      signals.push({
        label: "Distance to BE",
        value: `${beGapPct.toFixed(1)}% move needed ${ok === "good" ? "— achievable" : ok === "warn" ? "— moderate effort" : "— large move required"}`,
        status: ok,
      });
      score += beGapPct < 3 ? +15 : beGapPct < 6 ? +5 : -15;
    }
  }

  // ── Theta signal ──────────────────────────────────────────────────────────
  const thetaDay = Math.round(theta);
  if (cat === "sell_vol" || cat === "sell_dir") {
    const ok = theta > 100 ? "good" : theta > 0 ? "warn" : "bad";
    signals.push({
      label: "Time Decay",
      value: `+₹${Math.abs(thetaDay).toLocaleString("en-IN")}/day in your favour`,
      status: ok,
    });
    score += theta > 200 ? +15 : theta > 50 ? +8 : theta > 0 ? +3 : -10;
  } else if (cat === "buy_vol" || cat === "buy_dir") {
    const ok = Math.abs(theta) < 200 ? "warn" : "bad";
    signals.push({
      label: "Time Decay",
      value: `-₹${Math.abs(thetaDay).toLocaleString("en-IN")}/day working against you`,
      status: ok,
    });
    score += Math.abs(theta) < 100 ? +5 : Math.abs(theta) < 300 ? 0 : -10;
  }

  // ── R:R signal ────────────────────────────────────────────────────────────
  if (rr !== null) {
    const ok = rr > 1.5 ? "good" : rr > 0.6 ? "warn" : "bad";
    signals.push({
      label: "Reward : Risk",
      value: `${rr.toFixed(2)}× ${ok === "good" ? "— favourable" : ok === "warn" ? "— acceptable" : "— unfavourable"}`,
      status: ok,
    });
    score += rr > 2 ? +15 : rr > 1.2 ? +8 : rr > 0.6 ? +2 : -12;
  }

  // ── Vega signal for vol strategies ───────────────────────────────────────
  if ((cat === "buy_vol" || cat === "sell_vol") && vega !== 0) {
    const isLong = vega > 0;
    const ok: FitSignal["status"] =
      (isLong && cat === "buy_vol") || (!isLong && cat === "sell_vol") ? "good" : "bad";
    signals.push({
      label: "Vol Exposure",
      value: `${isLong ? "+" : ""}${vega.toFixed(0)} vega — ${isLong ? "profits if IV rises" : "profits if IV falls"}`,
      status: ok,
    });
    score += ok === "good" ? +5 : -5;
  }

  // ── Clamp score ───────────────────────────────────────────────────────────
  score = Math.max(0, Math.min(100, score));

  const verdict: FitVerdict = score >= 65 ? "recommended" : score >= 42 ? "caution" : "avoid";

  // ── Headline narrative ─────────────────────────────────────────────────────
  const headlines: Record<FitVerdict, Record<StrategyCategory, string>> = {
    recommended: {
      buy_vol:  `HV is at ${hvPct}th pct — vol is cheap. Good time to buy a ${name} ahead of potential expansion.`,
      sell_vol: `HV at ${hvPct}th pct means premium is rich. ${name} is well-positioned to collect theta.`,
      buy_dir:  `Premium cost is moderate (HV ${hvPct}th pct). Reasonable entry for a directional bet.`,
      sell_dir: `Elevated vol (${hvPct}th pct) inflates premium — good time to sell. Defined range expected.`,
      spread:   `Moderate vol (${hvPct}th pct) and healthy R:R make this spread a cost-effective play.`,
      pin:      `Vol is suppressed (${hvPct}th pct). Market calm — Butterfly is a strong pin strategy here.`,
    },
    caution: {
      buy_vol:  `HV is at ${hvPct}th pct — fair, not cheap. Entry is viable but vol expansion is needed sooner.`,
      sell_vol: `HV at ${hvPct}th pct — premium is moderate. Selling works but margin of safety is thinner.`,
      buy_dir:  `HV at ${hvPct}th pct makes options fairly priced. Momentum confirmation helps before entry.`,
      sell_dir: `Vol is moderate — selling works but the premium collected may not justify the risk right now.`,
      spread:   `Vol is at extremes. Spread still viable but pricing may be less efficient than ideal.`,
      pin:      `Vol is moderate — Butterfly can work but requires precise timing near expiry.`,
    },
    avoid: {
      buy_vol:  `HV is at ${hvPct}th pct — vol is expensive. Paying high premium for a ${name} is risky. Wait for vol to cool.`,
      sell_vol: `HV at ${hvPct}th pct — premium is thin. ${name} offers poor risk-reward in this low-vol environment.`,
      buy_dir:  `High vol (${hvPct}th pct) makes options expensive. The breakeven gap is too wide for the expected move.`,
      sell_dir: `Vol is low — premium collected is minimal. Unlimited risk for thin reward. Avoid.`,
      spread:   `Extreme vol makes spread pricing unfavourable. Consider waiting for vol to normalise.`,
      pin:      `Elevated vol (${hvPct}th pct) — market is too active for a pin strategy. High risk of assignment.`,
    },
  };

  const headline = headlines[verdict][cat];

  return { verdict, score, signals, headline };
}

// ── Verdict colours ───────────────────────────────────────────────────────────
const VERDICT_STYLE = {
  recommended: {
    badge:   "bg-emerald-100 text-emerald-800 border-emerald-300",
    badgeDk: "bg-emerald-900/40 text-emerald-300 border-emerald-700",
    bar:     "bg-emerald-500",
    icon:    "text-emerald-600",
    iconDk:  "text-emerald-400",
    label:   "Recommended",
  },
  caution: {
    badge:   "bg-amber-100 text-amber-800 border-amber-300",
    badgeDk: "bg-amber-900/40 text-amber-300 border-amber-700",
    bar:     "bg-amber-400",
    icon:    "text-amber-600",
    iconDk:  "text-amber-400",
    label:   "Use with Caution",
  },
  avoid: {
    badge:   "bg-red-100 text-red-800 border-red-300",
    badgeDk: "bg-red-900/40 text-red-300 border-red-700",
    bar:     "bg-red-500",
    icon:    "text-red-600",
    iconDk:  "text-red-400",
    label:   "Avoid Right Now",
  },
};

const SIGNAL_STYLE: Record<FitSignal["status"], { light: string; dark: string; dot: string }> = {
  good: { light: "bg-emerald-50 text-emerald-700 border-emerald-200", dark: "bg-emerald-900/30 text-emerald-300 border-emerald-700/50", dot: "bg-emerald-500" },
  warn: { light: "bg-amber-50 text-amber-700 border-amber-200",       dark: "bg-amber-900/30 text-amber-300 border-amber-700/50",       dot: "bg-amber-400"   },
  bad:  { light: "bg-red-50 text-red-700 border-red-200",             dark: "bg-red-900/30 text-red-300 border-red-700/50",             dot: "bg-red-500"     },
};

function StrategyInsightCard({
  legs, payoff, greeks, spotInfo,
}: {
  legs:     Array<{ action: string; option_type: string; lots: number; strike: number }>;
  payoff:   any;
  greeks:   any;
  spotInfo: SpotInfo | null;
}) {
  const { theme: appTheme } = useTheme();
  const isDark = appTheme === "dark";

  const name = detectStrategy(legs);
  const fit  = computeMarketFit(name, spotInfo!, payoff, greeks);

  const cardBg  = isDark ? "bg-slate-800/60 border-slate-700"       : "bg-white border-gray-200";
  const labelCl = isDark ? "text-slate-400"                          : "text-gray-400";
  const textCl  = isDark ? "text-slate-200"                          : "text-gray-800";
  const mutedCl = isDark ? "text-slate-400"                          : "text-gray-500";
  const trackCl = isDark ? "bg-slate-700"                            : "bg-gray-100";
  const innerCl = isDark ? "bg-slate-700/50 border-slate-600/50"     : "bg-gray-50 border-gray-100";

  if (!fit) return null;

  const vs = VERDICT_STYLE[fit.verdict];
  const badgeCl = isDark ? vs.badgeDk : vs.badge;
  const iconCl  = isDark ? vs.iconDk  : vs.icon;

  return (
    <div className={`rounded-xl border ${cardBg} p-3 mt-2 shadow-sm`}>
      {/* ── Header: verdict badge + score bar ── */}
      <div className="flex items-center justify-between gap-3 mb-2.5">
        <div className="flex items-center gap-2">
          <Activity className={`w-4 h-4 shrink-0 ${iconCl}`} />
          <span className={`text-[10px] font-bold uppercase tracking-wider ${labelCl}`}>
            Market Fit · {name ?? "Custom"}
          </span>
        </div>
        <span className={`flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full border ${badgeCl}`}>
          {fit.verdict === "recommended" ? "✅" : fit.verdict === "caution" ? "⚡" : "❌"}
          {vs.label}
        </span>
      </div>

      {/* Score bar */}
      <div className={`rounded-full h-1.5 w-full ${trackCl} mb-3 overflow-hidden`}>
        <div
          className={`h-full rounded-full transition-all duration-700 ${vs.bar}`}
          style={{ width: `${fit.score}%` }}
        />
      </div>

      {/* ── Live signal chips ── */}
      <div className="flex flex-wrap gap-1.5 mb-2.5">
        {fit.signals.map((sig, i) => {
          const sc = SIGNAL_STYLE[sig.status];
          const cl = isDark ? sc.dark : sc.light;
          return (
            <div key={i} className={`flex items-center gap-1 text-[9px] font-medium px-2 py-0.5 rounded-full border ${cl}`}>
              <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${sc.dot}`} />
              <span className="font-semibold">{sig.label}:</span>
              <span>{sig.value}</span>
            </div>
          );
        })}
      </div>

      {/* ── Narrative ── */}
      <div className={`rounded-lg border px-2.5 py-2 ${innerCl}`}>
        <p className={`text-[10px] leading-relaxed ${mutedCl}`}>
          <span className={`font-semibold ${textCl}`}>Verdict: </span>
          {fit.headline}
        </p>
      </div>
    </div>
  );
}

// ── NSE expiry helpers ────────────────────────────────────────────────────────
function getNSEExpiries(n = 14): Array<{ date: string; label: string; monthly: boolean }> {
  const results: Array<{ date: string; label: string; monthly: boolean }> = [];
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const d = new Date(today);
  // Skip to the *next* Thursday (not today even if it is Thursday)
  d.setDate(d.getDate() + 1);
  while (d.getDay() !== 4) d.setDate(d.getDate() + 1);
  for (let i = 0; i < n; i++) {
    const iso = d.toISOString().slice(0, 10);
    const nextWeek = new Date(d);
    nextWeek.setDate(d.getDate() + 7);
    const isMonthly = nextWeek.getMonth() !== d.getMonth();
    const months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
    const short = `${d.getDate()} ${months[d.getMonth()]}`;
    const label = `${short}${isMonthly ? " ★ Monthly" : " · Weekly"}`;
    results.push({ date: iso, label, monthly: isMonthly });
    d.setDate(d.getDate() + 7);
  }
  return results;
}

function dteFromDate(dateStr: string): number {
  const target = new Date(dateStr);
  target.setHours(0, 0, 0, 0);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return Math.max(1, Math.round((target.getTime() - today.getTime()) / 86400000));
}

// ── TABS ──────────────────────────────────────────────────────────────────────
type Tab = "strategy" | "backtest" | "risk" | "smart";

// ── Smart Builder ─────────────────────────────────────────────────────────────
interface SuggestedLeg { action: "buy"|"sell"; option_type: "call"|"put"; strike: number; lots: number; }
interface SuggestedStrategy {
  name: string; description: string; category: string; outlook: string;
  fit_score: number; rationale: string; key_risk: string; is_custom: boolean;
  legs: SuggestedLeg[];
}
interface SmartSuggestResult {
  market_state: {
    vol_regime: string; vol_bias: string; hv_pct: number; hv: number;
    spot: number; atm: number; step: number; lot_size: number;
  };
  recommendations: SuggestedStrategy[];   // 12 predefined, sorted by fit score
  ai_suggestions:  SuggestedStrategy[];   // 5 AI-invented, regime-specific
}

const VOL_REGIME_CHIP: Record<string, string> = {
  low:       "bg-sky-50   text-sky-700   border border-sky-200",
  moderate:  "bg-amber-50 text-amber-700 border border-amber-200",
  high:      "bg-orange-50 text-orange-700 border border-orange-200",
  very_high: "bg-rose-50  text-rose-700  border border-rose-200",
};
const VOL_REGIME_LABEL: Record<string, string> = {
  low: "Low Vol", moderate: "Moderate Vol", high: "High Vol", very_high: "Very High Vol",
};
const BIAS_CHIP: Record<string, string> = {
  expanding:   "bg-rose-50  text-rose-700",
  contracting: "bg-sky-50   text-sky-700",
  stable:      "bg-gray-50  text-gray-600",
};
const OUTLOOK_ICON: Record<string, string> = {
  bullish: "↑", bearish: "↓", neutral: "↔", volatile: "↕",
};

function SmartBuilderTab({
  symbol, spotInfo, setLegs, setTab, isDark, doFetchSpot, onAnalyse,
}: {
  symbol: string;
  spotInfo: SpotInfo | null;
  setLegs: (legs: Leg[]) => void;
  setTab:  (t: Tab) => void;
  isDark:  boolean;
  doFetchSpot: () => Promise<SpotInfo | null>;
  onAnalyse:   (legs: Leg[]) => void;
}) {
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState("");
  const [result,   setResult]   = useState<SmartSuggestResult | null>(null);
  const [expandedPre, setExpandedPre] = useState<number | null>(null);
  const [expandedAI,  setExpandedAI]  = useState<number | null>(0);

  const card    = isDark ? "bg-slate-800 border-slate-700" : "bg-white border-gray-200";
  const aiCard  = isDark ? "bg-violet-950/40 border-violet-800/50" : "bg-violet-50 border-violet-200";
  const muted   = isDark ? "text-slate-400" : "text-gray-500";
  const h3      = isDark ? "text-slate-100" : "text-gray-800";
  const body    = isDark ? "bg-slate-900" : "bg-gray-50";

  async function fetchSuggestions() {
    if (!symbol) return;
    setLoading(true);
    setError("");
    try {
      const data = await post<SmartSuggestResult>("/options/smart-suggest",
        { symbol: symbol.trim().toUpperCase() });
      setResult(data);
      setExpandedAI(0);
      setExpandedPre(null);
    } catch (e: any) {
      setError(e?.message || "Failed to get suggestions");
    } finally {
      setLoading(false);
    }
  }

  async function useStrategy(rec: SuggestedStrategy) {
    let info = spotInfo;
    if (!info) info = await doFetchSpot();
    const ls = info?.lot_size ?? 75;
    const iv = info?.hv30     ?? 0.20;
    const newLegs: Leg[] = rec.legs.map(l => ({
      id: crypto.randomUUID(), action: l.action, option_type: l.option_type,
      strike: l.strike, premium: 0, lots: l.lots, lot_size: ls, iv,
    }));
    setLegs(newLegs);
    setTab("strategy");
    // Auto-analyse immediately — pass legs directly since state hasn't committed yet
    onAnalyse(newLegs);
  }

  function scoreColor(s: number) {
    return s >= 65 ? "bg-emerald-500" : s >= 42 ? "bg-amber-400" : "bg-rose-400";
  }
  function scoreLabelCls(s: number) {
    return s >= 65 ? "text-emerald-600" : s >= 42 ? "text-amber-500" : "text-rose-500";
  }

  // Shared strategy card renderer
  function StratCard({
    rec, i, isOpen, onToggle, isAI,
  }: { rec: SuggestedStrategy; i: number; isOpen: boolean; onToggle: () => void; isAI: boolean }) {
    const baseCard = isAI ? aiCard : card;
    return (
      <div className={`${baseCard} rounded-xl border overflow-hidden transition-shadow ${isOpen ? "shadow-md" : ""}`}>
        <div className="flex items-center gap-3 px-4 py-3 cursor-pointer hover:opacity-90" onClick={onToggle}>
          {/* Rank badge */}
          <span className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold shrink-0
            ${i === 0
              ? isAI ? "bg-violet-500 text-white" : "bg-amber-400 text-white"
              : isDark ? "bg-slate-700 text-slate-300" : "bg-gray-100 text-gray-500"}`}>
            {i + 1}
          </span>

          {/* Name + badges */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className={`text-sm font-bold truncate ${h3}`}>{rec.name}</span>
              {isAI && (
                <span className="text-[9px] font-bold px-1.5 py-0.5 rounded-full bg-violet-500 text-white uppercase tracking-wide shrink-0 flex items-center gap-0.5">
                  ✦ AI
                </span>
              )}
              <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium border shrink-0
                ${OUTLOOK_CHIP[rec.outlook as Outlook] ?? "bg-gray-50 text-gray-500 border-gray-200"}`}>
                {OUTLOOK_ICON[rec.outlook] ?? ""} {rec.outlook}
              </span>
            </div>
            <div className="flex items-center gap-2 mt-1.5">
              <div className={`flex-1 h-1.5 rounded-full overflow-hidden ${isDark ? "bg-slate-700" : "bg-gray-100"}`}>
                <div className={`h-full rounded-full transition-all ${scoreColor(rec.fit_score)}`}
                     style={{ width: `${rec.fit_score}%` }} />
              </div>
              <span className={`text-[11px] font-bold shrink-0 ${scoreLabelCls(rec.fit_score)}`}>
                {rec.fit_score}/100
              </span>
            </div>
          </div>

          {/* Use button */}
          <button
            onClick={e => { e.stopPropagation(); useStrategy(rec); }}
            className={`shrink-0 flex items-center gap-1.5 text-[11px] font-semibold text-white px-3 py-1.5 rounded-lg transition
              ${isAI ? "bg-violet-600 hover:bg-violet-700" : "bg-indigo-600 hover:bg-indigo-700"}`}
          >
            <Play className="w-3 h-3" /> Use
          </button>
          <ChevronDown className={`w-4 h-4 shrink-0 ${muted} transition-transform ${isOpen ? "rotate-180" : ""}`} />
        </div>

        {/* Expanded details */}
        {isOpen && (
          <div className={`border-t px-4 py-3 flex flex-col gap-3
            ${isDark
              ? isAI ? "border-violet-800/40 bg-violet-950/30" : "border-slate-700 bg-slate-900/50"
              : isAI ? "border-violet-100 bg-violet-50/60" : "border-gray-100 bg-gray-50"}`}>

            {/* Description (for AI strategies) */}
            {isAI && (
              <p className={`text-xs italic ${isDark ? "text-violet-300" : "text-violet-700"}`}>
                {rec.description}
              </p>
            )}

            {/* Legs */}
            <div>
              <p className={`text-[10px] font-bold uppercase tracking-widest ${muted} mb-1.5`}>Legs</p>
              <div className="flex flex-wrap gap-1.5">
                {rec.legs.map((l, li) => (
                  <span key={li} className={`text-[11px] font-mono font-medium px-2 py-0.5 rounded
                    ${l.action === "buy"
                      ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                      : "bg-rose-50   text-rose-700   border border-rose-200"}`}>
                    {l.action === "buy" ? "+" : "−"}{l.lots}× {l.option_type.toUpperCase()} {l.strike.toLocaleString("en-IN")}
                  </span>
                ))}
              </div>
            </div>

            {/* Rationale */}
            <div>
              <p className={`text-[10px] font-bold uppercase tracking-widest ${muted} mb-1`}>Why now?</p>
              <p className={`text-xs leading-relaxed ${isDark ? "text-slate-300" : "text-gray-700"}`}>{rec.rationale}</p>
            </div>

            {/* Risk */}
            <div className={`flex items-start gap-2 text-xs rounded-lg px-3 py-2
              ${isDark ? "bg-rose-950/40 text-rose-300 border border-rose-900/40"
                       : "bg-rose-50   text-rose-700  border border-rose-100"}`}>
              <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
              <span>{rec.key_risk}</span>
            </div>

            <button
              onClick={() => useStrategy(rec)}
              className={`self-start flex items-center gap-2 text-sm font-semibold text-white px-4 py-2 rounded-lg transition shadow-sm
                ${isAI ? "bg-violet-600 hover:bg-violet-700" : "bg-indigo-600 hover:bg-indigo-700"}`}
            >
              <Play className="w-3.5 h-3.5" /> Load into Strategy Builder → backtest it
            </button>
          </div>
        )}
      </div>
    );
  }

  const VOL_REGIME_SENTIMENT: Record<string, { icon: string; desc: string }> = {
    low:       { icon: "😴", desc: "Market is calm. AI suggests buying-time-value or back-spread strategies." },
    moderate:  { icon: "⚖️", desc: "Balanced conditions. AI recommends defined-risk net-credit structures." },
    high:      { icon: "🔥", desc: "Vol is rich. AI picks premium-selling and ratio strategies." },
    very_high: { icon: "⚡", desc: "Extreme vol spike. AI selects wide condors and crash-protection plays." },
  };

  return (
    <div className={`flex flex-col gap-4 p-4 ${body} rounded-2xl border ${isDark ? "border-slate-700" : "border-gray-200"} min-h-[480px]`}>

      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className={`text-base font-bold ${h3} flex items-center gap-2`}>
            <Zap className="w-4 h-4 text-amber-500" />
            Smart Strategy Builder
          </h2>
          <p className={`text-xs mt-0.5 ${muted}`}>
            Scores all 12 standard strategies + generates 5 unique AI suggestions
            tailored to the current {symbol} market sentiment — 17 strategies total.
          </p>
        </div>
        <button
          onClick={fetchSuggestions}
          disabled={loading}
          className="shrink-0 flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60
                     text-white text-sm font-semibold px-4 py-2 rounded-lg transition shadow-sm"
        >
          {loading
            ? <><RefreshCw className="w-4 h-4 animate-spin" /> Analysing…</>
            : <><Activity className="w-4 h-4" /> Analyse &amp; Suggest</>}
        </button>
      </div>

      {error && (
        <div className="flex items-center gap-2 text-red-500 text-sm bg-red-50 border border-red-200 rounded-lg p-3">
          <AlertTriangle className="w-4 h-4 shrink-0" /> {error}
        </div>
      )}

      {!result && !loading && !error && (
        <div className={`flex flex-col items-center justify-center flex-1 gap-3 py-12 ${muted} text-sm text-center`}>
          <Target className="w-10 h-10 opacity-30" />
          <div>
            <p className="font-medium">No analysis yet</p>
            <p className="text-xs mt-1 opacity-70">
              Click "Analyse &amp; Suggest" to score all 17 strategies for current {symbol} conditions
            </p>
          </div>
        </div>
      )}

      {result && (
        <>
          {/* ── Market State Card ── */}
          <div className={`${card} rounded-xl border p-4`}>
            <div className="flex flex-wrap gap-4 items-start">
              <div>
                <p className={`text-[10px] font-bold uppercase tracking-widest ${muted}`}>Vol Regime</p>
                <span className={`mt-1 inline-flex items-center text-xs font-semibold px-2.5 py-1 rounded-full ${VOL_REGIME_CHIP[result.market_state.vol_regime] ?? ""}`}>
                  {VOL_REGIME_LABEL[result.market_state.vol_regime] ?? result.market_state.vol_regime}
                </span>
              </div>
              <div>
                <p className={`text-[10px] font-bold uppercase tracking-widest ${muted}`}>HV Percentile</p>
                <p className={`text-xl font-bold mt-0.5 ${h3}`}>{result.market_state.hv_pct.toFixed(0)}<span className="text-sm font-normal ml-0.5">th</span></p>
              </div>
              <div>
                <p className={`text-[10px] font-bold uppercase tracking-widest ${muted}`}>Annualised HV</p>
                <p className={`text-xl font-bold mt-0.5 ${h3}`}>{result.market_state.hv.toFixed(1)}<span className="text-sm font-normal ml-0.5">%</span></p>
              </div>
              <div>
                <p className={`text-[10px] font-bold uppercase tracking-widest ${muted}`}>Vol Bias</p>
                <span className={`mt-1 inline-flex items-center text-xs font-medium px-2 py-0.5 rounded-full capitalize ${BIAS_CHIP[result.market_state.vol_bias]}`}>
                  {result.market_state.vol_bias}
                </span>
              </div>
              <div className="ml-auto text-right">
                <p className={`text-[10px] font-bold uppercase tracking-widest ${muted}`}>ATM Strike</p>
                <p className={`text-sm font-bold mt-0.5 ${h3}`}>₹{result.market_state.atm.toLocaleString("en-IN")}</p>
              </div>
            </div>
            {/* Sentiment message */}
            {VOL_REGIME_SENTIMENT[result.market_state.vol_regime] && (
              <p className={`mt-3 text-xs flex items-center gap-1.5 ${isDark ? "text-slate-300" : "text-gray-600"}`}>
                <span>{VOL_REGIME_SENTIMENT[result.market_state.vol_regime].icon}</span>
                <span>{VOL_REGIME_SENTIMENT[result.market_state.vol_regime].desc}</span>
              </p>
            )}
          </div>

          {/* ── AI Suggested Strategies (5) ── */}
          <div className="flex flex-col gap-2">
            {/* AI section header */}
            <div className={`flex items-center gap-2 px-3 py-2 rounded-lg
              ${isDark ? "bg-violet-900/30 border border-violet-800/40" : "bg-violet-50 border border-violet-200"}`}>
              <Sparkles className="w-4 h-4 text-violet-500 shrink-0" />
              <div className="flex-1">
                <p className="text-xs font-bold text-violet-600">
                  AI Suggested — based on {VOL_REGIME_LABEL[result.market_state.vol_regime] ?? "current"} market sentiment
                </p>
                <p className={`text-[10px] ${isDark ? "text-violet-400" : "text-violet-500"}`}>
                  5 unique strategies invented for the current vol regime · these change with market conditions
                </p>
              </div>
              <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full bg-violet-500 text-white shrink-0`}>
                {result.ai_suggestions?.length ?? 0} strategies
              </span>
            </div>

            {(result.ai_suggestions ?? []).map((rec, i) => (
              <StratCard
                key={rec.name} rec={rec} i={i} isAI={true}
                isOpen={expandedAI === i}
                onToggle={() => setExpandedAI(expandedAI === i ? null : i)}
              />
            ))}
          </div>

          {/* ── Predefined Strategies (12) ── */}
          <div className="flex flex-col gap-2">
            {/* Predefined section header */}
            <div className={`flex items-center gap-2 px-3 py-2 rounded-lg
              ${isDark ? "bg-slate-800 border border-slate-700" : "bg-gray-100 border border-gray-200"}`}>
              <BookOpen className="w-4 h-4 text-indigo-500 shrink-0" />
              <div className="flex-1">
                <p className={`text-xs font-bold ${h3}`}>Standard Strategies — All 12, scored by fit</p>
                <p className={`text-[10px] ${muted}`}>
                  Classic strategies scored against current {symbol} HV percentile · sorted best fit first
                </p>
              </div>
              <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${isDark ? "bg-slate-700 text-slate-300" : "bg-gray-200 text-gray-600"} shrink-0`}>
                12 strategies
              </span>
            </div>

            {result.recommendations.map((rec, i) => (
              <StratCard
                key={rec.name} rec={rec} i={i} isAI={false}
                isOpen={expandedPre === i}
                onToggle={() => setExpandedPre(expandedPre === i ? null : i)}
              />
            ))}
          </div>
        </>
      )}
    </div>
  );
}

export default function OptionsStrategyTester() {
  const { theme } = useTheme();
  const isDark = theme === "dark";
  const [tab, setTab] = useState<Tab>("strategy");

  // Symbol / spot state
  const [symbol, setSymbol] = useState("NIFTY");
  const [spotInfo, setSpotInfo] = useState<SpotInfo | null>(null);
  const [loadingSpot, setLoadingSpot] = useState(false);
  const [spotErr, setSpotErr] = useState("");

  // Strategy builder state
  const [legs, setLegs]   = useState<Leg[]>([]);
  const NSE_EXPIRIES = getNSEExpiries(14);
  const [expiryDate, setExpiryDate] = useState(NSE_EXPIRIES[0].date);
  const [T, setT] = useState(() => dteFromDate(NSE_EXPIRIES[0].date));
  const [analysis, setAnalysis] = useState<any>(null);
  const [loadingAnalysis, setLoadingAnalysis] = useState(false);
  const [analysisErr, setAnalysisErr] = useState("");

  // Sync T whenever expiryDate changes
  useEffect(() => { setT(dteFromDate(expiryDate)); }, [expiryDate]);

  // Backtest state
  const [btStrategy, setBtStrategy] = useState("short_straddle");
  const [btStart, setBtStart]       = useState("2020-01-01");
  const [btEnd, setBtEnd]           = useState(new Date().toISOString().slice(0, 10));
  const [btLots, setBtLots]         = useState(1);
  const [btEntryDte, setBtEntryDte] = useState(30);
  const [btRollDte, setBtRollDte]   = useState(0);
  const [btOtmPct, setBtOtmPct]     = useState(5);
  const [btResult, setBtResult]     = useState<any>(null);
  const [loadingBt, setLoadingBt]   = useState(false);
  const [btErr, setBtErr]           = useState("");

  // Backtest animation
  const [btPlayIdx, setBtPlayIdx]     = useState(0);
  const [btPlaying, setBtPlaying]     = useState(false);
  const [btPlaySpeed, setBtPlaySpeed] = useState(120); // ms per step
  const btIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Risk state
  const [varResult, setVarResult]       = useState<any>(null);
  const [scResult, setScResult]         = useState<any>(null);
  const [loadingRisk, setLoadingRisk]   = useState(false);
  const [riskErr, setRiskErr]           = useState("");
  const [varHorizon, setVarHorizon]     = useState(5);
  const [varSims, setVarSims]           = useState(10000);
  const [varConf, setVarConf]           = useState(0.95);

  // ── Fetch spot ──────────────────────────────────────────────────────────────
  // Returns the SpotInfo so callers (e.g. quick-add) can use it immediately
  const doFetchSpot = useCallback(async (): Promise<SpotInfo | null> => {
    if (!symbol.trim()) return null;
    setLoadingSpot(true);
    setSpotErr("");
    try {
      const info = await get<SpotInfo>(`/options/spot/${symbol.trim().toUpperCase()}`);
      setSpotInfo(info);
      setLegs(prev => prev.map(l => ({
        ...l,
        lot_size: info.lot_size,
        strike: l.strike === 0 ? info.atm : l.strike,
        iv: l.iv === 0 ? info.hv30 : l.iv,
      })));
      return info;
    } catch (e: any) {
      setSpotErr(e?.message || "Failed to fetch spot price");
      return null;
    } finally {
      setLoadingSpot(false);
    }
  }, [symbol]);

  const fetchSpot = useCallback(() => doFetchSpot(), [doFetchSpot]);

  // ── Add leg ─────────────────────────────────────────────────────────────────
  function addLeg(partial?: Partial<Leg>) {
    const spot = spotInfo?.spot ?? 0;
    const atm  = spotInfo?.atm  ?? 0;
    const ls   = spotInfo?.lot_size ?? 75;
    const hv   = spotInfo?.hv30 ?? 0.20;
    const newLeg: Leg = {
      id:          crypto.randomUUID(),
      action:      partial?.action      ?? "buy",
      option_type: partial?.option_type ?? "call",
      strike:      partial?.strike      ?? atm,
      premium:     0,
      lots:        partial?.lots        ?? 1,
      lot_size:    ls,
      iv:          hv,
    };
    setLegs(prev => [...prev, newLeg]);
  }

  function removeLeg(id: string) {
    setLegs(prev => prev.filter(l => l.id !== id));
  }

  function updateLeg(id: string, field: keyof Leg, val: any) {
    setLegs(prev => prev.map(l => l.id === id ? { ...l, [field]: val } : l));
  }

  // ── Analyse strategy ─────────────────────────────────────────────────────────
  // legsParam lets callers (e.g. Smart Builder) pass fresh legs before React state commits
  async function analyseStrategy(legsParam?: Leg[]) {
    const effectiveLegs = legsParam ?? legs;
    if (!effectiveLegs.length) { setAnalysisErr("Add at least one leg"); return; }
    const si = spotInfo ?? await doFetchSpot();
    if (!si) { setAnalysisErr("Could not load spot price — please try again"); return; }
    setLoadingAnalysis(true);
    setAnalysisErr("");
    setAnalysis(null);
    try {
      const res = await post("/options/strategy", {
        legs:    effectiveLegs.map(l => ({ ...l, iv: l.iv || si.hv30 })),
        S:       si.spot,
        T:       T / 365,
        sigma:   si.hv30,
        r:       0.07,
        spot_range_pct: 0.20,
      });
      setAnalysis(res);
      // Update premiums from API using the effective legs as base
      setLegs(effectiveLegs.map((l, i) => ({
        ...l,
        premium: res.legs?.[i]?.premium ?? l.premium,
      })));
    } catch (e: any) {
      setAnalysisErr(e?.message || "Analysis failed");
    } finally {
      setLoadingAnalysis(false);
    }
  }

  // ── Backtest animation effect ─────────────────────────────────────────────────
  useEffect(() => {
    if (!btPlaying || !btResult) return;
    const total = btResult.equity_curve?.length ?? 0;
    btIntervalRef.current = setInterval(() => {
      setBtPlayIdx(prev => {
        if (prev >= total - 1) {
          setBtPlaying(false);
          return prev;
        }
        return prev + 1;
      });
    }, btPlaySpeed);
    return () => { if (btIntervalRef.current) clearInterval(btIntervalRef.current); };
  }, [btPlaying, btResult, btPlaySpeed]);

  // ── Run backtest ─────────────────────────────────────────────────────────────
  async function runBacktest() {
    if (!symbol.trim()) { setBtErr("Enter a symbol"); return; }
    setLoadingBt(true);
    setBtErr("");
    setBtResult(null);
    setBtPlaying(false);
    setBtPlayIdx(0);
    if (btIntervalRef.current) clearInterval(btIntervalRef.current);
    try {
      const res = await post("/options/backtest", {
        symbol:    symbol.trim().toUpperCase(),
        strategy:  btStrategy,
        start_date: btStart,
        end_date:   btEnd,
        lots:       btLots,
        lot_size:   spotInfo?.lot_size,
        entry_dte:  btEntryDte,
        roll_dte:   btRollDte,
        otm_pct:    btOtmPct / 100,
      });
      setBtResult(res);
      // Start playback automatically
      setBtPlayIdx(0);
      setBtPlaying(true);
    } catch (e: any) {
      setBtErr(e?.message || "Backtest failed");
    } finally {
      setLoadingBt(false);
    }
  }

  // ── Risk analysis ─────────────────────────────────────────────────────────────
  async function runRisk() {
    if (!legs.length || !spotInfo) { setRiskErr("Build strategy and fetch spot first"); return; }
    if (!analysis)                 { setRiskErr("Run Analyse Strategy first"); return; }
    setLoadingRisk(true);
    setRiskErr("");
    try {
      const legPayload = legs.map(l => ({
        ...l, iv: l.iv || spotInfo.hv30,
        premium: l.premium || 0,
      }));
      const [varRes, scRes] = await Promise.all([
        post("/options/var", {
          legs: legPayload, S: spotInfo.spot, T: T / 365,
          sigma: spotInfo.hv30, r: 0.07,
          horizon_days: varHorizon, num_simulations: varSims,
          confidence: varConf,
        }),
        post("/options/scenario", {
          legs: legPayload, S: spotInfo.spot, T: T / 365, r: 0.07,
        }),
      ]);
      setVarResult(varRes);
      setScResult(scRes);
    } catch (e: any) {
      setRiskErr(e?.message || "Risk analysis failed");
    } finally {
      setLoadingRisk(false);
    }
  }

  // ── Render ────────────────────────────────────────────────────────────────────
  const tabCls = (t: Tab) =>
    `px-5 py-2.5 text-sm font-medium rounded-t-lg border-b-2 transition-colors ${
      tab === t
        ? `border-indigo-600 text-indigo-500 ${isDark ? "bg-slate-800" : "bg-white"}`
        : `border-transparent ${isDark ? "text-slate-400 hover:text-slate-200 hover:border-slate-500" : "text-gray-500 hover:text-gray-700 hover:border-gray-300"}`
    }`;

  const chartGrid  = isDark ? "#1e293b" : "#f0f0f0";
  const chartTick  = { fontSize: 10, fill: isDark ? "#64748b" : "#6b7280" };
  const tooltipStyle = { fontSize: 11, borderRadius: 8, backgroundColor: isDark ? "#1e293b" : "#fff", border: `1px solid ${isDark ? "#334155" : "#e5e7eb"}`, color: isDark ? "#e2e8f0" : "#111827" };

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Options Strategy Tester</h1>
          <p className="text-sm text-gray-500">
            NSE options — Black-Scholes pricing · event-driven backtesting · Monte Carlo VaR
          </p>
        </div>
      </div>

      {/* Symbol bar */}
      {(() => {
        const INDICES = [
          { sym: "NIFTY",      label: "NIFTY 50",     lot: 75, exch: "NSE" },
          { sym: "BANKNIFTY",  label: "BANK NIFTY",   lot: 30, exch: "NSE" },
          { sym: "FINNIFTY",   label: "FIN NIFTY",    lot: 40, exch: "NSE" },
          { sym: "MIDCPNIFTY", label: "MIDCAP NIFTY", lot: 75, exch: "NSE" },
          { sym: "SENSEX",     label: "SENSEX",        lot: 10, exch: "BSE" },
          { sym: "BANKEX",     label: "BANKEX",        lot: 15, exch: "BSE" },
        ];
        const switchIndex = async (sym: string) => {
          if (sym === symbol && spotInfo) return;
          setSymbol(sym);
          setSpotInfo(null);
          setLegs([]);
          setAnalysis(null);
          setLoadingSpot(true);
          setSpotErr("");
          try {
            const info = await get<SpotInfo>(`/options/spot/${sym}`);
            setSpotInfo(info);
          } catch (e: any) {
            setSpotErr(e?.message || `Failed to fetch ${sym}`);
          } finally {
            setLoadingSpot(false);
          }
        };
        return (
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
            {/* Segmented control */}
            <div className="bg-gray-50 border-b border-gray-100 p-2">
              <div className="bg-gray-100 rounded-xl p-1 flex gap-0.5">
                {INDICES.map(({ sym, label, lot, exch }) => {
                  const active = symbol === sym;
                  const fetching = active && loadingSpot;
                  return (
                    <button
                      key={sym}
                      onClick={() => switchIndex(sym)}
                      disabled={loadingSpot}
                      className={`flex-1 flex flex-col items-center py-2 px-1 rounded-lg transition-all duration-150 disabled:opacity-60
                        ${active
                          ? "bg-white shadow-sm text-gray-900"
                          : "text-gray-500 hover:text-gray-700 hover:bg-gray-50"
                        }`}
                    >
                      <span className="text-xs font-bold tracking-tight leading-tight whitespace-nowrap">
                        {fetching
                          ? <span className="flex items-center gap-1"><RefreshCw className="w-3 h-3 animate-spin" />{label}</span>
                          : label}
                      </span>
                      <span className={`text-[10px] leading-tight mt-0.5 font-medium
                        ${active ? "text-indigo-500" : "text-gray-400"}`}>
                        {exch} · {lot}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Live market data strip */}
            {spotInfo && (
              <div className="flex items-center divide-x divide-gray-100 dark:divide-slate-800/80 px-1">
                <div className="flex items-baseline gap-1.5 px-4 py-3">
                  <span className="text-xl font-bold text-gray-900">
                    ₹{spotInfo.spot.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </span>
                  <span className="text-xs text-gray-400 font-medium">SPOT</span>
                </div>
                <div className="flex items-center gap-5 px-5 py-3 flex-1">
                  <div className="text-center">
                    <p className="text-xs text-gray-400 font-medium mb-0.5">ATM Strike</p>
                    <p className="text-sm font-bold text-gray-800">₹{spotInfo.atm.toLocaleString("en-IN")}</p>
                  </div>
                  <div className="text-center">
                    <p className="text-xs text-gray-400 font-medium mb-0.5">HV 30d</p>
                    <p className="text-sm font-bold text-orange-600">{pct(spotInfo.hv30_pct)}</p>
                  </div>
                  <div className="text-center">
                    <p className="text-xs text-gray-400 font-medium mb-0.5">Lot Size</p>
                    <p className="text-sm font-bold text-gray-800">{spotInfo.lot_size} units</p>
                  </div>
                </div>
                <button
                  onClick={fetchSpot}
                  disabled={loadingSpot}
                  className="px-4 py-3 text-gray-400 hover:text-indigo-600 transition disabled:opacity-40"
                  title="Refresh"
                >
                  <RefreshCw className={`w-4 h-4 ${loadingSpot ? "animate-spin" : ""}`} />
                </button>
              </div>
            )}

            {!spotInfo && !loadingSpot && !spotErr && (
              <div className="px-4 py-3 text-sm text-gray-400 flex items-center gap-2">
                <Zap className="w-4 h-4 text-indigo-300" />
                Select an index above to load live market data
              </div>
            )}

            {loadingSpot && !spotInfo && (
              <div className="px-4 py-3 text-sm text-gray-400 flex items-center gap-2">
                <RefreshCw className="w-4 h-4 animate-spin text-indigo-400" />
                Fetching {symbol} live data…
              </div>
            )}

            {spotErr && (
              <div className="px-4 py-3">
                <p className="text-red-500 text-sm flex items-center gap-1">
                  <AlertTriangle className="w-4 h-4" /> {spotErr}
                </p>
              </div>
            )}
          </div>
        );
      })()}

      {/* Tabs */}
      <div className="border-b border-gray-200">
        <nav className="flex gap-1">
          <button className={tabCls("strategy")} onClick={() => setTab("strategy")}>Strategy &amp; Payoff</button>
          <button className={tabCls("backtest")} onClick={() => setTab("backtest")}>Backtest</button>
          <button className={tabCls("risk")}     onClick={() => setTab("risk")}>Risk Analysis</button>
          <button className={tabCls("smart")}    onClick={() => setTab("smart")}>
            <span className="flex items-center gap-1.5">
              <Zap className="w-3.5 h-3.5" />
              Smart Builder
            </span>
          </button>
        </nav>
      </div>

      {/* ── TAB: Strategy Builder ────────────────────────────────────────── */}
      {tab === "strategy" && (
        <div className="bg-white rounded-2xl border border-gray-200 shadow-sm flex flex-col overflow-hidden" style={{ minHeight: 540 }}>

          {/* ── TOP STRIP: Quick Add (full-width horizontal bar) ─────────── */}
          {(() => {
            const addStrategy = async (qs: typeof QUICK_STRATEGIES[0]) => {
              const info = spotInfo ?? await doFetchSpot();
              if (!info) return;
              const atm  = info.atm;
              const step = atm >= 10000 ? 100 : atm >= 2000 ? 50 : 10;
              const otm  = step * 3;
              const newLegs = qs.legs.map((l) => {
                const offset = l.spreadMult !== undefined ? step * l.spreadMult : otm * (l.otmMult ?? 0);
                const strike = l.option_type === "call" ? atm + offset : atm - offset;
                return {
                  id: crypto.randomUUID(),
                  action:      l.action      ?? ("buy" as const),
                  option_type: l.option_type ?? ("call" as const),
                  strike, premium: 0,
                  lots:     l.lots ?? 1,
                  lot_size: info.lot_size,
                  iv:       info.hv30,
                };
              });
              setLegs(newLegs);
            };
            return (
              <div className="border-b border-gray-100 px-4 py-2 flex flex-wrap items-center gap-x-1.5 gap-y-1.5">
                <span className="text-[9px] font-bold text-gray-400 uppercase tracking-widest mr-1 shrink-0">Add</span>
                {STRATEGY_GROUPS.map((group, gi) => (
                  <span key={group.label} className="contents">
                    {gi > 0 && <span className="text-gray-200 mx-0.5 select-none text-sm leading-none">·</span>}
                    <span className="text-[8px] font-bold text-gray-300 uppercase tracking-widest shrink-0">{group.label}:</span>
                    {group.items.map(qs => (
                      <button key={qs.label} onClick={() => addStrategy(qs)}
                        className={`flex items-center gap-1 px-2 py-0.5 text-[10px] font-medium rounded-md border transition-colors ${OUTLOOK_CHIP[qs.outlook]}`}>
                        <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${OUTLOOK_DOT[qs.outlook]}`} />
                        {qs.label}
                      </button>
                    ))}
                  </span>
                ))}
                <button onClick={() => addLeg()}
                  className="ml-auto flex items-center gap-1 px-2 py-0.5 text-[10px] rounded-md border border-dashed border-gray-200 text-gray-400 hover:bg-gray-50 transition shrink-0">
                  <Plus className="w-2.5 h-2.5" /> Custom
                </button>
              </div>
            );
          })()}

          {/* ── BODY: Left / Right split ──────────────────────────────────── */}
          <div className="flex flex-1 overflow-hidden">

          {/* ── LEFT: Builder ─────────────────────────────────────────────── */}
          <div className="w-[38%] flex-shrink-0 flex flex-col border-r border-gray-100">

            {/* Legs header */}
            <div className="px-4 py-2 border-b border-gray-100 flex items-center justify-between bg-gray-50/60">
              <div className="flex items-center gap-2">
                <span className="text-xs font-semibold text-gray-600">Legs</span>
                {legs.length > 0 && (
                  <button
                    onClick={() => setLegs([])}
                    className="flex items-center gap-0.5 text-[10px] text-gray-300 hover:text-red-400 transition px-1.5 py-0.5 rounded hover:bg-red-50 border border-transparent hover:border-red-100"
                    title="Clear all legs"
                  >
                    <X className="w-2.5 h-2.5" />
                    Clear
                  </button>
                )}
              </div>
              <div className="flex items-center gap-2">
                <label className="text-[10px] text-gray-400 font-medium uppercase tracking-wide">Expiry</label>
                <select
                  value={expiryDate}
                  onChange={e => setExpiryDate(e.target.value)}
                  className={`border rounded px-2 py-0.5 text-[11px] font-medium ${isDark ? "bg-slate-700 border-slate-600 text-slate-200" : "border-gray-200 bg-white text-gray-700"}`}
                >
                  {NSE_EXPIRIES.map(ex => (
                    <option key={ex.date} value={ex.date}
                      style={ex.monthly ? { fontWeight: 700 } : {}}>
                      {ex.label}
                    </option>
                  ))}
                </select>
                <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded ${isDark ? "bg-slate-700 text-indigo-400" : "bg-indigo-50 text-indigo-600"}`}>
                  {T}d
                </span>
              </div>
            </div>

            {/* Legs body */}
            <div className="flex-1 overflow-y-auto">
              {legs.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-full py-10 text-gray-400">
                  <Plus className="w-8 h-8 mb-2 opacity-30" />
                  <p className="text-sm">No legs yet</p>
                  <p className="text-xs mt-0.5">Pick a strategy or add a custom leg above</p>
                </div>
              ) : (
                <table className="w-full text-xs">
                  <thead className="bg-gray-50 text-[10px] text-gray-400 uppercase tracking-wide sticky top-0">
                    <tr>
                      <th className="px-3 py-2 text-left">Action</th>
                      <th className="px-3 py-2 text-left">Type</th>
                      <th className="px-3 py-2 text-left">Strike</th>
                      <th className="px-3 py-2 text-left">IV%</th>
                      <th className="px-3 py-2 text-left">Lots</th>
                      <th className="px-3 py-2 text-left">Sz</th>
                      <th className="px-3 py-2 text-left">Prem</th>
                      <th className="px-3 py-2" />
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50 dark:divide-slate-800/80">
                    {legs.map(leg => (
                      <tr key={leg.id} className="hover:bg-gray-50/70">
                        <td className="px-3 py-1.5">
                          <select
                            value={leg.action}
                            onChange={e => updateLeg(leg.id, "action", e.target.value)}
                            className={`rounded px-1.5 py-0.5 text-[10px] font-bold border-0 cursor-pointer ${
                              leg.action === "buy" ? "bg-green-100 text-green-800" : "bg-red-100 text-red-800"
                            }`}
                          >
                            <option value="buy">BUY</option>
                            <option value="sell">SELL</option>
                          </select>
                        </td>
                        <td className="px-3 py-1.5">
                          <select
                            value={leg.option_type}
                            onChange={e => updateLeg(leg.id, "option_type", e.target.value)}
                            className="border border-gray-200 rounded px-1.5 py-0.5 text-[10px]"
                          >
                            <option value="call">CE</option>
                            <option value="put">PE</option>
                          </select>
                        </td>
                        <td className="px-3 py-1.5">
                          <input
                            type="number" step={50} min={0}
                            value={leg.strike}
                            onChange={e => updateLeg(leg.id, "strike", Number(e.target.value))}
                            className="border border-gray-200 rounded px-1.5 py-0.5 text-xs w-20 font-mono"
                          />
                        </td>
                        <td className="px-3 py-1.5">
                          <input
                            type="number" step={0.5} min={1} max={300}
                            value={parseFloat((leg.iv * 100).toFixed(1))}
                            onChange={e => updateLeg(leg.id, "iv", Number(e.target.value) / 100)}
                            className="border border-gray-200 rounded px-1.5 py-0.5 text-xs w-14 font-mono"
                          />
                        </td>
                        <td className="px-3 py-1.5">
                          <input
                            type="number" min={1} max={50}
                            value={leg.lots}
                            onChange={e => updateLeg(leg.id, "lots", Number(e.target.value))}
                            className="border border-gray-200 rounded px-1.5 py-0.5 text-xs w-12"
                          />
                        </td>
                        <td className="px-3 py-1.5">
                          <input
                            type="number" min={1}
                            value={leg.lot_size}
                            onChange={e => updateLeg(leg.id, "lot_size", Number(e.target.value))}
                            className="border border-gray-200 rounded px-1.5 py-0.5 text-xs w-14"
                          />
                        </td>
                        <td className="px-3 py-1.5 font-mono text-gray-400">
                          {leg.premium > 0 ? `₹${leg.premium.toFixed(1)}` : "—"}
                        </td>
                        <td className="px-3 py-1.5">
                          <button onClick={() => removeLeg(leg.id)} className="text-red-300 hover:text-red-500 transition">
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>

            {/* Greeks (when available) */}
            {analysis && (
              <div className="px-4 py-3 border-t border-gray-100 bg-gray-50/40">
                <p className="text-[10px] font-bold text-gray-400 uppercase tracking-widest mb-2">Portfolio Greeks</p>
                <GreeksBar g={analysis.greeks} />
              </div>
            )}

            {/* Footer: error + CTA */}
            {analysisErr && (
              <div className="px-4 py-2 bg-red-50 border-t border-red-100 text-red-600 text-xs">
                {analysisErr}
              </div>
            )}
          </div>

          {/* ── RIGHT: Payoff ────────────────────────────────────────── */}
          <div className="flex-1 flex flex-col min-w-0 p-5">
            {!analysis ? (
              <div className="flex flex-col items-center justify-center h-full text-gray-300">
                <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-indigo-50 to-violet-100 flex items-center justify-center mb-4 shadow-sm">
                  <BarChart2 className="w-8 h-8 text-indigo-300" />
                </div>
                <p className="text-sm font-semibold text-gray-400 mb-1">
                  {legs.length ? "Ready to analyse" : "No strategy yet"}
                </p>
                <p className="text-xs text-gray-300 mb-4">
                  {legs.length
                    ? `${legs.length} leg${legs.length > 1 ? "s" : ""} added — run analysis to see payoff`
                    : "Pick a strategy from the bar above to get started"}
                </p>
                {legs.length > 0 && (
                  <button
                    onClick={analyseStrategy}
                    disabled={loadingAnalysis}
                    className="flex items-center gap-2 px-5 py-2 rounded-xl text-sm font-semibold bg-gradient-to-r from-indigo-600 to-violet-600 text-white shadow hover:shadow-md hover:from-indigo-700 hover:to-violet-700 transition-all active:scale-[0.97]"
                  >
                    {loadingAnalysis ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4" />}
                    {loadingAnalysis ? "Analysing…" : "Analyse Strategy"}
                  </button>
                )}
              </div>
            ) : (
              <div className="flex flex-col gap-3 h-full">

                {/* Summary strip */}
                <div className="grid grid-cols-3 gap-2.5">
                  {(() => {
                    const np = analysis.payoff?.net_premium ?? 0;
                    const isCredit = np >= 0;
                    return (
                      <div className={`rounded-xl border p-3 ${isCredit ? "bg-green-50 border-green-200" : "bg-red-50 border-red-200"}`}>
                        <div className="flex items-center justify-between mb-0.5">
                          <p className="text-[10px] font-semibold text-gray-500 uppercase">Net Premium</p>
                          <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded-full ${isCredit ? "bg-green-200 text-green-800" : "bg-red-200 text-red-700"}`}>
                            {isCredit ? "CREDIT" : "DEBIT"}
                          </span>
                        </div>
                        <p className={`text-base font-bold ${isCredit ? "text-green-700" : "text-red-600"}`}>{fmtINR(Math.abs(np))}</p>
                      </div>
                    );
                  })()}
                  <div className="bg-gray-50 rounded-xl border border-gray-100 p-3">
                    <p className="text-[10px] text-gray-400 uppercase mb-0.5">Max Profit</p>
                    <p className="text-base font-bold text-green-600">
                      {analysis.payoff?.max_profit != null ? fmtINR(analysis.payoff.max_profit) : "∞"}
                    </p>
                  </div>
                  <div className="bg-gray-50 rounded-xl border border-gray-100 p-3">
                    <p className="text-[10px] text-gray-400 uppercase mb-0.5">Max Loss</p>
                    <p className="text-base font-bold text-red-500">
                      {analysis.payoff?.max_loss != null ? fmtINR(analysis.payoff.max_loss) : "∞"}
                    </p>
                  </div>
                </div>

                {/* P&L Chart */}
                <div className="flex-1 flex flex-col min-h-0">
                  <div className="flex items-center justify-between mb-1.5">
                    <p className="text-xs font-semibold text-gray-600">P&amp;L at Expiry</p>
                    <div className="flex items-center gap-3">
                      <div className="flex gap-3 text-[10px] text-gray-400">
                        <span className="flex items-center gap-1"><span className="w-3 h-0.5 bg-indigo-500 inline-block rounded" /> P&amp;L</span>
                        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-orange-400 inline-block" /> Spot</span>
                      </div>
                      <button
                        onClick={() => setAnalysis(null)}
                        title="Clear chart"
                        className="flex items-center gap-1 text-[10px] text-gray-300 hover:text-red-400 transition px-1.5 py-0.5 rounded hover:bg-red-50"
                      >
                        <X className="w-3 h-3" /> Clear
                      </button>
                    </div>
                  </div>
                  <ResponsiveContainer width="100%" height={230}>
                    <LineChart data={analysis.payoff.spots.map((s: number, i: number) => ({
                      spot: s, pnl: analysis.payoff.payoffs[i],
                    }))}>
                      <CartesianGrid strokeDasharray="3 3" stroke={chartGrid} />
                      <XAxis dataKey="spot" tickFormatter={(v: number) => `₹${(v / 1000).toFixed(0)}k`} tick={chartTick} />
                      <YAxis tickFormatter={(v: number) => v >= 1e5 ? `${(v / 1e5).toFixed(1)}L` : v.toLocaleString("en-IN")} tick={chartTick} width={55} />
                      <Tooltip
                        formatter={(v: number) => [fmtINR(v), "P&L"]}
                        labelFormatter={(l: number) => `Spot: ₹${Number(l).toLocaleString("en-IN")}`}
                        contentStyle={tooltipStyle}
                      />
                      <ReferenceLine y={0} stroke="#d1d5db" strokeWidth={1} />
                      {spotInfo && (
                        <ReferenceLine x={spotInfo.spot} stroke="#f97316" strokeDasharray="4 2"
                          label={{ value: "Spot", fill: "#f97316", fontSize: 9 }} />
                      )}
                      {analysis.payoff.breakevens?.map((be: number, i: number) => (
                        <ReferenceLine key={i} x={be} stroke="#10b981" strokeDasharray="3 3"
                          label={{ value: "BE", fill: "#059669", fontSize: 9 }} />
                      ))}
                      <Line type="monotone" dataKey="pnl" stroke="#6366f1" strokeWidth={2.5} dot={false} activeDot={{ r: 4 }} />
                    </LineChart>
                  </ResponsiveContainer>

                  {/* Heatmap */}
                  <PnlHeatmap
                    spots={analysis.payoff.spots}
                    payoffs={analysis.payoff.payoffs}
                    currentSpot={spotInfo?.spot}
                  />

                  {/* Strategy Insight — below heatmap */}
                  <StrategyInsightCard
                    legs={legs}
                    payoff={analysis.payoff}
                    greeks={analysis.greeks}
                    spotInfo={spotInfo}
                  />
                </div>
              </div>
            )}
          </div>

          </div>{/* end flex body */}
        </div>
      )}

      {/* ── TAB: Backtest ───────────────────────────────────────────────── */}
      {tab === "backtest" && (
        <div className="space-y-4">
          {/* Config */}
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
            <h3 className="font-semibold text-gray-800 mb-4">Backtest Configuration</h3>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
              <div>
                <label className="block text-xs text-gray-500 mb-1 font-medium">Strategy</label>
                <select
                  value={btStrategy}
                  onChange={e => setBtStrategy(e.target.value)}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                >
                  {PRESETS.map(s => (
                    <option key={s} value={s}>{PRESET_LABELS[s] ?? s}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1 font-medium">Start Date</label>
                <input type="date" value={btStart} onChange={e => setBtStart(e.target.value)}
                       className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1 font-medium">End Date</label>
                <input type="date" value={btEnd} onChange={e => setBtEnd(e.target.value)}
                       className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1 font-medium">Lots</label>
                <input type="number" min={1} max={50} value={btLots}
                       onChange={e => setBtLots(Number(e.target.value))}
                       className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1 font-medium">Entry DTE (days)</label>
                <input type="number" min={1} max={90} value={btEntryDte}
                       onChange={e => setBtEntryDte(Number(e.target.value))}
                       className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1 font-medium">Roll DTE (0 = hold)</label>
                <input type="number" min={0} max={30} value={btRollDte}
                       onChange={e => setBtRollDte(Number(e.target.value))}
                       className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1 font-medium">OTM Wing %</label>
                <input type="number" min={1} max={30} value={btOtmPct} step={0.5}
                       onChange={e => setBtOtmPct(Number(e.target.value))}
                       className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
              </div>
            </div>

            <div className="mt-4 flex items-center gap-3">
              <button
                onClick={runBacktest}
                disabled={loadingBt}
                className="flex items-center gap-2 bg-indigo-600 text-white px-6 py-2 rounded-lg text-sm hover:bg-indigo-700 disabled:opacity-60 transition"
              >
                {loadingBt ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
                {loadingBt ? "Running backtest…" : "Run Backtest"}
              </button>
              {loadingBt && (
                <span className="text-xs text-gray-400">
                  Fetching {symbol} history and simulating trades…
                </span>
              )}
            </div>
          </div>

          {btErr && (
            <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-xl px-4 py-3">
              <AlertTriangle className="w-4 h-4 inline mr-2" />{btErr}
            </div>
          )}

          {/* Results */}
          {btResult && (
            <div className="space-y-4">
              {/* Metrics */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {[
                  { label: "Total P&L",      val: fmtINR(btResult.metrics.total_pnl),         clrFn: clr(btResult.metrics.total_pnl) },
                  { label: "Win Rate",       val: pct(btResult.metrics.win_rate),              clrFn: "text-gray-900" },
                  { label: "Sharpe Ratio",   val: fmt(btResult.metrics.sharpe_ratio),          clrFn: clr(btResult.metrics.sharpe_ratio) },
                  { label: "Sortino Ratio",  val: fmt(btResult.metrics.sortino_ratio),         clrFn: clr(btResult.metrics.sortino_ratio) },
                  { label: "Profit Factor",  val: btResult.metrics.profit_factor != null ? fmt(btResult.metrics.profit_factor) : "∞",  clrFn: "text-gray-900" },
                  { label: "Max Drawdown",   val: fmtINR(btResult.metrics.max_drawdown),      clrFn: "text-red-600" },
                  { label: "Avg Win",        val: fmtINR(btResult.metrics.avg_win),            clrFn: "text-green-600" },
                  { label: "Avg Loss",       val: fmtINR(btResult.metrics.avg_loss),           clrFn: "text-red-600" },
                  { label: "Total Trades",   val: String(btResult.metrics.total_trades),       clrFn: "text-gray-900" },
                  { label: "Best Trade",     val: fmtINR(btResult.metrics.best_trade),         clrFn: "text-green-600" },
                  { label: "Worst Trade",    val: fmtINR(btResult.metrics.worst_trade),        clrFn: "text-red-600" },
                  { label: "Avg Trade",      val: fmtINR(btResult.metrics.avg_trade_pnl),      clrFn: clr(btResult.metrics.avg_trade_pnl) },
                ].map(m => (
                  <div key={m.label} className="bg-white rounded-xl border border-gray-200 shadow-sm p-4">
                    <p className="text-xs text-gray-500 uppercase tracking-wide mb-1">{m.label}</p>
                    <p className={`text-lg font-bold ${m.clrFn}`}>{m.val}</p>
                  </div>
                ))}
              </div>

              {/* Animated equity curve simulation */}
              {(() => {
                const curve      = btResult.equity_curve ?? [];
                const totalPts   = curve.length;
                const visibleCurve = curve.slice(0, btPlayIdx + 1);
                const currentPt  = curve[btPlayIdx];
                const currentPnl = currentPt?.cumulative_pnl ?? 0;
                const isProfit   = currentPnl >= 0;
                const progress   = totalPts > 1 ? btPlayIdx / (totalPts - 1) : 1;
                // Find current active trade
                const activeTrade = btResult.trades?.find((t: any) =>
                  t.entry_date <= (currentPt?.date ?? "") &&
                  (currentPt?.date ?? "") <= t.exit_date
                );
                return (
                  <div className={`rounded-xl border shadow-sm overflow-hidden ${isDark ? "bg-slate-800 border-slate-700" : "bg-white border-gray-200"}`}>
                    {/* Header with live P&L card */}
                    <div className={`flex items-center justify-between gap-4 px-5 py-4 border-b ${isDark ? "border-slate-700 bg-slate-800" : "border-gray-100 bg-white"}`}>
                      <div>
                        <h3 className={`font-semibold text-sm ${isDark ? "text-slate-100" : "text-gray-800"}`}>
                          Equity Simulation
                        </h3>
                        <p className={`text-[11px] mt-0.5 ${isDark ? "text-slate-400" : "text-gray-400"}`}>
                          {currentPt?.date ?? "—"} · trade {btPlayIdx + 1} of {totalPts}
                        </p>
                      </div>

                      {/* Live P&L card */}
                      <div className={`flex items-center gap-4 px-4 py-2.5 rounded-xl border ${
                        isProfit
                          ? isDark ? "bg-emerald-950/40 border-emerald-700/50" : "bg-emerald-50 border-emerald-200"
                          : isDark ? "bg-rose-950/40 border-rose-800/50" : "bg-rose-50 border-rose-200"
                      }`}>
                        <div className="text-center">
                          <p className={`text-[10px] font-medium uppercase tracking-wide ${isDark ? "text-slate-400" : "text-gray-400"}`}>Cum P&L</p>
                          <p className={`text-lg font-bold font-mono ${isProfit ? "text-emerald-600" : "text-rose-600"}`}>
                            {fmtINR(currentPnl)}
                          </p>
                        </div>
                        {activeTrade && (
                          <>
                            <div className={`w-px h-8 ${isDark ? "bg-slate-600" : "bg-gray-200"}`} />
                            <div className="text-center">
                              <p className={`text-[10px] font-medium uppercase tracking-wide ${isDark ? "text-slate-400" : "text-gray-400"}`}>Trade P&L</p>
                              <p className={`text-sm font-bold ${clr(activeTrade.trade_pnl)}`}>
                                {fmtINR(activeTrade.trade_pnl)}
                              </p>
                            </div>
                            <div className="text-center">
                              <p className={`text-[10px] font-medium uppercase tracking-wide ${isDark ? "text-slate-400" : "text-gray-400"}`}>Spot</p>
                              <p className={`text-sm font-bold ${isDark ? "text-slate-200" : "text-gray-700"}`}>
                                ₹{(activeTrade.spot_entry ?? 0).toLocaleString("en-IN")}
                              </p>
                            </div>
                          </>
                        )}
                      </div>
                    </div>

                    {/* Chart */}
                    <div className="px-4 pt-4 pb-2">
                      <ResponsiveContainer width="100%" height={260}>
                        <LineChart data={visibleCurve} margin={{ top: 5, right: 16, left: 10, bottom: 5 }}>
                          <CartesianGrid strokeDasharray="3 3" stroke={chartGrid} />
                          <XAxis dataKey="date" tick={chartTick}
                                 tickFormatter={(d: string) => d.slice(0, 7)} />
                          <YAxis tickFormatter={(v: number) => fmtINR(v)} tick={chartTick} width={72} />
                          <Tooltip
                            formatter={(v: number) => [fmtINR(v), "Cum P&L"]}
                            contentStyle={tooltipStyle}
                          />
                          <ReferenceLine y={0} stroke={isDark ? "#475569" : "#9ca3af"} strokeDasharray="4 4" />
                          <Line
                            type="monotone" dataKey="cumulative_pnl"
                            stroke={isProfit ? "#10b981" : "#ef4444"}
                            strokeWidth={2.5} dot={false} isAnimationActive={false}
                            activeDot={{ r: 4, fill: isProfit ? "#10b981" : "#ef4444" }}
                          />
                        </LineChart>
                      </ResponsiveContainer>
                    </div>

                    {/* Progress bar */}
                    <div className={`mx-4 mb-3 h-1.5 rounded-full overflow-hidden ${isDark ? "bg-slate-700" : "bg-gray-100"}`}>
                      <div
                        className={`h-full rounded-full transition-all ${isProfit ? "bg-emerald-500" : "bg-rose-500"}`}
                        style={{ width: `${progress * 100}%` }}
                      />
                    </div>

                    {/* Controls */}
                    <div className={`px-4 pb-4 flex items-center gap-3 flex-wrap`}>
                      {/* Play/Pause */}
                      <button
                        onClick={() => {
                          if (btPlayIdx >= totalPts - 1) { setBtPlayIdx(0); setBtPlaying(true); return; }
                          setBtPlaying(p => !p);
                        }}
                        className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold text-white transition shadow-sm
                          ${isProfit ? "bg-emerald-600 hover:bg-emerald-700" : "bg-indigo-600 hover:bg-indigo-700"}`}
                      >
                        {btPlaying
                          ? <><span className="w-3.5 h-3.5 flex items-center justify-center gap-0.5"><span className="w-1 h-3 bg-white rounded-sm inline-block" /><span className="w-1 h-3 bg-white rounded-sm inline-block" /></span>Pause</>
                          : <><Play className="w-3.5 h-3.5" />{btPlayIdx >= totalPts - 1 ? "Replay" : "Play"}</>
                        }
                      </button>

                      {/* Reset */}
                      <button
                        onClick={() => { setBtPlaying(false); setBtPlayIdx(0); }}
                        className={`p-2 rounded-lg border transition ${isDark ? "border-slate-600 text-slate-400 hover:text-slate-200 hover:border-slate-400" : "border-gray-200 text-gray-400 hover:text-gray-700 hover:border-gray-300"}`}
                        title="Reset to start"
                      >
                        <RefreshCw className="w-4 h-4" />
                      </button>

                      {/* Scrub slider */}
                      <input
                        type="range" min={0} max={totalPts - 1} value={btPlayIdx}
                        onChange={e => { setBtPlaying(false); setBtPlayIdx(Number(e.target.value)); }}
                        className="flex-1 min-w-[100px] accent-indigo-600 cursor-pointer"
                      />

                      {/* Speed */}
                      <div className="flex items-center gap-1.5">
                        <span className={`text-[10px] font-medium ${isDark ? "text-slate-400" : "text-gray-400"}`}>Speed</span>
                        {[{ label: "0.5×", ms: 240 }, { label: "1×", ms: 120 }, { label: "2×", ms: 60 }, { label: "5×", ms: 24 }].map(s => (
                          <button
                            key={s.ms}
                            onClick={() => setBtPlaySpeed(s.ms)}
                            className={`text-[10px] font-bold px-2 py-0.5 rounded border transition
                              ${btPlaySpeed === s.ms
                                ? "bg-indigo-600 text-white border-indigo-600"
                                : isDark ? "border-slate-600 text-slate-400 hover:border-indigo-500 hover:text-indigo-400" : "border-gray-200 text-gray-400 hover:border-indigo-400 hover:text-indigo-600"}`}
                          >
                            {s.label}
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>
                );
              })()}

              {/* Trade log */}
              <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
                <div className="px-4 py-3 border-b border-gray-100">
                  <h3 className="font-semibold text-gray-800">Trade Log</h3>
                </div>
                <div className="overflow-x-auto">
                  <table className="min-w-full text-xs">
                    <thead className="bg-gray-50 text-gray-500 uppercase tracking-wide">
                      <tr>
                        {["Entry","Exit","Expiry","Spot In","Spot Out","IV%","Credit","Debit","Comm","P&L","Cum P&L"].map(h => (
                          <th key={h} className="px-3 py-2 text-left font-medium">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100 dark:divide-slate-800/80">
                      {btResult.trades.map((t: any, i: number) => (
                        <tr key={i} className="hover:bg-gray-50">
                          <td className="px-3 py-2 font-mono">{t.entry_date}</td>
                          <td className="px-3 py-2 font-mono">{t.exit_date}</td>
                          <td className="px-3 py-2 font-mono">{t.expiry}</td>
                          <td className="px-3 py-2 font-mono">{t.spot_entry?.toLocaleString("en-IN")}</td>
                          <td className="px-3 py-2 font-mono">{t.spot_exit?.toLocaleString("en-IN")}</td>
                          <td className="px-3 py-2">{t.iv_entry_pct?.toFixed(1)}%</td>
                          <td className="px-3 py-2 text-green-700">₹{t.entry_credit?.toFixed(0)}</td>
                          <td className="px-3 py-2 text-red-600">₹{t.exit_debit?.toFixed(0)}</td>
                          <td className="px-3 py-2 text-gray-400">₹{t.commission?.toFixed(0)}</td>
                          <td className={`px-3 py-2 font-bold ${clr(t.trade_pnl)}`}>
                            {fmtINR(t.trade_pnl)}
                          </td>
                          <td className={`px-3 py-2 font-bold ${clr(t.cumulative_pnl)}`}>
                            {fmtINR(t.cumulative_pnl)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── TAB: Risk Analysis ──────────────────────────────────────────── */}
      {tab === "risk" && (
        <div className="space-y-4">
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
            <h3 className="font-semibold text-gray-800 mb-4">Risk Analysis Parameters</h3>
            <div className="grid grid-cols-3 gap-4 mb-4">
              <div>
                <label className="block text-xs text-gray-500 mb-1 font-medium">VaR Horizon (trading days)</label>
                <input type="number" min={1} max={252} value={varHorizon}
                       onChange={e => setVarHorizon(Number(e.target.value))}
                       className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1 font-medium">Simulations</label>
                <select value={varSims} onChange={e => setVarSims(Number(e.target.value))}
                        className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm">
                  {[1000, 5000, 10000, 20000].map(n => (
                    <option key={n} value={n}>{n.toLocaleString()}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1 font-medium">Confidence Level</label>
                <select value={varConf} onChange={e => setVarConf(Number(e.target.value))}
                        className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm">
                  {[0.90, 0.95, 0.99].map(c => (
                    <option key={c} value={c}>{(c * 100).toFixed(0)}%</option>
                  ))}
                </select>
              </div>
            </div>
            <button
              onClick={runRisk}
              disabled={loadingRisk || !legs.length || !spotInfo || !analysis}
              className="flex items-center gap-2 bg-indigo-600 text-white px-6 py-2 rounded-lg text-sm hover:bg-indigo-700 disabled:opacity-60 transition"
            >
              {loadingRisk ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Shield className="w-4 h-4" />}
              {loadingRisk ? "Running…" : "Run Risk Analysis"}
            </button>
            {!legs.length && (
              <p className="text-xs text-amber-600 mt-2">
                Build a strategy and click Analyse Strategy first
              </p>
            )}
          </div>

          {riskErr && (
            <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-xl px-4 py-3">
              <AlertTriangle className="w-4 h-4 inline mr-2" />{riskErr}
            </div>
          )}

          {varResult && (
            <div className="space-y-4">
              {/* VaR summary */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {[
                  { label: `VaR (${(varConf * 100).toFixed(0)}%)`, val: fmtINR(varResult.var), color: "text-red-600" },
                  { label: "CVaR (Exp. Shortfall)", val: fmtINR(varResult.cvar), color: "text-red-700" },
                  { label: "Mean P&L", val: fmtINR(varResult.mean_pnl), color: clr(varResult.mean_pnl) },
                  { label: "Std Dev", val: fmtINR(varResult.std_pnl), color: "text-gray-700" },
                  { label: "Best Case (p99)", val: fmtINR(varResult.percentiles?.p99), color: "text-green-600" },
                  { label: "p75",              val: fmtINR(varResult.percentiles?.p75), color: "text-green-500" },
                  { label: "Median (p50)",     val: fmtINR(varResult.percentiles?.p50), color: clr(varResult.percentiles?.p50 ?? 0) },
                  { label: "Worst Case (p1)",  val: fmtINR(varResult.percentiles?.p1),  color: "text-red-600" },
                ].map(m => (
                  <div key={m.label} className="bg-white rounded-xl border border-gray-200 shadow-sm p-4">
                    <p className="text-xs text-gray-500 uppercase tracking-wide mb-1">{m.label}</p>
                    <p className={`text-lg font-bold ${m.color}`}>{m.val}</p>
                  </div>
                ))}
              </div>

              {/* P&L Histogram */}
              <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-4">
                <h3 className="font-semibold text-gray-800 mb-3">
                  P&L Distribution ({varResult.num_simulations.toLocaleString()} simulations)
                </h3>
                <ResponsiveContainer width="100%" height={250}>
                  <BarChart data={varResult.histogram}
                            margin={{ top: 5, right: 20, left: 20, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke={chartGrid} />
                    <XAxis dataKey="midpoint"
                           tickFormatter={(v: number) => v >= 1e5 ? `${(v / 1e5).toFixed(0)}L` : String(Math.round(v))}
                           tick={chartTick} />
                    <YAxis tick={chartTick} />
                    <Tooltip
                      formatter={(v: number, n: string) => [v, "Scenarios"]}
                      labelFormatter={(l: number) => `P&L: ${fmtINR(l)}`}
                      contentStyle={tooltipStyle}
                    />
                    <ReferenceLine x={0} stroke="#9ca3af" />
                    <ReferenceLine x={-varResult.var} stroke="#ef4444" strokeDasharray="4 2"
                                   label={{ value: "VaR", fill: "#ef4444", fontSize: 10 }} />
                    <Bar dataKey="count" radius={[2, 2, 0, 0]}>
                      {varResult.histogram.map((entry: any, i: number) => (
                        <Cell key={i}
                              fill={entry.midpoint >= 0 ? "#6366f1" : "#f87171"}
                              fillOpacity={0.8} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          {/* Scenario analysis matrix */}
          {scResult && (
            <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-4">
              <div className="flex items-center gap-2 mb-4">
                <h3 className="font-semibold text-gray-800">Scenario Analysis Matrix</h3>
                <span className="text-xs text-gray-400">(estimated P&L today — not at expiry)</span>
              </div>
              <div className="overflow-x-auto">
                <table className="text-xs border-collapse min-w-full">
                  <thead>
                    <tr>
                      <th className="border border-gray-200 bg-gray-50 px-3 py-2 text-gray-500">
                        Price ↓ / Vol →
                      </th>
                      {scResult.vol_shocks.map((v: number) => (
                        <th key={v}
                            className="border border-gray-200 bg-gray-50 px-3 py-2 text-gray-600 font-medium">
                          Vol {v > 0 ? "+" : ""}{v}%
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {scResult.matrix.map((row: any[], ri: number) => (
                      <tr key={ri}>
                        <td className="border border-gray-200 bg-gray-50 px-3 py-2 text-gray-600 font-medium">
                          Price {scResult.price_shocks[ri] > 0 ? "+" : ""}
                          {scResult.price_shocks[ri]}%
                        </td>
                        {row.map((cell: any, ci: number) => {
                          const v    = cell.pnl;
                          const abs  = Math.abs(v);
                          const norm = Math.min(abs / (Math.abs(scResult.matrix.flat().reduce((mx: number, c: any) => Math.max(mx, Math.abs(c.pnl)), 0)) || 1), 1);
                          const alpha = 0.15 + norm * 0.6;
                          const bg_c  = v > 0 ? `rgba(34,197,94,${alpha})` : v < 0 ? `rgba(239,68,68,${alpha})` : "rgb(249,250,251)";
                          return (
                            <td key={ci}
                                className="border border-gray-200 px-3 py-2 text-center font-mono"
                                style={{ background: bg_c }}>
                              {fmtINR(v)}
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="text-xs text-gray-400 mt-2">
                Green = profit · Red = loss · Assumes no change in time to expiry
              </p>
            </div>
          )}
        </div>
      )}

      {/* ── TAB: Smart Builder ──────────────────────────────────────────────── */}
      {tab === "smart" && (
        <SmartBuilderTab
          symbol={symbol}
          spotInfo={spotInfo}
          setLegs={setLegs}
          setTab={setTab}
          isDark={isDark}
          doFetchSpot={doFetchSpot}
          onAnalyse={analyseStrategy}
        />
      )}

    </div>
  );
}
