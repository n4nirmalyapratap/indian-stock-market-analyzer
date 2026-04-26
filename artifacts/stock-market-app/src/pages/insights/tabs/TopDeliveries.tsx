import { PageHeader, FeatureLocked } from "../_shared";
import { Truck } from "lucide-react";

export default function TopDeliveries() {
  return (
    <div>
      <PageHeader title="Top Delivery Stocks"
        info="Stocks where most of the day's volume was actually delivered (not intraday-squared)" />
      <FeatureLocked
        icon={<Truck className="w-6 h-6" />}
        title="High-delivery percentage stocks"
        whatIsThis="Delivery percentage measures how much of a day's traded volume actually changed hands (i.e. was delivered to demat accounts) versus intraday speculation. Sustained high delivery on a moving stock is a strong sign of accumulation by genuine buyers — one of the most-watched institutional footprints."
        sourceName="NSE India Bhavcopy"
        sourceUrl="https://www.nseindia.com/all-reports"
        expectedColumns={["Symbol", "Traded Qty", "Delivered Qty", "Delivery %", "Daily Change", "5-day Avg %"]}
      />
    </div>
  );
}
