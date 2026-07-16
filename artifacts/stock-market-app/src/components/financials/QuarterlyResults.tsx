/**
 * QuarterlyResults — the detailed quarterly P&L parsed from the SEBI
 * Reg-33 (in-bse-fin) XBRL filing. This is the "filed results" view that
 * Yahoo can't provide: the full expense breakdown, current/deferred tax,
 * basic AND diluted EPS, segment results, and a standalone/consolidated
 * toggle. Distinct from the Yahoo-sourced "Income Statement" tab.
 *
 * Layout mirrors Screener.in's P&L: line items as rows, quarters as
 * columns (newest leftmost). Row set adapts to the filing format
 * (standard Ind-AS vs the banking Form-B layout).
 */
import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, type QuarterlyResultRow } from "@/lib/api";
import { Loader2, AlertCircle } from "lucide-react";

interface Props {
  symbol: string;
}

interface RowDef {
  key:   string;
  label: string;
  bold?: boolean;   // subtotal / headline line
  eps?:  boolean;   // render as ₹ per share, not ₹ Cr
}

// Standard Ind-AS P&L line order (non-financial companies).
const STANDARD_ROWS: RowDef[] = [
  { key: "revenueFromOperations",        label: "Revenue from Operations" },
  { key: "otherIncome",                  label: "Other Income" },
  { key: "totalIncome",                  label: "Total Income", bold: true },
  { key: "costOfMaterials",              label: "Cost of Materials Consumed" },
  { key: "purchasesOfStockInTrade",      label: "Purchases of Stock-in-Trade" },
  { key: "changesInInventories",         label: "Changes in Inventories" },
  { key: "employeeBenefitExpense",       label: "Employee Benefit Expense" },
  { key: "financeCosts",                 label: "Finance Costs" },
  { key: "depreciation",                 label: "Depreciation & Amortisation" },
  { key: "otherExpenses",                label: "Other Expenses" },
  { key: "totalExpenses",                label: "Total Expenses", bold: true },
  { key: "profitBeforeExceptionalAndTax",label: "Profit before Exceptional & Tax" },
  { key: "exceptionalItems",             label: "Exceptional Items" },
  { key: "profitBeforeTax",              label: "Profit before Tax", bold: true },
  { key: "taxExpense",                   label: "Tax Expense" },
  { key: "netProfit",                    label: "Net Profit", bold: true },
  { key: "basicEps",                     label: "Basic EPS (₹)", eps: true },
  { key: "dilutedEps",                   label: "Diluted EPS (₹)", eps: true },
];

// Banking / FI Form-B layout.
const BANKING_ROWS: RowDef[] = [
  { key: "interestEarned",   label: "Interest Earned" },
  { key: "otherIncome",      label: "Other Income" },
  { key: "totalIncome",      label: "Total Income", bold: true },
  { key: "interestExpended", label: "Interest Expended" },
  { key: "operatingExpenses",label: "Operating Expenses" },
  { key: "totalExpenditure", label: "Total Expenditure", bold: true },
  { key: "operatingProfit",  label: "Operating Profit (pre-provision)", bold: true },
  { key: "provisions",       label: "Provisions & Contingencies" },
  { key: "profitBeforeTax",  label: "Profit before Tax", bold: true },
  { key: "taxExpense",       label: "Tax Expense" },
  { key: "netProfit",        label: "Net Profit", bold: true },
  { key: "basicEps",         label: "Basic EPS (₹)", eps: true },
  { key: "dilutedEps",       label: "Diluted EPS (₹)", eps: true },
];

function fCr(v: number | null | undefined): string {
  if (v == null) return "—";
  return v.toLocaleString("en-IN", { minimumFractionDigits: 0, maximumFractionDigits: 0 });
}

function fEps(v: number | null | undefined): string {
  if (v == null) return "—";
  return `₹${v.toFixed(2)}`;
}

function qLabel(iso: string): string {
  const d = new Date(iso);
  const m = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"][d.getMonth()];
  return `${m} '${String(d.getFullYear()).slice(2)}`;
}

