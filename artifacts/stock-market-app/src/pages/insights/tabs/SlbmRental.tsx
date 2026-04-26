import { useQuery } from "@tanstack/react-query";
import { fetchApi } from "@/lib/api";
import { PageHeader, Loading, EmptyState } from "../_shared";
import { Repeat } from "lucide-react";

export default function SlbmRental() {
  const { data, isLoading } = useQuery<{ available: boolean; message?: string }>({
    queryKey: ["insights/slbm"],
    queryFn: () => fetchApi(`/insights/slbm`),
    staleTime: 60 * 60_000,
  });
  return (
    <div>
      <PageHeader title="Stock Rental via SLBM" info="Securities Lending and Borrowing Mechanism" />
      {isLoading ? <Loading /> : (
        <EmptyState
          icon={<Repeat className="w-10 h-10" />}
          title="SLBM data coming soon"
          message={data?.message || "NSE's SLB report (sec_lend_borrow.csv) is published EOD; integration is on the roadmap."}
        />
      )}
    </div>
  );
}
