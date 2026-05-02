import { RefreshCw, Wifi, WifiOff, CheckCircle2 } from "lucide-react";
import type { QueryKey } from "@tanstack/react-query";
import { useRefreshMarketData, type MarketDataMeta } from "@/lib/marketData";

interface Props {
  meta?:        MarketDataMeta | null;
  /** Query key(s) to invalidate when the user clicks Refresh. */
  refreshKeys?: QueryKey | QueryKey[];
  /** When true, the Refresh button is hidden (e.g. for read-only summaries). */
  hideRefresh?: boolean;
  /** Optional label override for the data-source pill. */
  label?:       string;
  className?:   string;
}

function relTime(iso?: string | null): string {
  if (!iso) return "just now";
  const t = Date.parse(iso);
  if (!Number.isFinite(t)) return "just now";
  const diff = Date.now() - t;
  const s = Math.floor(diff / 1000);
  if (s < 5)        return "just now";
  if (s < 60)       return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60)       return `${m} min ago`;
  const h = Math.floor(m / 60);
  if (h < 24)       return `${h} hr ago`;
  const d = Math.floor(h / 24);
  return `${d} day${d > 1 ? "s" : ""} ago`;
}

function stateLabel(state?: string): { label: string; cls: string; Icon: typeof Wifi } {
  switch (state) {
    case "OPEN":     return { label: "Live",       cls: "text-green-700 bg-green-50 border-green-200",   Icon: Wifi };
    case "PRE_OPEN": return { label: "Pre-Open",   cls: "text-amber-700 bg-amber-50 border-amber-200",   Icon: WifiOff };
    case "WEEKEND":  return { label: "Weekend",    cls: "text-slate-600 bg-slate-50 border-slate-200",   Icon: WifiOff };
    case "CLOSED":   return { label: "Closed",     cls: "text-slate-700 bg-slate-50 border-slate-200",   Icon: WifiOff };
    default:         return { label: state || "—", cls: "text-slate-500 bg-slate-50 border-slate-200",   Icon: WifiOff };
  }
}

/**
 * Tiny pill that shows where the displayed price came from, when it was
 * captured, and the current market state. Includes an optional Refresh
 * button that invalidates the matching React-Query key(s).
 */
export default function DataFreshness({
  meta,
  refreshKeys,
  hideRefresh,
  label,
  className = "",
}: Props) {
  const refresh = useRefreshMarketData();
  if (!meta) return null;

  const { label: stateText, cls: stateCls, Icon } = stateLabel(meta.marketState);
  const sourceText = label ?? (meta.source || "—");
  const ageText    = relTime(meta.asOf ?? null);
  const sealed     = !!meta.eodSealed;

  return (
    <div
      data-testid="data-freshness"
      className={`flex flex-wrap items-center gap-2 text-xs ${className}`}
    >
      <span className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white px-2 py-0.5 text-slate-700">
        <span className="font-medium">{sourceText}</span>
      </span>
      <span className="text-slate-400">•</span>
      <span className="text-slate-500" title={meta.asOf ?? ""}>{ageText}</span>
      <span className="text-slate-400">•</span>
      <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 ${stateCls}`}>
        <Icon className="h-3 w-3" /> {stateText}
      </span>
      {sealed && (
        <span
          className="inline-flex items-center gap-1 rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-emerald-700"
          title={meta.eodDate ? `Official close for ${meta.eodDate}` : "Official EOD close"}
        >
          <CheckCircle2 className="h-3 w-3" /> EOD
        </span>
      )}
      {!hideRefresh && refreshKeys && (
        <button
          type="button"
          onClick={() => refresh(refreshKeys)}
          className="ml-1 inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white px-2 py-0.5 text-slate-600 hover:bg-slate-50 active:scale-95 transition"
          aria-label="Refresh data"
        >
          <RefreshCw className="h-3 w-3" /> Refresh
        </button>
      )}
    </div>
  );
}
