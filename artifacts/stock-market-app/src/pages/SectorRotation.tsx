/**
 * SectorRotation — the "Find Winning Stocks via Sector Rotation" cockpit.
 *
 * Two-pane funnel:
 *   LEFT  — pick a sector / sub-industry (Strength Leaderboard, default, or RRG).
 *   RIGHT — its strongest stocks appear immediately (ranked: relative strength +
 *           delivery + above-trend).
 *
 * Sectors and sub-industries both drill to a ranked stock shortlist. This page
 * also absorbs the old Hyper-Granular grid (sub-industry RS / delivery / breadth
 * live in the leaderboard rows).
 */
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  ScatterChart, Scatter, XAxis, YAxis, ZAxis, ReferenceLine,
  Tooltip, ResponsiveContainer, Cell,
} from "recharts";
import {
  Activity, Loader2, AlertCircle, TrendingUp, TrendingDown, Truck, MousePointerClick,
} from "lucide-react";
import { api, RrgEntity, ShortlistStock } from "@/lib/api";
import { marketDataQueryOptions } from "@/lib/marketData";
import ChartButton from "@/components/ChartButton";
import StockLogo from "@/components/StockLogo";
import { fmtPct } from "@/lib/format";

type Level = "sector" | "subindustry";

// Indicators pre-applied when opening a stock in Chart Studio from the cockpit:
// trend (50/200 EMA) + momentum (RSI, MACD) — the standard rotation read.
const CHART_PRESET = "ema50,ema200,rsi,macd";

const QUADRANTS = ["Leading", "Improving", "Weakening", "Lagging"] as const;
const QUAD_COLOR: Record<string, string> = {
  Leading:   "#10b981",
  Improving: "#3b82f6",
  Weakening: "#f59e0b",
  Lagging:   "#f43f5e",
};

// "Strength" logic (composite tiers, same as the Market Sectors page).
type Logic = "rotation" | "strength";
const TIER_ORDER = ["DEEP_GREEN", "LIGHT_GREEN", "YELLOW", "ORANGE", "DEEP_RED"] as const;
const TIER_COLOR: Record<string, string> = {
  DEEP_GREEN: "#16a34a", LIGHT_GREEN: "#4ade80", YELLOW: "#ca8a04", ORANGE: "#ea580c", DEEP_RED: "#dc2626",
};
const TIER_LABEL: Record<string, string> = {
  DEEP_GREEN: "Deep Green", LIGHT_GREEN: "Light Green", YELLOW: "Neutral", ORANGE: "Weakening", DEEP_RED: "Deep Red",
};
const zoneOf = (e: RrgEntity, logic: Logic) => (logic === "strength" ? (e.tier || "—") : e.quadrant);
const zoneColor = (z: string, logic: Logic) => (logic === "strength" ? TIER_COLOR : QUAD_COLOR)[z] || "#6366f1";
const zoneLabel = (z: string, logic: Logic) => (logic === "strength" ? (TIER_LABEL[z] || z) : z);
const metricOf = (e: RrgEntity, logic: Logic): number | null =>
  logic === "strength" ? (e.strengthScore ?? null) : (e.rsPct ?? null);

function RrgTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null;
  const p = payload[0]?.payload;
  if (!p) return null;
  return (
    <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg px-3 py-2 text-xs shadow-lg">
      <div className="font-bold text-gray-900 dark:text-white">{p.name}</div>
      <div className="text-gray-500 dark:text-gray-400">{p.quadrant}</div>
      <div className="tabular-nums">RS-Ratio {p.x?.toFixed(1)} · RS-Mom {p.y?.toFixed(1)}</div>
    </div>
  );
}

