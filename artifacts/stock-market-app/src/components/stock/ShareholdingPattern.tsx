/**
 * ShareholdingPattern — quarterly Promoter / FII / DII / Public %
 * breakdown for a single security.
 *
 * Layout strategy
 * ---------------
 * Desktop (md+): pivot table with quarters as columns — identical to
 *   Screener / Tickertape power-user view.
 * Mobile (< md): quarter-picker bar + card rows with visual % bars
 *   and delta chips. No horizontal scroll; one quarter visible at a time.
 */
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, type ShareholdingRow, type ShareholdingNamedHolder } from "@/lib/api";
import {
  AlertCircle, Users, Loader2, ShieldAlert, Lock,
  ChevronLeft, ChevronRight, TrendingUp, TrendingDown, Minus,
} from "lucide-react";


interface Props {
  symbol: string;
}


// ── Bucket definitions ────────────────────────────────────────────────────

type BucketKey = "promoterPct" | "fiiPct" | "diiPct" | "govtPct" | "publicPct";

interface Bucket {
  key:      BucketKey;
  label:    string;
  dotClass: string;
  barClass: string;
  core:     boolean;
}

const BUCKETS: Bucket[] = [
  { key: "promoterPct", label: "Promoters",  dotClass: "bg-indigo-500",  barClass: "bg-indigo-500",  core: true  },
  { key: "fiiPct",      label: "FIIs",       dotClass: "bg-emerald-500", barClass: "bg-emerald-500", core: true  },
  { key: "diiPct",      label: "DIIs",       dotClass: "bg-amber-500",   barClass: "bg-amber-500",   core: true  },
  { key: "govtPct",     label: "Government", dotClass: "bg-rose-400",    barClass: "bg-rose-400",    core: false },
  { key: "publicPct",   label: "Public",     dotClass: "bg-sky-500",     barClass: "bg-sky-500",     core: true  },
];

const FLAG_LABELS: Record<string, string> = {
  hasOutstandingEsop:          "ESOP",
  hasWarrants:                 "Warrants",
  hasConvertibles:             "Convertibles",
  hasDifferentialVotingRights: "DVR",
  hasDepositoryReceipts:       "ADR/GDR",
  hasPartlyPaidShares:         "Partly-paid",
  isPsu:                       "PSU",
  isSme:                       "SME",
};

const GROUP_CLASS: Record<string, string> = {
  "FII / FPI":   "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
  "Mutual Fund": "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  "Insurance":   "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  "Public":      "bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300",
  "Other Indian":"bg-indigo-100 text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300",
};


// ── Helpers ───────────────────────────────────────────────────────────────

function quarterLabel(iso: string): string {
  const [y, m] = iso.split("-");
  const months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  return `${months[parseInt(m, 10) - 1]} ${y}`;
}


function holderDelta(
  holder: ShareholdingNamedHolder,
  prevByName: Map<string, number>,
): { text: string; cls: string } | null {
  if (holder.pct == null) return null;
  const prev = prevByName.get(holder.name.trim().toLowerCase());
  if (prev === undefined) return { text: "NEW", cls: "text-indigo-600 dark:text-indigo-400" };
  const d = holder.pct - prev;
  if (Math.abs(d) < 0.01) return { text: "—", cls: "text-gray-400" };
  const sign = d > 0 ? "+" : "";
  return {
    text: `${sign}${d.toFixed(2)}`,
    cls: d > 0 ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400",
  };
}


// ── Desktop table cells ───────────────────────────────────────────────────

function PctCell({ value }: { value: number | null }) {
  if (value === null || value === undefined) {
    return <td className="px-3 py-2 text-right text-gray-400 dark:text-gray-600">—</td>;
  }
  return (
    <td className="px-3 py-2 text-right tabular-nums text-gray-900 dark:text-gray-100">
      {value.toFixed(2)}%
    </td>
  );
}

function CountCell({ value }: { value: number | null }) {
  if (value === null || value === undefined) {
    return <td className="px-3 py-2 text-right text-gray-400 dark:text-gray-600">—</td>;
  }
  return (
    <td className="px-3 py-2 text-right tabular-nums text-gray-500 dark:text-gray-400">
      {value.toLocaleString("en-IN")}
    </td>
  );
}


