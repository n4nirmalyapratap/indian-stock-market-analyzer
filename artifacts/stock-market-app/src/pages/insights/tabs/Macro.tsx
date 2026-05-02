import { useQuery } from "@tanstack/react-query";
import {
  ResponsiveContainer, LineChart, Line, BarChart, Bar, XAxis, YAxis,
  Tooltip, CartesianGrid, ReferenceLine, Legend,
} from "recharts";
import {
  TrendingUp, TrendingDown, Minus, Activity, Sparkles, ExternalLink,
} from "lucide-react";
import { api } from "@/lib/api";
import type { MacroQuote, MacroSeriesPoint } from "@/lib/api";
import { Card, PageHeader, Loading, ErrorState, useChartPalette, fmtNum } from "../_shared";

/* ──────────────────────────────────────────────────────────────────────────
 * Macro tab — India macro pulse dashboard.
 *
 * Sections (top-to-bottom):
 *   1. Headline tiles              (Repo · CPI · IIP · USD/INR · 10Y · Brent)
 *   2. AI commentary               ("what changed this week")
 *   3. RBI policy-rate timeline    (line chart)
 *   4. CPI vs IIP overlay          (line chart, YoY %)
 *   5. GDP growth (YoY)            (bar chart)
 *   6. Currency / commodities row  (USD/INR, DXY, Brent, Gold, VIX cards)
 *   7. Sources footer
 * ────────────────────────────────────────────────────────────────────── */

function fmtTileValue(v: number | null | undefined, unit: string): string {
  if (v == null || isNaN(v)) return "—";
  if (unit === "₹") return `₹${v.toFixed(2)}`;
  if (unit === "$") return `$${v.toFixed(2)}`;
  return `${v.toFixed(2)}${unit}`;
}

function fmtTileDelta(d: number | null | undefined, unit: string): string {
  if (d == null || isNaN(d)) return "—";
  const sign = d >= 0 ? "+" : "";
  return `${sign}${d.toFixed(2)}${unit}`;
}

function HeadlineTile({
  label, unit, value, delta, deltaUnit, asOf,
}: {
  label: string; unit: string;
  value: number | null; delta: number | null; deltaUnit: string;
  asOf: string | null;
}) {
  const up   = (delta ?? 0) > 0;
  const down = (delta ?? 0) < 0;
  return (
    <Card className="p-4">
      <p className="text-[11px] font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">{label}</p>
      <p className="text-2xl font-bold text-gray-900 dark:text-white mt-1">{fmtTileValue(value, unit)}</p>
      <p
        className={`text-xs font-semibold flex items-center gap-1 mt-1
          ${up ? "text-green-600 dark:text-green-400" : ""}
          ${down ? "text-red-500 dark:text-red-400" : ""}
          ${!up && !down ? "text-gray-400 dark:text-gray-500" : ""}`}
      >
        {up && <TrendingUp className="w-3.5 h-3.5" />}
        {down && <TrendingDown className="w-3.5 h-3.5" />}
        {!up && !down && <Minus className="w-3.5 h-3.5" />}
        {fmtTileDelta(delta, deltaUnit)}
      </p>
      {asOf && (
        <p className="text-[10px] text-gray-400 dark:text-gray-500 mt-1.5 truncate">
          as of {asOf.slice(0, 10)}
        </p>
      )}
    </Card>
  );
}

function CurrencyCard({ label, q, unit = "" }: { label: string; q: MacroQuote; unit?: string }) {
  const price = q?.price ?? null;
  const ch = q?.pChange ?? 0;
  const up = ch > 0;
  const down = ch < 0;
  return (
    <Card className="p-3">
      <div className="flex items-center justify-between">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">{label}</p>
        <span className={`text-[11px] font-semibold flex items-center gap-0.5
          ${up ? "text-green-600 dark:text-green-400" : ""}
          ${down ? "text-red-500 dark:text-red-400" : ""}
          ${!up && !down ? "text-gray-400 dark:text-gray-500" : ""}`}>
          {up && <TrendingUp className="w-3 h-3" />}
          {down && <TrendingDown className="w-3 h-3" />}
          {ch.toFixed(2)}%
        </span>
      </div>
      <p className="text-base font-bold text-gray-900 dark:text-white mt-0.5">
        {price != null ? `${unit}${fmtNum(price, 2)}` : "—"}
      </p>
    </Card>
  );
}

