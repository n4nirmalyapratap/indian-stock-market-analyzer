import { useQuery } from "@tanstack/react-query";
import { Globe, TrendingUp, TrendingDown, Minus } from "lucide-react";
import { api, type GlobalIndex, type GlobalIndicesRegion } from "@/lib/api";

// ── helpers ──────────────────────────────────────────────────────────────────

function fmtVal(v: number | null): string {
  if (v == null) return "—";
  if (v >= 1000) return v.toLocaleString("en-US", { maximumFractionDigits: 0 });
  return v.toFixed(2);
}

function fmtPct(p: number | null): string {
  if (p == null) return "—";
  const sign = p >= 0 ? "+" : "";
  return `${sign}${p.toFixed(2)}%`;
}

const REGION_LABELS: Record<string, string> = {
  Americas:      "🌎 Americas",
  Europe:        "🌍 Europe",
  "Asia Pacific":"🌏 Asia Pacific",
  India:         "🇮🇳 India",
};

// ── skeleton ─────────────────────────────────────────────────────────────────

function SkeletonRow() {
  return (
    <div className="flex items-center justify-between py-[5px]">
      <div className="h-3 w-24 bg-gray-100 dark:bg-gray-700 rounded animate-pulse" />
      <div className="h-3 w-16 bg-gray-100 dark:bg-gray-700 rounded animate-pulse" />
    </div>
  );
}

// ── single index row ──────────────────────────────────────────────────────────

function IndexRow({ idx }: { idx: GlobalIndex }) {
  const up   = idx.pChange != null && idx.pChange > 0;
  const down = idx.pChange != null && idx.pChange < 0;

  return (
    <div className="flex items-center justify-between py-[5px] group">
      <span className="flex items-center gap-1.5 min-w-0 text-xs text-gray-700 dark:text-gray-300">
        <span className="text-sm leading-none">{idx.flag}</span>
        <span className="truncate">{idx.name}</span>
      </span>
      {idx.source_blocked ? (
        <span
          className="text-[10px] px-1.5 py-0.5 rounded font-medium flex-shrink-0 ml-2"
          style={{ background: "rgba(156,163,175,0.12)", color: "#9ca3af" }}
          title="Data not available — NSE IFSC feed is not accessible from this server"
        >
          Unavailable
        </span>
      ) : (
        <div className="flex items-center gap-2 flex-shrink-0 ml-2">
          <span className="text-xs font-medium tabular-nums text-gray-900 dark:text-white">
            {fmtVal(idx.value)}
          </span>
          <span
            className={`text-[11px] font-semibold tabular-nums flex items-center gap-0.5 w-[58px] justify-end
              ${up   ? "text-green-600 dark:text-green-400" : ""}
              ${down ? "text-red-500  dark:text-red-400"   : ""}
              ${!up && !down ? "text-gray-400 dark:text-gray-500" : ""}`}
          >
            {up   && <TrendingUp   className="w-2.5 h-2.5 flex-shrink-0" />}
            {down && <TrendingDown className="w-2.5 h-2.5 flex-shrink-0" />}
            {!up && !down && <Minus className="w-2.5 h-2.5 flex-shrink-0" />}
            {fmtPct(idx.pChange)}
          </span>
        </div>
      )}
    </div>
  );
}

// ── region column ─────────────────────────────────────────────────────────────

function RegionColumn({ region, loading }: { region: GlobalIndicesRegion; loading: boolean }) {
  return (
    <div className="min-w-0">
      <p className="text-[10px] font-bold uppercase tracking-widest text-gray-400 dark:text-gray-500 mb-2 pb-1.5 border-b border-gray-100 dark:border-white/[0.06]">
        {REGION_LABELS[region.label] ?? region.label}
      </p>
      {loading
        ? Array.from({ length: 3 }).map((_, i) => <SkeletonRow key={i} />)
        : region.indices.map(idx => <IndexRow key={idx.symbol} idx={idx} />)
      }
    </div>
  );
}

// ── main component ────────────────────────────────────────────────────────────

export default function GlobalIndicesPanel() {
  const { data, isLoading, error } = useQuery({
    queryKey:          ["global-indices"],
    queryFn:           api.globalIndices,
    staleTime:         5 * 60 * 1000,
    refetchInterval:   5 * 60 * 1000,
    refetchOnWindowFocus: false,
  });

  if (error) return null;

  const regions = data?.regions ?? [];

  const asOfStr = data?.asOf
    ? new Date(data.asOf).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })
    : null;

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-100 dark:border-gray-700 shadow-sm overflow-hidden">
      {/* header */}
      <div className="flex items-center justify-between px-5 pt-4 pb-3 border-b border-gray-50 dark:border-white/[0.04]">
        <h2 className="font-semibold text-gray-800 dark:text-gray-100 flex items-center gap-2 text-sm">
          <Globe className="w-4 h-4 text-blue-500 dark:text-blue-400 flex-shrink-0" />
          World Markets
        </h2>
        <div className="flex items-center gap-2">
          {isLoading && (
            <span className="w-3 h-3 rounded-full border-2 border-blue-400 border-t-transparent animate-spin inline-block" />
          )}
          {asOfStr && !isLoading && (
            <span className="text-[10px] text-gray-400 dark:text-gray-500 tabular-nums">
              as of {asOfStr}
            </span>
          )}
        </div>
      </div>

      {/* region columns */}
      <div className="px-5 py-3 grid grid-cols-2 lg:grid-cols-4 gap-x-5 gap-y-4">
        {isLoading && regions.length === 0
          ? ["Americas", "Europe", "Asia Pacific", "India"].map(lbl => (
              <RegionColumn
                key={lbl}
                region={{ label: lbl, indices: [] }}
                loading
              />
            ))
          : regions.map(r => (
              <RegionColumn key={r.label} region={r} loading={false} />
            ))
        }
      </div>
    </div>
  );
}
