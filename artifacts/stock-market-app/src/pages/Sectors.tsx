import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "wouter";
import { api, SectorHeatmapItem } from "@/lib/api";
import { TrendingUp, TrendingDown, Info, Target, Shield, BarChart2, Zap, Activity, ChevronRight } from "lucide-react";
import { useTheme } from "@/context/ThemeContext";

// ── Theme-aware tier config ────────────────────────────────────────────────────
function getTierMeta(isDark: boolean) {
  return {
    DEEP_GREEN:  { label: "Deep Green",  color: isDark ? "#4ade80" : "#15803d", bg: isDark ? "rgba(21,128,61,0.2)"   : "#dcfce7", border: isDark ? "rgba(74,222,128,0.3)"  : "#86efac", badge: "bg-green-700 text-white" },
    LIGHT_GREEN: { label: "Light Green", color: isDark ? "#86efac" : "#16a34a", bg: isDark ? "rgba(22,163,74,0.15)"  : "#f0fdf4", border: isDark ? "rgba(134,239,172,0.3)" : "#bbf7d0", badge: "bg-green-500 text-white" },
    YELLOW:      { label: "Neutral",     color: isDark ? "#fde047" : "#ca8a04", bg: isDark ? "rgba(202,138,4,0.15)"  : "#fefce8", border: isDark ? "rgba(253,224,71,0.3)"  : "#fde68a", badge: "bg-yellow-500 text-white" },
    ORANGE:      { label: "Weakening",   color: isDark ? "#fb923c" : "#ea580c", bg: isDark ? "rgba(234,88,12,0.15)"  : "#fff7ed", border: isDark ? "rgba(251,146,60,0.3)"  : "#fed7aa", badge: "bg-orange-500 text-white" },
    DEEP_RED:    { label: "Deep Red",    color: isDark ? "#f87171" : "#dc2626", bg: isDark ? "rgba(220,38,38,0.15)"  : "#fef2f2", border: isDark ? "rgba(248,113,113,0.3)" : "#fecaca", badge: "bg-red-600 text-white" },
  } as const;
}

function getPhaseMeta(isDark: boolean) {
  return {
    "Early Cycle / Recovery":  { icon: "🌱", abbr: "Early",     color: isDark ? "#86efac" : "#16a34a", bg: isDark ? "rgba(22,163,74,0.15)"  : "#f0fdf4", border: isDark ? "rgba(134,239,172,0.3)" : "#bbf7d0" },
    "Mid Cycle / Expansion":   { icon: "🚀", abbr: "Mid",       color: isDark ? "#93c5fd" : "#2563eb", bg: isDark ? "rgba(37,99,235,0.15)"   : "#eff6ff", border: isDark ? "rgba(147,197,253,0.3)" : "#bfdbfe" },
    "Late Cycle / Slowdown":   { icon: "🌅", abbr: "Late",      color: isDark ? "#fcd34d" : "#d97706", bg: isDark ? "rgba(217,119,6,0.15)"   : "#fffbeb", border: isDark ? "rgba(252,211,77,0.3)"  : "#fde68a" },
    "Recession / Contraction": { icon: "🛡️", abbr: "Recession", color: isDark ? "#f87171" : "#dc2626", bg: isDark ? "rgba(220,38,38,0.15)"   : "#fef2f2", border: isDark ? "rgba(248,113,113,0.3)" : "#fecaca" },
  } as const;
}

const PHASE_ORDER = [
  "Early Cycle / Recovery",
  "Mid Cycle / Expansion",
  "Late Cycle / Slowdown",
  "Recession / Contraction",
] as const;

function fmt(n?: number, dec = 2) {
  if (n == null) return "—";
  return (n >= 0 ? "+" : "") + n.toFixed(dec);
}

function MomentumBar({ value, max = 1.5, isDark }: { value: number; max?: number; isDark: boolean }) {
  const pct = Math.max(0, Math.min(100, ((value + max) / (max * 2)) * 100));
  const color = value >= 0.5 ? "#16a34a" : value >= 0 ? "#4ade80" : value >= -0.5 ? "#facc15" : value >= -1 ? "#fb923c" : "#dc2626";
  return (
    <div className="w-full h-1.5 rounded-full overflow-hidden" style={{ background: isDark ? "#374151" : "#f3f4f6" }}>
      <div className="h-full rounded-full transition-all" style={{ width: `${pct}%`, backgroundColor: color }} />
    </div>
  );
}

// ── Shared card shell ─────────────────────────────────────────────────────────
function Card({ isDark, children, className = "" }: { isDark: boolean; children: React.ReactNode; className?: string }) {
  return (
    <div className={`rounded-2xl border shadow-sm overflow-hidden ${className}`}
      style={{ background: isDark ? "#1e293b" : "#fff", borderColor: isDark ? "#334155" : "#f3f4f6" }}>
      {children}
    </div>
  );
}

