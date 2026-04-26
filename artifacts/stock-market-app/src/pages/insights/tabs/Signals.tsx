import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchApi } from "@/lib/api";
import { PageHeader, Card, PillTabs, Loading, EmptyState, MenuDropdown, ErrorState } from "../_shared";
import { Activity } from "lucide-react";

interface Signal {
  symbol: string;
  name: string;
  ltp: number;
  rsi: number | null;
  ma20: number;
  ma50: number;
  verdict: "Bullish" | "Bearish" | "Neutral" | string;
  reasons: string[];
}

interface SignalsResponse {
  available: boolean;
  message?: string;
  items: Signal[];
}

type Verdict = "all" | "bullish" | "bearish" | "neutral";

const VERDICT_OPTIONS: { value: Verdict; label: string }[] = [
  { value: "all", label: "All" },
  { value: "bullish", label: "Bullish" },
  { value: "bearish", label: "Bearish" },
  { value: "neutral", label: "Neutral" },
];

function verdictBadge(v: string) {
  const cls = v === "Bullish"
    ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300"
    : v === "Bearish"
    ? "bg-rose-500/15 text-rose-700 dark:text-rose-300"
    : "bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400";
  return `text-xs px-2 py-1 rounded-md font-semibold ${cls}`;
}

export default function Signals() {
  const [index, setIndex] = useState("NIFTY50");
  const [verdict, setVerdict] = useState<Verdict>("all");

  const { data: idxList } = useQuery<{ indices: { code: string; label: string }[] }>({
    queryKey: ["insights/indices"],
    queryFn: () => fetchApi(`/insights/indices`),
    staleTime: 60 * 60_000,
  });

  const { data, isLoading, error } = useQuery<SignalsResponse>({
    queryKey: ["insights/signals", index, verdict],
    queryFn: () => fetchApi(`/insights/signals?index=${index}&verdict=${verdict}`),
    staleTime: 5 * 60_000,
  });

  const counts = useMemo(() => {
    const c = { Bullish: 0, Bearish: 0, Neutral: 0 };
    (data?.items || []).forEach(it => {
      if (it.verdict in c) (c as any)[it.verdict]++;
    });
    return c;
  }, [data]);

  const indexOptions = (idxList?.indices || [{ code: "NIFTY50", label: "Nifty 50" }])
    .map(o => ({ value: o.code, label: o.label }));

  return (
    <div>
      <PageHeader title="Signals" subtitle="Technical signals (RSI + MA crossover) computed live across the index" />

      <div className="flex flex-wrap items-center gap-2 mb-4">
        <MenuDropdown label="Index" value={index} onChange={setIndex} options={indexOptions} maxButtonWidth={240}/>
        <PillTabs value={verdict} onChange={(v) => setVerdict(v as Verdict)} options={VERDICT_OPTIONS}/>

        <div className="ml-auto flex gap-2 text-[11px]">
          <span className={verdictBadge("Bullish")}>{counts.Bullish} Bullish</span>
          <span className={verdictBadge("Bearish")}>{counts.Bearish} Bearish</span>
          <span className={verdictBadge("Neutral")}>{counts.Neutral} Neutral</span>
        </div>
      </div>

      {isLoading && <Loading label="Computing signals…" />}
      {error && !isLoading && <ErrorState message={(error as Error).message} />}
      {!isLoading && !error && (data?.items || []).length === 0 && (
        <EmptyState title="No signals" message="No matching signals for this filter." icon={<Activity className="w-10 h-10"/>}/>
      )}

      {data?.items && data.items.length > 0 && (
        <Card className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-xs uppercase text-gray-500 dark:text-gray-400 bg-gray-50 dark:bg-gray-900/40">
              <tr>
                <th className="px-4 py-3 text-left">Stock</th>
                <th className="px-4 py-3 text-right">LTP</th>
                <th className="px-4 py-3 text-right">RSI</th>
                <th className="px-4 py-3 text-right">MA20</th>
                <th className="px-4 py-3 text-right">MA50</th>
                <th className="px-4 py-3 text-left">Signal</th>
                <th className="px-4 py-3 text-left">Why</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map(s => (
                <tr key={s.symbol} className="border-t border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700/30 transition">
                  <td className="px-4 py-2.5 font-medium text-gray-900 dark:text-white">{s.name}</td>
                  <td className="px-4 py-2.5 text-right tabular-nums">{s.ltp.toFixed(2)}</td>
                  <td className="px-4 py-2.5 text-right tabular-nums">{s.rsi != null ? s.rsi.toFixed(1) : "—"}</td>
                  <td className="px-4 py-2.5 text-right tabular-nums text-gray-500 dark:text-gray-400">{s.ma20.toFixed(2)}</td>
                  <td className="px-4 py-2.5 text-right tabular-nums text-gray-500 dark:text-gray-400">{s.ma50.toFixed(2)}</td>
                  <td className="px-4 py-2.5"><span className={verdictBadge(s.verdict)}>{s.verdict}</span></td>
                  <td className="px-4 py-2.5 text-xs text-gray-500 dark:text-gray-400">
                    {s.reasons.length ? s.reasons.join(" · ") : "—"}
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
