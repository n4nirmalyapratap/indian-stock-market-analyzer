import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchApi } from "@/lib/api";
import { PageHeader, PillTabs, Dropdown, Card, Loading, EmptyState, fmtNum } from "../_shared";
import { Truck } from "lucide-react";

type Period = "daily" | "weekly" | "monthly";
type Index = "NIFTY50" | "NIFTYBANK" | "NIFTY100";

interface DeliveryItem {
  symbol: string;
  name?: string;
  ltp?: number;
  change?: number;
  changePct?: number;
  traded?: number;
  delivered?: number;
  deliveredPct?: number;
}

interface DeliveriesResponse {
  available: boolean;
  message?: string;
  items: DeliveryItem[];
}

export default function TopDeliveries() {
  const [period, setPeriod] = useState<Period>("daily");
  const [index, setIndex] = useState<Index>("NIFTY50");

  const { data, isLoading } = useQuery<DeliveriesResponse>({
    queryKey: ["insights/top-deliveries", period, index],
    queryFn: () => fetchApi(`/insights/top-deliveries?period=${period}&index=${index}`),
    staleTime: 30 * 60_000,
  });

  const items = data?.items || [];
  const top5 = items.slice(0, 5);

  return (
    <div>
      <PageHeader
        title="Top Deliveries"
        info="Stocks with the highest delivery percentage"
        right={
          <Dropdown label="Index :" value={index} onChange={setIndex} options={[
            {value:"NIFTY50",label:"Nifty 50"},
            {value:"NIFTYBANK",label:"Nifty Bank"},
            {value:"NIFTY100",label:"Nifty 100"},
          ]}/>
        }
      />
      <PillTabs value={period} onChange={setPeriod} options={[
        {value:"daily",label:"Daily"},{value:"weekly",label:"Weekly"},{value:"monthly",label:"Monthly"},
      ]}/>

      {top5.length > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3 mt-4 mb-4">
          {top5.map(it => (
            <Card key={it.symbol} className="p-3">
              <div className="flex items-center justify-between mb-1">
                <span className="text-sm font-bold text-gray-900 dark:text-white truncate">{it.name || it.symbol}</span>
                <span className={`text-xs ${(it.changePct ?? 0) >= 0 ? "text-green-600" : "text-red-500"}`}>
                  {fmtNum(it.ltp)}{(it.changePct ?? 0) >= 0 ? " ▲" : " ▼"}
                </span>
              </div>
              <p className="text-[11px] text-gray-500">Delivered</p>
              <p className="text-base font-bold text-gray-900 dark:text-white">{fmtNum(it.deliveredPct)}%</p>
              <p className="text-[10px] text-gray-500 mt-1">of {fmtNum((it.traded ?? 0) / 1e7)} Cr trades</p>
            </Card>
          ))}
        </div>
      )}

      {isLoading && <Loading />}
      {!isLoading && items.length === 0 && (
        <EmptyState
          icon={<Truck className="w-10 h-10" />}
          title="No delivery data"
          message={data?.message || "Daily delivery position bhavcopy is not reachable from this environment."}
        />
      )}

      {items.length > 0 && (
        <Card className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-xs uppercase text-gray-500 dark:text-gray-400 bg-gray-50 dark:bg-gray-800/40">
              <tr>
                <th className="px-4 py-3 text-left">Stock</th>
                <th className="px-4 py-3 text-right">LTP</th>
                <th className="px-4 py-3 text-right">Change</th>
                <th className="px-4 py-3 text-right">Change %</th>
                <th className="px-4 py-3 text-right">Traded</th>
                <th className="px-4 py-3 text-right">Delivered</th>
                <th className="px-4 py-3 text-right">Delivered %</th>
              </tr>
            </thead>
            <tbody>
              {items.map(it => (
                <tr key={it.symbol} className="border-t border-gray-100 dark:border-white/[0.05]">
                  <td className="px-4 py-2.5 font-medium text-gray-900 dark:text-white">{it.name || it.symbol}</td>
                  <td className="px-4 py-2.5 text-right">{fmtNum(it.ltp)}</td>
                  <td className={`px-4 py-2.5 text-right ${(it.change ?? 0) >= 0 ? "text-green-600" : "text-red-500"}`}>{fmtNum(it.change)}</td>
                  <td className={`px-4 py-2.5 text-right ${(it.changePct ?? 0) >= 0 ? "text-green-600" : "text-red-500"}`}>{fmtNum(it.changePct)}%</td>
                  <td className="px-4 py-2.5 text-right">{it.traded != null ? new Intl.NumberFormat("en-IN").format(it.traded) : "—"}</td>
                  <td className="px-4 py-2.5 text-right">{it.delivered != null ? new Intl.NumberFormat("en-IN").format(it.delivered) : "—"}</td>
                  <td className="px-4 py-2.5 text-right font-semibold text-indigo-600 dark:text-indigo-400">{fmtNum(it.deliveredPct)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