// ── Mobile: quarter picker ────────────────────────────────────────────────
// Simple prev/next navigator — no scrollable pill strip that goes off-screen.

function QuarterPicker({
  rows,
  selectedIdx,
  onSelect,
}: {
  rows: ShareholdingRow[];
  selectedIdx: number;
  onSelect: (i: number) => void;
}) {
  const canOlder = selectedIdx < rows.length - 1;
  const canNewer = selectedIdx > 0;
  const current = rows[selectedIdx];
  return (
    <div className="flex items-center justify-between gap-3 px-4 py-2.5 bg-gray-50 dark:bg-gray-900/60 border-b border-gray-100 dark:border-gray-700">
      {/* ← Older */}
      <button
        disabled={!canOlder}
        onClick={() => onSelect(selectedIdx + 1)}
        className="flex items-center gap-1 text-xs font-medium px-2 py-1.5 rounded-md disabled:opacity-30 text-gray-500 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors"
        aria-label="Older quarter"
      >
        <ChevronLeft className="w-3.5 h-3.5" />
        Older
      </button>

      {/* Current quarter label + counter */}
      <div className="flex flex-col items-center">
        <span className="text-sm font-semibold text-gray-900 dark:text-gray-100">
          {current ? quarterLabel(current.asOnDate) : "—"}
        </span>
        <span className="text-[10px] text-gray-400 dark:text-gray-500 tabular-nums">
          {selectedIdx + 1} / {rows.length}
        </span>
      </div>

      {/* Newer → */}
      <button
        disabled={!canNewer}
        onClick={() => onSelect(selectedIdx - 1)}
        className="flex items-center gap-1 text-xs font-medium px-2 py-1.5 rounded-md disabled:opacity-30 text-gray-500 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors"
        aria-label="Newer quarter"
      >
        Newer
        <ChevronRight className="w-3.5 h-3.5" />
      </button>
    </div>
  );
}


// ── Mobile: bucket card row ───────────────────────────────────────────────

function BucketCard({
  bucket,
  value,
  prevValue,
  maxValue,
}: {
  bucket: Bucket;
  value: number | null;
  prevValue: number | null;
  maxValue: number;
}) {
  const delta = value != null && prevValue != null ? value - prevValue : null;
  const barWidth = value != null && maxValue > 0 ? Math.max(2, (value / maxValue) * 100) : 0;

  return (
    <div className="flex items-center gap-3 px-4 py-3">
      <span className={`w-2.5 h-2.5 rounded-full shrink-0 ${bucket.dotClass}`} />
      <span className="w-24 shrink-0 text-sm font-medium text-gray-700 dark:text-gray-200">
        {bucket.label}
      </span>

      {/* Visual bar */}
      <div className="flex-1 h-2 bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-300 ${bucket.barClass}`}
          style={{ width: value != null ? `${barWidth}%` : "0%" }}
        />
      </div>

      {/* Value + delta */}
      <div className="flex items-center gap-1.5 min-w-[80px] justify-end">
        <span className="text-sm font-semibold tabular-nums text-gray-900 dark:text-gray-100">
          {value != null ? `${value.toFixed(2)}%` : "—"}
        </span>
        {delta != null && Math.abs(delta) >= 0.01 && (
          <span
            className={`text-[11px] tabular-nums font-medium flex items-center gap-0.5 ${
              delta > 0
                ? "text-emerald-600 dark:text-emerald-400"
                : "text-rose-600 dark:text-rose-400"
            }`}
          >
            {delta > 0
              ? <TrendingUp className="w-3 h-3" />
              : <TrendingDown className="w-3 h-3" />}
            {Math.abs(delta).toFixed(2)}
          </span>
        )}
        {delta != null && Math.abs(delta) < 0.01 && (
          <Minus className="w-3 h-3 text-gray-400" />
        )}
      </div>
    </div>
  );
}


// ── Mobile: pledge row ────────────────────────────────────────────────────

