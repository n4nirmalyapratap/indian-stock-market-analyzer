import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchApi } from "@/lib/api";
import { PageHeader, Dropdown, Loading, EmptyState } from "../_shared";
import { PieChart } from "lucide-react";

export default function MfHoldings() {
  const [amc, setAmc] = useState("ppfas");
  const [scheme, setScheme] = useState("flexi-cap");
  const [view, setView] = useState<"holdingsPct" | "majorActions" | "changePct">("holdingsPct");
  const [freq, setFreq] = useState<"monthly" | "quarterly">("monthly");

  const { data, isLoading } = useQuery<{ available: boolean; message?: string }>({
    queryKey: ["insights/mf-holdings", amc, scheme],
    queryFn: () => fetchApi(`/insights/mf-holdings?amc=${amc}&scheme=${scheme}`),
    staleTime: 60 * 60_000,
  });

  return (
    <div>
      <PageHeader
        title="Mutual Funds - Stock Holdings"
        right={
          <div className="flex flex-wrap gap-2 items-center text-xs">
            <label className="flex items-center gap-1"><input type="checkbox" /> Major Actions</label>
            <label className="flex items-center gap-1"><input type="checkbox" /> Change %</label>
          </div>
        }
      />
      <div className="flex flex-wrap items-center gap-3 mb-4">
        <Dropdown label="AMC :" value={amc} onChange={setAmc} options={[
          {value:"ppfas",label:"PPFAS Mutual Fund"},
          {value:"hdfc",label:"HDFC Mutual Fund"},
          {value:"icici",label:"ICICI Pru Mutual Fund"},
          {value:"sbi",label:"SBI Mutual Fund"},
          {value:"axis",label:"Axis Mutual Fund"},
        ]}/>
        <Dropdown label="Scheme :" value={scheme} onChange={setScheme} options={[
          {value:"flexi-cap",label:"Parag Parikh Flexi Cap Fund Direct-Gr…"},
          {value:"liquid",label:"Parag Parikh Liquid Fund Direct-Gr…"},
        ]}/>
        <div className="ml-auto flex gap-2">
          <Dropdown value={view} onChange={setView} options={[
            {value:"holdingsPct",label:"Holdings %"},
            {value:"majorActions",label:"Major Actions"},
            {value:"changePct",label:"Change %"},
          ]}/>
          <Dropdown value={freq} onChange={setFreq} options={[
            {value:"monthly",label:"Monthly"},
            {value:"quarterly",label:"Quarterly"},
          ]}/>
        </div>
      </div>

      {isLoading && <Loading />}
      {!isLoading && (
        <EmptyState
          icon={<PieChart className="w-10 h-10" />}
          title="MF holdings data coming soon"
          message={data?.message || "AMFI publishes monthly mutual-fund portfolios as scheme PDFs which require parsing. This feed is on the roadmap; for now, please refer to AMFI's official site."}
        />
      )}
    </div>
  );
}
