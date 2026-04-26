import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchApi } from "@/lib/api";
import { PageHeader, PillTabs, Card, Loading, EmptyState, fmtNum } from "../_shared";
import { Rocket, Info } from "lucide-react";

type Status = "open" | "upcoming" | "listed";

interface IpoItem {
  name: string;
  symbol?: string;
  exchange?: string;
  opensOn?: string;
  closesOn?: string;
  ipoSizeCr?: number;
  priceRange?: string;
  minBid?: number;
  subscriptionTimes?: number;
  status?: Status;
}

interface IpoResponse {
  available: boolean;
  message?: string;
  items: IpoItem[];
}

export default function Ipo() {
  const [status, setStatus] = useState<Status>("open");

  const { data, isLoading } = useQuery<IpoResponse>({
    queryKey: ["insights/ipos", status],
    queryFn: () => fetchApi(`/insights/ipos?status=${status}`),
    staleTime: 30 * 60_000,
  });

  const items = data?.items || [];
  const openNow = items.filter(i => (i.subscriptionTimes ?? 0) > 0).slice(0, 3);

  return (
    <div>
      <PageHeader title="Apply for Open IPOs" />
      <PillTabs value={status} onChange={setStatus} options={[
        {value:"open",label:"Open IPOs"},{value:"upcoming",label:"Upcoming IPOs"},{value:"listed",label:"Listed IPOs"},
      ]}/>

      {openNow.length > 0 && (
        <>
          <h3 className="mt-4 text-sm font-semibold text-gray-700 dark:text-gray-300">Open Now for Subscription</h3>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3 mt-2 mb-4">
            {openNow.map((it, i) => (
              <Card key={i} className="p-3">
                <div className="flex items-center gap-1.5 mb-1">
                  <span className="text-sm font-bold text-gray-900 dark:text-white truncate">{it.name}</span>
                  {it.subscriptionTimes != null && (
                    <span className="text-[10px] px-1 py-0.5 rounded bg-orange-100 dark:bg-orange-500/15 text-orange-600 dark:text-orange-300">
                      {it.subscriptionTimes.toFixed(2)}x
                    </span>
                  )}
                </div>
                <p className="text-[11px] text-gray-500 mt-1">IPO Size <span className="text-gray-900 dark:text-white font-medium">{fmtNum(it.ipoSizeCr)} Cr.</span></p>
                <p className="text-[11px] text-gray-500">Min Bid <span className="text-gray-900 dark:text-white font-medium">{it.minBid ? new Intl.NumberFormat("en-IN").format(it.minBid) : "—"}</span></p>
              </Card>
            ))}
          </div>
        </>
      )}

      {(items.length > 0) && (
        <>
          <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">Open for Bid</h3>
          <Card className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-xs uppercase text-gray-500 dark:text-gray-400 bg-gray-50 dark:bg-gray-800/40">
                <tr>
                  <th className="px-4 py-3 text-left">Company Name</th>
                  <th className="px-4 py-3 text-left">Opens On</th>
                  <th className="px-4 py-3 text-left">Closes On</th>
                  <th className="px-4 py-3 text-right">IPO Size (Cr)</th>
                  <th className="px-4 py-3 text-left">Price Range</th>
                  <th className="px-4 py-3 text-right">Min Bid Amount</th>
                  <th className="px-4 py-3 text-center">Action</th>
                </tr>
              </thead>
              <tbody>
                {items.map((it, i) => (
                  <tr key={i} className="border-t border-gray-100 dark:border-white/[0.05]">
                    <td className="px-4 py-2.5 font-medium text-gray-900 dark:text-white">
                      {it.name}
                      {it.exchange && <span className="ml-2 text-[10px] px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300">{it.exchange}</span>}
                    </td>
                    <td className="px-4 py-2.5 text-gray-600 dark:text-gray-300">{it.opensOn}</td>
                    <td className="px-4 py-2.5 text-gray-600 dark:text-gray-300">{it.closesOn}</td>
                    <td className="px-4 py-2.5 text-right">{fmtNum(it.ipoSizeCr)}</td>
                    <td className="px-4 py-2.5">{it.priceRange || "—"}</td>
                    <td className="px-4 py-2.5 text-right">{it.minBid ? new Intl.NumberFormat("en-IN").format(it.minBid) : "—"}</td>
                    <td className="px-4 py-2.5 text-center">
                      <button className="text-xs px-3 py-1 rounded bg-green-500 text-white hover:bg-green-600">Apply</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </>
      )}

      {isLoading && <Loading />}
      {!isLoading && items.length === 0 && (
        <EmptyState
          icon={<Rocket className="w-10 h-10" />}
          title="No IPOs in this category"
          message={data?.message || "No active IPOs found for the selected status."}
        />
      )}
    </div>
  );
}