/** Tiny inline SVG sparkline (no chart lib) — coloured by net direction. */
function Sparkline({ values, w = 54, h = 16 }: { values?: number[]; w?: number; h?: number }) {
  if (!values || values.length < 2) return <span className="text-[10px] text-gray-300 dark:text-gray-600">—</span>;
  const min = Math.min(...values), max = Math.max(...values), span = max - min || 1;
  const pts = values.map((v, i) =>
    `${((i / (values.length - 1)) * w).toFixed(1)},${(h - ((v - min) / span) * h).toFixed(1)}`).join(" ");
  const up = values[values.length - 1] >= values[0];
  return (
    <svg width={w} height={h} className="flex-shrink-0" aria-label="delivery trend">
      <polyline points={pts} fill="none" stroke={up ? "#10b981" : "#f43f5e"} strokeWidth={1.5}
                strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

/** LEFT pane — ranked, scannable list. Logic-aware: 'strength' colours by tier
 *  and ranks by composite score; 'rotation' colours by RRG quadrant and ranks
 *  by RS%. The other lens is shown as a small confluence dot. */
function Leaderboard({ entities, logic, selected, onPick }: {
  entities: RrgEntity[]; logic: Logic; selected: string | null; onPick: (n: string) => void;
}) {
  const [zone, setZone] = useState<string>("All");
  const [q, setQ] = useState("");
  const order: readonly string[] = logic === "strength" ? TIER_ORDER : QUADRANTS;
  const present = order.filter(z => entities.some(e => zoneOf(e, logic) === z));
  const counts: Record<string, number> = {};
  for (const e of entities) { const z = zoneOf(e, logic); counts[z] = (counts[z] || 0) + 1; }
  const metrics = entities.map(e => metricOf(e, logic) ?? -1e9);
  const lo = Math.min(...metrics), hi = Math.max(...metrics);
  const barPct = (m: number | null) => (m == null ? 0 : hi > lo ? Math.round(((m - lo) / (hi - lo)) * 100) : 50);
  const ql = q.trim().toLowerCase();
  const ranked = [...entities].sort((a, b) => (metricOf(b, logic) ?? -1e9) - (metricOf(a, logic) ?? -1e9));
  const filtered = ranked.filter(e =>
    (zone === "All" || zoneOf(e, logic) === zone) && (!ql || e.name.toLowerCase().includes(ql)));
  return (
    <div>
      <div className="flex items-center gap-1.5 mb-2 flex-wrap">
        {(["All", ...present]).map(z => (
          <button key={z} onClick={() => setZone(z)}
            className={`px-2 py-0.5 rounded-full text-[11px] font-semibold border transition ${
              zone === z ? "bg-indigo-600 text-white border-indigo-600"
                         : "bg-gray-50 dark:bg-gray-700/50 text-gray-600 dark:text-gray-300 border-gray-200 dark:border-gray-700 hover:bg-gray-100 dark:hover:bg-gray-700"
            }`}>
            {z === "All" ? "All" : zoneLabel(z, logic)}{z !== "All" && counts[z] ? ` ${counts[z]}` : ""}
          </button>
        ))}
        <input value={q} onChange={e => setQ(e.target.value)} placeholder="Search…"
          className="ml-auto text-xs px-2 py-1 rounded-md border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900/50 text-gray-700 dark:text-gray-200 w-32 focus:outline-none focus:ring-1 focus:ring-indigo-400" />
      </div>
      {filtered.length === 0 ? (
        <div className="py-12 text-center text-sm text-gray-400">No matches.</div>
      ) : (
      <div className="max-h-[460px] overflow-y-auto divide-y divide-gray-100 dark:divide-gray-700/60 pr-1">
        {filtered.map(e => {
          const z = zoneOf(e, logic);
          const col = zoneColor(z, logic);
          const metric = metricOf(e, logic);
          const hasRrg = e.rsMomentum != null;
          const gaining = hasRrg && e.rsMomentum >= 100;
          const confColor = logic === "strength" ? QUAD_COLOR[e.quadrant] : (e.tier ? TIER_COLOR[e.tier] : null);
          const confTitle = logic === "strength"
            ? `Rotation: ${e.quadrant}`
            : `Strength: ${e.tier ? (TIER_LABEL[e.tier] || e.tier) : "—"}`;
          return (
            <button key={e.name} onClick={() => onPick(e.name)}
              className={`w-full flex items-center gap-3 px-1.5 py-2 text-left transition ${
                selected === e.name ? "bg-indigo-50/70 dark:bg-indigo-500/10" : "hover:bg-gray-50 dark:hover:bg-white/[0.03]"
              }`}>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold text-gray-900 dark:text-white truncate">{e.name}</span>
                  <span className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded flex-shrink-0"
                        style={{ color: col, backgroundColor: col + "22" }}>{zoneLabel(z, logic)}</span>
                  {confColor && <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: confColor }} title={confTitle} />}
                  {e.deliveryBuildup && <Truck className="w-3 h-3 text-indigo-500 flex-shrink-0" aria-label="delivery build-up" />}
                </div>
                <div className="mt-1 h-1.5 rounded-full bg-gray-100 dark:bg-gray-700 overflow-hidden">
                  <div className="h-full rounded-full" style={{ width: `${barPct(metric)}%`, backgroundColor: col }} />
                </div>
              </div>
              <span className={`flex items-center gap-1 text-xs font-semibold flex-shrink-0 w-[68px] justify-end ${
                !hasRrg ? "text-gray-400 dark:text-gray-500" : gaining ? "text-emerald-600 dark:text-emerald-400" : "text-rose-500"
              }`}>
                {hasRrg ? (gaining ? <TrendingUp className="w-3.5 h-3.5" /> : <TrendingDown className="w-3.5 h-3.5" />) : null}
                {hasRrg ? (gaining ? "gaining" : "fading") : "no data yet"}
              </span>
              <span className="text-[11px] text-gray-500 dark:text-gray-400 w-20 text-right tabular-nums flex-shrink-0 hidden sm:inline">
                {logic === "strength"
                  ? (e.strengthScore != null ? `Str ${e.strengthScore.toFixed(Math.abs(e.strengthScore) >= 10 ? 0 : 1)}` : "—")
                  : (e.rsPct != null ? `RS ${e.rsPct >= 0 ? "+" : ""}${e.rsPct.toFixed(1)}%` : "—")}
              </span>
            </button>
          );
        })}
      </div>
      )}
    </div>
  );
}

