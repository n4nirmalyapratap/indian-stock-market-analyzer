import { PageHeader, FeatureLocked } from "../_shared";
import { Users } from "lucide-react";

export default function MtfInsights() {
  return (
    <div>
      <PageHeader title="MTF Insights"
        info="Margin Trading Facility — leveraged positions financed by your broker" />
      <FeatureLocked
        icon={<Users className="w-6 h-6" />}
        title="MTF positions per scrip"
        whatIsThis="Margin Trading Facility (MTF) lets retail clients buy stocks on borrowed money, with the broker funding up to 75% of the trade. Aggregated MTF interest at the scrip level is a useful proxy for retail leverage and crowded longs."
        sourceName="NSE India"
        sourceUrl="https://www.nseindia.com/products-services/margin-trading-facility"
        expectedColumns={["Symbol", "MTF Outstanding", "Daily Change", "% of Free Float", "Top Brokers"]}
      />
    </div>
  );
}
