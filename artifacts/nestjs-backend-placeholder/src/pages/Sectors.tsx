import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { TrendingUp, TrendingDown, Info, Target, Shield, BarChart2, Zap, Activity } from "lucide-react";

// ── Tier config ───────────────────────────────────────────────────────────────
const TIER_META: Record<string, { label: string; color: string; bg: string; border: string; badge: string }> = {
  DEEP_GREEN:  { label: "Deep Green",  color: "#15803d", bg: "#dcfce7", border: "#86efac", badge: "bg-green-700 text-white" },
  LIGHT_GREEN: { label: "Light Green", color: "#16a34a", bg: "#f0fdf4", border: "#bbf7d0", badge: "bg-green-500 text-white" },
  YELLOW:      { label: "Neutral",     color: "#ca8a04", bg: "#fefce8", border: "#fde68a", badge: "bg-yellow-500 text-white" },
  ORANGE:      { label: "Weakening",   color: "#ea580c", bg: "#fff7ed", border: "#fed7aa", badge: "bg-orange-500 text-white" },
  DEEP_RED:    { label: "Deep Red",    color: "#dc2626", bg: "#fef2f2", border: "#fecaca", badge: "bg-red-600 text-white" },
};

const PHASE_ORDER = [
  "Early Cycle / Recovery",
  "Mid Cycle / Expansion",
  "Late Cycle / Slowdown",
  "Recession / Contraction",
];

const PHASE_META: Record<string, { icon: string; abbr: string; color: string; bg: string; border: string }> = {
  "Early Cycle / Recovery":  { icon: "🌱", abbr: "Early",     color: "#16a34a", bg: "#f0fdf4", border: "#bbf7d0" },
  "Mid Cycle / Expansion":   { icon: "🚀", abbr: "Mid",       color: "#2563eb", bg: "#eff6ff", border: "#bfdbfe" },
  "Late Cycle / Slowdown":   { icon: "🌅", abbr: "Late",      color: "#d97706", bg: "#fffbeb", border: "#fde68a" },
  "Recession / Contraction": { icon: "🛡️", abbr: "Recession", color: "#dc2626", bg: "#fef2f2", border: "#fecaca" },
};

function fmt(n?: number, dec = 2) {
  if (n == null) return "—";
  return (n >= 0 ? "+" : "") + n.toFixed(dec);
}

