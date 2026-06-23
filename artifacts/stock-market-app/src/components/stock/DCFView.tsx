import { useQuery } from "@tanstack/react-query";
import { api, type DcfResponse } from "@/lib/api";
import { TrendingUp, TrendingDown, Minus, AlertCircle, Loader2 } from "lucide-react";

type DcfVerdict = DcfResponse["verdict"];
interface VerdictStyle { label: string; bg: string; text: string; Icon: typeof TrendingUp }
const VERDICT_STYLE: Record<DcfVerdict, VerdictStyle> = {
  UNDERVALUED: { label: "Undervalued", bg: "bg-green-50 dark:bg-green-500/10",  text: "text-green-700 dark:text-green-400",  Icon: TrendingUp },
  FAIR:        { label: "Fair value",  bg: "bg-amber-50 dark:bg-amber-500/10",  text: "text-amber-700 dark:text-amber-400",  Icon: Minus },
  OVERVALUED:  { label: "Overvalued",  bg: "bg-red-50 dark:bg-red-500/10",      text: "text-red-700 dark:text-red-400",      Icon: TrendingDown },
  UNKNOWN:     { label: "Unknown",     bg: "bg-gray-50 dark:bg-gray-500/10",    text: "text-gray-700 dark:text-gray-400",    Icon: Minus },
};

function fmtINR(v: number | null | undefined, digits = 2): string {
  if (v == null || !isFinite(v)) return "—";
  return v.toLocaleString("en-IN", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}
function fmtCr(v: number | null | undefined): string {
  if (v == null || !isFinite(v)) return "—";
  return `₹${v.toLocaleString("en-IN", { maximumFractionDigits: 0 })} Cr`;
}

function Stat({ label, value, highlight, tone }: {
  label: string; value: string; highlight?: boolean; tone?: "pos" | "neg";
}) {
  const toneClass =
    tone === "pos" ? "text-green-600 dark:text-green-400"
    : tone === "neg" ? "text-red-600 dark:text-red-400"
    : highlight ? "text-indigo-600 dark:text-indigo-400"
    : "text-gray-900 dark:text-white";
  return (
    <div className="rounded-lg bg-gray-50 dark:bg-gray-800/50 p-4">
      <p className="text-xs text-gray-500 dark:text-gray-400">{label}</p>
      <p className={`mt-1 text-xl font-bold ${toneClass}`}>{value}</p>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-4 border-b border-dashed border-gray-100 dark:border-gray-800 pb-2">
      <span className="text-gray-500 dark:text-gray-400">{label}</span>
      <span className="font-medium text-gray-900 dark:text-white text-right">{value}</span>
    </div>
  );
}

export default function DCFView({ symbol }: { symbol: string }) {
  const { data, isLoading, error } = useQuery<DcfResponse>({
    queryKey: ["dcf", symbol],
    queryFn: () => api.stockDcf(symbol),
    enabled: !!symbol,
    staleTime: 60 * 60 * 1000,
    retry: 0,
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center gap-2 py-16 text-sm text-gray-500">
        <Loader2 className="w-4 h-4 animate-spin" />
        Computing DCF for {symbol}…
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 dark:bg-red-500/10 dark:border-red-500/30 p-4 flex gap-3 items-start">
        <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
        <div className="text-sm text-red-700 dark:text-red-300">
          <p className="font-medium">Could not compute DCF for {symbol}.</p>
          <p className="mt-1 text-red-600 dark:text-red-400">{(error as Error).message || "Unknown error."}</p>
        </div>
      </div>
    );
  }

  if (!data) return null;

  const verdictKey = data.verdict ?? "UNKNOWN";
  const v = VERDICT_STYLE[verdictKey] ?? VERDICT_STYLE.UNKNOWN;

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-wide text-gray-400">{data.symbol}</p>
            <h2 className="text-xl font-bold text-gray-900 dark:text-white">{data.companyName}</h2>
            <p className="text-xs text-gray-400 mt-1">Two-stage DCF · explicit assumptions</p>
          </div>
          <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold ${v.bg} ${v.text}`}>
            <v.Icon className="w-3.5 h-3.5" />
            {v.label}
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-6">
          <Stat label="Intrinsic value / share" value={`₹${fmtINR(data.intrinsicValue)}`} highlight />
          <Stat label="Current price" value={data.currentPrice != null ? `₹${fmtINR(data.currentPrice)}` : "—"} />
          <Stat
            label="Margin of safety"
            value={data.marginOfSafety != null ? `${(data.marginOfSafety * 100).toFixed(1)}%` : "—"}
            tone={data.marginOfSafety != null ? (data.marginOfSafety >= 0 ? "pos" : "neg") : undefined}
          />
        </div>
      </div>

      <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-6">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-4">Assumptions</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-6 gap-y-3 text-sm">
          <Row label="Base FCF (avg of last positives)" value={fmtCr(data.assumptions.baseFcfCr)} />
          <Row label="Growth Y1–5"     value={`${data.assumptions.growthYears1to5Pct.toFixed(2)}%`} />
          <Row label="Growth Y6–10"    value={`${data.assumptions.growthYears6to10Pct.toFixed(2)}%`} />
          <Row label="Terminal growth" value={`${data.assumptions.terminalGrowthPct.toFixed(2)}%`} />
          <Row label="WACC"            value={`${data.assumptions.waccPct.toFixed(2)}%`} />
          <Row label="Risk-free (India 10Y)" value={`${data.assumptions.riskFreePct.toFixed(2)}%`} />
          <Row label="Beta"                  value={data.assumptions.beta} />
          <Row label="Equity risk premium"   value={`${data.assumptions.equityRiskPremiumPct.toFixed(0)}%`} />
          <Row label="Horizon"               value={`${data.assumptions.horizonYears}y + Gordon`} />
          <Row label="Shares outstanding"    value={`${data.assumptions.sharesOutstandingCr.toFixed(2)} Cr`} />
          <Row label="Total debt"            value={fmtCr(data.assumptions.totalDebtCr)} />
          <Row label="Cash"                  value={fmtCr(data.assumptions.cashCr)} />
          <Row
            label="Net debt"
            value={
              data.assumptions.netDebtCr < 0
                ? `Net cash ${fmtCr(-data.assumptions.netDebtCr)}`
                : fmtCr(data.assumptions.netDebtCr)
            }
          />
          <Row label="Enterprise value" value={fmtCr(data.assumptions.enterpriseValueCr)} />
          <Row label="Equity value"     value={fmtCr(data.assumptions.equityValueCr)} />
          <Row label="Growth source"    value={data.assumptions.growthSource} />
        </div>
      </div>

      {data.fcfHistoryCr.length > 0 && (
        <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-6">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-3">
            Recent annual Free Cash Flow (₹ Cr, most recent first)
          </h3>
          <div className="flex flex-wrap gap-2">
            {data.fcfHistoryCr.map((val, i) => (
              <div key={i} className="px-3 py-1.5 rounded-md bg-gray-50 dark:bg-gray-800 text-sm text-gray-700 dark:text-gray-200 font-mono">
                {val.toLocaleString("en-IN", { maximumFractionDigits: 0 })}
              </div>
            ))}
          </div>
        </div>
      )}

      <p className="text-xs text-gray-400">Source: {data.source}</p>
    </div>
  );
}
