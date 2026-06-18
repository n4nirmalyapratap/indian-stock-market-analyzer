/**
 * HiddenGemsBits — two small UI bits that drop into the Scanners
 * results panel only for scanners in the "Hidden Gems" category:
 *
 *   1. <HiddenGemScoreBadge>  — coloured pill showing the 0-100 score
 *      computed server-side from fundamentals. Hover reveals the
 *      breakdown (which sub-rules contributed which points), so users
 *      see WHY a stock scored where it did.
 *
 *   2. <ExitPlanButton>       — opens a modal that takes entry price +
 *      risk tolerance + horizon and returns 3 price targets, a stop
 *      loss, a trailing stop, and the risk-reward ratio. Pure client
 *      math, no backend round-trip — fast enough to feel instant.
 *
 * Both are designed to be opt-in: pass `result.hiddenGemScore` and
 * `result.symbol` from the scanner result row; nothing else needed.
 */
import { useState } from "react";
import { Target, X as XIcon, TrendingUp, TrendingDown, Shield } from "lucide-react";


// ── Score badge ─────────────────────────────────────────────────────────────


function scoreColor(score: number | null | undefined): { bg: string; text: string; border: string; label: string } {
  if (score == null) return { bg: "bg-gray-100 dark:bg-gray-800", text: "text-gray-500", border: "border-gray-200 dark:border-gray-700", label: "—" };
  if (score >= 80)   return { bg: "bg-emerald-100 dark:bg-emerald-900/40", text: "text-emerald-700 dark:text-emerald-300", border: "border-emerald-300 dark:border-emerald-700", label: "Strong" };
  if (score >= 60)   return { bg: "bg-lime-100 dark:bg-lime-900/40",       text: "text-lime-700 dark:text-lime-300",       border: "border-lime-300 dark:border-lime-700",       label: "Good" };
  if (score >= 40)   return { bg: "bg-amber-100 dark:bg-amber-900/40",     text: "text-amber-700 dark:text-amber-300",     border: "border-amber-300 dark:border-amber-700",     label: "Mixed" };
  return                       { bg: "bg-rose-100 dark:bg-rose-900/40",       text: "text-rose-700 dark:text-rose-300",       border: "border-rose-300 dark:border-rose-700",       label: "Weak" };
}