function PledgeCard({ value, prevValue }: { value: number | null; prevValue: number | null }) {
  const delta = value != null && prevValue != null ? value - prevValue : null;
  return (
    <div className="flex items-center gap-3 px-4 py-3 bg-rose-50/70 dark:bg-rose-900/10">
      <ShieldAlert className="w-4 h-4 text-rose-500 shrink-0" />
      <span className="flex-1 text-sm font-medium text-rose-700 dark:text-rose-300">
        Promoter Pledge
      </span>
      <div className="flex items-center gap-1.5">
        <span className={`text-sm font-semibold tabular-nums ${
          value && value > 0 ? "text-rose-600 dark:text-rose-400" : "text-gray-500 dark:text-gray-400"
        }`}>
          {value != null ? `${value.toFixed(2)}%` : "—"}
        </span>
        {delta != null && Math.abs(delta) >= 0.01 && (
          <span className={`text-[11px] tabular-nums font-medium ${
            delta > 0 ? "text-rose-600 dark:text-rose-400" : "text-emerald-600 dark:text-emerald-400"
          }`}>
            {delta > 0 ? "▲" : "▼"}{Math.abs(delta).toFixed(2)}
          </span>
        )}
      </div>
    </div>
  );
}


// ── Mobile: shareholders row ──────────────────────────────────────────────

function ShareholdersCard({ value }: { value: number | null }) {
  if (value == null) return null;
  return (
    <div className="flex items-center gap-3 px-4 py-3 border-t border-gray-100 dark:border-gray-700">
      <Users className="w-4 h-4 text-gray-400 shrink-0" />
      <span className="flex-1 text-sm text-gray-500 dark:text-gray-400">No. of Shareholders</span>
      <span className="text-sm tabular-nums text-gray-600 dark:text-gray-300">
        {value.toLocaleString("en-IN")}
      </span>
    </div>
  );
}


// ── Mobile: donut summary ─────────────────────────────────────────────────

