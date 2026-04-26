import { useQuery } from "@tanstack/react-query";
import { fetchApi } from "@/lib/api";
import { PageHeader, Loading, EmptyState } from "../_shared";
import { Users } from "lucide-react";

export default function MtfInsights() {
  const { data, isLoading } = useQuery<{ available: boolean; message?: string }>({
    queryKey: ["insights/mtf"],
    queryFn: () => fetchApi(`/insights/mtf`),
    staleTime: 60 * 60_000,
  });
  return (
    <div>
      <PageHeader title="MTF Insights" info="Margin Trading Facility positions per broker" />
      {isLoading ? <Loading /> : (
        <EmptyState
          icon={<Users className="w-10 h-10" />}
          title="MTF data coming soon"
          message={data?.message || "MTF data is published per-broker by NSE/BSE; an aggregated feed is on the roadmap."}
        />
      )}
    </div>
  );
}
