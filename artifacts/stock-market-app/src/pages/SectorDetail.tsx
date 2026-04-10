import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useParams, Link } from "wouter";
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis,
  CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine, ScatterChart, Scatter,
} from "recharts";
import {
  ArrowLeft, TrendingUp, TrendingDown, Info, BarChart2,
  DollarSign, Activity, Shield, Users, ChevronUp, ChevronDown, ChevronsUpDown,
} from "lucide-react";
import { api, SectorDetailData, ConstituentStock } from "@/lib/api";
import { useTheme } from "@/context/ThemeContext";
import ChartButton from "@/components/ChartButton";

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmt(n: number | null | undefined, dec = 2, suffix = "") {
  if (n == null) return "—";
  return n.toFixed(dec) + suffix;
}

function fmtPct(n: number | null | undefined) {
  if (n == null) return "—";
  return (n >= 0 ? "+" : "") + n.toFixed(2) + "%";
}

function fmtCr(n: number | null | undefined) {
  if (n == null) return "—";
  if (n >= 1_00_000) return "₹" + (n / 1_00_000).toFixed(1) + "L Cr";
  if (n >= 100) return "₹" + (n).toFixed(0) + " Cr";
  return "₹" + n.toFixed(2);
}

function fmtMarketCap(cap: number | null | undefined) {
  if (cap == null) return "—";
  // cap is in ₹ Lakh Crore
  return "₹" + cap.toFixed(1) + " L Cr";
}

function colorForPct(val: number | null) {
  if (val == null) return "#6b7280";
  if (val >= 2)  return "#16a34a";
  if (val >= 0)  return "#4ade80";
  if (val >= -2) return "#f87171";
  return "#dc2626";
}

function TrendBadge({ val }: { val: number | null }) {
  if (val == null) return <span className="text-sm" style={{ color: "#9ca3af" }}>—</span>;
  const color = colorForPct(val);
  const Icon = val >= 0 ? TrendingUp : TrendingDown;
  return (
    <span className="flex items-center gap-1 text-sm font-semibold" style={{ color }}>
      <Icon className="w-3.5 h-3.5" />
      {fmtPct(val)}
    </span>
  );
}

function InfoTip({ text }: { text: string }) {
  return (
    <span className="group relative inline-block ml-1 cursor-help">
      <Info className="w-3.5 h-3.5 text-gray-400" />
      <span className="absolute left-1/2 -translate-x-1/2 bottom-full mb-2 px-2 py-1 rounded text-xs w-56
                       bg-gray-900 text-white opacity-0 group-hover:opacity-100 transition-opacity z-50 pointer-events-none">
        {text}
      </span>
    </span>
  );
}

const TABS = ["Overview", "Performance", "Valuation", "Profitability", "Financial Health", "Constituents"] as const;
type Tab = typeof TABS[number];

// ── Metric card ───────────────────────────────────────────────────────────────

function MetricCard({
  label, value, sub, tip, isDark,
}: {
  label: string; value: string; sub?: string; tip?: string; isDark: boolean;
}) {
  return (
    <div className="rounded-xl p-4 border" style={{
      background: isDark ? "#1e293b" : "#f8fafc",
      borderColor: isDark ? "#334155" : "#e2e8f0",
    }}>
      <div className="flex items-center gap-1 text-xs mb-1" style={{ color: isDark ? "#94a3b8" : "#6b7280" }}>
        {label}
        {tip && <InfoTip text={tip} />}
      </div>
      <div className="text-xl font-bold" style={{ color: isDark ? "#f1f5f9" : "#111827" }}>{value}</div>
      {sub && <div className="text-xs mt-0.5" style={{ color: isDark ? "#64748b" : "#9ca3af" }}>{sub}</div>}
    </div>
  );
}

// ── Overview Tab ──────────────────────────────────────────────────────────────

