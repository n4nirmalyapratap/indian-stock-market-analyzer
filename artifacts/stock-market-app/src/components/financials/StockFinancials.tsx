import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ComposedChart, Line, Cell,
} from "recharts";
import { api } from "@/lib/api";
import type { IncomeRow, BalanceSheetRow, CashFlowRow, DividendRow, EpsRow } from "@/lib/api";
import { TrendingUp, TrendingDown, Minus } from "lucide-react";

// ── Formatters ────────────────────────────────────────────────────────────────

function fCr(val: number | null | undefined, short = false): string {
  if (val == null) return "—";
  if (short) {
    if (Math.abs(val) >= 100_000) return `${(val / 100_000).toFixed(1)}L Cr`;
    if (Math.abs(val) >= 1_000)   return `${(val / 1_000).toFixed(1)}K Cr`;
    return `${val.toFixed(0)} Cr`;
  }
  return `₹${val.toLocaleString("en-IN", { minimumFractionDigits: 0, maximumFractionDigits: 0 })} Cr`;
}

function fNum(val: number | null | undefined, suffix = "", decimals = 2): string {
  if (val == null) return "—";
  return `${val.toFixed(decimals)}${suffix}`;
}

function fMCap(val: number | null | undefined): string {
  if (val == null) return "—";
  const cr = val / 1e7;
  if (cr >= 100_000) return `₹${(cr / 100_000).toFixed(2)} L Cr`;
  if (cr >= 1_000)   return `₹${(cr / 1_000).toFixed(2)} K Cr`;
  return `₹${cr.toFixed(0)} Cr`;
}

function shortDate(date: string): string {
  const d = new Date(date);
  return `${d.toLocaleString("en-IN", { month: "short" })} '${String(d.getFullYear()).slice(2)}`;
}

function yrDate(date: string): string {
  return `FY${String(new Date(date).getFullYear()).slice(2)}`;
}

function growth(curr: number | null, prev: number | null): number | null {
  if (curr == null || prev == null || prev === 0) return null;
  return ((curr - prev) / Math.abs(prev)) * 100;
}

// ── Shared UI primitives ──────────────────────────────────────────────────────

function MetricCard({ label, value, sub, positive }: {
  label: string; value: string; sub?: string; positive?: boolean;
}) {
  return (
    <div className="bg-white rounded-xl border border-gray-100 p-4 flex flex-col gap-1">
      <span className="text-xs text-gray-500 font-medium uppercase tracking-wide">{label}</span>
      <span className="text-lg font-bold text-gray-900">{value}</span>
      {sub != null && (
        <span className={`text-xs font-medium ${positive === true ? "text-emerald-600" : positive === false ? "text-red-500" : "text-gray-400"}`}>
          {sub}
        </span>
      )}
    </div>
  );
}

function SectionHeader({ title, sub }: { title: string; sub?: string }) {
  return (
    <div className="mb-3">
      <h3 className="text-sm font-semibold text-gray-700">{title}</h3>
      {sub && <p className="text-xs text-gray-400">{sub}</p>}
    </div>
  );
}

function StatRow({ label, value, positive }: { label: string; value: string; positive?: boolean }) {
  return (
    <div className="flex justify-between items-center py-2.5 border-b border-gray-50 last:border-0">
      <span className="text-sm text-gray-500">{label}</span>
      <span className={`text-sm font-semibold ${positive === true ? "text-emerald-600" : positive === false ? "text-red-500" : "text-gray-900"}`}>
        {value}
      </span>
    </div>
  );
}

function PeriodToggle({ period, onChange }: { period: "annual" | "quarterly"; onChange: (v: "annual" | "quarterly") => void }) {
  return (
    <div className="flex bg-gray-100 rounded-lg p-0.5 text-xs font-medium">
      {(["annual", "quarterly"] as const).map(p => (
        <button
          key={p}
          onClick={() => onChange(p)}
          className={`px-3 py-1.5 rounded-md transition-all ${period === p ? "bg-white text-indigo-700 shadow-sm" : "text-gray-500 hover:text-gray-700"}`}
        >
          {p === "annual" ? "Annual" : "Quarterly"}
        </button>
      ))}
    </div>
  );
}