function shortDate(d: string): string {
  // FRED dates are YYYY-MM-DD; show YY-Mon for chart axis.
  if (!d || d.length < 7) return d;
  const [y, m] = d.split("-");
  const months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  const mi = parseInt(m, 10) - 1;
  return `${months[mi] ?? m} ${y.slice(2)}`;
}

function buildOverlay(cpi: MacroSeriesPoint[], iip: MacroSeriesPoint[]) {
  const map = new Map<string, { date: string; cpi?: number; iip?: number }>();
  for (const p of cpi) map.set(p.date, { date: p.date, cpi: p.value });
  for (const p of iip) {
    const cur = map.get(p.date);
    if (cur) cur.iip = p.value; else map.set(p.date, { date: p.date, iip: p.value });
  }
  return Array.from(map.values()).sort((a, b) => a.date.localeCompare(b.date));
}

export default function Macro() {
  const palette = useChartPalette();
  const { data, isLoading, error } = useQuery({
    queryKey: ["macro-dashboard"],
    queryFn:  api.macroDashboard,
    staleTime: 60 * 60 * 1000,
    refetchOnWindowFocus: false,
  });

  if (isLoading) return <Loading label="Loading India macro pulse…" />;
  if (error)     return <ErrorState message={`Could not load macro data: ${(error as Error).message}`} />;
  if (!data)     return null;

  const strip = data.currencyStrip;
  const overlay = buildOverlay(data.cpi, data.iip);

  // Compute headline tiles from dashboard payload (mirrors /macro/strip values).
  const repoNow  = data.rateTimeline.length ? data.rateTimeline[data.rateTimeline.length - 1] : null;
  const repoPrev = data.rateTimeline.length > 1 ? data.rateTimeline[data.rateTimeline.length - 2] : null;
  const cpiNow   = data.cpi.length ? data.cpi[data.cpi.length - 1] : null;
  const cpiPrev  = data.cpi.length > 1 ? data.cpi[data.cpi.length - 2] : null;
  const iipNow   = data.iip.length ? data.iip[data.iip.length - 1] : null;
  const iipPrev  = data.iip.length > 1 ? data.iip[data.iip.length - 2] : null;
  const yldHist  = data.yieldCurve.ind10yHistory ?? [];
  const yldPrev  = yldHist.length > 1 ? yldHist[yldHist.length - 2] : null;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Macro Pulse — India"
        subtitle="RBI policy, CPI, IIP, USD/INR, India 10Y and Brent in one view."
      />

      {/* ── Headline tiles ──────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        <HeadlineTile
          label="RBI Repo"
          unit="%"
          value={repoNow?.value ?? null}
          delta={repoNow && repoPrev ? repoNow.value - repoPrev.value : null}
          deltaUnit="pp"
          asOf={repoNow?.date ?? null}
        />
        <HeadlineTile
          label="CPI YoY"
          unit="%"
          value={cpiNow?.value ?? null}
          delta={cpiNow && cpiPrev ? cpiNow.value - cpiPrev.value : null}
          deltaUnit="pp"
          asOf={cpiNow?.date ?? null}
        />
        <HeadlineTile
          label="IIP YoY"
          unit="%"
          value={iipNow?.value ?? null}
          delta={iipNow && iipPrev ? iipNow.value - iipPrev.value : null}
          deltaUnit="pp"
          asOf={iipNow?.date ?? null}
        />
        <HeadlineTile
          label="USD/INR"
          unit="₹"
          value={strip.usdinr?.price ?? null}
          delta={strip.usdinr?.pChange ?? null}
          deltaUnit="%"
          asOf={data.fetchedAt}
        />
        <HeadlineTile
          label="India 10Y"
          unit="%"
          value={data.yieldCurve.ind10yNow}
          delta={data.yieldCurve.ind10yNow != null && yldPrev ? data.yieldCurve.ind10yNow - yldPrev.value : null}
          deltaUnit="pp"
          asOf={data.yieldCurve.ind10yAsOf}
        />
        <HeadlineTile
          label="Brent"
          unit="$"
          value={strip.brent?.price ?? null}
          delta={strip.brent?.pChange ?? null}
          deltaUnit="%"
          asOf={data.fetchedAt}
        />
      </div>

      {/* ── AI commentary ───────────────────────────────────────────────── */}
      {data.commentary && (
        <Card className="p-4 md:p-5 bg-gradient-to-br from-indigo-50/60 to-purple-50/40 dark:from-indigo-500/10 dark:to-purple-500/5 border-indigo-100 dark:border-indigo-500/20">
          <div className="flex items-start gap-3">
            <div className="w-8 h-8 rounded-lg bg-indigo-100 dark:bg-indigo-500/20 text-indigo-600 dark:text-indigo-400 flex items-center justify-center flex-shrink-0">
              <Sparkles className="w-4 h-4" />
            </div>
            <div className="min-w-0">
              <p className="text-xs font-bold uppercase tracking-wider text-indigo-700 dark:text-indigo-300">
                What changed this week
              </p>
              <p className="text-sm text-gray-700 dark:text-gray-200 mt-1.5 leading-relaxed">
                {data.commentary}
              </p>
            </div>
          </div>
        </Card>
      )}

      {/* ── RBI policy-rate timeline ────────────────────────────────────── */}
      <Card className="p-4 md:p-5">
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-semibold text-gray-900 dark:text-white">RBI Policy Rate Timeline</h3>
          <span className="text-xs text-gray-500 dark:text-gray-400">Source: FRED · INDIRSTPR</span>
        </div>
        {data.rateTimeline.length === 0 ? (
          <p className="text-sm text-gray-500 dark:text-gray-400 py-8 text-center">No rate data available.</p>
        ) : (
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data.rateTimeline}>
                <CartesianGrid strokeDasharray="3 3" stroke={palette.border} />
                <XAxis dataKey="date" tick={{ fontSize: 10, fill: palette.muted }} tickFormatter={shortDate} minTickGap={30} />
                <YAxis tick={{ fontSize: 10, fill: palette.muted }} domain={["auto", "auto"]} unit="%" />
                <Tooltip
                  contentStyle={{ background: palette.surf, border: `1px solid ${palette.border}`, borderRadius: 8, color: palette.text }}
                  labelFormatter={shortDate}
                  formatter={(v: number) => [`${v.toFixed(2)}%`, "Repo"]}
                />
                <Line type="stepAfter" dataKey="value" stroke={palette.accent} strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </Card>

      {/* ── CPI / IIP overlay ───────────────────────────────────────────── */}
      <Card className="p-4 md:p-5">
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-semibold text-gray-900 dark:text-white">CPI vs Industrial Production (YoY %)</h3>
          <span className="text-xs text-gray-500 dark:text-gray-400">Source: FRED · INDCPIALLMINMEI / INDPROINDMISMEI</span>
        </div>
        {overlay.length === 0 ? (
          <p className="text-sm text-gray-500 dark:text-gray-400 py-8 text-center">No CPI/IIP data available.</p>
        ) : (
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={overlay}>
                <CartesianGrid strokeDasharray="3 3" stroke={palette.border} />
                <XAxis dataKey="date" tick={{ fontSize: 10, fill: palette.muted }} tickFormatter={shortDate} minTickGap={30} />
                <YAxis tick={{ fontSize: 10, fill: palette.muted }} unit="%" />
                <ReferenceLine y={0} stroke={palette.muted} strokeDasharray="3 3" />
                <Tooltip
                  contentStyle={{ background: palette.surf, border: `1px solid ${palette.border}`, borderRadius: 8, color: palette.text }}
                  labelFormatter={shortDate}
                  formatter={(v: number, n: string) => [`${v.toFixed(2)}%`, n.toUpperCase()]}
                />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Line type="monotone" dataKey="cpi" name="CPI YoY" stroke={palette.fii} strokeWidth={2} dot={false} connectNulls />
                <Line type="monotone" dataKey="iip" name="IIP YoY" stroke={palette.dii} strokeWidth={2} dot={false} connectNulls />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </Card>

      {/* ── GDP YoY bars ────────────────────────────────────────────────── */}
      <Card className="p-4 md:p-5">
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-semibold text-gray-900 dark:text-white">Real GDP Growth (YoY %, Quarterly)</h3>
          <span className="text-xs text-gray-500 dark:text-gray-400">Source: FRED · INDGDPRQDSMEI</span>
        </div>
        {data.gdp.length === 0 ? (
          <p className="text-sm text-gray-500 dark:text-gray-400 py-8 text-center">No GDP data available.</p>
        ) : (
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data.gdp}>
                <CartesianGrid strokeDasharray="3 3" stroke={palette.border} />
                <XAxis dataKey="date" tick={{ fontSize: 10, fill: palette.muted }} tickFormatter={shortDate} minTickGap={30} />
                <YAxis tick={{ fontSize: 10, fill: palette.muted }} unit="%" />
                <Tooltip
                  contentStyle={{ background: palette.surf, border: `1px solid ${palette.border}`, borderRadius: 8, color: palette.text }}
                  labelFormatter={shortDate}
                  formatter={(v: number) => [`${v.toFixed(2)}%`, "GDP YoY"]}
                />
                <Bar dataKey="value" fill={palette.line} radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </Card>

      {/* ── Currency / commodity strip ──────────────────────────────────── */}
      <Card className="p-4 md:p-5">
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-semibold text-gray-900 dark:text-white flex items-center gap-2">
            <Activity className="w-4 h-4 text-indigo-500" />
            Currency &amp; Commodities
          </h3>
          <span className="text-xs text-gray-500 dark:text-gray-400">Source: Yahoo Finance · Live</span>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <CurrencyCard label="USD/INR" q={strip.usdinr} unit="₹" />
          <CurrencyCard label="DXY"     q={strip.dxy} />
          <CurrencyCard label="Brent"   q={strip.brent} unit="$" />
          <CurrencyCard label="Gold"    q={strip.gold}  unit="$" />
          <CurrencyCard label="India VIX" q={strip.vix} />
        </div>
      </Card>

      {/* ── Sources footer ──────────────────────────────────────────────── */}
      {data.sources && data.sources.length > 0 && (
        <Card className="p-3">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">Sources</span>
            {data.sources.map(s => (
              <a
                key={s.id}
                href={
                  s.id === "fred"  ? "https://fred.stlouisfed.org/" :
                  s.id === "yahoo" ? "https://finance.yahoo.com/" :
                  s.id === "rbi"   ? "https://dbie.rbi.org.in/" :
                  "#"
                }
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 text-[11px] px-2 py-1 rounded-md bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-indigo-50 dark:hover:bg-indigo-900/30 hover:text-indigo-700 dark:hover:text-indigo-300 transition border border-gray-200 dark:border-gray-600"
                title={s.covers}
              >
                {s.label} <ExternalLink className="w-3 h-3" />
              </a>
            ))}
            {data.fetchedAt && (
              <span className="text-[11px] text-gray-400 dark:text-gray-500 ml-auto">
                Fetched {data.fetchedAt.slice(0, 19).replace("T", " ")} UTC
              </span>
            )}
          </div>
        </Card>
      )}
    </div>
  );
}