function DonutSummary({ row, visibleBuckets }: { row: ShareholdingRow; visibleBuckets: Bucket[] }) {
  const total = visibleBuckets.reduce((s, b) => s + (row[b.key] ?? 0), 0);
  if (total < 90) return null;

  let cumulativeDeg = 0;
  const segments = visibleBuckets
    .filter((b) => (row[b.key] ?? 0) > 0)
    .map((b) => {
      const pct = (row[b.key] ?? 0);
      const deg = (pct / 100) * 360;
      const start = cumulativeDeg;
      cumulativeDeg += deg;
      return { ...b, pct, start, deg };
    });

  const gradientParts = segments.map((s) => {
    const colorMap: Record<string, string> = {
      "bg-indigo-500": "#6366f1",
      "bg-emerald-500": "#10b981",
      "bg-amber-500": "#f59e0b",
      "bg-rose-400": "#fb7185",
      "bg-sky-500": "#0ea5e9",
    };
    const color = colorMap[s.dotClass] ?? "#9ca3af";
    return `${color} ${s.start}deg ${s.start + s.deg}deg`;
  });

  return (
    <div className="flex items-center gap-4 px-4 py-3 border-b border-gray-100 dark:border-gray-700">
      <div
        className="w-14 h-14 rounded-full shrink-0"
        style={{
          background: `conic-gradient(${gradientParts.join(", ")})`,
          WebkitMaskImage: "radial-gradient(circle, transparent 45%, black 45%)",
          maskImage: "radial-gradient(circle, transparent 45%, black 45%)",
        }}
      />
      <div className="flex flex-wrap gap-x-3 gap-y-1">
        {segments.map((s) => {
          const colorMap: Record<string, string> = {
            "bg-indigo-500": "text-indigo-600 dark:text-indigo-400",
            "bg-emerald-500": "text-emerald-600 dark:text-emerald-400",
            "bg-amber-500": "text-amber-600 dark:text-amber-400",
            "bg-rose-400": "text-rose-500 dark:text-rose-400",
            "bg-sky-500": "text-sky-600 dark:text-sky-400",
          };
          return (
            <div key={s.key} className="flex items-center gap-1 text-xs">
              <span className={`w-2 h-2 rounded-full ${s.dotClass}`} />
              <span className="text-gray-600 dark:text-gray-300">{s.label}</span>
              <span className={`font-semibold tabular-nums ${colorMap[s.dotClass] ?? ""}`}>
                {s.pct.toFixed(1)}%
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}


// ── Shared: structure strip ───────────────────────────────────────────────

function StructureStrip({ row }: { row: ShareholdingRow }) {
  const stats: { label: string; value: string }[] = [];
  if (row.dematPct != null) stats.push({ label: "Demat", value: `${row.dematPct.toFixed(1)}%` });
  if (row.lockedInPct != null && row.lockedInPct > 0.01)
    stats.push({ label: "Locked-in", value: `${row.lockedInPct.toFixed(1)}%` });
  const fpi = row.details?.fpiLimits;
  if (fpi?.limitsUtilizedPct != null && fpi?.boardApprovedPct != null)
    stats.push({ label: "FII limit", value: `${fpi.limitsUtilizedPct.toFixed(1)}% / ${fpi.boardApprovedPct.toFixed(0)}%` });

  const flags = Object.entries(row.details?.flags ?? {})
    .filter(([k, v]) => v && FLAG_LABELS[k])
    .map(([k]) => FLAG_LABELS[k]);

  if (!stats.length && !flags.length) return null;

  return (
    <div className="px-4 py-3 border-t border-gray-100 dark:border-gray-700 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs">
      {stats.map((s) => (
        <span key={s.label} className="text-gray-500 dark:text-gray-400">
          {s.label}: <span className="font-medium text-gray-800 dark:text-gray-200 tabular-nums">{s.value}</span>
        </span>
      ))}
      {flags.length > 0 && (
        <span className="flex flex-wrap items-center gap-1.5">
          {flags.map((f) => (
            <span key={f} className="px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300">
              {f}
            </span>
          ))}
        </span>
      )}
    </div>
  );
}


// ── Shared: top disclosed holders ─────────────────────────────────────────

function TopHolders({ rows }: { rows: ShareholdingRow[] }) {
  const latest = rows[0];
  const holders = (latest?.details?.namedHolders ?? []).filter((h) => h.pct != null);
  if (!holders.length) return null;

  const prevByName = new Map<string, number>();
  for (const h of rows[1]?.details?.namedHolders ?? []) {
    if (h.pct != null) prevByName.set(h.name.trim().toLowerCase(), h.pct);
  }

  const top = holders.slice(0, 12);
  return (
    <div className="px-4 py-4 border-t border-gray-100 dark:border-gray-700">
      <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-0.5">
        Top Disclosed Holders
      </h4>
      <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
        As of {quarterLabel(latest.asOnDate)}. Δ vs previous quarter.
      </p>
      <div className="space-y-1.5">
        {top.map((h) => {
          const delta = holderDelta(h, prevByName);
          return (
            <div key={`${h.name}-${h.shares}`} className="flex items-center gap-2 text-sm">
              <span
                className={`text-[10px] px-1.5 py-0.5 rounded font-medium shrink-0 ${
                  GROUP_CLASS[h.group] ?? "bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300"
                }`}
              >
                {h.group}
              </span>
              <span className="flex-1 truncate text-gray-700 dark:text-gray-200 text-xs" title={h.name}>
                {h.name}
              </span>
              <span className="tabular-nums font-medium text-gray-900 dark:text-gray-100 text-xs">
                {h.pct!.toFixed(2)}%
              </span>
              {delta && (
                <span className={`tabular-nums text-xs w-10 text-right ${delta.cls}`}>
                  {delta.text}
                </span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}


// ── Main component ────────────────────────────────────────────────────────

export default function ShareholdingPattern({ symbol }: Props) {
  const [view, setView] = useState<"quarterly" | "yearly">("quarterly");
  const [forceRefresh, setForceRefresh] = useState(false);
  const [mobileQIdx, setMobileQIdx] = useState(0);

  const { data, isLoading, error, isFetching } = useQuery({
    queryKey: ["shareholding", symbol, view, forceRefresh],
    queryFn: () => {
      const opts = { view, quarters: 32, force: forceRefresh };
      if (forceRefresh) setTimeout(() => setForceRefresh(false), 0);
      return api.stockShareholding(symbol, opts);
    },
    enabled: !!symbol,
    staleTime: 7 * 24 * 3600 * 1000,
  });

  const handleForceRefresh = () => setForceRefresh(true);

  const ordered = useMemo<ShareholdingRow[]>(() => {
    if (!data?.rows) return [];
    return data.rows;
  }, [data]);

  const visibleBuckets = useMemo(
    () => BUCKETS.filter((b) => b.core || ordered.some((r) => r[b.key] != null)),
    [ordered],
  );

  const showPledge = useMemo(
    () => ordered.some((r) => r.promoterPledgePct != null),
    [ordered],
  );

  // Clamp mobile index after data load.
  const safeQIdx = Math.min(mobileQIdx, Math.max(0, ordered.length - 1));
  const mobileRow = ordered[safeQIdx] ?? null;
  const mobilePrevRow = ordered[safeQIdx + 1] ?? null;

  // Max % across all buckets for the current mobile quarter (normalises bars).
  const mobileMaxPct = useMemo(() => {
    if (!mobileRow) return 100;
    return Math.max(...visibleBuckets.map((b) => mobileRow[b.key] ?? 0), 1);
  }, [mobileRow, visibleBuckets]);

  // ── loading / error / empty states ──
  if (isLoading) {
    return (
      <div className="flex items-center gap-2 p-6 text-sm text-gray-500">
        <Loader2 className="w-4 h-4 animate-spin" /> Loading shareholding pattern…
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center gap-2 text-amber-600 bg-amber-50 border border-amber-200 rounded-lg p-3 text-sm">
        <AlertCircle className="w-4 h-4" /> {(error as Error).message}
      </div>
    );
  }

  if (!ordered.length) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-1">
          Shareholding Pattern
        </h3>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          No data available for {symbol}. Try refreshing in a moment.
        </p>
        <button
          onClick={handleForceRefresh}
          className="mt-3 text-xs px-3 py-1.5 rounded-md bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600"
        >
          Refresh
        </button>
      </div>
    );
  }

  // ── shared header ──
  const Header = (
    <div className="px-4 py-4 flex flex-wrap items-center justify-between gap-3 border-b border-gray-200 dark:border-gray-700">
      <div>
        <h3 className="text-base font-semibold text-gray-900 dark:text-gray-100">
          Shareholding Pattern
        </h3>
        <p className="text-xs text-gray-500 dark:text-gray-400">Numbers in percentages</p>
      </div>
      <div className="flex items-center gap-2 flex-wrap">
        {data?.sources?.length ? (
          <span className="text-[10px] uppercase tracking-wide px-2 py-1 rounded bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300">
            {data.sources.join(" + ")}
          </span>
        ) : null}
        <div className="inline-flex rounded-md border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900 text-xs font-medium">
          <button
            onClick={() => setView("quarterly")}
            className={`px-3 py-1.5 rounded-md transition-colors ${
              view === "quarterly"
                ? "bg-indigo-50 dark:bg-indigo-900/40 text-indigo-700 dark:text-indigo-200"
                : "text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
            }`}
          >
            Quarterly
          </button>
          <button
            onClick={() => setView("yearly")}
            className={`px-3 py-1.5 rounded-md transition-colors ${
              view === "yearly"
                ? "bg-indigo-50 dark:bg-indigo-900/40 text-indigo-700 dark:text-indigo-200"
                : "text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
            }`}
          >
            Yearly
          </button>
        </div>
        <button
          onClick={handleForceRefresh}
          disabled={isFetching}
          className="text-xs px-3 py-1.5 rounded-md bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 disabled:opacity-50"
        >
          {isFetching ? "Refreshing…" : "Refresh"}
        </button>
      </div>
    </div>
  );

  // ── footer note (shared) ──
  const Footer = (
    <div className="px-4 py-2 text-[11px] text-gray-400 dark:text-gray-500 border-t border-gray-100 dark:border-gray-700">
      * Categories follow SEBI LODR filings. Pledge / demat / holder details from XBRL; classifications may shift across periods.
    </div>
  );

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
      {Header}

      {/* ── MOBILE layout (hidden on md+) ── */}
      <div className="block md:hidden">
        {/* Quarter picker */}
        <QuarterPicker
          rows={ordered}
          selectedIdx={safeQIdx}
          onSelect={setMobileQIdx}
        />

        {mobileRow && (
          <>
            {/* Donut overview */}
            <DonutSummary row={mobileRow} visibleBuckets={visibleBuckets} />

            {/* Delta legend */}
            {mobilePrevRow && (
              <p className="px-4 pt-2 text-[11px] text-gray-400 dark:text-gray-500">
                Δ vs {quarterLabel(mobilePrevRow.asOnDate)}
              </p>
            )}

            {/* Bucket rows */}
            <div className="divide-y divide-gray-50 dark:divide-gray-700/60">
              {visibleBuckets.map((b) => (
                <BucketCard
                  key={b.key}
                  bucket={b}
                  value={mobileRow[b.key] ?? null}
                  prevValue={mobilePrevRow ? (mobilePrevRow[b.key] ?? null) : null}
                  maxValue={mobileMaxPct}
                />
              ))}

              {showPledge && (
                <PledgeCard
                  value={mobileRow.promoterPledgePct ?? null}
                  prevValue={mobilePrevRow?.promoterPledgePct ?? null}
                />
              )}

              {ordered.some((r) => r.numShareholders != null) && (
                <ShareholdersCard value={mobileRow.numShareholders ?? null} />
              )}
            </div>

            <StructureStrip row={mobileRow} />
          </>
        )}

        {/* Top holders always uses latest quarter regardless of selected */}
        <TopHolders rows={ordered} />
      </div>

      {/* ── DESKTOP layout (hidden below md) ── */}
      <div className="hidden md:block">
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="bg-gray-50 dark:bg-gray-900/40">
              <tr>
                <th className="sticky left-0 z-10 bg-gray-50 dark:bg-gray-900/40 px-3 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide" />
                {ordered.map((r) => (
                  <th key={r.asOnDate}
                      className="px-3 py-2 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                    {quarterLabel(r.asOnDate)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
              {visibleBuckets.map((b, i) => {
                const rowBg = i % 2 === 0
                  ? "bg-white dark:bg-gray-800"
                  : "bg-gray-50 dark:bg-gray-900";
                return (
                  <tr key={b.key} className={rowBg}>
                    <td className={`sticky left-0 z-10 ${rowBg} px-3 py-2 font-medium text-gray-700 dark:text-gray-200`}>
                      <span className="inline-flex items-center gap-2">
                        <span className={`w-2 h-2 rounded-full ${b.dotClass}`} />
                        {b.label}
                      </span>
                    </td>
                    {ordered.map((r) => (
                      <PctCell key={r.asOnDate} value={r[b.key]} />
                    ))}
                  </tr>
                );
              })}
              {showPledge && (
                <tr className="bg-rose-50/60 dark:bg-rose-900/10">
                  <td className="sticky left-0 z-10 bg-rose-50/60 dark:bg-rose-900/10 px-3 py-2 font-medium text-rose-700 dark:text-rose-300">
                    <span className="inline-flex items-center gap-2">
                      <ShieldAlert className="w-3.5 h-3.5" />
                      Promoter Pledge
                    </span>
                  </td>
                  {ordered.map((r) => {
                    const v = r.promoterPledgePct;
                    return (
                      <td key={r.asOnDate}
                          className={`px-3 py-2 text-right tabular-nums ${
                            v && v > 0
                              ? "text-rose-600 dark:text-rose-400 font-semibold"
                              : "text-gray-500 dark:text-gray-400"
                          }`}>
                        {v == null ? "—" : `${v.toFixed(2)}%`}
                      </td>
                    );
                  })}
                </tr>
              )}
              {ordered.some((r) => r.numShareholders != null) && (
                <tr className="bg-white dark:bg-gray-800">
                  <td className="sticky left-0 z-10 bg-white dark:bg-gray-800 px-3 py-2 font-medium text-gray-500 dark:text-gray-400">
                    <span className="inline-flex items-center gap-2">
                      <Users className="w-3.5 h-3.5" />
                      No. of Shareholders
                    </span>
                  </td>
                  {ordered.map((r) => (
                    <CountCell key={r.asOnDate} value={r.numShareholders} />
                  ))}
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {ordered[0] && <StructureStrip row={ordered[0]} />}
        <TopHolders rows={ordered} />
      </div>

      {Footer}
    </div>
  );
}