function OverviewTab({
  data, isDark, period, onPeriodChange,
}: {
  data: SectorDetailData;
  isDark: boolean;
  period: "3mo" | "6mo" | "1y" | "5y";
  onPeriodChange: (p: "3mo" | "6mo" | "1y" | "5y") => void;
}) {
  const rs = data.relativeStrength ?? [];
  const gridCol = isDark ? "#334155" : "#f1f5f9";
  const axisCol = isDark ? "#94a3b8" : "#6b7280";

  // Sub-sample for display
  const displayData = useMemo(() => {
    if (rs.length <= 252) return rs;
    const step = Math.ceil(rs.length / 252);
    return rs.filter((_, i) => i % step === 0 || i === rs.length - 1);
  }, [rs]);

  const last = displayData[displayData.length - 1];
  const first = displayData[0];
  const rsChange = last && first ? last.ratio - 100 : null;

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <MetricCard
          label="Market Cap (Proxy)"
          value={fmtMarketCap(data.marketCap)}
          tip="Approximate aggregate market cap of the sector"
          isDark={isDark}
        />
        <MetricCard
          label="RS vs Nifty 50"
          value={rsChange != null ? fmtPct(rsChange) : "—"}
          sub="over the period"
          tip="Relative Strength: how the sector has performed versus Nifty 50. Above 100 = outperforming."
          isDark={isDark}
        />
        <MetricCard
          label="Advances"
          value={String(data.constituents?.filter(c => (c.change1d ?? 0) > 0).length ?? "—")}
          sub="stocks up today"
          isDark={isDark}
        />
        <MetricCard
          label="Declines"
          value={String(data.constituents?.filter(c => (c.change1d ?? 0) < 0).length ?? "—")}
          sub="stocks down today"
          isDark={isDark}
        />
      </div>

      <div className="rounded-xl border p-4" style={{
        background: isDark ? "#1e293b" : "#fff",
        borderColor: isDark ? "#334155" : "#e2e8f0",
      }}>
        <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
          <div>
            <h3 className="font-semibold text-sm" style={{ color: isDark ? "#f1f5f9" : "#111827" }}>
              Relative Strength vs Nifty 50
            </h3>
            <p className="text-xs mt-0.5" style={{ color: isDark ? "#94a3b8" : "#6b7280" }}>
              Above 100 = outperforming · Below 100 = underperforming
            </p>
          </div>
          <div className="flex gap-1">
            {(["3mo","6mo","1y","5y"] as const).map(p => (
              <button
                key={p}
                onClick={() => onPeriodChange(p)}
                className="px-2.5 py-1 rounded text-xs font-medium transition-colors"
                style={{
                  background: period === p ? "#6366f1" : isDark ? "#334155" : "#f3f4f6",
                  color: period === p ? "#fff" : isDark ? "#cbd5e1" : "#374151",
                }}
              >
                {p.toUpperCase()}
              </button>
            ))}
          </div>
        </div>
        {displayData.length > 0 ? (
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={displayData} margin={{ top: 5, right: 10, left: -10, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={gridCol} />
              <XAxis
                dataKey="date"
                tick={{ fill: axisCol, fontSize: 10 }}
                tickFormatter={d => d.slice(2, 7)}
                interval="preserveStartEnd"
              />
              <YAxis tick={{ fill: axisCol, fontSize: 10 }} domain={["auto", "auto"]} />
              <ReferenceLine y={100} stroke="#6366f1" strokeDasharray="4 4" label={{ value: "Benchmark", fill: axisCol, fontSize: 9 }} />
              <Tooltip
                contentStyle={{ background: isDark ? "#1e293b" : "#fff", border: `1px solid ${isDark ? "#334155" : "#e2e8f0"}`, borderRadius: 8 }}
                labelStyle={{ color: isDark ? "#f1f5f9" : "#111827", fontSize: 11 }}
                formatter={(v: number) => [v.toFixed(2), "RS Ratio"]}
              />
              <Line
                type="monotone"
                dataKey="ratio"
                stroke="#6366f1"
                dot={false}
                strokeWidth={2}
              />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <div className="h-64 flex items-center justify-center text-sm" style={{ color: isDark ? "#64748b" : "#9ca3af" }}>
            Historical data unavailable for this sector
          </div>
        )}
      </div>
    </div>
  );
}

// ── Performance Tab ───────────────────────────────────────────────────────────

function PerformanceTab({ data, isDark }: { data: SectorDetailData; isDark: boolean }) {
  const p = data.performance ?? {};
  const periods = [
    { key: "1W", label: "1 Week" },
    { key: "1M", label: "1 Month" },
    { key: "3M", label: "3 Months" },
    { key: "6M", label: "6 Months" },
    { key: "1Y", label: "1 Year" },
    { key: "YTD", label: "YTD" },
  ];

  const hdrTxt = isDark ? "#f1f5f9" : "#111827";
  const muTxt  = isDark ? "#94a3b8" : "#6b7280";
  const rowBg  = isDark ? "#1e293b" : "#fff";
  const borderCol = isDark ? "#334155" : "#e2e8f0";

  return (
    <div className="space-y-5">
      <div className="rounded-xl border overflow-hidden" style={{ borderColor: borderCol }}>
        <div className="px-4 py-3 border-b" style={{ background: isDark ? "#0f172a" : "#f8fafc", borderColor: borderCol }}>
          <h3 className="font-semibold text-sm" style={{ color: hdrTxt }}>Price Performance</h3>
        </div>
        <div>
          {periods.map((pr, i) => (
            <div key={pr.key}
              className="flex items-center justify-between px-4 py-3"
              style={{
                background: rowBg,
                borderBottom: i < periods.length - 1 ? `1px solid ${borderCol}` : "none",
              }}>
              <span className="text-sm" style={{ color: muTxt }}>{pr.label}</span>
              <TrendBadge val={p[pr.key] ?? null} />
            </div>
          ))}
        </div>
      </div>

      <div className="grid md:grid-cols-2 gap-4">
        <div className="rounded-xl border p-4" style={{ background: isDark ? "#1e293b" : "#fff", borderColor: isDark ? "#334155" : "#e2e8f0" }}>
          <h3 className="font-semibold text-sm mb-3 flex items-center gap-1.5" style={{ color: "#16a34a" }}>
            <TrendingUp className="w-4 h-4" /> Top Gainers Today
          </h3>
          <div className="space-y-2">
            {data.topGainers?.length ? data.topGainers.map(s => (
              <div key={s.symbol} className="flex items-center justify-between text-sm">
                <span className="font-medium" style={{ color: hdrTxt }}>{s.symbol.replace(".NS", "")}</span>
                <TrendBadge val={s.change1d} />
              </div>
            )) : <p className="text-xs" style={{ color: muTxt }}>No data available</p>}
          </div>
        </div>
        <div className="rounded-xl border p-4" style={{ background: isDark ? "#1e293b" : "#fff", borderColor: isDark ? "#334155" : "#e2e8f0" }}>
          <h3 className="font-semibold text-sm mb-3 flex items-center gap-1.5" style={{ color: "#dc2626" }}>
            <TrendingDown className="w-4 h-4" /> Top Losers Today
          </h3>
          <div className="space-y-2">
            {data.topLosers?.length ? data.topLosers.map(s => (
              <div key={s.symbol} className="flex items-center justify-between text-sm">
                <span className="font-medium" style={{ color: hdrTxt }}>{s.symbol.replace(".NS", "")}</span>
                <TrendBadge val={s.change1d} />
              </div>
            )) : <p className="text-xs" style={{ color: muTxt }}>No data available</p>}
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Valuation Tab ─────────────────────────────────────────────────────────────

function ValuationTab({ data, isDark }: { data: SectorDetailData; isDark: boolean }) {
  const [mode, setMode] = useState<"cap" | "equal">("cap");
  const v = data.valuation;
  const hdrTxt = isDark ? "#f1f5f9" : "#111827";

  const metrics = [
    {
      key: "pe", label: "P/E Ratio",
      val: mode === "cap" ? v?.pe : v?.pe_equal,
      tip: "Price-to-Earnings: Sum of Market Caps / Sum of Net Earnings. High P/E suggests high growth expectations but is less reliable when earnings are negative.",
    },
    {
      key: "pb", label: "P/B Ratio",
      val: mode === "cap" ? v?.pb : v?.pb_equal,
      tip: "Price-to-Book: Sum of Market Caps / Sum of Book Values. Most useful for asset-heavy sectors (Financials, Industrials). Below 1 may indicate undervaluation.",
    },
    {
      key: "ps", label: "P/S Ratio",
      val: mode === "cap" ? v?.ps : v?.ps_equal,
      tip: "Price-to-Sales: Sum of Market Caps / Sum of Total Revenues. Key metric for sectors with unprofitable companies (e.g. early-stage tech).",
    },
    {
      key: "evEbitda", label: "EV/EBITDA",
      val: mode === "cap" ? v?.evEbitda : v?.evEbitda_equal,
      tip: "Enterprise Value / EBITDA. Capital-structure-neutral metric useful for comparing sectors with different debt levels.",
    },
  ];

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-2">
        <span className="text-xs" style={{ color: isDark ? "#94a3b8" : "#6b7280" }}>Weighting method:</span>
        {([["cap", "Market Cap Weighted"], ["equal", "Equal Weighted"]] as const).map(([k, l]) => (
          <button
            key={k}
            onClick={() => setMode(k)}
            className="px-3 py-1 rounded-full text-xs font-medium transition-colors"
            style={{
              background: mode === k ? "#6366f1" : isDark ? "#334155" : "#f3f4f6",
              color: mode === k ? "#fff" : isDark ? "#cbd5e1" : "#374151",
            }}
          >
            {l}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {metrics.map(m => (
          <div key={m.key} className="rounded-xl border p-4" style={{
            background: isDark ? "#1e293b" : "#f8fafc",
            borderColor: isDark ? "#334155" : "#e2e8f0",
          }}>
            <div className="flex items-center gap-1 text-xs mb-1" style={{ color: isDark ? "#94a3b8" : "#6b7280" }}>
              {m.label}
              <InfoTip text={m.tip} />
            </div>
            <div className="text-2xl font-bold" style={{ color: hdrTxt }}>
              {m.val != null ? m.val.toFixed(1) + "×" : "—"}
            </div>
          </div>
        ))}
      </div>

      {v && (
        <div className="rounded-xl border p-4" style={{ background: isDark ? "#1e293b" : "#f8fafc", borderColor: isDark ? "#334155" : "#e2e8f0" }}>
          <p className="text-xs" style={{ color: isDark ? "#94a3b8" : "#6b7280" }}>
            Based on {v.sampleSize} constituent stocks · {mode === "cap" ? "Market-capitalization weighted" : "Equal weighted (average across all stocks)"} · Data from Yahoo Finance
          </p>
        </div>
      )}

      {data.constituents && data.constituents.length > 0 && (
        <div className="rounded-xl border p-4" style={{ background: isDark ? "#1e293b" : "#fff", borderColor: isDark ? "#334155" : "#e2e8f0" }}>
          <h3 className="font-semibold text-sm mb-3" style={{ color: hdrTxt }}>
            Valuation by Stock (P/E vs P/B)
          </h3>
          <ResponsiveContainer width="100%" height={220}>
            <ScatterChart margin={{ top: 5, right: 10, left: -10, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={isDark ? "#334155" : "#f1f5f9"} />
              <XAxis
                dataKey="pb" name="P/B"
                tick={{ fill: isDark ? "#94a3b8" : "#6b7280", fontSize: 10 }}
                label={{ value: "P/B", position: "insideBottom", offset: -2, fill: isDark ? "#94a3b8" : "#6b7280", fontSize: 10 }}
              />
              <YAxis
                dataKey="pe" name="P/E"
                tick={{ fill: isDark ? "#94a3b8" : "#6b7280", fontSize: 10 }}
                label={{ value: "P/E", angle: -90, position: "insideLeft", fill: isDark ? "#94a3b8" : "#6b7280", fontSize: 10 }}
              />
              <Tooltip
                contentStyle={{ background: isDark ? "#1e293b" : "#fff", border: `1px solid ${isDark ? "#334155" : "#e2e8f0"}`, borderRadius: 8 }}
                formatter={(v: number, name: string) => [v.toFixed(2) + "×", name]}
                labelFormatter={(_, payload) => payload?.[0]?.payload?.symbol?.replace(".NS", "") ?? ""}
              />
              <Scatter
                data={data.constituents.filter(c => c.pe != null && c.pb != null && c.pe > 0 && c.pb > 0 && c.pe < 200)}
                fill="#6366f1"
                fillOpacity={0.7}
              />
            </ScatterChart>
          </ResponsiveContainer>
          <p className="text-xs mt-1 text-center" style={{ color: isDark ? "#64748b" : "#9ca3af" }}>
            Scatter: P/B (x-axis) vs P/E (y-axis) · Each dot = one constituent stock
          </p>
        </div>
      )}
    </div>
  );
}

// ── Profitability Tab ─────────────────────────────────────────────────────────

function ProfitabilityTab({ data, isDark }: { data: SectorDetailData; isDark: boolean }) {
  const p = data.profitability;
  const hdrTxt = isDark ? "#f1f5f9" : "#111827";
  const muTxt  = isDark ? "#94a3b8" : "#6b7280";

  const barData = data.constituents?.filter(c => c.roe != null).map(c => ({
    name:   c.symbol.replace(".NS", ""),
    roe:    c.roe ? +(c.roe * 100).toFixed(1) : 0,
    margin: c.pe ? +(1 / c.pe * 100).toFixed(1) : 0,
  })) ?? [];

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="rounded-xl border p-4" style={{ background: isDark ? "#1e293b" : "#f8fafc", borderColor: isDark ? "#334155" : "#e2e8f0" }}>
          <div className="flex items-center gap-1 text-xs mb-1" style={{ color: muTxt }}>
            Aggregate Net Profit Margin
            <InfoTip text="Sum of Net Incomes / Sum of Revenues. Declining margins signal rising competition or costs." />
          </div>
          <div className="text-3xl font-bold" style={{ color: hdrTxt }}>
            {p?.netMargin != null ? p.netMargin.toFixed(1) + "%" : "—"}
          </div>
          <div className="text-xs mt-1" style={{ color: muTxt }}>
            Market-cap weighted · {p?.sampleSize ?? 0} stocks
          </div>
        </div>
        <div className="rounded-xl border p-4" style={{ background: isDark ? "#1e293b" : "#f8fafc", borderColor: isDark ? "#334155" : "#e2e8f0" }}>
          <div className="flex items-center gap-1 text-xs mb-1" style={{ color: muTxt }}>
            Aggregate ROE
            <InfoTip text="Return on Equity: Sum of Net Incomes / Sum of Shareholder Equity. High ROE indicates efficiency — cross-check D/E to ensure it's not just from high leverage." />
          </div>
          <div className="text-3xl font-bold" style={{ color: hdrTxt }}>
            {p?.roe != null ? p.roe.toFixed(1) + "%" : "—"}
          </div>
          <div className="text-xs mt-1" style={{ color: muTxt }}>
            Market-cap weighted · {p?.sampleSize ?? 0} stocks
          </div>
        </div>
      </div>

      {barData.length > 0 && (
        <div className="rounded-xl border p-4" style={{ background: isDark ? "#1e293b" : "#fff", borderColor: isDark ? "#334155" : "#e2e8f0" }}>
          <h3 className="font-semibold text-sm mb-3" style={{ color: hdrTxt }}>ROE by Constituent Stock</h3>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={barData} margin={{ top: 5, right: 10, left: -10, bottom: 20 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={isDark ? "#334155" : "#f1f5f9"} />
              <XAxis dataKey="name" tick={{ fill: isDark ? "#94a3b8" : "#6b7280", fontSize: 9 }} angle={-30} textAnchor="end" />
              <YAxis tick={{ fill: isDark ? "#94a3b8" : "#6b7280", fontSize: 10 }} />
              <Tooltip
                contentStyle={{ background: isDark ? "#1e293b" : "#fff", border: `1px solid ${isDark ? "#334155" : "#e2e8f0"}`, borderRadius: 8 }}
                formatter={(v: number) => [v.toFixed(1) + "%", "ROE"]}
              />
              <Bar dataKey="roe" fill="#6366f1" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}

// ── Financial Health Tab ──────────────────────────────────────────────────────

function FinancialHealthTab({ data, isDark }: { data: SectorDetailData; isDark: boolean }) {
  const h = data.financialHealth;
  const hdrTxt = isDark ? "#f1f5f9" : "#111827";
  const muTxt  = isDark ? "#94a3b8" : "#6b7280";

  const deData = data.constituents?.filter(c => c.debtToEquity != null && c.debtToEquity >= 0)
    .map(c => ({ name: c.symbol.replace(".NS", ""), de: +(c.debtToEquity!).toFixed(2) }))
    .sort((a, b) => b.de - a.de) ?? [];

  return (
    <div className="space-y-5">
      <div className="rounded-xl border p-5" style={{ background: isDark ? "#1e293b" : "#f8fafc", borderColor: isDark ? "#334155" : "#e2e8f0" }}>
        <div className="flex items-center gap-1 text-xs mb-1" style={{ color: muTxt }}>
          Aggregate Debt-to-Equity Ratio
          <InfoTip text="Sum of Total Debts / Sum of Shareholder Equity. What's 'high' depends on the sector — Financials normally run high D/E. A sharp upward trend is a red flag." />
        </div>
        <div className="text-4xl font-bold" style={{ color: hdrTxt }}>
          {h?.debtToEquity != null ? h.debtToEquity.toFixed(2) + "×" : "—"}
        </div>
        <div className="text-xs mt-1" style={{ color: muTxt }}>
          Average across {h?.sampleSize ?? 0} stocks with available data
        </div>
      </div>

      {deData.length > 0 && (
        <div className="rounded-xl border p-4" style={{ background: isDark ? "#1e293b" : "#fff", borderColor: isDark ? "#334155" : "#e2e8f0" }}>
          <h3 className="font-semibold text-sm mb-3" style={{ color: hdrTxt }}>D/E by Constituent Stock</h3>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={deData} layout="vertical" margin={{ top: 0, right: 20, left: 20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={isDark ? "#334155" : "#f1f5f9"} />
              <XAxis type="number" tick={{ fill: isDark ? "#94a3b8" : "#6b7280", fontSize: 10 }} />
              <YAxis type="category" dataKey="name" tick={{ fill: isDark ? "#94a3b8" : "#6b7280", fontSize: 10 }} width={70} />
              <Tooltip
                contentStyle={{ background: isDark ? "#1e293b" : "#fff", border: `1px solid ${isDark ? "#334155" : "#e2e8f0"}`, borderRadius: 8 }}
                formatter={(v: number) => [v.toFixed(2) + "×", "D/E"]}
              />
              <Bar dataKey="de" fill="#f59e0b" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}

// ── Constituents Tab ──────────────────────────────────────────────────────────

type SortKey = keyof ConstituentStock;
function ConstituentTab({ data, isDark }: { data: SectorDetailData; isDark: boolean }) {
  const [sortKey, setSortKey] = useState<SortKey>("marketCap");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  const hdrTxt = isDark ? "#f1f5f9" : "#111827";
  const muTxt  = isDark ? "#94a3b8" : "#6b7280";
  const borderCol = isDark ? "#334155" : "#e2e8f0";

  const sorted = useMemo(() => {
    const rows = [...(data.constituents ?? [])];
    rows.sort((a, b) => {
      const av = a[sortKey] as number | null ?? -Infinity;
      const bv = b[sortKey] as number | null ?? -Infinity;
      return sortDir === "desc" ? (bv as number) - (av as number) : (av as number) - (bv as number);
    });
    return rows;
  }, [data.constituents, sortKey, sortDir]);

  function toggleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir(d => d === "desc" ? "asc" : "desc");
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  }

  function SortIcon({ k }: { k: SortKey }) {
    if (sortKey !== k) return <ChevronsUpDown className="w-3 h-3 inline ml-0.5 opacity-40" />;
    return sortDir === "desc"
      ? <ChevronDown className="w-3 h-3 inline ml-0.5" />
      : <ChevronUp className="w-3 h-3 inline ml-0.5" />;
  }

  const cols: { key: SortKey; label: string; fmt: (v: ConstituentStock) => string }[] = [
    { key: "name",          label: "Stock",          fmt: r => r.symbol.replace(".NS", "") },
    { key: "price",         label: "Price",          fmt: r => r.price != null ? "₹" + r.price.toLocaleString("en-IN", { maximumFractionDigits: 1 }) : "—" },
    { key: "change1d",      label: "1D %",           fmt: r => fmtPct(r.change1d) },
    { key: "marketCap",     label: "Mkt Cap",        fmt: r => fmtCr(r.marketCap != null ? r.marketCap / 1e7 : null) },
    { key: "pe",            label: "P/E",            fmt: r => fmt(r.pe, 1, "×") },
    { key: "pb",            label: "P/B",            fmt: r => fmt(r.pb, 1, "×") },
    { key: "evEbitda",      label: "EV/EBITDA",      fmt: r => fmt(r.evEbitda, 1, "×") },
    { key: "roe",           label: "ROE",            fmt: r => r.roe != null ? (r.roe * 100).toFixed(1) + "%" : "—" },
    { key: "debtToEquity",  label: "D/E",            fmt: r => fmt(r.debtToEquity, 2, "×") },
    { key: "dividendYield", label: "Div Yield",      fmt: r => r.dividendYield != null ? (r.dividendYield * 100).toFixed(2) + "%" : "—" },
  ];

  return (
    <div className="rounded-xl border overflow-hidden" style={{ borderColor: borderCol }}>
      <div className="overflow-x-auto">
        <table className="w-full text-xs min-w-[720px]">
          <thead>
            <tr style={{ background: isDark ? "#0f172a" : "#f8fafc", borderBottom: `1px solid ${borderCol}` }}>
              {cols.map(c => (
                <th
                  key={c.key}
                  className="px-3 py-2.5 text-left font-medium cursor-pointer select-none whitespace-nowrap hover:opacity-80 transition-opacity"
                  style={{ color: muTxt }}
                  onClick={() => toggleSort(c.key)}
                >
                  {c.label}<SortIcon k={c.key} />
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sorted.map((row, i) => (
              <tr key={row.symbol}
                style={{
                  background: isDark ? (i % 2 === 0 ? "#1e293b" : "#0f172a") : (i % 2 === 0 ? "#fff" : "#f8fafc"),
                  borderBottom: `1px solid ${borderCol}`,
                }}>
                {cols.map(c => {
                  const isChange = c.key === "change1d";
                  const val = isChange ? row.change1d : null;
                  return (
                    <td key={c.key} className="px-3 py-2 whitespace-nowrap"
                      style={{ color: isChange ? colorForPct(val) : hdrTxt }}>
                      {c.key === "name" ? (
                        <span className="flex items-center gap-0.5">
                          {c.fmt(row)}
                          <ChartButton symbol={row.symbol} />
                        </span>
                      ) : c.fmt(row)}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function SectorDetail() {
  const { sectorId } = useParams<{ sectorId: string }>();
  const { theme } = useTheme();
  const isDark = theme === "dark";
  const [activeTab, setActiveTab] = useState<Tab>("Overview");
  const [period, setPeriod] = useState<"3mo" | "6mo" | "1y" | "5y">("1y");

  const { data, isLoading, error } = useQuery({
    queryKey:  ["sectorDetail", sectorId, period],
    queryFn:   () => api.sectorDetail(sectorId ?? "", period),
    staleTime: 15 * 60 * 1000,
    enabled:   !!sectorId,
  });

  const hdrTxt = isDark ? "#f1f5f9" : "#111827";
  const muTxt  = isDark ? "#94a3b8" : "#6b7280";
  const bg     = isDark ? "#0f172a" : "#f8fafc";

  const TAB_ICONS: Record<Tab, React.ReactNode> = {
    "Overview":        <Activity className="w-3.5 h-3.5" />,
    "Performance":     <TrendingUp className="w-3.5 h-3.5" />,
    "Valuation":       <DollarSign className="w-3.5 h-3.5" />,
    "Profitability":   <BarChart2 className="w-3.5 h-3.5" />,
    "Financial Health":<Shield className="w-3.5 h-3.5" />,
    "Constituents":    <Users className="w-3.5 h-3.5" />,
  };

  return (
    <div className="space-y-5 min-h-screen" style={{ background: bg }}>
      <div className="flex items-center gap-3">
        <Link href="/sectors">
          <button className="flex items-center gap-1.5 text-sm font-medium rounded-lg px-3 py-1.5 transition-colors"
            style={{ background: isDark ? "#1e293b" : "#fff", color: muTxt, border: `1px solid ${isDark ? "#334155" : "#e2e8f0"}` }}>
            <ArrowLeft className="w-4 h-4" /> Back to Sectors
          </button>
        </Link>
      </div>

      {isLoading ? (
        <div className="space-y-4">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-32 animate-pulse rounded-2xl" style={{ background: isDark ? "#1e293b" : "#f3f4f6" }} />
          ))}
          <p className="text-center text-sm animate-pulse" style={{ color: muTxt }}>
            Fetching sector data — loading price history and fundamentals…
          </p>
        </div>
      ) : error || !data ? (
        <div className="rounded-2xl border p-8 text-center" style={{ background: isDark ? "#1e293b" : "#fff", borderColor: isDark ? "#334155" : "#e2e8f0" }}>
          <p className="font-semibold" style={{ color: hdrTxt }}>Sector not found</p>
          <p className="text-sm mt-1" style={{ color: muTxt }}>Symbol: {sectorId}</p>
        </div>
      ) : (
        <>
          <div className="rounded-2xl border p-5" style={{ background: isDark ? "#1e293b" : "#fff", borderColor: isDark ? "#334155" : "#e2e8f0" }}>
            <div className="flex items-start justify-between flex-wrap gap-3">
              <div>
                <h1 className="text-2xl font-bold flex items-center gap-1" style={{ color: hdrTxt }}>
                  {data.name}
                  <ChartButton symbol={data.symbol} />
                </h1>
                <p className="text-sm mt-0.5" style={{ color: muTxt }}>
                  Sector Deep-Dive · Top-down analysis from macro to individual stocks
                </p>
              </div>
              <div className="text-right">
                <div className="text-lg font-bold" style={{ color: hdrTxt }}>
                  {fmtMarketCap(data.marketCap)}
                </div>
                <div className="text-xs" style={{ color: muTxt }}>Approx. Market Cap</div>
              </div>
            </div>
          </div>

          <div className="flex gap-1 overflow-x-auto pb-1 scrollbar-hide">
            {TABS.map(t => (
              <button
                key={t}
                onClick={() => setActiveTab(t)}
                className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium whitespace-nowrap transition-colors"
                style={{
                  background: activeTab === t ? "#6366f1" : isDark ? "#1e293b" : "#fff",
                  color:      activeTab === t ? "#fff"    : muTxt,
                  border:     `1px solid ${activeTab === t ? "#6366f1" : isDark ? "#334155" : "#e2e8f0"}`,
                }}
              >
                {TAB_ICONS[t]}
                {t}
              </button>
            ))}
          </div>

          <div>
            {activeTab === "Overview"         && <OverviewTab data={data} isDark={isDark} period={period} onPeriodChange={setPeriod} />}
            {activeTab === "Performance"      && <PerformanceTab data={data} isDark={isDark} />}
            {activeTab === "Valuation"        && <ValuationTab data={data} isDark={isDark} />}
            {activeTab === "Profitability"    && <ProfitabilityTab data={data} isDark={isDark} />}
            {activeTab === "Financial Health" && <FinancialHealthTab data={data} isDark={isDark} />}
            {activeTab === "Constituents"     && <ConstituentTab data={data} isDark={isDark} />}
          </div>
        </>
      )}
    </div>
  );
}