const CHART_COLORS = {
  revenue:  "#6366f1",
  gross:    "#8b5cf6",
  opIncome: "#06b6d4",
  net:      "#10b981",
  ebitda:   "#f59e0b",
  assets:   "#6366f1",
  debt:     "#ef4444",
  equity:   "#10b981",
  opCF:     "#6366f1",
  freeCF:   "#10b981",
  capex:    "#ef4444",
  div:      "#f59e0b",
  eps:      "#6366f1",
};

const CustomTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-gray-900 text-white text-xs rounded-lg px-3 py-2 shadow-xl border border-gray-700">
      <p className="font-semibold mb-1 text-gray-300">{label}</p>
      {payload.map((p: any, i: number) => (
        <p key={i} style={{ color: p.color }}>
          {p.name}: {typeof p.value === "number" && Math.abs(p.value) > 10 ? fCr(p.value) : fNum(p.value)}
        </p>
      ))}
    </div>
  );
};

// ── Tab components ────────────────────────────────────────────────────────────

function OverviewTab({ ov, income }: { ov: any; income: IncomeRow[] }) {
  const latest  = income[income.length - 1];
  const prev    = income[income.length - 2];
  const revGr   = growth(latest?.revenue, prev?.revenue);
  const netGr   = growth(latest?.netIncome, prev?.netIncome);

  const miniData = income.slice(-4).map(r => ({
    date: yrDate(r.date), revenue: r.revenue, netIncome: r.netIncome,
  }));

  return (
    <div className="space-y-5">
      {/* Key metrics grid */}
      <div>
        <SectionHeader title="Valuation" />
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
          <MetricCard label="Market Cap"    value={fMCap(ov.marketCap)} />
          <MetricCard label="P/E (TTM)"     value={fNum(ov.trailingPE, "x")} />
          <MetricCard label="P/E (Fwd)"     value={fNum(ov.forwardPE, "x")} />
          <MetricCard label="P/B"           value={fNum(ov.priceToBook, "x")} />
          <MetricCard label="P/S"           value={fNum(ov.priceToSales, "x")} />
          <MetricCard label="EV/EBITDA"     value={fNum(ov.evToEbitda, "x")} />
          <MetricCard label="EPS (TTM)"     value={ov.trailingEps != null ? `₹${fNum(ov.trailingEps)}` : "—"} />
          <MetricCard label="EPS (Fwd)"     value={ov.forwardEps != null ? `₹${fNum(ov.forwardEps)}` : "—"} />
        </div>
      </div>

      <div>
        <SectionHeader title="Profitability" />
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
          <MetricCard label="ROE"           value={fNum(ov.roe, "%")}
            sub={ov.roe != null ? (ov.roe > 15 ? "Strong" : ov.roe > 8 ? "Moderate" : "Weak") : undefined}
            positive={ov.roe != null ? ov.roe > 12 : undefined} />
          <MetricCard label="ROA"           value={fNum(ov.roa, "%")} />
          <MetricCard label="Gross Margin"  value={fNum(ov.grossMargin, "%")} positive={ov.grossMargin != null ? ov.grossMargin > 20 : undefined} />
          <MetricCard label="Net Margin"    value={fNum(ov.netMargin, "%")} positive={ov.netMargin != null ? ov.netMargin > 10 : undefined} />
          <MetricCard label="Op. Margin"    value={fNum(ov.operatingMargin, "%")} positive={ov.operatingMargin != null ? ov.operatingMargin > 15 : undefined} />
          <MetricCard label="Rev. Growth"   value={fNum(ov.revenueGrowth, "%")} positive={ov.revenueGrowth != null ? ov.revenueGrowth > 0 : undefined} />
          <MetricCard label="Earn. Growth"  value={fNum(ov.earningsGrowth, "%")} positive={ov.earningsGrowth != null ? ov.earningsGrowth > 0 : undefined} />
          <MetricCard label="52W Change"    value={fNum(ov.weekChange52, "%")} positive={ov.weekChange52 != null ? ov.weekChange52 > 0 : undefined} />
        </div>
      </div>

      {/* Revenue + Net Income mini charts */}
      {miniData.length > 0 && (
        <div className="grid md:grid-cols-2 gap-4">
          <div className="bg-white rounded-xl border border-gray-100 p-4">
            <div className="flex justify-between items-start mb-3">
              <div>
                <p className="text-xs text-gray-500 uppercase font-medium">Revenue (Annual)</p>
                <p className="text-lg font-bold text-gray-900">{fCr(latest?.revenue)}</p>
              </div>
              {revGr != null && (
                <span className={`flex items-center gap-0.5 text-xs font-semibold px-2 py-1 rounded-full ${revGr >= 0 ? "bg-emerald-50 text-emerald-600" : "bg-red-50 text-red-500"}`}>
                  {revGr >= 0 ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
                  {revGr >= 0 ? "+" : ""}{revGr.toFixed(1)}% YoY
                </span>
              )}
            </div>
            <ResponsiveContainer width="100%" height={100}>
              <BarChart data={miniData} margin={{ top: 4, right: 4, left: 4, bottom: 0 }}>
                <Bar dataKey="revenue" fill={CHART_COLORS.revenue} radius={[3, 3, 0, 0]} />
                <XAxis dataKey="date" tick={{ fontSize: 10, fill: "#9ca3af" }} axisLine={false} tickLine={false} />
                <Tooltip content={<CustomTooltip />} />
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="bg-white rounded-xl border border-gray-100 p-4">
            <div className="flex justify-between items-start mb-3">
              <div>
                <p className="text-xs text-gray-500 uppercase font-medium">Net Income (Annual)</p>
                <p className="text-lg font-bold text-gray-900">{fCr(latest?.netIncome)}</p>
              </div>
              {netGr != null && (
                <span className={`flex items-center gap-0.5 text-xs font-semibold px-2 py-1 rounded-full ${netGr >= 0 ? "bg-emerald-50 text-emerald-600" : "bg-red-50 text-red-500"}`}>
                  {netGr >= 0 ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
                  {netGr >= 0 ? "+" : ""}{netGr.toFixed(1)}% YoY
                </span>
              )}
            </div>
            <ResponsiveContainer width="100%" height={100}>
              <BarChart data={miniData} margin={{ top: 4, right: 4, left: 4, bottom: 0 }}>
                <Bar dataKey="netIncome" fill={CHART_COLORS.net} radius={[3, 3, 0, 0]} />
                <XAxis dataKey="date" tick={{ fontSize: 10, fill: "#9ca3af" }} axisLine={false} tickLine={false} />
                <Tooltip content={<CustomTooltip />} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </div>
  );
}

function IncomeStatementTab({ annual, quarterly }: { annual: IncomeRow[]; quarterly: IncomeRow[] }) {
  const [period, setPeriod] = useState<"annual" | "quarterly">("annual");
  const rows = period === "annual" ? annual : quarterly;
  const fmt = period === "annual" ? yrDate : shortDate;

  const chartData = rows.map(r => ({
    date: fmt(r.date), revenue: r.revenue, grossProfit: r.grossProfit,
    operatingIncome: r.operatingIncome, netIncome: r.netIncome, ebitda: r.ebitda,
  }));

  return (
    <div className="space-y-5">
      <div className="flex justify-between items-center">
        <SectionHeader title="Income Statement" sub="All values in ₹ Crores" />
        <PeriodToggle period={period} onChange={setPeriod} />
      </div>

      {/* Main chart */}
      <div className="bg-white rounded-xl border border-gray-100 p-4">
        <p className="text-xs text-gray-500 mb-3 font-medium">Revenue vs Profits</p>
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" vertical={false} />
            <XAxis dataKey="date" tick={{ fontSize: 11, fill: "#9ca3af" }} axisLine={false} tickLine={false} />
            <YAxis tickFormatter={v => fCr(v, true)} tick={{ fontSize: 10, fill: "#9ca3af" }} axisLine={false} tickLine={false} width={70} />
            <Tooltip content={<CustomTooltip />} />
            <Bar dataKey="revenue"       name="Revenue"          fill={CHART_COLORS.revenue}  radius={[3, 3, 0, 0]} />
            <Bar dataKey="grossProfit"   name="Gross Profit"     fill={CHART_COLORS.gross}    radius={[3, 3, 0, 0]} />
            <Bar dataKey="netIncome"     name="Net Income"       fill={CHART_COLORS.net}      radius={[3, 3, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* EBITDA & Operating Income */}
      <div className="bg-white rounded-xl border border-gray-100 p-4">
        <p className="text-xs text-gray-500 mb-3 font-medium">EBITDA vs Operating Income</p>
        <ResponsiveContainer width="100%" height={180}>
          <BarChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" vertical={false} />
            <XAxis dataKey="date" tick={{ fontSize: 11, fill: "#9ca3af" }} axisLine={false} tickLine={false} />
            <YAxis tickFormatter={v => fCr(v, true)} tick={{ fontSize: 10, fill: "#9ca3af" }} axisLine={false} tickLine={false} width={70} />
            <Tooltip content={<CustomTooltip />} />
            <Bar dataKey="ebitda"         name="EBITDA"           fill={CHART_COLORS.ebitda}   radius={[3, 3, 0, 0]} />
            <Bar dataKey="operatingIncome" name="Operating Income" fill={CHART_COLORS.opIncome} radius={[3, 3, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b-2 border-gray-100">
              <th className="text-left py-2.5 text-xs text-gray-500 font-semibold uppercase pr-4">Metric</th>
              {rows.slice().reverse().map(r => (
                <th key={r.date} className="text-right py-2.5 text-xs text-gray-500 font-semibold px-2">{fmt(r.date)}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {([
              ["Revenue",          "revenue"],
              ["Gross Profit",     "grossProfit"],
              ["Operating Income", "operatingIncome"],
              ["EBITDA",           "ebitda"],
              ["Net Income",       "netIncome"],
            ] as [string, keyof IncomeRow][]).map(([label, key]) => (
              <tr key={key} className="border-b border-gray-50 hover:bg-gray-50/50 transition-colors">
                <td className="py-2.5 text-gray-600 font-medium pr-4">{label}</td>
                {rows.slice().reverse().map(r => (
                  <td key={r.date} className="py-2.5 text-right text-gray-900 font-medium px-2">
                    {fCr(r[key] as number | null)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function StatisticsTab({ ov }: { ov: any }) {
  const sections = [
    {
      title: "Valuation",
      rows: [
        { label: "P/E Ratio (TTM)",         value: fNum(ov.trailingPE, "x") },
        { label: "P/E Ratio (Forward)",      value: fNum(ov.forwardPE, "x") },
        { label: "Price / Book",             value: fNum(ov.priceToBook, "x") },
        { label: "Price / Sales",            value: fNum(ov.priceToSales, "x") },
        { label: "EV / EBITDA",              value: fNum(ov.evToEbitda, "x") },
        { label: "Book Value per Share",     value: ov.bookValue != null ? `₹${fNum(ov.bookValue)}` : "—" },
      ],
    },
    {
      title: "Profitability",
      rows: [
        { label: "Return on Equity (ROE)",   value: fNum(ov.roe, "%"), positive: ov.roe != null ? ov.roe > 12 : undefined },
        { label: "Return on Assets (ROA)",   value: fNum(ov.roa, "%"), positive: ov.roa != null ? ov.roa > 5 : undefined },
        { label: "Gross Margin",             value: fNum(ov.grossMargin, "%"), positive: ov.grossMargin != null ? ov.grossMargin > 20 : undefined },
        { label: "Operating Margin",         value: fNum(ov.operatingMargin, "%"), positive: ov.operatingMargin != null ? ov.operatingMargin > 15 : undefined },
        { label: "Net Profit Margin",        value: fNum(ov.netMargin, "%"), positive: ov.netMargin != null ? ov.netMargin > 10 : undefined },
        { label: "Revenue Growth (YoY)",     value: fNum(ov.revenueGrowth, "%"), positive: ov.revenueGrowth != null ? ov.revenueGrowth > 0 : undefined },
        { label: "Earnings Growth (YoY)",    value: fNum(ov.earningsGrowth, "%"), positive: ov.earningsGrowth != null ? ov.earningsGrowth > 0 : undefined },
      ],
    },
    {
      title: "Financial Health",
      rows: [
        { label: "Debt / Equity",            value: fNum(ov.debtToEquity, "x"), positive: ov.debtToEquity != null ? ov.debtToEquity < 1 : undefined },
        { label: "Current Ratio",            value: fNum(ov.currentRatio, "x"), positive: ov.currentRatio != null ? ov.currentRatio > 1.5 : undefined },
        { label: "Dividend Yield",           value: fNum(ov.dividendYield, "%") },
        { label: "Dividend Rate (Annual)",   value: ov.dividendRate != null ? `₹${fNum(ov.dividendRate)}` : "—" },
        { label: "52-Week Change",           value: fNum(ov.weekChange52, "%"), positive: ov.weekChange52 != null ? ov.weekChange52 > 0 : undefined },
      ],
    },
  ];

  return (
    <div className="grid md:grid-cols-3 gap-5">
      {sections.map(sec => (
        <div key={sec.title} className="bg-white rounded-xl border border-gray-100 p-4">
          <SectionHeader title={sec.title} />
          {sec.rows.map(r => (
            <StatRow key={r.label} label={r.label} value={r.value} positive={(r as any).positive} />
          ))}
        </div>
      ))}
    </div>
  );
}

function DividendsTab({ dividends, ov }: { dividends: DividendRow[]; ov: any }) {
  const recent = dividends.slice(-12);
  const annual = dividends.reduce<Record<string, number>>((acc, d) => {
    const yr = new Date(d.date).getFullYear().toString();
    acc[yr] = (acc[yr] || 0) + d.amount;
    return acc;
  }, {});
  const annualData = Object.entries(annual).sort(([a], [b]) => a.localeCompare(b)).map(([yr, amt]) => ({ date: `FY${yr.slice(2)}`, amount: amt }));

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        <MetricCard label="Dividend Yield" value={fNum(ov.dividendYield, "%")} />
        <MetricCard label="Annual DPS"     value={ov.dividendRate != null ? `₹${fNum(ov.dividendRate)}` : "—"} />
        <MetricCard label="Total Paid (All Time)" value={dividends.length > 0 ? `₹${dividends.reduce((s, d) => s + d.amount, 0).toFixed(0)}` : "—"} />
      </div>

      {annualData.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-100 p-4">
          <p className="text-xs text-gray-500 mb-3 font-medium">Annual Dividend Payout (₹ per share)</p>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={annualData} margin={{ top: 8, right: 8, left: 0, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" vertical={false} />
              <XAxis dataKey="date" tick={{ fontSize: 11, fill: "#9ca3af" }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 10, fill: "#9ca3af" }} axisLine={false} tickLine={false} />
              <Tooltip content={<CustomTooltip />} formatter={(v: any) => [`₹${v.toFixed(0)}`, "Dividend"]} />
              <Bar dataKey="amount" name="Dividend (₹)" fill={CHART_COLORS.div} radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {recent.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-100 p-4">
          <p className="text-xs text-gray-500 mb-3 font-medium">Recent Dividend Payments</p>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b-2 border-gray-100">
                <th className="text-left py-2 text-xs text-gray-500 font-semibold uppercase">Ex-Date</th>
                <th className="text-right py-2 text-xs text-gray-500 font-semibold uppercase">Amount (₹/share)</th>
              </tr>
            </thead>
            <tbody>
              {recent.slice().reverse().map((d, i) => (
                <tr key={i} className="border-b border-gray-50 hover:bg-gray-50/50">
                  <td className="py-2.5 text-gray-600">{new Date(d.date).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })}</td>
                  <td className="py-2.5 text-right font-semibold text-gray-900">₹{d.amount.toFixed(0)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function EarningsTab({ annual, quarterly }: { annual: EpsRow[]; quarterly: EpsRow[] }) {
  const [period, setPeriod] = useState<"annual" | "quarterly">("quarterly");
  const rows = period === "annual" ? annual : quarterly;
  const fmt = period === "annual" ? yrDate : shortDate;
  const chartData = rows.map(r => ({ date: fmt(r.date), eps: r.eps, positive: (r.eps ?? 0) >= 0 }));

  return (
    <div className="space-y-5">
      <div className="flex justify-between items-center">
        <SectionHeader title="Earnings Per Share" sub="Diluted EPS (₹)" />
        <PeriodToggle period={period} onChange={setPeriod} />
      </div>

      <div className="bg-white rounded-xl border border-gray-100 p-4">
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" vertical={false} />
            <XAxis dataKey="date" tick={{ fontSize: 11, fill: "#9ca3af" }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fontSize: 10, fill: "#9ca3af" }} axisLine={false} tickLine={false} />
            <Tooltip content={<CustomTooltip />} formatter={(v: any) => [`₹${v.toFixed(2)}`, "EPS"]} />
            <Bar dataKey="eps" name="EPS (₹)" radius={[3, 3, 0, 0]}>
              {chartData.map((entry, i) => (
                <Cell key={i} fill={entry.positive ? CHART_COLORS.eps : "#ef4444"} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b-2 border-gray-100">
              <th className="text-left py-2.5 text-xs text-gray-500 font-semibold uppercase pr-4">Period</th>
              <th className="text-right py-2.5 text-xs text-gray-500 font-semibold uppercase">EPS (₹)</th>
              <th className="text-right py-2.5 text-xs text-gray-500 font-semibold uppercase">QoQ / YoY</th>
            </tr>
          </thead>
          <tbody>
            {rows.slice().reverse().map((r, i, arr) => {
              const prev = arr[i + 1];
              const gr = growth(r.eps, prev?.eps);
              return (
                <tr key={r.date} className="border-b border-gray-50 hover:bg-gray-50/50">
                  <td className="py-2.5 text-gray-600 pr-4">{fmt(r.date)}</td>
                  <td className="py-2.5 text-right font-semibold text-gray-900">
                    {r.eps != null ? `₹${r.eps.toFixed(2)}` : "—"}
                  </td>
                  <td className="py-2.5 text-right">
                    {gr != null ? (
                      <span className={`text-xs font-medium ${gr >= 0 ? "text-emerald-600" : "text-red-500"}`}>
                        {gr >= 0 ? "+" : ""}{gr.toFixed(1)}%
                      </span>
                    ) : "—"}
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

function RevenueTab({ annual, quarterly }: { annual: IncomeRow[]; quarterly: IncomeRow[] }) {
  const [period, setPeriod] = useState<"annual" | "quarterly">("annual");
  const rows = period === "annual" ? annual : quarterly;
  const fmt = period === "annual" ? yrDate : shortDate;

  const chartData = rows.map((r, i, arr) => {
    const prev = arr[i - 1];
    const gr = growth(r.revenue, prev?.revenue);
    return { date: fmt(r.date), revenue: r.revenue, grossProfit: r.grossProfit, growth: gr };
  });

  const latest = rows[rows.length - 1];
  const prev   = rows[rows.length - 2];
  const revGr  = growth(latest?.revenue, prev?.revenue);

  return (
    <div className="space-y-5">
      <div className="flex justify-between items-center">
        <div>
          <SectionHeader title="Revenue" sub="₹ Crores" />
          {revGr != null && (
            <span className={`inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-full ${revGr >= 0 ? "bg-emerald-50 text-emerald-600" : "bg-red-50 text-red-500"}`}>
              {revGr >= 0 ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
              {revGr >= 0 ? "+" : ""}{revGr.toFixed(1)}% {period === "annual" ? "YoY" : "QoQ"}
            </span>
          )}
        </div>
        <PeriodToggle period={period} onChange={setPeriod} />
      </div>

      <div className="bg-white rounded-xl border border-gray-100 p-4">
        <ResponsiveContainer width="100%" height={260}>
          <ComposedChart data={chartData} margin={{ top: 8, right: 30, left: 0, bottom: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" vertical={false} />
            <XAxis dataKey="date" tick={{ fontSize: 11, fill: "#9ca3af" }} axisLine={false} tickLine={false} />
            <YAxis yAxisId="left" tickFormatter={v => fCr(v, true)} tick={{ fontSize: 10, fill: "#9ca3af" }} axisLine={false} tickLine={false} width={75} />
            <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 10, fill: "#9ca3af" }} axisLine={false} tickLine={false} tickFormatter={v => `${v?.toFixed(0)}%`} />
            <Tooltip content={<CustomTooltip />} />
            <Bar yAxisId="left" dataKey="revenue"     name="Revenue"      fill={CHART_COLORS.revenue} radius={[3, 3, 0, 0]} />
            <Bar yAxisId="left" dataKey="grossProfit" name="Gross Profit" fill={CHART_COLORS.gross}   radius={[3, 3, 0, 0]} />
            <Line yAxisId="right" type="monotone" dataKey="growth" name="YoY Growth %" stroke="#f59e0b" strokeWidth={2} dot={{ fill: "#f59e0b", r: 3 }} />
          </ComposedChart>
        </ResponsiveContainer>
        <p className="text-xs text-gray-400 mt-2 text-center">Bars = Revenue & Gross Profit • Line = YoY Growth %</p>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b-2 border-gray-100">
              <th className="text-left py-2.5 text-xs text-gray-500 font-semibold uppercase pr-4">Period</th>
              <th className="text-right py-2.5 text-xs text-gray-500 font-semibold uppercase">Revenue</th>
              <th className="text-right py-2.5 text-xs text-gray-500 font-semibold uppercase">Gross Profit</th>
              <th className="text-right py-2.5 text-xs text-gray-500 font-semibold uppercase">Gross Margin</th>
              <th className="text-right py-2.5 text-xs text-gray-500 font-semibold uppercase">Growth</th>
            </tr>
          </thead>
          <tbody>
            {rows.slice().reverse().map((r, i, arr) => {
              const prev = arr[i + 1];
              const gr = growth(r.revenue, prev?.revenue);
              const gm = r.revenue && r.grossProfit ? (r.grossProfit / r.revenue * 100) : null;
              return (
                <tr key={r.date} className="border-b border-gray-50 hover:bg-gray-50/50">
                  <td className="py-2.5 text-gray-600 pr-4">{fmt(r.date)}</td>
                  <td className="py-2.5 text-right font-semibold text-gray-900">{fCr(r.revenue)}</td>
                  <td className="py-2.5 text-right text-gray-700">{fCr(r.grossProfit)}</td>
                  <td className="py-2.5 text-right text-gray-700">{gm != null ? `${gm.toFixed(1)}%` : "—"}</td>
                  <td className="py-2.5 text-right">
                    {gr != null ? (
                      <span className={`text-xs font-medium ${gr >= 0 ? "text-emerald-600" : "text-red-500"}`}>
                        {gr >= 0 ? "+" : ""}{gr.toFixed(1)}%
                      </span>
                    ) : "—"}
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

// ── Main component ────────────────────────────────────────────────────────────

const TABS = [
  { key: "overview",   label: "Overview" },
  { key: "income",     label: "Income Statement" },
  { key: "statistics", label: "Statistics & Ratios" },
  { key: "dividends",  label: "Dividends" },
  { key: "earnings",   label: "Earnings" },
  { key: "revenue",    label: "Revenue" },
] as const;

type TabKey = typeof TABS[number]["key"];

export default function StockFinancials({ symbol }: { symbol: string }) {
  const [tab, setTab] = useState<TabKey>("overview");

  const { data, isLoading, error } = useQuery({
    queryKey: ["financials", symbol],
    queryFn: () => api.stockFinancials(symbol),
    enabled: !!symbol,
    staleTime: 10 * 60 * 1000,
    retry: 1,
  });

  if (isLoading) {
    return (
      <div className="space-y-3 py-4">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="h-20 bg-gray-100 animate-pulse rounded-xl" />
        ))}
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="py-6 text-center text-sm text-gray-400">
        Financial data not available for {symbol}. Only listed NSE equities are supported.
      </div>
    );
  }

  const { overview: ov, incomeStatement, balanceSheet: _bs, cashFlow: _cf, dividends, eps } = data;

  return (
    <div className="space-y-4" data-testid="stock-financials">
      {/* Tab nav */}
      <div className="flex gap-1 overflow-x-auto border-b border-gray-100 pb-0">
        {TABS.map(t => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            data-testid={`tab-${t.key}`}
            className={`flex-shrink-0 px-4 py-2.5 text-sm font-medium border-b-2 transition-all ${
              tab === t.key
                ? "border-indigo-600 text-indigo-700"
                : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-200"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div>
        {tab === "overview"   && <OverviewTab ov={ov} income={incomeStatement.annual} />}
        {tab === "income"     && <IncomeStatementTab annual={incomeStatement.annual} quarterly={incomeStatement.quarterly} />}
        {tab === "statistics" && <StatisticsTab ov={ov} />}
        {tab === "dividends"  && <DividendsTab dividends={dividends} ov={ov} />}
        {tab === "earnings"   && <EarningsTab annual={eps.annual} quarterly={eps.quarterly} />}
        {tab === "revenue"    && <RevenueTab annual={incomeStatement.annual} quarterly={incomeStatement.quarterly} />}
      </div>
    </div>
  );
}
