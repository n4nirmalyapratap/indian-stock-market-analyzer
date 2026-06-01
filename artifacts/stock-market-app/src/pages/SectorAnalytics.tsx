import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "wouter";
import { api, SyntheticGridRow } from "@/lib/api";
import { useTheme } from "@/context/ThemeContext";
import {
  Layers, TrendingUp, Droplets, Activity, ChevronDown, ChevronRight,
  ArrowUp, ArrowDown, Info, Loader2,
} from "lucide-react";

type SortKey = "rs30d" | "deliveryBuildup" | "breadth50emaPct";

const SORTS: { key: SortKey; label: string; icon: typeof TrendingUp }[] = [
  { key: "rs30d",            label: "Relative Strength", icon: TrendingUp },
  { key: "deliveryBuildup",  label: "Delivery Build-up", icon: Droplets },
  { key: "breadth50emaPct",  label: "50-EMA Breadth",    icon: Activity },
];

function fmtPct(v: number | null, signed = false): string {
  if (v == null || Number.isNaN(v)) return "—";
  const s = signed && v > 0 ? "+" : "";
  return `${s}${v.toFixed(2)}%`;
}

function fmtCap(v: number | null): string {
  if (v == null || v <= 0) return "—";
  const cr = v / 1e7; // INR → ₹ Crore
  if (cr >= 1e5) return `₹${(cr / 1e5).toFixed(2)}L Cr`;
  if (cr >= 1e3) return `₹${(cr / 1e3).toFixed(1)}K Cr`;
  return `₹${cr.toFixed(0)} Cr`;
}

function rsColor(v: number | null, isDark: boolean): string {
  if (v == null) return isDark ? "#64748b" : "#94a3b8";
  if (v >= 3) return "#16a34a";
  if (v >= 0) return "#4ade80";
  if (v >= -3) return "#fb923c";
  return "#dc2626";
}

function Bar({ value, max, isDark }: { value: number | null; max: number; isDark: boolean }) {
  if (value == null) return <span className="text-xs" style={{ color: isDark ? "#64748b" : "#9ca3af" }}>—</span>;
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  const color = value >= 60 ? "#16a34a" : value >= 40 ? "#facc15" : "#fb923c";
  return (
    <div className="w-full h-2 rounded-full overflow-hidden" style={{ background: isDark ? "#374151" : "#f3f4f6" }}>
      <div className="h-full rounded-full transition-all" style={{ width: `${pct}%`, backgroundColor: color }} />
    </div>
  );
}

// ── Drill-down constituents (lazy loaded on expand) ───────────────────────────
function Drilldown({ subIndustry, isDark }: { subIndustry: string; isDark: boolean }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["synthetic-drilldown", subIndustry],
    queryFn: () => api.syntheticDrilldown(subIndustry),
  });

  const muTxt = isDark ? "#94a3b8" : "#6b7280";
  const cellBg = isDark ? "#0f172a" : "#f8fafc";

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 px-5 py-4 text-xs" style={{ color: muTxt, background: cellBg }}>
        <Loader2 className="w-3.5 h-3.5 animate-spin" /> Loading constituents…
      </div>
    );
  }
  if (isError || !data || !data.available || data.constituents.length === 0) {
    return (
      <div className="px-5 py-4 text-xs" style={{ color: muTxt, background: cellBg }}>
        No constituent data available for this sub-industry.
      </div>
    );
  }

  return (
    <div className="px-5 py-3" style={{ background: cellBg }}>
      <div className="grid grid-cols-12 gap-2 px-2 pb-2 text-[10px] font-semibold uppercase tracking-wide" style={{ color: muTxt }}>
        <div className="col-span-5">Constituent</div>
        <div className="col-span-3 text-right">Market Cap</div>
        <div className="col-span-2 text-right">Weight</div>
        <div className="col-span-2 text-right">Cap Tier</div>
      </div>
      {data.constituents.map((c) => (
        <Link
          key={c.symbol}
          href={`/trading?symbol=${encodeURIComponent(c.symbol)}`}
          className="grid grid-cols-12 gap-2 px-2 py-2 rounded-lg items-center hover:bg-black/5 dark:hover:bg-white/5 transition-colors"
        >
          <div className="col-span-5 min-w-0">
            <p className="text-xs font-semibold truncate" style={{ color: isDark ? "#f1f5f9" : "#111827" }}>{c.symbol}</p>
            <p className="text-[10px] truncate" style={{ color: muTxt }}>{c.name}</p>
          </div>
          <div className="col-span-3 text-right text-xs font-mono" style={{ color: isDark ? "#cbd5e1" : "#374151" }}>{fmtCap(c.marketCap)}</div>
          <div className="col-span-2 text-right text-xs font-mono" style={{ color: isDark ? "#cbd5e1" : "#374151" }}>{c.weightPct == null ? "—" : `${c.weightPct.toFixed(1)}%`}</div>
          <div className="col-span-2 text-right text-[10px]" style={{ color: muTxt }}>{c.capCategory || "—"}</div>
        </Link>
      ))}
    </div>
  );
}