export default function QuarterlyResults({ symbol }: Props) {
  const [basis, setBasis] = useState<"consolidated" | "standalone">("consolidated");

  const { data, isLoading, error } = useQuery({
    queryKey: ["quarterly-results", symbol, basis],
    queryFn: () => api.stockQuarterlyResults(symbol, { basis, quarters: 12 }),
    enabled: !!symbol,
    staleTime: 60 * 60 * 1000,   // filings are immutable; cache an hour
  });

  const rows = data?.rows ?? [];

  // Pick the row template from the latest filing's format. Always keep the
  // subtotal (bold) and EPS rows to preserve the P&L skeleton; for detail
  // lines, drop any that are zero/blank in EVERY quarter — a services firm
  // reports ₹0 for Cost of Materials / Inventory every quarter, and a wall
  // of zeros is noise (this mirrors how Screener hides irrelevant lines).
  // Rows with a real value in any quarter stay — e.g. Exceptional Items
  // that is 0 most quarters but −958 in one.
  const visibleRows = useMemo<RowDef[]>(() => {
    if (!rows.length) return [];
    const template = rows[0].format === "banking" ? BANKING_ROWS : STANDARD_ROWS;
    return template.filter(r =>
      r.bold || r.eps ||
      rows.some(q => { const v = q.lineItems[r.key]; return v != null && v !== 0; }),
    );
  }, [rows]);

  const latestSegments = rows[0]?.segments ?? null;

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 p-6 text-sm text-gray-500">
        <Loader2 className="w-4 h-4 animate-spin" /> Loading filed results…
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
  if (!rows.length) {
    return (
      <div className="py-6 text-center text-sm text-gray-400">
        No filed quarterly results available for {symbol}. SEBI Reg-33 XBRL is
        parsed for most NSE-listed companies; insurers and some newly-listed
        names may not be covered yet.
      </div>
    );
  }

  const bothBases = (data?.available?.length ?? 0) > 1;

  return (
    <div className="space-y-4">
      {/* Header: title, basis toggle, source/period note */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-gray-700">Quarterly Results</h3>
          <p className="text-xs text-gray-400">
            From SEBI filing · ₹ Crores · {data?.basis === "consolidated" ? "Consolidated" : "Standalone"}
            {rows[0]?.audited != null && ` · ${rows[0].audited ? "Audited" : "Unaudited"} (latest)`}
          </p>
        </div>
        {bothBases && (
          <div className="flex bg-gray-100 rounded-lg p-0.5 text-xs font-medium">
            {(["consolidated", "standalone"] as const).map(b => (
              <button
                key={b}
                onClick={() => setBasis(b)}
                disabled={!data?.available?.includes(b)}
                className={`px-3 py-1.5 rounded-md transition-all capitalize disabled:opacity-40 ${
                  data?.basis === b ? "bg-white text-indigo-700 shadow-sm" : "text-gray-500 hover:text-gray-700"
                }`}
              >
                {b}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Pivoted P&L table */}
      <div className="overflow-x-auto bg-white rounded-xl border border-gray-100">
        <table className="min-w-full text-sm">
          <thead className="bg-gray-50">
            <tr>
              <th className="sticky left-0 z-10 bg-gray-50 border-r border-gray-100 text-left px-3 py-2.5 text-xs text-gray-500 font-semibold uppercase">
                Line Item
              </th>
              {rows.map(q => (
                <th key={q.periodEnd} className="text-right px-3 py-2.5 text-xs text-gray-500 font-semibold whitespace-nowrap">
                  {qLabel(q.periodEnd)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visibleRows.map(r => (
              <tr key={r.key} className={`border-t border-gray-50 ${r.bold ? "bg-gray-50/40" : ""}`}>
                {/* Sticky cells MUST be fully opaque — a translucent bg
                    (bg-gray-50/40) lets the scrolled columns bleed through
                    the pinned label on phones, which read as garbage values
                    next to "Total Income". */}
                <td title={r.label}
                    className={`sticky left-0 z-10 px-3 py-2 whitespace-nowrap border-r border-gray-100 max-w-[45vw] overflow-hidden text-ellipsis sm:max-w-none ${r.bold ? "bg-gray-50 font-semibold text-gray-800" : "bg-white text-gray-600"}`}>
                  {r.label}
                </td>
                {rows.map(q => {
                  const v = q.lineItems[r.key];
                  return (
                    <td key={q.periodEnd}
                        className={`px-3 py-2 text-right tabular-nums whitespace-nowrap ${
                          r.bold ? "font-semibold text-gray-900" : "text-gray-700"
                        } ${v != null && v < 0 ? "text-red-500" : ""}`}>
                      {r.eps ? fEps(v) : fCr(v)}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Segment results (latest quarter) */}
      {latestSegments && latestSegments.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-100 p-4">
          <p className="text-xs text-gray-500 mb-3 font-medium">
            Segment Results — {qLabel(rows[0].periodEnd)} (₹ Crores)
          </p>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b-2 border-gray-100">
                <th className="text-left py-2 text-xs text-gray-500 font-semibold uppercase">Segment</th>
                <th className="text-right py-2 text-xs text-gray-500 font-semibold uppercase">Revenue</th>
                <th className="text-right py-2 text-xs text-gray-500 font-semibold uppercase">Result (PBIT)</th>
              </tr>
            </thead>
            <tbody>
              {latestSegments.map((s, i) => (
                <tr key={i} className="border-b border-gray-50">
                  <td className="py-2 text-gray-700">{s.name}</td>
                  <td className="py-2 text-right tabular-nums text-gray-900">{fCr(s.revenue)}</td>
                  <td className={`py-2 text-right tabular-nums ${s.result != null && s.result < 0 ? "text-red-500" : "text-gray-700"}`}>
                    {fCr(s.result)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="text-[11px] text-gray-400 px-1">
        * Parsed from the company's SEBI quarterly-results XBRL filing. Values in ₹ Crores; EPS in ₹/share.
      </p>
    </div>
  );
}
