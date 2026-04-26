import { useQuery } from "@tanstack/react-query";
import { fetchApi } from "@/lib/api";
import { PageHeader, Loading, FeatureLocked } from "../_shared";
import { BarChart3 } from "lucide-react";

interface FiiDiiResponse { available: boolean; message?: string; }

export default function FiiDii() {
  const { isLoading } = useQuery<FiiDiiResponse>({
    queryKey: ["insights/fii-dii"],
    queryFn: () => fetchApi(`/insights/fii-dii?segment=equity&period=daily&range=30d`),
    staleTime: 60 * 60_000,
  });

  return (
    <div>
      <PageHeader title="FII / DII Activity"
        info="Daily provisional cash-market trades by Foreign and Domestic Institutional Investors" />
      {isLoading ? <Loading /> : (
        <FeatureLocked
          icon={<BarChart3 className="w-6 h-6" />}
          title="FII / DII flow data"
          whatIsThis="FII (Foreign Institutional Investors) and DII (Domestic Institutional Investors) flows show how the largest players moved capital in and out of Indian markets each day. This number is one of the most-watched daily indicators on D-Street."
          sourceName="NSE India"
          sourceUrl="https://www.nseindia.com/reports/fii-dii"
          expectedColumns={["Date", "FII Buy", "FII Sell", "FII Net", "DII Buy", "DII Sell", "DII Net", "30-day Trend"]}
        />
      )}
    </div>
  );
}