export default function SectorAnalytics() {
  const { theme } = useTheme();
  const isDark = theme === "dark";
  const [sortKey, setSortKey] = useState<SortKey>("rs30d");
  const [expanded, setExpanded] = useState<string | null>(null);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["synthetic-grid"],
    queryFn: () => api.syntheticGrid(),
  });

  const rows = useMemo(() => {
    const r = [...(data?.rows ?? [])];
    r.sort((a, b) => {
      const av = a[sortKey], bv = b[sortKey];
      const an = av == null ? -Infinity : (typeof av === "boolean" ? (av ? 1 : 0) : av);
      const bn = bv == null ? -Infinity : (typeof bv === "boolean" ? (bv ? 1 : 0) : bv);
      return (bn as number) - (an as number);
    });
    return r;
  }, [data, sortKey]);

  const bg = isDark ? "#0f172a" : "#f9fafb";
  const cardBg = isDark ? "#1e293b" : "#fff";
  const border = isDark ? "#334155" : "#f3f4f6";
  const muTxt = isDark ? "#94a3b8" : "#6b7280";
  const headTxt = isDark ? "#f1f5f9" : "#111827";

  return (
    <div className="min-h-full" style={{ background: bg }}>
      <div className="max-w-6xl mx-auto px-4 py-6">
        {/* Header */}
        <div className="flex items-start gap-3 mb-1">
          <div className="w-9 h-9 rounded-xl bg-indigo-500/10 flex items-center justify-center flex-shrink-0">
            <Layers className="w-5 h-5 text-indigo-500" />
          </div>
          <div>
            <h1 className="text-xl font-bold" style={{ color: headTxt }}>Hyper-Granular Sector Rotation</h1>
            <p className="text-sm" style={{ color: muTxt }}>
              Synthetic sub-industry indices built from real market-cap-weighted constituent moves, NSE delivery flows, and 50-EMA breadth.
            </p>
          </div>
        </div>

        {/* Sort toggles */}
        <div className="flex flex-wrap items-center gap-2 mt-5 mb-4">
          <span className="text-xs font-medium" style={{ color: muTxt }}>Rank by:</span>
          {SORTS.map(({ key, label, icon: Icon }) => {
            const active = sortKey === key;
            return (
              <button
                key={key}
                onClick={() => setSortKey(key)}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all border"
                style={active
                  ? { background: "#6366f1", borderColor: "#6366f1", color: "#fff" }
                  : { background: cardBg, borderColor: border, color: muTxt }}
              >
                <Icon className="w-3.5 h-3.5" /> {label}
              </button>
            );
          })}
          {data?.asOf && (
            <span className="ml-auto text-xs flex items-center gap-1" style={{ color: muTxt }}>
              <Info className="w-3 h-3" /> As of {data.asOf}
            </span>
          )}
        </div>

        {/* States */}
        {isLoading && (
          <div className="flex items-center justify-center gap-2 py-20 text-sm" style={{ color: muTxt }}>
            <Loader2 className="w-4 h-4 animate-spin" /> Loading rotation grid…
          </div>
        )}

        {isError && (
          <div className="rounded-2xl border p-8 text-center" style={{ background: cardBg, borderColor: border }}>
            <p className="text-sm font-medium" style={{ color: headTxt }}>Could not load the rotation grid.</p>
            <p className="text-xs mt-1" style={{ color: muTxt }}>Please try again shortly.</p>
          </div>
        )}

        {!isLoading && !isError && data && !data.available && (
          <div className="rounded-2xl border p-8 text-center" style={{ background: cardBg, borderColor: border }}>
            <Layers className="w-8 h-8 mx-auto mb-3 text-indigo-400" />
            <p className="text-sm font-medium" style={{ color: headTxt }}>Synthetic indices are still warming up.</p>
            <p className="text-xs mt-1" style={{ color: muTxt }}>
              {data.note || "The nightly engine has not produced metrics yet. Check back after the next market close."}
            </p>
          </div>
        )}

        {/* Grid */}
        {!isLoading && !isError && data?.available && rows.length > 0 && (
          <div className="rounded-2xl border overflow-hidden" style={{ background: cardBg, borderColor: border }}>
            {/* Column header */}
            <div className="grid grid-cols-12 gap-2 px-5 py-3 text-[10px] font-semibold uppercase tracking-wide border-b"
              style={{ color: muTxt, borderColor: border }}>
              <div className="col-span-4">Sub-Industry</div>
              <div className="col-span-2 text-right">30D RS</div>
              <div className="col-span-2 text-right">Delivery</div>
              <div className="col-span-3">50-EMA Breadth</div>
              <div className="col-span-1 text-right">#</div>
            </div>

            {rows.map((r: SyntheticGridRow) => {
              const open = expanded === r.subIndustry;
              return (
                <div key={r.subIndustry} className="border-b last:border-b-0" style={{ borderColor: border }}>
                  <button
                    onClick={() => setExpanded(open ? null : r.subIndustry)}
                    className="w-full grid grid-cols-12 gap-2 px-5 py-3 items-center text-left hover:bg-black/[0.02] dark:hover:bg-white/[0.03] transition-colors"
                  >
                    {/* Name */}
                    <div className="col-span-4 flex items-center gap-2 min-w-0">
                      {open ? <ChevronDown className="w-4 h-4 flex-shrink-0" style={{ color: muTxt }} />
                            : <ChevronRight className="w-4 h-4 flex-shrink-0" style={{ color: muTxt }} />}
                      <span className="text-sm font-semibold truncate" style={{ color: headTxt }}>{r.subIndustry}</span>
                    </div>

                    {/* 30D RS */}
                    <div className="col-span-2 text-right">
                      <span className="text-sm font-mono font-semibold inline-flex items-center justify-end gap-0.5"
                        style={{ color: rsColor(r.rs30d, isDark) }}>
                        {r.rs30d != null && (r.rs30d >= 0 ? <ArrowUp className="w-3 h-3" /> : <ArrowDown className="w-3 h-3" />)}
                        {fmtPct(r.rs30d, true)}
                      </span>
                    </div>

                    {/* Delivery */}
                    <div className="col-span-2 text-right">
                      <div className="text-sm font-mono" style={{ color: isDark ? "#cbd5e1" : "#374151" }}>{fmtPct(r.avgDeliveryPct)}</div>
                      {r.deliveryBuildup && (
                        <span className="inline-block mt-0.5 px-1.5 py-0.5 rounded text-[9px] font-bold"
                          style={{ background: "#16a34a22", color: "#16a34a" }}>BUILD-UP</span>
                      )}
                    </div>

                    {/* Breadth */}
                    <div className="col-span-3 flex items-center gap-2">
                      <Bar value={r.breadth50emaPct} max={100} isDark={isDark} />
                      <span className="text-xs font-mono w-10 text-right flex-shrink-0" style={{ color: muTxt }}>
                        {r.breadth50emaPct == null ? "—" : `${Math.round(r.breadth50emaPct)}%`}
                      </span>
                    </div>

                    {/* Count */}
                    <div className="col-span-1 text-right text-xs font-mono" style={{ color: muTxt }}>{r.constituentCount}</div>
                  </button>

                  {open && <Drilldown subIndustry={r.subIndustry} isDark={isDark} />}
                </div>
              );
            })}
          </div>
        )}

        {/* Methodology note */}
        <p className="text-[11px] mt-4 leading-relaxed" style={{ color: muTxt }}>
          <strong>RS</strong> = 30-day return of the synthetic index minus Nifty 50 over the same window.{" "}
          <strong>Delivery build-up</strong> flags when average delivery % runs ≥15% above its 20-day average — a proxy for institutional accumulation.{" "}
          <strong>Breadth</strong> is the share of constituents trading above their own 50-day EMA. Missing values render as “—” rather than zero.
        </p>
      </div>
    </div>
  );
}
