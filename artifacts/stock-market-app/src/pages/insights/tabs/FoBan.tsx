import { useQuery } from "@tanstack/react-query";
import { fetchApi } from "@/lib/api";
import { PageHeader, Card, Loading, EmptyState, fmtNum } from "../_shared";
import { Ban, ArrowRight } from "lucide-react";

interface FoBanItem {
  symbol: string;
  name?: string;
  ltp?: number;
  change?: number;
  changePct?: number;
  prevMwplPct?: number;
  currentMwplPct?: number;
  status?: "Banned" | "Possible Entrant" | "Possible Exit";
}

interface FoBanResponse {
  available: boolean;
  message?: string;
  items: FoBanItem[];
}

export default function FoBan() {
  const { data, isLoading } = useQuery<FoBanResponse>({
    queryKey: ["insights/fo-ban"],
    queryFn: () => fetchApi(`/insights/fo-ban`),
    staleTime: 5 * 60_000,
  });

  const items = data?.items || [];
  const top5 = items.slice(0, 5);

  return (
    <div>
      <PageHeader title="F&O Ban - MWPL" info="Stocks approaching or crossing 95% Market Wide Position Limit" />
      <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">High Option Activity Stocks</h3>

      {top5.length > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3 mb-4">
          {top5.map(it => (
            <Card key={it.symbol} className="p-3">
              <div className="flex items-center gap-1.5 mb-2">
                <span className="text-sm font-bold text-gray-900 dark:text-white truncate">{it.name || it.symbol}</span>
              </div>
              <p className="text-[11px] text-gray-500">Current MWPL %</p>
              <p className="text-base font-bold text-gray-900 dark:text-white">{fmtNum(it.currentMwplPct)}%</p>
              <span className="inline-block mt-1 text-[10px] px-1.5 py-0.5 rounded bg-orange-100 dark:bg-orange-500/15 text-orange-600 dark:text-orange-300">
                {it.status || "Possible Entrant"}
              </span>
            </Card>
          ))}
        </div>
      )}

      {isLoading && <Loading />}
      {!isLoading && items.length === 0 && (
        <EmptyState
          icon={<Ban className="w-10 h-10" />}
          title="No F&O ban data"
          message={data?.message || "Live F&O MWPL list is not currently available from this environment."}
        />
      )}

      {items.length > 0 && (
        <Card className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-xs uppercase text-gray-500 dark:text-gray-400 bg-gray-50 dark:bg-gray-800/40">
              <tr>
                <th className="px-4 py-3 text-left">Stock</th>
                <th className="px-4 py-3 text-left">Action</th>
                <th className="px-4 py-3 text-right">LTP</th>
                <th className="px-4 py-3 text-right">Change</th>
                <th className="px-4 py-3 text-right">% Change</th>
                <th className="px-4 py-3 text-right">Previous MWPL %</th>
                <th className="px-4 py-3 text-right">Current MWPL %</th>
                <th className="px-4 py-3 text-center">Status</th>
              </tr>
            </thead>
            <tbody>
              {items.map(it => (
                <tr key={it.symbol} className="border-t border-gray-100 dark:border-white/[0.05]">
                  <td className="px-4 py-2.5 font-medium text-gray-900 dark:text-white">{it.name || it.symbol}</td>
                  <td className="px-4 py-2.5">
                    <span className="text-[11px] px-1.5 py-0.5 rounded bg-orange-100 dark:bg-orange-500/15 text-orange-600 dark:text-orange-300">
                      {it.status || "Possible Entrant"}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-right">{fmtNum(it.ltp)}</td>
                  <td className={`px-4 py-2.5 text-right font-semibold ${(it.change ?? 0) >= 0 ? "text-green-600" : "text-red-500"}`}>{fmtNum(it.change)}</td>
                  <td className={`px-4 py-2.5 text-right font-semibold ${(it.changePct ?? 0) >= 0 ? "text-green-600" : "text-red-500"}`}>{fmtNum(it.changePct)}%</td>
                  <td className="px-4 py-2.5 text-right">{fmtNum(it.prevMwplPct)}</td>
                  <td className="px-4 py-2.5 text-right font-semibold">{fmtNum(it.currentMwplPct)}</td>
                  <td className="px-4 py-2.5 text-center"><ArrowRight className="w-4 h-4 inline text-red-400" /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
