import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchApi } from "@/lib/api";
import { PageHeader, PillTabs, Card, Loading, EmptyState, fmtNum } from "../_shared";
import { Briefcase } from "lucide-react";

type DealFilter = "all" | "buy" | "sell";
type TypeFilter = "all" | "bulk" | "block";

interface RawDeal {
  type: "bulk" | "block";
  date: string;
  symbol: string;
  name?: string;
  client?: string;
  side?: string;        // "BUY" | "SELL"
  quantity?: number;
  price?: number;
}

interface DealsResponse {
  bulk: RawDeal[];
  block: RawDeal[];
  total?: number;
  refreshedAt?: string;
}

interface NormDeal extends RawDeal {
  valueCr: number;       // ₹ Crores = qty * price / 1e7
}

function normalize(rs: RawDeal[] = [], type: "bulk" | "block"): NormDeal[] {
  return rs.map(r => {
    const qty = r.quantity ?? 0;
    const price = r.price ?? 0;
    return { ...r, type, valueCr: (qty * price) / 1e7 };
  });
}

export default function BulkBlockDeals() {
  const [actionFilter, setActionFilter] = useState<DealFilter>("all");
  const [typeFilter, setTypeFilter] = useState<TypeFilter>("all");

  const { data, isLoading } = useQuery<DealsResponse>({
    queryKey: ["insights/news-deals"],
    queryFn: () => fetchApi(`/news/deals`),
    staleTime: 5 * 60_000,
  });

  const all: NormDeal[] = useMemo(() => [
    ...normalize(data?.bulk, "bulk"),
    ...normalize(data?.block, "block"),
  ], [data]);

  const filtered = useMemo(() => {
    let r = all;
    if (typeFilter !== "all") r = r.filter(d => d.type === typeFilter);
    if (actionFilter !== "all") {
      r = r.filter(d => (d.side || "").toUpperCase() === actionFilter.toUpperCase());
    }
    return r;
  }, [all, actionFilter, typeFilter]);

  const highlights = useMemo(() => {
    return [...all].sort((a, b) => b.valueCr - a.valueCr).slice(0, 5);
  }, [all]);

  return (
    <div>
      <PageHeader title="Bulk/Block Deals" info="Bulk and block trades reported to exchanges" />

      {highlights.length > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3 mb-4">
          {highlights.map((d, i) => (
            <Card key={i} className="p-3">
              <div className="flex items-start justify-between mb-1">
                <span className="text-xs font-bold text-gray-900 dark:text-white truncate flex-1">{d.name || d.symbol}</span>
                <span className={`text-[10px] px-1.5 py-0.5 rounded-md font-semibold ml-1 ${
                  (d.side||"").toUpperCase() === "SELL" ? "bg-red-100 text-red-700 dark:bg-red-500/20 dark:text-red-300"
                  : "bg-green-100 text-green-700 dark:bg-green-500/20 dark:text-green-300"
                }`}>{d.side || "—"}</span>
              </div>
              <p className="text-[11px] text-gray-500">Deal Size</p>
              <p className="text-sm font-bold text-gray-900 dark:text-white">₹{fmtNum(d.valueCr)} Cr</p>
              <p className="text-[10px] text-gray-500 truncate mt-1" title={d.client}>by {d.client || "—"}</p>
            </Card>
          ))}
        </div>
      )}

      <div className="flex flex-wrap gap-3 items-center justify-between mb-3">
        <PillTabs value={actionFilter} onChange={setActionFilter} options={[
          {value:"all",label:"All"},{value:"buy",label:"Buy"},{value:"sell",label:"Sell"},
        ]}/>
        <PillTabs value={typeFilter} onChange={setTypeFilter} options={[
          {value:"all",label:"Bulk + Block"},{value:"bulk",label:"Bulk"},{value:"block",label:"Block"},
        ]}/>
      </div>

      {isLoading && <Loading />}
      {!isLoading && filtered.length === 0 && (
        <EmptyState title="No deals" message="No bulk/block deals available." icon={<Briefcase className="w-10 h-10"/>}/>
      )}

      {filtered.length > 0 && (
        <Card className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-xs uppercase text-gray-500 dark:text-gray-400 bg-gray-50 dark:bg-gray-800/40">
              <tr>
                <th className="px-4 py-3 text-left">Stock</th>
                <th className="px-4 py-3 text-left">Date</th>
                <th className="px-4 py-3 text-left">Client</th>
                <th className="px-4 py-3 text-left">Side</th>
                <th className="px-4 py-3 text-right">Qty</th>
                <th className="px-4 py-3 text-right">Avg Price</th>
                <th className="px-4 py-3 text-right">Value (Cr)</th>
              </tr>
            </thead>
            <tbody>
              {filtered.slice(0, 200).map((d, i) => (
                <tr key={d.symbol + d.date + i} className="border-t border-gray-100 dark:border-white/[0.05]">
                  <td className="px-4 py-2.5 font-medium text-gray-900 dark:text-white">
                    {d.name || d.symbol}
                    <span className="ml-2 text-[10px] px-1.5 py-0.5 rounded-md bg-orange-100 dark:bg-orange-500/15 text-orange-600 dark:text-orange-300 uppercase">{d.type}</span>
                  </td>
                  <td className="px-4 py-2.5 text-gray-500 dark:text-gray-400">{d.date}</td>
                  <td className="px-4 py-2.5 text-gray-600 dark:text-gray-300 max-w-xs truncate" title={d.client}>{d.client}</td>
                  <td className={`px-4 py-2.5 font-semibold ${(d.side||"").toUpperCase() === "SELL" ? "text-red-500" : "text-green-600"}`}>{d.side}</td>
                  <td className="px-4 py-2.5 text-right">{d.quantity != null ? new Intl.NumberFormat("en-IN").format(d.quantity) : "—"}</td>
                  <td className="px-4 py-2.5 text-right">{fmtNum(d.price)}</td>
                  <td className="px-4 py-2.5 text-right font-semibold">{fmtNum(d.valueCr)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