/** RIGHT pane — the winning-stocks shortlist for the picked group. */
function ShortlistPanel({ title, isLoading, data }: {
  title: string; isLoading: boolean; data?: { available?: boolean; stocks?: ShortlistStock[] };
}) {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-100 dark:border-gray-700 overflow-hidden lg:sticky lg:top-4">
      <div className="px-4 py-3 border-b border-gray-100 dark:border-gray-700 flex items-center gap-2">
        <TrendingUp className="w-4 h-4 text-emerald-500 flex-shrink-0" />
        <div className="min-w-0">
          <div className="text-sm font-bold text-gray-900 dark:text-white truncate">Winning stocks</div>
          <div className="text-[11px] text-gray-400 truncate">{title}</div>
        </div>
      </div>
      {isLoading ? (
        <div className="flex items-center justify-center py-10 text-gray-500"><Loader2 className="w-4 h-4 animate-spin mr-2" /> Ranking…</div>
      ) : !data?.available || !(data?.stocks?.length) ? (
        <div className="py-10 text-center text-sm text-gray-500">No rankable stocks here.</div>
      ) : (
        <div className="max-h-[520px] overflow-y-auto divide-y divide-gray-100 dark:divide-gray-700/60">
          {data.stocks.map((s, i) => (
            <div key={s.symbol} className="px-3 py-2 flex items-center gap-2.5 hover:bg-gray-50 dark:hover:bg-white/[0.03]">
              <span className="text-[11px] text-gray-400 w-4 tabular-nums flex-shrink-0">{i + 1}</span>
              <StockLogo symbol={s.symbol} name={s.name} size={26} shape="circle" />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1.5">
                  <span className="text-sm font-bold text-gray-900 dark:text-white truncate">{s.symbol}</span>
                  <ChartButton symbol={s.symbol} indicators={CHART_PRESET} />
                </div>
                <div className="text-[10px] text-gray-500 tabular-nums flex items-center gap-2">
                  <span className={s.rs != null && s.rs >= 0 ? "text-emerald-600" : "text-rose-500"}>
                    RS {s.rs != null ? fmtPct(s.rs) : "—"}
                  </span>
                  <span className="flex items-center gap-1" title="Delivery % (last ~12 sessions)">
                    Del {s.delivPct != null ? `${s.delivPct.toFixed(0)}%` : "—"}
                    <Sparkline values={s.delivTrend} />
                  </span>
                  {s.aboveTrend && <span className="text-indigo-500" title="Above 50-EMA">▲</span>}
                </div>
              </div>
              <span className="inline-block px-2 py-0.5 rounded-full text-xs font-bold bg-indigo-50 text-indigo-700 dark:bg-indigo-500/15 dark:text-indigo-300 tabular-nums flex-shrink-0">
                {s.score.toFixed(0)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function SectorRotation() {
  const [level, setLevel] = useState<Level>("sector");
  const [view, setView] = useState<"leaderboard" | "rrg">("leaderboard");
  const [logic, setLogic] = useState<Logic>("strength");   // default matches Market Sectors page
  const [tf, setTf] = useState<"short" | "mid" | "long">("short");
  const [selected, setSelected] = useState<string | null>(null);

  // Each query is gated to the level it feeds, so the expensive sub-industry
  // RRG build is never triggered for users who only look at sectors. React-Query
  // keeps each level's result cached, so switching back is instant within the
  // staleTime window.
  const funnelQ = useQuery(
    marketDataQueryOptions(["sector-rotation", "funnel", tf], () => api.sectorRotationFunnel(tf),
      { enabled: level === "sector" }),
  );
  const subRrgQ = useQuery(
    marketDataQueryOptions(["sector-rotation", "rrg", "subindustry", tf], () => api.sectorRotationRrg("subindustry", tf),
      { enabled: level === "subindustry" }),
  );
  const shortlistQ = useQuery(
    marketDataQueryOptions(
      ["sector-rotation", "shortlist", level, selected ?? ""],
      () => api.sectorRotationShortlist(level === "sector" ? { sector: selected as string } : { subIndustry: selected as string }),
      { enabled: !!selected },
    ),
  );

  const entities: RrgEntity[] = level === "sector" ? (funnelQ.data?.sectors ?? []) : (subRrgQ.data?.entities ?? []);
  const isLoading = level === "sector" ? funnelQ.isLoading : subRrgQ.isLoading;
  const isError   = level === "sector" ? funnelQ.isError   : subRrgQ.isError;
  const emptyNote = level === "subindustry" ? subRrgQ.data?.note : null;

  const points = entities.map(e => ({ x: e.rsRatio, y: e.rsMomentum, name: e.name, quadrant: e.quadrant }));
  const selectedEntity = entities.find(e => e.name === selected);
  const tail = (selectedEntity?.tail ?? []).map(p => ({ x: p.rsRatio, y: p.rsMomentum, name: selectedEntity?.name, quadrant: p.quadrant }));

  const onPick = (name: string) => setSelected(prev => (prev === name ? null : name));
  const switchLevel = (l: Level) => { setLevel(l); setSelected(null); };

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
            <Activity className="w-6 h-6 text-indigo-500" /> Sector Rotation Cockpit
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Pick a strong sector or sub-industry → see its strongest stocks on the right.
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {/* Logic: Strength (durable) vs Rotation (timing) */}
          <div className="flex items-center gap-1.5 bg-gray-100 dark:bg-gray-800 rounded-lg p-1">
            {([["strength", "Strength"], ["rotation", "Rotation"]] as const).map(([lg, lbl]) => (
              <button key={lg} onClick={() => setLogic(lg)}
                title={lg === "strength"
                  ? "Broad, durable strength (trend + breadth) — matches the Market Sectors page"
                  : "Relative-strength rotation timing vs Nifty"}
                className={`px-2.5 py-1.5 rounded-md text-xs font-semibold transition ${
                  logic === lg ? "bg-indigo-600 text-white" : "text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700"
                }`}>
                {lbl}
              </button>
            ))}
          </div>
          {/* Timeframe: long ≈ Market-Sectors strength, short = early rotation */}
          <div className="flex items-center gap-1.5 bg-gray-100 dark:bg-gray-800 rounded-lg p-1">
            {([["short", "1M"], ["mid", "3M"], ["long", "6M"]] as const).map(([t, lbl]) => (
              <button key={t} onClick={() => setTf(t)}
                title={t === "short" ? "1 month — rotation" : t === "mid" ? "3 months" : "6 months — long-term strength"}
                className={`px-2.5 py-1.5 rounded-md text-xs font-semibold transition ${
                  tf === t ? "bg-indigo-600 text-white" : "text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700"
                }`}>
                {lbl}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-1.5 bg-gray-100 dark:bg-gray-800 rounded-lg p-1">
            {(["sector", "subindustry"] as Level[]).map(l => (
              <button key={l} onClick={() => switchLevel(l)}
                className={`px-3 py-1.5 rounded-md text-xs font-semibold transition ${
                  level === l ? "bg-indigo-600 text-white" : "text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700"
                }`}>
                {l === "sector" ? "Sectors" : "Sub-industries"}
              </button>
            ))}
          </div>
        </div>
      </div>

      {isLoading && (
        <div className="flex items-center justify-center py-24 text-gray-500 dark:text-gray-400">
          <Loader2 className="w-5 h-5 animate-spin mr-2" /> Loading rotation…
        </div>
      )}
      {isError && (
        <div className="flex items-center justify-center py-24 text-rose-600 dark:text-rose-400">
          <AlertCircle className="w-5 h-5 mr-2" /> Could not load rotation data.
        </div>
      )}

      {!isLoading && !isError && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-5 items-start">
          {/* LEFT: leaderboard / RRG */}
          <div className="lg:col-span-2 bg-white dark:bg-gray-800 rounded-xl border border-gray-100 dark:border-gray-700 p-4">
            <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
              <div className="flex items-center gap-2">
                <h2 className="text-sm font-bold text-gray-900 dark:text-white">
                  {view === "rrg" ? "Relative Rotation Graph" : "Strength leaderboard"}
                  <span className="font-normal text-gray-400"> · vs NIFTY 50</span>
                </h2>
                <span className="text-[11px] text-gray-400">{entities.length} {level === "sector" ? "sectors" : "sub-industries"}</span>
              </div>
              <div className="flex items-center gap-1 bg-gray-100 dark:bg-gray-900/60 rounded-lg p-0.5">
                {(["leaderboard", "rrg"] as const).map(v => (
                  <button key={v} onClick={() => setView(v)}
                    className={`px-2.5 py-1 rounded-md text-[11px] font-semibold transition ${
                      view === v ? "bg-indigo-600 text-white" : "text-gray-500 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200"
                    }`}>
                    {v === "leaderboard" ? "Leaderboard" : "RRG"}
                  </button>
                ))}
              </div>
            </div>

            {entities.length === 0 ? (
              <div className="flex flex-col items-center justify-center text-center px-6 py-16">
                <AlertCircle className="w-6 h-6 text-gray-400 mb-2" />
                <p className="text-sm text-gray-500 dark:text-gray-400 max-w-sm">{emptyNote || "No rotation data available yet."}</p>
              </div>
            ) : view === "leaderboard" ? (
              <Leaderboard entities={entities} logic={logic} selected={selected} onPick={onPick} />
            ) : (
              <>
                <div className="flex flex-wrap gap-3 mb-2 text-[10px] text-gray-500 dark:text-gray-400">
                  {QUADRANTS.map(q => (
                    <span key={q} className="flex items-center gap-1">
                      <span className="w-2 h-2 rounded-full" style={{ backgroundColor: QUAD_COLOR[q] }} />{q}
                    </span>
                  ))}
                </div>
                <div className="relative">
                  <span className="absolute top-0 right-3 z-10 text-[10px] font-bold pointer-events-none" style={{ color: QUAD_COLOR.Leading }}>LEADING ↗ strong &amp; rising</span>
                  <span className="absolute top-0 left-12 z-10 text-[10px] font-bold pointer-events-none" style={{ color: QUAD_COLOR.Improving }}>↖ IMPROVING · turning up</span>
                  <span className="absolute bottom-8 right-3 z-10 text-[10px] font-bold pointer-events-none" style={{ color: QUAD_COLOR.Weakening }}>WEAKENING ↘ fading</span>
                  <span className="absolute bottom-8 left-12 z-10 text-[10px] font-bold pointer-events-none" style={{ color: QUAD_COLOR.Lagging }}>↙ LAGGING · weak</span>
                  <ResponsiveContainer width="100%" height={420}>
                    <ScatterChart margin={{ top: 10, right: 20, bottom: 20, left: 0 }}>
                      <ReferenceLine x={100} stroke="#9ca3af" strokeDasharray="3 3" />
                      <ReferenceLine y={100} stroke="#9ca3af" strokeDasharray="3 3" />
                      <XAxis type="number" dataKey="x" name="RS-Ratio" domain={["dataMin - 1", "dataMax + 1"]}
                             tick={{ fontSize: 11 }} label={{ value: "RS-Ratio →", position: "insideBottom", offset: -8, fontSize: 11 }} />
                      <YAxis type="number" dataKey="y" name="RS-Momentum" domain={["dataMin - 1", "dataMax + 1"]}
                             tick={{ fontSize: 11 }} label={{ value: "RS-Momentum →", angle: -90, position: "insideLeft", fontSize: 11 }} />
                      <ZAxis range={[60, 200]} />
                      <Tooltip content={<RrgTooltip />} cursor={{ strokeDasharray: "3 3" }} />
                      {tail.length > 1 && (
                        <Scatter data={tail} line={{ stroke: QUAD_COLOR[selectedEntity?.quadrant ?? "Leading"], strokeWidth: 2 }}
                                 fill={QUAD_COLOR[selectedEntity?.quadrant ?? "Leading"]} legendType="none" />
                      )}
                      <Scatter data={points} onClick={(d: any) => d?.name && onPick(d.name)}>
                        {points.map((p, i) => (
                          <Cell key={i} fill={QUAD_COLOR[p.quadrant] ?? "#6366f1"}
                                fillOpacity={selected && p.name !== selected ? 0.35 : 0.95}
                                stroke={p.name === selected ? "#111827" : "none"} strokeWidth={2} />
                        ))}
                      </Scatter>
                    </ScatterChart>
                  </ResponsiveContainer>
                </div>
              </>
            )}
            <p className="text-[11px] text-gray-400 mt-2">
              {view === "rrg"
                ? "Right = stronger than Nifty · up = gaining strength · click a point for its stocks."
                : logic === "strength"
                  ? "Strength — durable strength (trend + breadth), matches Market Sectors. Dot = its rotation zone (confluence)."
                  : "Rotation — relative strength vs Nifty + momentum (early timing). Dot = its strength tier (confluence)."}
            </p>
          </div>

          {/* RIGHT: winning stocks for the picked group */}
          <div className="lg:col-span-1">
            {selected ? (
              <ShortlistPanel title={selected} isLoading={shortlistQ.isLoading} data={shortlistQ.data} />
            ) : (
              <div className="bg-white dark:bg-gray-800 rounded-xl border border-dashed border-gray-200 dark:border-gray-700 p-8 text-center text-sm text-gray-500 dark:text-gray-400 lg:sticky lg:top-4">
                <MousePointerClick className="w-6 h-6 mx-auto mb-2 text-gray-400" />
                Click a {level === "sector" ? "sector" : "sub-industry"} on the left to see its strongest stocks.
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
