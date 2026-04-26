import { useQuery } from "@tanstack/react-query";
import { fetchApi } from "@/lib/api";
import { PageHeader, Card, Loading, FeatureLocked, fmtNum } from "../_shared";
import { Ban } from "lucide-react";

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

function statusBadge(s?: string) {
  if (s === "Banned") return "bg-rose-500/15 text-rose-700 dark:text-rose-300";
  if (s === "Possible Entrant") return "bg-amber-500/15 text-amber-700 dark:text-amber-300";
  if (s === "Possible Exit") return "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300";
  return "bg-muted text-muted-foreground";
}

export default function FoBan() {
  const { data, isLoading } = useQuery<FoBanResponse>({
    queryKey: ["insights/fo-ban"],
    queryFn: () => fetchApi(`/insights/fo-ban`),
    staleTime: 5 * 60_000,
  });

  return (
    <div>
      <PageHeader title="F&O Ban — MWPL Tracker"
        info="Market Wide Position Limit usage — entering / exiting the F&O ban list" />

      {isLoading && <Loading />}

      {!isLoading && data?.available === false && (
        <FeatureLocked
          icon={<Ban className="w-6 h-6" />}
          title="F&O Ban / MWPL data"
          whatIsThis="When a stock's open interest crosses 95% of its Market Wide Position Limit (MWPL), NSE bans new F&O positions. Tracking 'possible entrants' (≥ 80%) and 'possible exits' lets you front-run the squeeze."
          sourceName="NSE India"
          sourceUrl="https://www.nseindia.com/market-data/securities-banned-period"
          expectedColumns={["Symbol", "LTP", "% Change", "Prev MWPL %", "Current MWPL %", "Status"]}
        />
      )}

      {!isLoading && data?.available && (data.items?.length || 0) > 0 && (
        <Card className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-xs uppercase text-muted-foreground bg-muted/40">
              <tr>
                <th className="px-4 py-3 text-left">Symbol</th>
                <th className="px-4 py-3 text-right">LTP</th>
                <th className="px-4 py-3 text-right">% Change</th>
                <th className="px-4 py-3 text-right">Prev MWPL %</th>
                <th className="px-4 py-3 text-right">Current MWPL %</th>
                <th className="px-4 py-3 text-left">Status</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map(it => (
                <tr key={it.symbol} className="border-t border-card-border hover:bg-accent/30">
                  <td className="px-4 py-2.5 font-semibold text-foreground">{it.symbol}</td>
                  <td className="px-4 py-2.5 text-right tabular-nums">{fmtNum(it.ltp)}</td>
                  <td className={`px-4 py-2.5 text-right tabular-nums ${(it.changePct ?? 0) >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-rose-500"}`}>
                    {(it.changePct ?? 0) >= 0 ? "+" : ""}{it.changePct?.toFixed(2)}%
                  </td>
                  <td className="px-4 py-2.5 text-right tabular-nums">{it.prevMwplPct?.toFixed(1)}%</td>
                  <td className="px-4 py-2.5 text-right tabular-nums font-semibold">{it.currentMwplPct?.toFixed(1)}%</td>
                  <td className="px-4 py-2.5">
                    <span className={`text-[11px] px-2 py-1 rounded-md font-medium ${statusBadge(it.status)}`}>
                      {it.status || "—"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