function TierBadge({ tier }: { tier: string }) {
  const m = TIER_META[tier] || TIER_META.YELLOW;
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full font-semibold ${m.badge}`}>
      {m.label}
    </span>
  );
}

function MomentumBar({ value, max = 1.5 }: { value: number; max?: number }) {
  const pct = Math.max(0, Math.min(100, ((value + max) / (max * 2)) * 100));
  const color = value >= 0.5 ? "#16a34a" : value >= 0 ? "#4ade80" : value >= -0.5 ? "#facc15" : value >= -1 ? "#fb923c" : "#dc2626";
  return (
    <div className="w-full h-1.5 bg-gray-100 rounded-full overflow-hidden">
      <div className="h-full rounded-full transition-all" style={{ width: `${pct}%`, backgroundColor: color }} />
    </div>
  );
}

// ── Economic Cycle Phase Panel ────────────────────────────────────────────────
function EconomicPhasePanel({ phase }: { phase: any }) {
  if (!phase) return null;
  const current = phase.phase as string;
  const phaseScores: Record<string, number> = phase.phaseScores || {};

  return (
    <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
      <div className="px-5 py-4 border-b border-gray-50">
        <div className="flex items-center gap-2">
          <Activity className="w-4 h-4 text-indigo-600" />
          <h2 className="font-bold text-gray-900 text-sm">Phase 1 — Economic Cycle Assessment</h2>
          <span className="ml-auto text-xs text-gray-400 flex items-center gap-1">
            <Info className="w-3 h-3" /> India / NSE Context
          </span>
        </div>
      </div>

      {/* 4-phase cycle steps */}
      <div className="p-5">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-5">
          {PHASE_ORDER.map((p) => {
            const m = PHASE_META[p];
            const isCurrent = p === current;
            const score = phaseScores[p] ?? 0;
            return (
              <div
                key={p}
                className={`rounded-xl p-3 border-2 transition-all ${
                  isCurrent
                    ? "border-current shadow-md"
                    : "border-gray-100 opacity-60"
                }`}
                style={isCurrent ? { borderColor: m.color, backgroundColor: m.bg } : {}}
              >
                <div className="text-xl mb-1">{m.icon}</div>
                <p className={`text-xs font-bold ${isCurrent ? "" : "text-gray-500"}`}
                   style={isCurrent ? { color: m.color } : {}}>
                  {m.abbr}
                </p>
                <p className="text-xs text-gray-500 leading-tight mt-0.5"
                   style={{ fontSize: "10px" }}>
                  {p.replace(" / ", "/").split(" / ")[1] || p}
                </p>
                {Object.keys(phaseScores).length > 0 && (
                  <p className="text-xs font-mono mt-1" style={{ color: isCurrent ? m.color : "#9ca3af" }}>
                    {score >= 0 ? "+" : ""}{score.toFixed(2)}
                  </p>
                )}
              </div>
            );
          })}
        </div>

        {/* Current phase details */}
        <div
          className="rounded-xl p-4"
          style={{ backgroundColor: PHASE_META[current]?.bg || "#f9fafb", border: `1px solid ${PHASE_META[current]?.border || "#e5e7eb"}` }}
        >
          <div className="flex items-start justify-between gap-3">
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-1">
                <span className="text-lg">{PHASE_META[current]?.icon}</span>
                <h3 className="font-bold text-gray-900 text-sm">{current}</h3>
                <span
                  className="text-xs px-2 py-0.5 rounded-full font-semibold text-white"
                  style={{ backgroundColor: PHASE_META[current]?.color || "#6b7280" }}
                >
                  {phase.confidence}% confidence
                </span>
              </div>
              <p className="text-xs text-gray-600 leading-relaxed">{phase.characteristics}</p>
            </div>
          </div>

          <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <p className="text-xs font-semibold text-gray-500 mb-1">Theoretically Favored</p>
              <div className="flex flex-wrap gap-1">
                {(phase.theorySectors || []).map((s: string) => (
                  <span key={s} className="text-xs bg-white border border-gray-200 text-gray-700 px-2 py-0.5 rounded-full">
                    {s}
                  </span>
                ))}
              </div>
            </div>
            <div>
              <p className="text-xs font-semibold text-gray-500 mb-1">Strategy</p>
              <p className="text-xs text-gray-600 leading-relaxed">{phase.strategy}</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Sector Strength Matrix ─────────────────────────────────────────────────────
function StrengthMatrix({ sectors }: { sectors: any[] }) {
  if (!sectors?.length) return null;

  const byTier: Record<string, any[]> = {
    DEEP_GREEN: [], LIGHT_GREEN: [], YELLOW: [], ORANGE: [], DEEP_RED: [],
  };
  for (const s of sectors) {
    const t = s.momentum?.tier || "YELLOW";
    if (byTier[t]) byTier[t].push(s);
  }

  return (
    <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
      <div className="px-5 py-4 border-b border-gray-50">
        <div className="flex items-center gap-2">
          <BarChart2 className="w-4 h-4 text-indigo-600" />
          <h2 className="font-bold text-gray-900 text-sm">Phase 2 — Sector Strength Matrix</h2>
          <span className="ml-auto text-xs text-gray-400">Momentum Score Ranked</span>
        </div>
      </div>

      <div className="p-5 space-y-4">
        {Object.entries(byTier).map(([tier, secs]) => {
          if (!secs.length) return null;
          const m = TIER_META[tier];
          return (
            <div key={tier}>
              <div className="flex items-center gap-2 mb-2">
                <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: m.color }} />
                <span className="text-xs font-bold" style={{ color: m.color }}>{m.label}</span>
                <span className="text-xs text-gray-400">({secs.length} sector{secs.length !== 1 ? "s" : ""})</span>
                {tier === "LIGHT_GREEN" && (
                  <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded-full font-medium ml-auto">
                    ← Ideal Entry
                  </span>
                )}
                {tier === "DEEP_GREEN" && (
                  <span className="text-xs bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full font-medium ml-auto">
                    Consider Trimming
                  </span>
                )}
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {secs.map((s: any) => (
                  <div
                    key={s.symbol}
                    className="rounded-xl p-3 border"
                    style={{ backgroundColor: m.bg, borderColor: m.border }}
                  >
                    <div className="flex items-center justify-between mb-1.5">
                      <div>
                        <span className="font-bold text-gray-900 text-sm">{s.name}</span>
                        <span className="ml-2 text-xs text-gray-400">{s.symbol}</span>
                      </div>
                      <span className={`text-xs font-semibold ${s.pChange >= 0 ? "text-green-600" : "text-red-500"}`}>
                        {s.pChange >= 0 ? "▲" : "▼"} {Math.abs(s.pChange || 0).toFixed(2)}%
                      </span>
                    </div>
                    <MomentumBar value={s.momentum?.composite ?? 0} />
                    <div className="flex gap-3 mt-1.5 text-xs text-gray-500">
                      <span title="Relative Strength vs Nifty 50">RS {fmt(s.momentum?.rs)}%</span>
                      <span title="6-month Rate of Change">ROC {fmt(s.momentum?.roc_6m)}%</span>
                      <span title="% stocks above 200-day SMA" className="ml-auto">
                        {s.momentum?.pct_above_200?.toFixed(0) ?? "—"}% &gt;200SMA
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Portfolio Strategy Panel ──────────────────────────────────────────────────
function PortfolioPanel({ strategy, phase }: { strategy: any; phase: any }) {
  if (!strategy) return null;
  const picks = strategy.topPicks || [];
  const risk  = strategy.riskManagement || {};
  const cs    = strategy.coreSatellite || {};

  return (
    <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
      <div className="px-5 py-4 border-b border-gray-50">
        <div className="flex items-center gap-2">
          <Target className="w-4 h-4 text-indigo-600" />
          <h2 className="font-bold text-gray-900 text-sm">Phase 3 — Portfolio Strategy</h2>
        </div>
      </div>

      <div className="p-5 space-y-5">
        {/* Core-Satellite allocation */}
        <div className="grid grid-cols-2 gap-3">
          <div className="bg-indigo-50 border border-indigo-100 rounded-xl p-3">
            <p className="text-xs font-bold text-indigo-700 mb-1">Core (60-70%)</p>
            <p className="text-xs text-indigo-600 leading-relaxed">{cs.core}</p>
          </div>
          <div className="bg-purple-50 border border-purple-100 rounded-xl p-3">
            <p className="text-xs font-bold text-purple-700 mb-1">Satellite (30-40%)</p>
            <p className="text-xs text-purple-600 leading-relaxed">{cs.satellite}</p>
          </div>
        </div>

        {/* Top picks */}
        {picks.length > 0 && (
          <div>
            <p className="text-xs font-bold text-gray-500 uppercase tracking-wide mb-2">
              Top Sector Picks (ranked by momentum + theory alignment)
            </p>
            <div className="space-y-2">
              {picks.map((p: any, i: number) => {
                const tm = TIER_META[p.tier || "YELLOW"];
                return (
                  <div
                    key={p.symbol}
                    className="rounded-xl p-4 border"
                    style={{ backgroundColor: tm.bg, borderColor: tm.border }}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="font-bold text-gray-900 text-sm">#{i + 1} {p.sector}</span>
                          <TierBadge tier={p.tier} />
                          {p.theoryMatch && (
                            <span className="text-xs bg-indigo-100 text-indigo-700 px-2 py-0.5 rounded-full font-medium">
                              Theory ✓
                            </span>
                          )}
                        </div>
                        <p className="text-xs text-gray-600 mt-1 leading-relaxed">{p.entryReason}</p>
                      </div>
                      <div className="text-right flex-shrink-0">
                        <p className="text-xs font-mono font-bold" style={{ color: tm.color }}>
                          Score {(p.composite ?? 0).toFixed(3)}
                        </p>
                        <p className="text-xs text-gray-400 mt-0.5">RS {fmt(p.rs)}%</p>
                        <p className="text-xs text-gray-400">ROC {fmt(p.roc_6m)}%</p>
                      </div>
                    </div>
                    <div className="mt-2 grid grid-cols-2 gap-2">
                      <div className="text-xs bg-white bg-opacity-60 rounded-lg p-2">
                        <p className="font-semibold text-gray-700">🚪 Exit Rule</p>
                        <p className="text-gray-500 mt-0.5">{p.exitRule}</p>
                      </div>
                      <div className="text-xs bg-white bg-opacity-60 rounded-lg p-2">
                        <p className="font-semibold text-gray-700">💰 Profit Rule</p>
                        <p className="text-gray-500 mt-0.5">{p.profitRule}</p>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Risk rules */}
        <div>
          <div className="flex items-center gap-1.5 mb-2">
            <Shield className="w-3.5 h-3.5 text-gray-500" />
            <p className="text-xs font-bold text-gray-500 uppercase tracking-wide">Risk Management Framework</p>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
            {[
              { label: "Stop-Loss",        value: risk.stopLoss },
              { label: "Profit-Taking",    value: risk.profitTaking },
              { label: "Exit Signal",      value: risk.exitSignal },
              { label: "Cash Reserve",     value: risk.cashReserve },
              { label: "Max per Sector",   value: risk.maxPerSector },
              { label: "Max per Stock",    value: risk.maxPerStock },
            ].filter(r => r.value).map((r) => (
              <div key={r.label} className="bg-gray-50 border border-gray-100 rounded-lg p-2.5">
                <p className="text-xs font-semibold text-gray-600">{r.label}</p>
                <p className="text-xs text-gray-500 mt-0.5 leading-relaxed">{r.value}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Full Sector Table ──────────────────────────────────────────────────────────
function SectorTable({ sectors }: { sectors: any[] }) {
  if (!sectors?.length) return null;
  return (
    <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
      <div className="px-5 py-4 border-b border-gray-50">
        <div className="flex items-center gap-2">
          <Zap className="w-4 h-4 text-indigo-600" />
          <h2 className="font-bold text-gray-900 text-sm">All Sectors — Detailed Scores</h2>
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-gray-50">
              <th className="text-left px-4 py-2.5 text-gray-500 font-semibold">Sector</th>
              <th className="text-center px-3 py-2.5 text-gray-500 font-semibold">Tier</th>
              <th className="text-right px-3 py-2.5 text-gray-500 font-semibold">Score</th>
              <th className="text-right px-3 py-2.5 text-gray-500 font-semibold">Day %</th>
              <th className="text-right px-3 py-2.5 text-gray-500 font-semibold">RS vs N50</th>
              <th className="text-right px-3 py-2.5 text-gray-500 font-semibold">6m ROC</th>
              <th className="text-right px-3 py-2.5 text-gray-500 font-semibold">&gt;200 SMA</th>
              <th className="text-right px-3 py-2.5 text-gray-500 font-semibold">Focus</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {sectors.map((s: any, i: number) => {
              const ms = s.momentum || {};
              const tm = TIER_META[ms.tier || "YELLOW"];
              return (
                <tr key={s.symbol} className="hover:bg-gray-50/50 transition-colors">
                  <td className="px-4 py-2.5">
                    <div className="flex items-center gap-2">
                      <span className="text-gray-400 font-mono w-5 text-right">{ms.rank || i + 1}</span>
                      <div>
                        <p className="font-semibold text-gray-900">{s.name}</p>
                        <p className="text-gray-400" style={{ fontSize: "10px" }}>{s.category}</p>
                      </div>
                    </div>
                  </td>
                  <td className="px-3 py-2.5 text-center">
                    <span
                      className="px-2 py-0.5 rounded-full text-white font-semibold"
                      style={{ backgroundColor: tm.color, fontSize: "10px" }}
                    >
                      {tm.label}
                    </span>
                  </td>
                  <td className="px-3 py-2.5 text-right font-mono font-bold" style={{ color: tm.color }}>
                    {ms.composite != null ? ms.composite.toFixed(3) : "—"}
                  </td>
                  <td className={`px-3 py-2.5 text-right font-semibold ${(s.pChange || 0) >= 0 ? "text-green-600" : "text-red-500"}`}>
                    {fmt(s.pChange)}%
                  </td>
                  <td className={`px-3 py-2.5 text-right ${(ms.rs || 0) >= 0 ? "text-green-600" : "text-red-500"}`}>
                    {fmt(ms.rs)}%
                  </td>
                  <td className={`px-3 py-2.5 text-right ${(ms.roc_6m || 0) >= 0 ? "text-green-600" : "text-red-500"}`}>
                    {fmt(ms.roc_6m)}%
                  </td>
                  <td className="px-3 py-2.5 text-right text-gray-700">
                    {ms.pct_above_200 != null ? ms.pct_above_200.toFixed(0) + "%" : "—"}
                  </td>
                  <td className="px-3 py-2.5 text-right">
                    <span className={`px-1.5 py-0.5 rounded text-white font-semibold ${
                      s.focus === "STRONG BUY" ? "bg-green-700" :
                      s.focus === "BUY"        ? "bg-green-500" :
                      s.focus === "HOLD"       ? "bg-gray-400" :
                      s.focus === "REDUCE"     ? "bg-orange-500" :
                                                 "bg-red-600"
                    }`} style={{ fontSize: "10px" }}>
                      {s.focus || "HOLD"}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Market Breadth Bar ────────────────────────────────────────────────────────
function BreadthBar({ rotation }: { rotation: any }) {
  if (!rotation) return null;
  const mb  = rotation.marketBreadth || {};
  const adv = mb.advancing || 0;
  const dec = mb.declining || 0;
  const unc = mb.unchanged || 0;
  const total = adv + dec + unc || 1;
  const tc = rotation.tierCounts || {};

  return (
    <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-5">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-bold text-gray-900 text-sm">Market Breadth</h3>
        <div className="flex gap-3 text-xs">
          <span className="text-green-600 font-bold">▲ {adv} rising</span>
          <span className="text-red-500 font-bold">▼ {dec} falling</span>
          <span className="text-gray-400">{unc} flat</span>
        </div>
      </div>

      {/* A/D breadth bar */}
      <div className="flex rounded-full overflow-hidden h-2.5 mb-4">
        <div className="bg-green-500 transition-all" style={{ width: `${(adv / total) * 100}%` }} />
        <div className="bg-gray-200 transition-all"  style={{ width: `${(unc / total) * 100}%` }} />
        <div className="bg-red-500 transition-all"   style={{ width: `${(dec / total) * 100}%` }} />
      </div>

      {/* Tier count badges */}
      {Object.keys(tc).length > 0 && (
        <div className="flex flex-wrap gap-2">
          {Object.entries(tc).map(([tier, count]) => {
            const tm = TIER_META[tier];
            if (!tm) return null;
            return (
              <div key={tier} className="flex items-center gap-1.5 text-xs">
                <div className="w-2 h-2 rounded-full" style={{ backgroundColor: tm.color }} />
                <span className="text-gray-600">{tm.label}</span>
                <span className="font-bold text-gray-900">{count as number}</span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────
export default function Sectors() {
  const { data: rotation, isLoading } = useQuery({
    queryKey: ["rotation"],
    queryFn:  api.sectorRotation,
    staleTime: 4 * 60 * 1000,
  });

  const sectors  = rotation?.sectors ?? [];
  const phase    = rotation?.economicPhase;
  const strategy = rotation?.portfolioStrategy;

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Sector Rotation Intelligence</h1>
        <p className="text-sm text-gray-500 mt-0.5">
          Hybrid 3-Phase Algorithm — Macro Assessment · Quantitative Momentum · Portfolio Strategy
        </p>
      </div>

      {isLoading ? (
        <div className="space-y-4">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-48 bg-gray-100 animate-pulse rounded-2xl" />
          ))}
          <p className="text-center text-sm text-gray-400 animate-pulse">
            Computing momentum scores — fetching 6-month history for all sectors…
          </p>
        </div>
      ) : (
        <>
          {/* Breadth summary */}
          <BreadthBar rotation={rotation} />

          {/* Phase 1 */}
          <EconomicPhasePanel phase={phase} />

          {/* Phase 2 */}
          <StrengthMatrix sectors={sectors} />

          {/* Phase 3 */}
          <PortfolioPanel strategy={strategy} phase={phase} />

          {/* Full table */}
          <SectorTable sectors={sectors} />

          {rotation && (
            <p className="text-center text-xs text-gray-400 pb-2">
              Scores computed at {new Date(rotation.timestamp).toLocaleString("en-IN")} ·
              Cached 4 h · Weighted: RS 40% | Breadth(200SMA) 25% | 6m ROC 20% | Volume 15%
            </p>
          )}
        </>
      )}
    </div>
  );
}