function CardHeader({ isDark, children }: { isDark: boolean; children: React.ReactNode }) {
  return (
    <div className="px-5 py-4" style={{ borderBottom: `1px solid ${isDark ? "#334155" : "#f9fafb"}` }}>
      {children}
    </div>
  );
}

// ── Economic Cycle Phase Panel ────────────────────────────────────────────────
function EconomicPhasePanel({ phase, isDark }: { phase: any; isDark: boolean }) {
  if (!phase) return null;
  const PHASE_META = getPhaseMeta(isDark);
  const current = phase.phase as string;
  const phaseScores: Record<string, number> = phase.phaseScores || {};
  const cm = PHASE_META[current as keyof typeof PHASE_META];
  const muTxt = isDark ? "#94a3b8" : "#6b7280";
  const bodyTxt = isDark ? "#cbd5e1" : "#4b5563";

  return (
    <Card isDark={isDark}>
      <CardHeader isDark={isDark}>
        <div className="flex items-center gap-2">
          <Activity className="w-4 h-4 text-indigo-500" />
          <h2 className="font-bold text-sm" style={{ color: isDark ? "#f1f5f9" : "#111827" }}>Phase 1 — Economic Cycle Assessment</h2>
          <span className="ml-auto text-xs flex items-center gap-1" style={{ color: muTxt }}>
            <Info className="w-3 h-3" /> India / NSE Context
          </span>
        </div>
      </CardHeader>
      <div className="p-5">
        {/* 4-phase cycle steps */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-5">
          {PHASE_ORDER.map((p) => {
            const m = PHASE_META[p];
            const isCurrent = p === current;
            const score = phaseScores[p] ?? 0;
            return (
              <div key={p} className="rounded-xl p-3 border-2 transition-all"
                style={isCurrent
                  ? { borderColor: m.color, backgroundColor: m.bg }
                  : { borderColor: isDark ? "#374151" : "#f3f4f6", opacity: 0.6 }}>
                <div className="text-xl mb-1">{m.icon}</div>
                <p className="text-xs font-bold" style={{ color: isCurrent ? m.color : muTxt }}>{m.abbr}</p>
                <p className="text-xs leading-tight mt-0.5" style={{ color: muTxt, fontSize: "10px" }}>
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

        {/* Current phase detail */}
        {cm && (
          <div className="rounded-xl p-4" style={{ backgroundColor: cm.bg, border: `1px solid ${cm.border}` }}>
            <div className="flex items-start gap-3">
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-lg">{cm.icon}</span>
                  <h3 className="font-bold text-sm" style={{ color: isDark ? "#f1f5f9" : "#111827" }}>{current}</h3>
                  <span className="text-xs px-2 py-0.5 rounded-full font-semibold text-white" style={{ backgroundColor: cm.color }}>
                    {phase.confidence}% confidence
                  </span>
                </div>
                <p className="text-xs leading-relaxed" style={{ color: bodyTxt }}>{phase.characteristics}</p>
              </div>
            </div>
            <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <p className="text-xs font-semibold mb-1" style={{ color: muTxt }}>Theoretically Favored</p>
                <div className="flex flex-wrap gap-1">
                  {(phase.theorySectors || []).map((s: string) => (
                    <span key={s} className="text-xs px-2 py-0.5 rounded-full"
                      style={{ background: isDark ? "rgba(255,255,255,0.1)" : "#fff", border: `1px solid ${isDark ? "#475569" : "#e5e7eb"}`, color: isDark ? "#cbd5e1" : "#374151" }}>
                      {s}
                    </span>
                  ))}
                </div>
              </div>
              <div>
                <p className="text-xs font-semibold mb-1" style={{ color: muTxt }}>Strategy</p>
                <p className="text-xs leading-relaxed" style={{ color: bodyTxt }}>{phase.strategy}</p>
              </div>
            </div>
          </div>
        )}
      </div>
    </Card>
  );
}

// ── Sector Strength Matrix ─────────────────────────────────────────────────────
function StrengthMatrix({ sectors, isDark }: { sectors: any[]; isDark: boolean }) {
  if (!sectors?.length) return null;
  const TIER_META = getTierMeta(isDark);
  const muTxt = isDark ? "#64748b" : "#9ca3af";

  const byTier: Record<string, any[]> = { DEEP_GREEN: [], LIGHT_GREEN: [], YELLOW: [], ORANGE: [], DEEP_RED: [] };
  for (const s of sectors) {
    const t = s.momentum?.tier || "YELLOW";
    if (byTier[t]) byTier[t].push(s);
  }

  return (
    <Card isDark={isDark}>
      <CardHeader isDark={isDark}>
        <div className="flex items-center gap-2">
          <BarChart2 className="w-4 h-4 text-indigo-500" />
          <h2 className="font-bold text-sm" style={{ color: isDark ? "#f1f5f9" : "#111827" }}>Phase 2 — Sector Strength Matrix</h2>
          <span className="ml-auto text-xs" style={{ color: muTxt }}>Momentum Score Ranked</span>
        </div>
      </CardHeader>
      <div className="p-5 space-y-4">
        {Object.entries(byTier).map(([tier, secs]) => {
          if (!secs.length) return null;
          const m = TIER_META[tier as keyof typeof TIER_META];
          return (
            <div key={tier}>
              <div className="flex items-center gap-2 mb-2">
                <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: m.color }} />
                <span className="text-xs font-bold" style={{ color: m.color }}>{m.label}</span>
                <span className="text-xs" style={{ color: muTxt }}>({secs.length} sector{secs.length !== 1 ? "s" : ""})</span>
                {tier === "LIGHT_GREEN" && (
                  <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded-full font-medium ml-auto">← Ideal Entry</span>
                )}
                {tier === "DEEP_GREEN" && (
                  <span className="text-xs bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full font-medium ml-auto">Consider Trimming</span>
                )}
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {secs.map((s: any) => (
                  <div key={s.symbol} className="rounded-xl p-3 border" style={{ backgroundColor: m.bg, borderColor: m.border }}>
                    <div className="flex items-center justify-between mb-1.5">
                      <div>
                        <span className="font-bold text-sm" style={{ color: isDark ? "#f1f5f9" : "#111827" }}>{s.name}</span>
                        <span className="ml-2 text-xs" style={{ color: muTxt }}>{s.symbol}</span>
                      </div>
                      <span className={`text-xs font-semibold ${s.pChange >= 0 ? "text-green-500" : "text-red-400"}`}>
                        {s.pChange >= 0 ? "▲" : "▼"} {Math.abs(s.pChange || 0).toFixed(2)}%
                      </span>
                    </div>
                    <MomentumBar value={s.momentum?.composite ?? 0} isDark={isDark} />
                    <div className="flex gap-3 mt-1.5 text-xs" style={{ color: muTxt }}>
                      <span>Strength {fmt(s.momentum?.rs)}%</span>
                      <span>6M {fmt(s.momentum?.roc_6m)}%</span>
                      <span className="ml-auto">{s.momentum?.pct_above_200?.toFixed(0) ?? "—"}% &gt;200SMA</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </Card>
  );
}

// ── Portfolio Strategy Panel ──────────────────────────────────────────────────
function PortfolioPanel({ strategy, isDark }: { strategy: any; isDark: boolean }) {
  if (!strategy) return null;
  const TIER_META = getTierMeta(isDark);
  const picks = strategy.topPicks || [];
  const risk  = strategy.riskManagement || {};
  const cs    = strategy.coreSatellite || {};
  const muTxt = isDark ? "#94a3b8" : "#6b7280";
  const bodyTxt = isDark ? "#cbd5e1" : "#4b5563";

  return (
    <Card isDark={isDark}>
      <CardHeader isDark={isDark}>
        <div className="flex items-center gap-2">
          <Target className="w-4 h-4 text-indigo-500" />
          <h2 className="font-bold text-sm" style={{ color: isDark ? "#f1f5f9" : "#111827" }}>Phase 3 — Portfolio Strategy</h2>
        </div>
      </CardHeader>
      <div className="p-5 space-y-5">
        {/* Core-Satellite */}
        <div className="grid grid-cols-2 gap-3">
          <div className="rounded-xl p-3" style={{ background: isDark ? "rgba(99,102,241,0.15)" : "#eef2ff", border: `1px solid ${isDark ? "rgba(99,102,241,0.3)" : "#c7d2fe"}` }}>
            <p className="text-xs font-bold mb-1" style={{ color: isDark ? "#a5b4fc" : "#4338ca" }}>Core (60-70%)</p>
            <p className="text-xs leading-relaxed" style={{ color: isDark ? "#818cf8" : "#6366f1" }}>{cs.core}</p>
          </div>
          <div className="rounded-xl p-3" style={{ background: isDark ? "rgba(139,92,246,0.15)" : "#f5f3ff", border: `1px solid ${isDark ? "rgba(139,92,246,0.3)" : "#ddd6fe"}` }}>
            <p className="text-xs font-bold mb-1" style={{ color: isDark ? "#c4b5fd" : "#7c3aed" }}>Satellite (30-40%)</p>
            <p className="text-xs leading-relaxed" style={{ color: isDark ? "#a78bfa" : "#8b5cf6" }}>{cs.satellite}</p>
          </div>
        </div>

        {/* Top picks */}
        {picks.length > 0 && (
          <div>
            <p className="text-xs font-bold uppercase tracking-wide mb-2" style={{ color: muTxt }}>
              Top Sector Picks (ranked by momentum + theory alignment)
            </p>
            <div className="space-y-2">
              {picks.map((p: any, i: number) => {
                const tm = TIER_META[p.tier as keyof typeof TIER_META || "YELLOW"];
                return (
                  <div key={p.symbol} className="rounded-xl p-4 border" style={{ backgroundColor: tm.bg, borderColor: tm.border }}>
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="font-bold text-sm" style={{ color: isDark ? "#f1f5f9" : "#111827" }}>#{i + 1} {p.sector}</span>
                          <span className={`text-xs px-2 py-0.5 rounded-full font-semibold ${tm.badge}`}>{tm.label}</span>
                          {p.theoryMatch && (
                            <span className="text-xs px-2 py-0.5 rounded-full font-medium" style={{ background: isDark ? "rgba(99,102,241,0.2)" : "#e0e7ff", color: isDark ? "#a5b4fc" : "#4338ca" }}>
                              Theory ✓
                            </span>
                          )}
                        </div>
                        <p className="text-xs mt-1 leading-relaxed" style={{ color: bodyTxt }}>{p.entryReason}</p>
                      </div>
                      <div className="text-right flex-shrink-0">
                        <p className="text-xs font-mono font-bold" style={{ color: tm.color }}>Score {(p.composite ?? 0).toFixed(3)}</p>
                        <p className="text-xs mt-0.5" style={{ color: muTxt }}>RS {fmt(p.rs)}%</p>
                        <p className="text-xs" style={{ color: muTxt }}>ROC {fmt(p.roc_6m)}%</p>
                      </div>
                    </div>
                    <div className="mt-2 grid grid-cols-2 gap-2">
                      {[["🚪 Exit Rule", p.exitRule], ["💰 Profit Rule", p.profitRule]].map(([label, val]) => (
                        <div key={label as string} className="rounded-lg p-2 text-xs" style={{ background: isDark ? "rgba(255,255,255,0.05)" : "rgba(255,255,255,0.6)" }}>
                          <p className="font-semibold" style={{ color: isDark ? "#e2e8f0" : "#374151" }}>{label as string}</p>
                          <p className="mt-0.5" style={{ color: muTxt }}>{val as string}</p>
                        </div>
                      ))}
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
            <Shield className="w-3.5 h-3.5" style={{ color: muTxt }} />
            <p className="text-xs font-bold uppercase tracking-wide" style={{ color: muTxt }}>Risk Management Framework</p>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
            {[
              { label: "Stop-Loss", value: risk.stopLoss },
              { label: "Profit-Taking", value: risk.profitTaking },
              { label: "Exit Signal", value: risk.exitSignal },
              { label: "Cash Reserve", value: risk.cashReserve },
              { label: "Max per Sector", value: risk.maxPerSector },
              { label: "Max per Stock", value: risk.maxPerStock },
            ].filter(r => r.value).map((r) => (
              <div key={r.label} className="rounded-lg p-2.5" style={{ background: isDark ? "#0f172a" : "#f9fafb", border: `1px solid ${isDark ? "#334155" : "#f3f4f6"}` }}>
                <p className="text-xs font-semibold" style={{ color: isDark ? "#94a3b8" : "#4b5563" }}>{r.label}</p>
                <p className="text-xs mt-0.5 leading-relaxed" style={{ color: isDark ? "#64748b" : "#6b7280" }}>{r.value}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </Card>
  );
}

// ── Full Sector Table ──────────────────────────────────────────────────────────
function SectorTable({ sectors, isDark }: { sectors: any[]; isDark: boolean }) {
  if (!sectors?.length) return null;
  const TIER_META = getTierMeta(isDark);
  const muTxt = isDark ? "#64748b" : "#9ca3af";
  const hdrTxt = isDark ? "#94a3b8" : "#6b7280";
  const bodyTxt = isDark ? "#f1f5f9" : "#111827";
  const rowHov = isDark ? "rgba(255,255,255,0.03)" : "rgba(0,0,0,0.02)";
  const divCol = isDark ? "#1e293b" : "#f9fafb";

  return (
    <Card isDark={isDark}>
      <CardHeader isDark={isDark}>
        <div className="flex items-center gap-2">
          <Zap className="w-4 h-4 text-indigo-500" />
          <h2 className="font-bold text-sm" style={{ color: bodyTxt }}>All Sectors — Detailed Scores</h2>
        </div>
      </CardHeader>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr style={{ borderBottom: `1px solid ${divCol}` }}>
              {["Sector","Tier","Score","Day %","RS vs N50","6m ROC",">200 SMA","Focus"].map((h, i) => (
                <th key={h} className={`py-2.5 font-semibold ${i === 0 ? "text-left px-4" : i >= 4 ? "text-right px-3" : "text-center px-3"}`} style={{ color: hdrTxt }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sectors.map((s: any, i: number) => {
              const ms = s.momentum || {};
              const tm = TIER_META[ms.tier as keyof typeof TIER_META || "YELLOW"];
              return (
                <tr key={s.symbol} className="transition-colors" style={{ borderBottom: `1px solid ${divCol}` }}
                  onMouseEnter={e => (e.currentTarget.style.background = rowHov)}
                  onMouseLeave={e => (e.currentTarget.style.background = "transparent")}>
                  <td className="px-4 py-2.5">
                    <div className="flex items-center gap-2">
                      <span className="font-mono w-5 text-right" style={{ color: muTxt }}>{ms.rank || i + 1}</span>
                      <div>
                        <p className="font-semibold" style={{ color: bodyTxt }}>{s.name}</p>
                        <p style={{ color: muTxt, fontSize: "10px" }}>{s.category}</p>
                      </div>
                    </div>
                  </td>
                  <td className="px-3 py-2.5 text-center">
                    <span className="px-2 py-0.5 rounded-full text-white font-semibold" style={{ backgroundColor: tm.color, fontSize: "10px" }}>{tm.label}</span>
                  </td>
                  <td className="px-3 py-2.5 text-right font-mono font-bold" style={{ color: tm.color }}>
                    {ms.composite != null ? ms.composite.toFixed(3) : "—"}
                  </td>
                  <td className={`px-3 py-2.5 text-right font-semibold ${(s.pChange || 0) >= 0 ? "text-green-500" : "text-red-400"}`}>{fmt(s.pChange)}%</td>
                  <td className={`px-3 py-2.5 text-right ${(ms.rs || 0) >= 0 ? "text-green-500" : "text-red-400"}`}>{fmt(ms.rs)}%</td>
                  <td className={`px-3 py-2.5 text-right ${(ms.roc_6m || 0) >= 0 ? "text-green-500" : "text-red-400"}`}>{fmt(ms.roc_6m)}%</td>
                  <td className="px-3 py-2.5 text-right" style={{ color: isDark ? "#cbd5e1" : "#374151" }}>
                    {ms.pct_above_200 != null ? ms.pct_above_200.toFixed(0) + "%" : "—"}
                  </td>
                  <td className="px-3 py-2.5 text-right">
                    <span className="px-1.5 py-0.5 rounded text-white font-semibold" style={{ fontSize: "10px",
                      backgroundColor: s.focus === "STRONG BUY" ? "#15803d" : s.focus === "BUY" ? "#16a34a" : s.focus === "HOLD" ? "#9ca3af" : s.focus === "REDUCE" ? "#f97316" : "#dc2626"
                    }}>{s.focus || "HOLD"}</span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

// ── Market Breadth Bar ────────────────────────────────────────────────────────
function BreadthBar({ rotation, isDark }: { rotation: any; isDark: boolean }) {
  if (!rotation) return null;
  const TIER_META = getTierMeta(isDark);
  const mb  = rotation.marketBreadth || {};
  const adv = mb.advancing || 0;
  const dec = mb.declining || 0;
  const unc = mb.unchanged || 0;
  const total = adv + dec + unc || 1;
  const tc = rotation.tierCounts || {};
  const hdrTxt = isDark ? "#f1f5f9" : "#111827";
  const muTxt = isDark ? "#94a3b8" : "#6b7280";

  return (
    <div className="rounded-2xl border shadow-sm p-5" style={{ background: isDark ? "#1e293b" : "#fff", borderColor: isDark ? "#334155" : "#f3f4f6" }}>
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-bold text-sm" style={{ color: hdrTxt }}>Market Breadth</h3>
        <div className="flex gap-3 text-xs">
          <span className="text-green-500 font-bold">▲ {adv} rising</span>
          <span className="text-red-400 font-bold">▼ {dec} falling</span>
          <span style={{ color: muTxt }}>{unc} flat</span>
        </div>
      </div>
      <div className="flex rounded-full overflow-hidden h-2.5 mb-4">
        <div className="bg-green-500 transition-all" style={{ width: `${(adv / total) * 100}%` }} />
        <div className="transition-all" style={{ width: `${(unc / total) * 100}%`, background: isDark ? "#374151" : "#e5e7eb" }} />
        <div className="bg-red-500 transition-all" style={{ width: `${(dec / total) * 100}%` }} />
      </div>
      {Object.keys(tc).length > 0 && (
        <div className="flex flex-wrap gap-2">
          {Object.entries(tc).map(([tier, count]) => {
            const tm = TIER_META[tier as keyof typeof TIER_META];
            if (!tm) return null;
            return (
              <div key={tier} className="flex items-center gap-1.5 text-xs">
                <div className="w-2 h-2 rounded-full" style={{ backgroundColor: tm.color }} />
                <span style={{ color: muTxt }}>{tm.label}</span>
                <span className="font-bold" style={{ color: hdrTxt }}>{count as number}</span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ── Sector Heat Map ───────────────────────────────────────────────────────────

const HEATMAP_METRICS: { key: keyof SectorHeatmapItem; label: string }[] = [
  { key: "change1d",  label: "1D" },
  { key: "change1w",  label: "1W" },
  { key: "change1m",  label: "1M" },
  { key: "change1y",  label: "1Y" },
  { key: "changeYTD", label: "YTD" },
];

function heatStyle(val: number | null, isDark: boolean): { bg: string; text: string } {
  if (val == null) return { bg: isDark ? "#1e293b" : "#f1f5f9", text: isDark ? "#64748b" : "#94a3b8" };
  const abs = Math.abs(val);
  const pos = val > 0;

  // Dead-flat neutral band (< 0.12%)
  if (abs < 0.12) return { bg: isDark ? "#334155" : "#e2e8f0", text: isDark ? "#94a3b8" : "#475569" };

  if (isDark) {
    if (pos) {
      if (abs < 0.5)  return { bg: "#14532d", text: "#86efac" };   // dim green
      if (abs < 1.5)  return { bg: "#166534", text: "#86efac" };   // medium green
      if (abs < 3.0)  return { bg: "#15803d", text: "#d1fae5" };   // strong green
      return                 { bg: "#16a34a", text: "#ffffff" };    // very strong
    } else {
      if (abs < 0.5)  return { bg: "#450a0a", text: "#fca5a5" };   // dim red
      if (abs < 1.5)  return { bg: "#7f1d1d", text: "#fecaca" };   // medium red
      if (abs < 3.0)  return { bg: "#991b1b", text: "#fecaca" };   // strong red
      return                 { bg: "#b91c1c", text: "#ffffff" };    // very strong
    }
  } else {
    if (pos) {
      if (abs < 0.5)  return { bg: "#dcfce7", text: "#166534" };   // pale green
      if (abs < 1.5)  return { bg: "#86efac", text: "#14532d" };   // soft green
      if (abs < 3.0)  return { bg: "#22c55e", text: "#ffffff" };   // strong green
      return                 { bg: "#16a34a", text: "#ffffff" };    // very strong
    } else {
      if (abs < 0.5)  return { bg: "#ffe4e6", text: "#9f1239" };   // pale red
      if (abs < 1.5)  return { bg: "#fca5a5", text: "#7f1d1d" };   // soft red
      if (abs < 3.0)  return { bg: "#ef4444", text: "#ffffff" };   // strong red
      return                 { bg: "#dc2626", text: "#ffffff" };    // very strong
    }
  }
}

function SectorHeatMap({ data, isDark }: { data: SectorHeatmapItem[]; isDark: boolean }) {
  const [metric, setMetric] = useState<keyof SectorHeatmapItem>("change1d");
  const muTxt = isDark ? "#64748b" : "#94a3b8";

  return (
    <Card isDark={isDark}>
      <CardHeader isDark={isDark}>
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center gap-2">
            <BarChart2 className="w-4 h-4 text-indigo-500" />
            <span className="font-semibold text-sm" style={{ color: isDark ? "#f1f5f9" : "#111827" }}>
              Sector Heat Map
            </span>
            <span className="text-xs hidden sm:inline" style={{ color: muTxt }}>
              Color = performance intensity
            </span>
          </div>
          <div className="flex gap-1">
            {HEATMAP_METRICS.map(m => (
              <button
                key={m.key as string}
                onClick={() => setMetric(m.key)}
                className="px-2.5 py-1 rounded text-xs font-medium transition-colors"
                style={{
                  background: metric === m.key ? "#6366f1" : isDark ? "#334155" : "#f3f4f6",
                  color: metric === m.key ? "#fff" : isDark ? "#cbd5e1" : "#374151",
                }}
              >
                {m.label}
              </button>
            ))}
          </div>
        </div>
      </CardHeader>

      <div className="p-3 space-y-3">
        {/* Uniform 7-column grid — 2 clean rows for 14 sectors, no blank gaps */}
        <div className="grid gap-1.5" style={{ gridTemplateColumns: "repeat(7, 1fr)" }}>
          {data.map((sector) => {
            const val  = sector[metric] as number | null;
            const hs   = heatStyle(val, isDark);
            const name = sector.name.replace(/nifty\s+/i, "").replace("NIFTY ", "");
            const capLabel = sector.marketCap >= 10
              ? `₹${sector.marketCap}L Cr`
              : `₹${sector.marketCap}L Cr`;

            return (
              <Link key={sector.symbol} href={`/sectors/${encodeURIComponent(sector.symbol)}`}>
                <div
                  className="flex flex-col items-center justify-center rounded-xl cursor-pointer select-none transition-all duration-150 hover:scale-105 hover:shadow-lg"
                  style={{ height: 88, background: hs.bg, gap: "1px" }}
                >
                  <span
                    className="text-xs font-semibold text-center leading-tight px-1"
                    style={{ color: hs.text, maxWidth: "92%" }}
                  >
                    {name}
                  </span>
                  <span
                    className="text-sm font-bold tabular-nums"
                    style={{ color: hs.text }}
                  >
                    {val != null ? (val >= 0 ? "+" : "") + val.toFixed(2) + "%" : "—"}
                  </span>
                  <span
                    className="text-xs tabular-nums"
                    style={{ color: hs.text, opacity: 0.65, fontSize: "0.65rem" }}
                  >
                    {capLabel}
                  </span>
                </div>
              </Link>
            );
          })}
        </div>

        {/* Elegant gradient legend */}
        <div className="flex items-center justify-end gap-2">
          <span className="text-xs" style={{ color: muTxt }}>Strong Loss</span>
          <div
            className="h-2 rounded-full"
            style={{
              width: 120,
              background: isDark
                ? "linear-gradient(to right, #991b1b, #7f1d1d, #334155, #166534, #15803d)"
                : "linear-gradient(to right, #dc2626, #f87171, #e2e8f0, #4ade80, #16a34a)",
            }}
          />
          <span className="text-xs" style={{ color: muTxt }}>Strong Gain</span>
        </div>
      </div>
    </Card>
  );
}

// ── Top Movers ────────────────────────────────────────────────────────────────

function TopMovers({ isDark }: { isDark: boolean }) {
  const [period, setPeriod] = useState<"1d" | "1w" | "1m" | "1y">("1d");

  const { data: movers, isLoading } = useQuery({
    queryKey:  ["sectorTopMovers", period],
    queryFn:   () => api.sectorTopMovers(period),
    staleTime: 5 * 60 * 1000,
  });

  const hdrTxt = isDark ? "#f1f5f9" : "#111827";
  const muTxt  = isDark ? "#94a3b8" : "#6b7280";
  const borderCol = isDark ? "#334155" : "#e2e8f0";

  return (
    <Card isDark={isDark}>
      <CardHeader isDark={isDark}>
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center gap-2">
            <Zap className="w-4 h-4 text-yellow-500" />
            <span className="font-semibold text-sm" style={{ color: hdrTxt }}>Top Movers</span>
          </div>
          <div className="flex gap-1">
            {(["1d","1w","1m","1y"] as const).map(p => (
              <button key={p} onClick={() => setPeriod(p)}
                className="px-2.5 py-1 rounded text-xs font-medium transition-colors"
                style={{
                  background: period === p ? "#6366f1" : isDark ? "#334155" : "#f3f4f6",
                  color: period === p ? "#fff" : isDark ? "#cbd5e1" : "#374151",
                }}>
                {p.toUpperCase()}
              </button>
            ))}
          </div>
        </div>
      </CardHeader>
      {isLoading ? (
        <div className="p-4 space-y-2">
          {[...Array(5)].map((_, i) => <div key={i} className="h-8 animate-pulse rounded" style={{ background: isDark ? "#334155" : "#f3f4f6" }} />)}
        </div>
      ) : (
        <div className="grid md:grid-cols-2 divide-y md:divide-y-0 md:divide-x" style={{ borderColor: borderCol }}>
          <div className="p-4">
            <div className="flex items-center gap-1.5 text-xs font-semibold mb-3" style={{ color: "#16a34a" }}>
              <TrendingUp className="w-3.5 h-3.5" /> Top Gainers
            </div>
            <div className="space-y-2">
              {movers?.gainers?.map(s => {
                const val = s[`change${period === "1d" ? "1d" : period === "1w" ? "1w" : period === "1m" ? "1m" : "1y"}` as keyof SectorHeatmapItem] as number | null;
                return (
                  <Link key={s.symbol} href={`/sectors/${encodeURIComponent(s.symbol)}`}>
                    <div className="flex items-center justify-between hover:opacity-80 transition-opacity cursor-pointer">
                      <div>
                        <div className="text-xs font-semibold" style={{ color: hdrTxt }}>
                          {s.name.replace("Nifty ", "")}
                        </div>
                        <div className="text-xs" style={{ color: muTxt }}>{s.category}</div>
                      </div>
                      <div className="flex items-center gap-1 text-xs font-bold" style={{ color: "#16a34a" }}>
                        <TrendingUp className="w-3 h-3" />
                        {val != null ? (val >= 0 ? "+" : "") + val.toFixed(2) + "%" : "—"}
                      </div>
                    </div>
                  </Link>
                );
              }) ?? <p className="text-xs" style={{ color: muTxt }}>No data</p>}
            </div>
          </div>
          <div className="p-4">
            <div className="flex items-center gap-1.5 text-xs font-semibold mb-3" style={{ color: "#dc2626" }}>
              <TrendingDown className="w-3.5 h-3.5" /> Top Losers
            </div>
            <div className="space-y-2">
              {movers?.losers?.map(s => {
                const val = s[`change${period === "1d" ? "1d" : period === "1w" ? "1w" : period === "1m" ? "1m" : "1y"}` as keyof SectorHeatmapItem] as number | null;
                return (
                  <Link key={s.symbol} href={`/sectors/${encodeURIComponent(s.symbol)}`}>
                    <div className="flex items-center justify-between hover:opacity-80 transition-opacity cursor-pointer">
                      <div>
                        <div className="text-xs font-semibold" style={{ color: hdrTxt }}>
                          {s.name.replace("Nifty ", "")}
                        </div>
                        <div className="text-xs" style={{ color: muTxt }}>{s.category}</div>
                      </div>
                      <div className="flex items-center gap-1 text-xs font-bold" style={{ color: "#dc2626" }}>
                        <TrendingDown className="w-3 h-3" />
                        {val != null ? (val >= 0 ? "+" : "") + val.toFixed(2) + "%" : "—"}
                      </div>
                    </div>
                  </Link>
                );
              }) ?? <p className="text-xs" style={{ color: muTxt }}>No data</p>}
            </div>
          </div>
        </div>
      )}
    </Card>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────
export default function Sectors() {
  const { theme } = useTheme();
  const isDark = theme === "dark";

  const { data: rotation, isLoading } = useQuery({
    queryKey: ["rotation"],
    queryFn:  api.sectorRotation,
    staleTime: 4 * 60 * 1000,
  });

  // Key includes the current hour so cache auto-busts every 60 min and fetches fresh data
  const heatmapHour = new Date().toISOString().slice(0, 13);
  const { data: heatmapData, isLoading: heatmapLoading } = useQuery({
    queryKey:  ["sectorHeatmap", heatmapHour],
    queryFn:   api.sectorHeatmap,
    staleTime: 2 * 60 * 1000,
  });

  const sectors  = rotation?.sectors ?? [];
  const phase    = rotation?.economicPhase;
  const strategy = rotation?.portfolioStrategy;
  const hdrTxt = isDark ? "#f1f5f9" : "#111827";
  const muTxt  = isDark ? "#94a3b8" : "#6b7280";

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-2xl font-bold" style={{ color: hdrTxt }}>Sector Analytics</h1>
          <p className="text-sm mt-0.5" style={{ color: muTxt }}>
            Top-down investing: Market → Sector → Stock · Click any sector for a deep dive
          </p>
        </div>
        <button
          onClick={() => document.getElementById("rotation-section")?.scrollIntoView({ behavior: "smooth" })}
          className="flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg transition-colors"
          style={{ background: isDark ? "#1e293b" : "#f3f4f6", color: muTxt }}>
          Rotation Analysis <ChevronRight className="w-3 h-3" />
        </button>
      </div>

      {heatmapLoading ? (
        <div className="h-48 animate-pulse rounded-2xl" style={{ background: isDark ? "#1e293b" : "#f3f4f6" }} />
      ) : heatmapData && heatmapData.length > 0 ? (
        <SectorHeatMap data={heatmapData} isDark={isDark} />
      ) : null}

      <TopMovers isDark={isDark} />

      <div id="rotation-section">
        <h2 className="text-base font-bold mb-3" style={{ color: hdrTxt }}>Rotation & Strength Analysis</h2>
      </div>

      {isLoading ? (
        <div className="space-y-4">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-48 animate-pulse rounded-2xl" style={{ background: isDark ? "#1e293b" : "#f3f4f6" }} />
          ))}
          <p className="text-center text-sm animate-pulse" style={{ color: muTxt }}>
            Analysing all market sectors — fetching 6-month price history…
          </p>
        </div>
      ) : (
        <>
          <BreadthBar rotation={rotation} isDark={isDark} />
          <EconomicPhasePanel phase={phase} isDark={isDark} />
          <StrengthMatrix sectors={sectors} isDark={isDark} />
          <PortfolioPanel strategy={strategy} isDark={isDark} />
          <SectorTable sectors={sectors} isDark={isDark} />
          {rotation && (
            <p className="text-center text-xs pb-2" style={{ color: muTxt }}>
              Scores updated at {new Date(rotation.timestamp).toLocaleString("en-IN")} ·
              Refreshes every 4 hours · Score formula: Market Strength 40% | Stocks Above 200-day Average 25% | 6-Month Price Change 20% | Volume 15%
            </p>
          )}
        </>
      )}
    </div>
  );
}
