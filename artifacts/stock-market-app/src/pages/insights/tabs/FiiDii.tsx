import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchApi } from "@/lib/api";
import { PageHeader, PillTabs, Dropdown, Card, Loading, EmptyState, fmtNum } from "../_shared";
import { BarChart3 } from "lucide-react";

type Segment = "equity" | "indexFuture" | "indexOption" | "stockFuture" | "stockOption";
type Period = "daily" | "weekly" | "monthly";
type Range = "30d" | "90d" | "1y";
type Participant = "both" | "fii" | "dii";

interface FiiDiiRow {
  date: string;
  fiiBuy: number;
  fiiSell: number;
  fiiNet: number;
  diiBuy: number;
  diiSell: number;
  diiNet: number;
}

interface FiiDiiResponse {
  segment: string;
  period: string;
  rows: FiiDiiRow[];
  available: boolean;
  message?: string;
}

export default function FiiDii() {
  const [segment, setSegment] = useState<Segment>("equity");
  const [period, setPeriod] = useState<Period>("daily");
  const [range, setRange] = useState<Range>("30d");
  const [participant, setParticipant] = useState<Participant>("both");

  const { data, isLoading } = useQuery<FiiDiiResponse>({
    queryKey: ["insights/fii-dii", segment, period, range],
    queryFn: () => fetchApi(`/insights/fii-dii?segment=${segment}&period=${period}&range=${range}`),
    staleTime: 5 * 60_000,
  });

  const rows = data?.rows || [];
  const latest = rows[0];

  return (
    <div>
      <PageHeader title="FII/DII Data" info="Foreign and Domestic Institutional flows" />

      <PillTabs value={segment} onChange={setSegment} options={[
        {value:"equity",label:"Equity"},
        {value:"indexFuture",label:"Index Future"},
        {value:"indexOption",label:"Index Option"},
        {value:"stockFuture",label:"Stock Future"},
        {value:"stockOption",label:"Stock Options"},
      ]}/>

      {/* Top summary cards */}
      {latest && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mt-4">
          {[
            { label: "Daily", date: rows[0]?.date, fii: rows[0]?.fiiNet, dii: rows[0]?.diiNet },
            { label: "Weekly", date: rows[6]?.date || rows.at(-1)?.date, fii: rows.slice(0,7).reduce((s,r)=>s+r.fiiNet,0), dii: rows.slice(0,7).reduce((s,r)=>s+r.diiNet,0) },
            { label: "Monthly", date: rows.at(-1)?.date, fii: rows.reduce((s,r)=>s+r.fiiNet,0), dii: rows.reduce((s,r)=>s+r.diiNet,0) },
          ].map(c => (
            <Card key={c.label} className="p-4">
              <div className="flex items-center justify-between text-xs text-gray-500 dark:text-gray-400 mb-3">
                <span className="font-semibold text-gray-900 dark:text-white">{c.label}</span>
                <span>{c.date}</span>
              </div>
              <div className="flex items-center justify-between text-sm mb-1">
                <span className="text-gray-600 dark:text-gray-400">FII</span>
                <span className={c.fii >= 0 ? "text-green-600 font-semibold" : "text-red-500 font-semibold"}>
                  {c.fii >= 0 ? "+" : ""}{fmtNum(c.fii)} Cr.
                </span>
              </div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-gray-600 dark:text-gray-400">DII</span>
                <span className={c.dii >= 0 ? "text-green-600 font-semibold" : "text-red-500 font-semibold"}>
                  {c.dii >= 0 ? "+" : ""}{fmtNum(c.dii)} Cr.
                </span>
              </div>
            </Card>
          ))}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-3 mt-4 mb-4">
        <Dropdown label="Participant :" value={participant} onChange={setParticipant} options={[
          {value:"both",label:"Both FII & DII"},{value:"fii",label:"FII only"},{value:"dii",label:"DII only"},
        ]}/>
        <div className="ml-auto flex gap-2 items-center">
          <PillTabs value={period} onChange={setPeriod} options={[
            {value:"daily",label:"Daily"},{value:"weekly",label:"Weekly"},{value:"monthly",label:"Monthly"},
          ]}/>
          <Dropdown value={range} onChange={setRange} options={[
            {value:"30d",label:"Last 30 Days"},{value:"90d",label:"Last 90 Days"},{value:"1y",label:"Last 1 Year"},
          ]}/>
        </div>
      </div>

      {isLoading && <Loading />}

      {!isLoading && data && !data.available && (
        <EmptyState
          icon={<BarChart3 className="w-10 h-10" />}
          title="FII/DII data unavailable"
          message={data.message || "Live FII/DII data source is not currently reachable from this environment. NSE blocks cloud-IP access to its participant-wise CSV. We're tracking adding a SEBI/exchange feed."}
        />
      )}

      {rows.length > 0 && (
        <Card className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-xs uppercase text-gray-500 dark:text-gray-400 bg-gray-50 dark:bg-gray-800/40">
              <tr>
                <th className="px-4 py-3 text-left">Date</th>
                {(participant === "both" || participant === "fii") && <>
                  <th className="px-4 py-3 text-right">FII Buy (Cr)</th>
                  <th className="px-4 py-3 text-right">FII Sell (Cr)</th>
                  <th className="px-4 py-3 text-right">FII Net (Cr)</th>
                </>}
                {(participant === "both" || participant === "dii") && <>
                  <th className="px-4 py-3 text-right">DII Buy (Cr)</th>
                  <th className="px-4 py-3 text-right">DII Sell (Cr)</th>
                  <th className="px-4 py-3 text-right">DII Net (Cr)</th>
                </>}
              </tr>
            </thead>
            <tbody>
              {rows.map(r => (
                <tr key={r.date} className="border-t border-gray-100 dark:border-white/[0.05]">
                  <td className="px-4 py-2.5 font-medium text-gray-900 dark:text-white">{r.date}</td>
                  {(participant === "both" || participant === "fii") && <>
                    <td className="px-4 py-2.5 text-right">{fmtNum(r.fiiBuy)}</td>
                    <td className="px-4 py-2.5 text-right">{fmtNum(r.fiiSell)}</td>
                    <td className={`px-4 py-2.5 text-right font-semibold ${r.fiiNet >= 0 ? "text-green-600" : "text-red-500"}`}>{fmtNum(r.fiiNet)}</td>
                  </>}
                  {(participant === "both" || participant === "dii") && <>
                    <td className="px-4 py-2.5 text-right">{fmtNum(r.diiBuy)}</td>
                    <td className="px-4 py-2.5 text-right">{fmtNum(r.diiSell)}</td>
                    <td className={`px-4 py-2.5 text-right font-semibold ${r.diiNet >= 0 ? "text-green-600" : "text-red-500"}`}>{fmtNum(r.diiNet)}</td>
                  </>}
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
