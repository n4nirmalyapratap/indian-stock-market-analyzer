import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchApi } from "@/lib/api";
import { PageHeader, PillTabs, Card, Loading, EmptyState } from "../_shared";
import { LineChart as LCIcon } from "lucide-react";
import { LineChart, Line, XAxis, YAxis, ResponsiveContainer, Tooltip, Legend, CartesianGrid } from "recharts";

type Period = "1m" | "6m" | "1y" | "5y" | "10y";
type Metric = "pe" | "pb" | "dy";

interface PointBag { date: string; [key: string]: number | string; }

interface ValuationResponse {
  available: boolean;
  message?: string;
  series: PointBag[];
  indices: { code: string; label: string; lastPrice?: number; change?: number; changePct?: number; }[];
}

const INDEX_OPTIONS = [
  { code: "^NSEI", label: "NIFTY 50" },
  { code: "^NSEBANK", label: "NIFTY BANK" },
  { code: "NIFTY_FIN_SERVICE.NS", label: "NIFTY FINANCIAL SERVICES" },
];

export default function MarketValuation() {
  const [period, setPeriod] = useState<Period>("5y");
  const [metric, setMetric] = useState<Metric>("pe");
  const [enabled, setEnabled] = useState<Record<string, boolean>>({ "^NSEI": true, "^NSEBANK": true });

  const codes = INDEX_OPTIONS.filter(i => enabled[i.code]).map(i => i.code).join(",");

  const { data, isLoading } = useQuery<ValuationResponse>({
    queryKey: ["insights/index-valuation", codes, period, metric],
    queryFn: () => fetchApi(`/insights/index-valuation?indices=${encodeURIComponent(codes)}&period=${period}&metric=${metric}`),
    enabled: codes.length > 0,
    staleTime: 30 * 60_000,
  });

  const colors = ["#3b82f6", "#8b5cf6", "#10b981", "#f59e0b"];

  return (
    <div>
      <PageHeader title="Market Valuation" />

      <div className="flex flex-wrap items-center gap-3 mb-4">
        {INDEX_OPTIONS.map((opt, i) => {
          const isOn = !!enabled[opt.code];
          const meta = data?.indices?.find(x => x.code === opt.code);
          return (
            <Card key={opt.code} className={`p-3 cursor-pointer ${isOn ? "ring-2 ring-indigo-200 dark:ring-indigo-500/30" : ""}`}>
              <label className="flex items-center gap-2 cursor-pointer">
                <input type="checkbox" checked={isOn} onChange={() => setEnabled(s => ({...s, [opt.code]: !s[opt.code]}))} />
                <div>
                  <p className="text-xs font-bold text-gray-900 dark:text-white">{opt.label}</p>
                  {meta && (
                    <p className="text-xs">
                      <span className="font-semibold">{meta.lastPrice?.toFixed(2)}</span>
                      <span className={`ml-1 ${(meta.change ?? 0) >= 0 ? "text-green-600" : "text-red-500"}`}>
                        {(meta.change ?? 0) >= 0 ? "+" : ""}{meta.change?.toFixed(2)} ({meta.changePct?.toFixed(2)}%)
                      </span>
                    </p>
                  )}
                </div>
              </label>
            </Card>
          );
        })}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <PillTabs value={period} onChange={setPeriod} options={[
          {value:"1m",label:"1M"},{value:"6m",label:"6M"},{value:"1y",label:"1Y"},{value:"5y",label:"5Y"},{value:"10y",label:"10Y"},
        ]}/>
        <PillTabs value={metric} onChange={setMetric} options={[
          {value:"pe",label:"PE Ratio"},{value:"pb",label:"PB Ratio"},{value:"dy",label:"Dividend Yield"},
        ]}/>
      </div>

      {isLoading && <Loading />}
      {!isLoading && data && data.series.length === 0 && (
        <EmptyState
          icon={<LCIcon className="w-10 h-10" />}
          title="No valuation history"
          message={data.message || "Index valuation history not currently available."}
        />
      )}

      {data && data.series.length > 0 && (
        <Card className="p-4">
          <div className="h-[420px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data.series}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" strokeOpacity={0.3}/>
                <XAxis dataKey="date" tick={{fontSize: 11}} />
                <YAxis tick={{fontSize: 11}} />
                <Tooltip />
                <Legend />
                {INDEX_OPTIONS.filter(o => enabled[o.code]).map((o, i) => (
                  <Line key={o.code} type="monotone" dataKey={o.label} stroke={colors[i % colors.length]} dot={false} strokeWidth={2}/>
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Card>
      )}
    </div>
  );
}