export function HiddenGemScoreBadge({
  score, breakdown,
}: {
  score: number | null | undefined;
  breakdown?: string[];
}) {
  const c = scoreColor(score);
  const tooltipText = (breakdown && breakdown.length > 0)
    ? breakdown.join("\n")
    : "fundamentals unavailable";
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md text-xs font-semibold border ${c.bg} ${c.text} ${c.border}`}
      title={tooltipText}
    >
      <span className="text-[10px] font-bold uppercase tracking-wider opacity-80">Gem</span>
      <span className="tabular-nums">{score == null ? "—" : `${score}`}</span>
      <span className="text-[10px] opacity-75">{c.label}</span>
    </span>
  );
}


// ── Exit Plan modal ─────────────────────────────────────────────────────────


type RiskTolerance     = "conservative" | "moderate" | "aggressive";
type InvestmentHorizon = "short-term"   | "medium-term" | "long-term";

interface ExitPlan {
  targetPrices:    { target1: number; target2: number; target3: number };
  stopLoss:        number;
  trailingStop:    number;
  riskRewardRatio: number;
  rule:            string;
}

function computeExitPlan(
  entryPrice: number,
  risk:       RiskTolerance,
  horizon:    InvestmentHorizon,
): ExitPlan {
  // Stop-loss % — lower for conservative, higher for aggressive (the
  // aggressive trader is willing to give the trade room to breathe).
  const stopLossPct = { conservative: 5, moderate: 10, aggressive: 15 }[risk];

  // Target multipliers per horizon — short trades take 5/10/15%, long
  // trades aim for 20/40/75%. Each row is (T1, T2, T3) where T3 is the
  // primary objective and T1/T2 are partial-exit checkpoints.
  const multipliers: Record<InvestmentHorizon, [number, number, number]> = {
    "short-term":  [1.05, 1.10, 1.15],
    "medium-term": [1.15, 1.25, 1.40],
    "long-term":   [1.20, 1.40, 1.75],
  };
  const [m1, m2, m3] = multipliers[horizon];

  const stopLoss     = entryPrice * (1 - stopLossPct / 100);
  const target1      = entryPrice * m1;
  const target2      = entryPrice * m2;
  const target3      = entryPrice * m3;
  // Trailing stop fixed at 5% below entry — conservative default;
  // user moves it up manually as price advances.
  const trailingStop = entryPrice * 0.95;

  const potentialLoss = entryPrice - stopLoss;
  const potentialGain = target3 - entryPrice;
  const riskRewardRatio = potentialLoss > 0 ? potentialGain / potentialLoss : 0;

  return {
    targetPrices:    { target1, target2, target3 },
    stopLoss,
    trailingStop,
    riskRewardRatio,
    rule:            `Exit ${riskRewardRatio.toFixed(1)}:1 R:R — sell 1/3 at T1, 1/3 at T2, hold rest to T3`,
  };
}


function ExitPlanModal({
  symbol, defaultEntry, onClose,
}: {
  symbol:       string;
  defaultEntry: number;
  onClose:      () => void;
}) {
  const [entry, setEntry]     = useState<string>(defaultEntry.toFixed(2));
  const [risk, setRisk]       = useState<RiskTolerance>("moderate");
  const [horizon, setHorizon] = useState<InvestmentHorizon>("medium-term");

  const entryNum = parseFloat(entry);
  const plan = !isNaN(entryNum) && entryNum > 0
    ? computeExitPlan(entryNum, risk, horizon)
    : null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="exit-plan-modal-title"
        className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-white/[0.08] shadow-2xl w-full max-w-md overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="px-5 py-3 border-b border-gray-100 dark:border-white/[0.04] flex items-start justify-between gap-3">
          <div>
            <h3 id="exit-plan-modal-title" className="font-bold text-gray-900 dark:text-white text-sm flex items-center gap-1.5">
              <Target className="w-3.5 h-3.5 text-indigo-500" />
              Exit Plan — {symbol}
            </h3>
            <p className="text-[11px] text-gray-500 dark:text-gray-400 mt-0.5">
              Pre-planned exits prevent emotional decisions when the trade moves.
            </p>
          </div>
          <button onClick={onClose} aria-label="Close" className="text-gray-400 hover:text-gray-700 dark:hover:text-gray-200">
            <XIcon className="w-4 h-4" />
          </button>
        </div>

        <div className="p-5 space-y-3">
          <label className="block">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
              Entry Price (₹)
            </span>
            <input
              type="number" step="any" value={entry}
              onChange={(e) => setEntry(e.target.value)}
              className="mt-1 block w-full rounded-md border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 px-3 py-2 text-sm text-gray-900 dark:text-white tabular-nums focus:border-indigo-400 focus:ring-1 focus:ring-indigo-400 outline-none"
              autoFocus
            />
          </label>

          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
                Risk Tolerance
              </span>
              <select
                value={risk}
                onChange={(e) => setRisk(e.target.value as RiskTolerance)}
                className="mt-1 block w-full rounded-md border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 px-3 py-2 text-sm text-gray-900 dark:text-white focus:border-indigo-400 focus:ring-1 focus:ring-indigo-400 outline-none"
              >
                <option value="conservative">Conservative (5% SL)</option>
                <option value="moderate">Moderate (10% SL)</option>
                <option value="aggressive">Aggressive (15% SL)</option>
              </select>
            </label>

            <label className="block">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
                Horizon
              </span>
              <select
                value={horizon}
                onChange={(e) => setHorizon(e.target.value as InvestmentHorizon)}
                className="mt-1 block w-full rounded-md border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 px-3 py-2 text-sm text-gray-900 dark:text-white focus:border-indigo-400 focus:ring-1 focus:ring-indigo-400 outline-none"
              >
                <option value="short-term">Short-term (days)</option>
                <option value="medium-term">Medium-term (weeks)</option>
                <option value="long-term">Long-term (months+)</option>
              </select>
            </label>
          </div>

          {plan && (
            <div className="mt-2 space-y-2">
              {/* Targets */}
              <div className="rounded-lg border border-emerald-200 dark:border-emerald-700/40 bg-emerald-50/50 dark:bg-emerald-900/10 p-3">
                <p className="text-[10px] font-bold uppercase tracking-widest text-emerald-700 dark:text-emerald-400 mb-1.5 flex items-center gap-1">
                  <TrendingUp className="w-3 h-3" /> Profit Targets
                </p>
                <div className="grid grid-cols-3 gap-2 text-center">
                  {[
                    { lbl: "T1 (sell 1/3)", v: plan.targetPrices.target1 },
                    { lbl: "T2 (sell 1/3)", v: plan.targetPrices.target2 },
                    { lbl: "T3 (hold rest)", v: plan.targetPrices.target3 },
                  ].map((t) => (
                    <div key={t.lbl}>
                      <p className="text-[10px] text-emerald-600 dark:text-emerald-400/80">{t.lbl}</p>
                      <p className="text-sm font-bold text-emerald-700 dark:text-emerald-300 tabular-nums">
                        ₹{t.v.toFixed(2)}
                      </p>
                      <p className="text-[10px] text-emerald-600/70 dark:text-emerald-400/60">
                        +{((t.v - entryNum) / entryNum * 100).toFixed(1)}%
                      </p>
                    </div>
                  ))}
                </div>
              </div>

              {/* Stop loss */}
              <div className="rounded-lg border border-rose-200 dark:border-rose-700/40 bg-rose-50/50 dark:bg-rose-900/10 p-3">
                <p className="text-[10px] font-bold uppercase tracking-widest text-rose-700 dark:text-rose-400 mb-1.5 flex items-center gap-1">
                  <TrendingDown className="w-3 h-3" /> Stop Loss
                </p>
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <p className="text-[10px] text-rose-600 dark:text-rose-400/80">Hard stop</p>
                    <p className="text-sm font-bold text-rose-700 dark:text-rose-300 tabular-nums">
                      ₹{plan.stopLoss.toFixed(2)}
                    </p>
                    <p className="text-[10px] text-rose-600/70 dark:text-rose-400/60">
                      {((plan.stopLoss - entryNum) / entryNum * 100).toFixed(1)}%
                    </p>
                  </div>
                  <div>
                    <p className="text-[10px] text-rose-600 dark:text-rose-400/80">Trailing stop</p>
                    <p className="text-sm font-bold text-rose-700 dark:text-rose-300 tabular-nums">
                      ₹{plan.trailingStop.toFixed(2)}
                    </p>
                    <p className="text-[10px] text-rose-600/70 dark:text-rose-400/60">
                      move up as price advances
                    </p>
                  </div>
                </div>
              </div>

              {/* R:R + rule */}
              <div className="rounded-lg border border-indigo-200 dark:border-indigo-700/40 bg-indigo-50/50 dark:bg-indigo-900/10 p-3 flex items-center gap-3">
                <Shield className="w-4 h-4 text-indigo-500 flex-shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-[10px] font-bold uppercase tracking-widest text-indigo-700 dark:text-indigo-400">
                    Risk : Reward
                  </p>
                  <p className="text-base font-bold text-indigo-700 dark:text-indigo-200 tabular-nums">
                    {plan.riskRewardRatio.toFixed(2)} : 1
                  </p>
                </div>
                <p className="text-[10px] text-indigo-600 dark:text-indigo-400 max-w-[170px] text-right leading-snug">
                  {plan.rule}
                </p>
              </div>
            </div>
          )}
        </div>

        <div className="px-5 py-3 border-t border-gray-100 dark:border-white/[0.04] flex items-center justify-end">
          <button
            onClick={onClose}
            className="px-3 py-1.5 rounded-md text-xs font-medium bg-gray-100 hover:bg-gray-200 dark:bg-gray-800 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}


export function ExitPlanButton({
  symbol, currentPrice,
}: {
  symbol:       string;
  currentPrice: number | null | undefined;
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        onClick={() => setOpen(true)}
        title="Plan exits for this stock"
        className="inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-md border bg-gray-50 hover:bg-indigo-50 text-gray-600 hover:text-indigo-700 border-gray-200 dark:bg-gray-800 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-indigo-900/30 dark:hover:text-indigo-300"
      >
        <Target className="w-2.5 h-2.5" />
        Exit Plan
      </button>
      {open && (
        <ExitPlanModal
          symbol={symbol}
          defaultEntry={currentPrice ?? 0}
          onClose={() => setOpen(false)}
        />
      )}
    </>
  );
}
