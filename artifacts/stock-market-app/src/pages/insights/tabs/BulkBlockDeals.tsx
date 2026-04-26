import { PageHeader, FeatureLocked } from "../_shared";
import { Briefcase } from "lucide-react";

export default function BulkBlockDeals() {
  return (
    <div>
      <PageHeader title="Bulk & Block Deals"
        info="Large single-trade transactions disclosed under SEBI rules" />
      <FeatureLocked
        icon={<Briefcase className="w-6 h-6" />}
        title="Bulk & Block deal disclosures"
        whatIsThis="Bulk deals (any single trade > 0.5% of listed shares) and block deals (negotiated trades ≥ ₹10 cr or ≥ 5 lakh shares) reveal which large institutions or HNIs are quietly building or trimming positions. NSE & BSE publish these EOD."
        sourceName="NSE India"
        sourceUrl="https://www.nseindia.com/market-data/bulk-deals"
        expectedColumns={["Date", "Symbol", "Client Name", "Buy / Sell", "Quantity", "Avg Price", "Deal Type"]}
      />
    </div>
  );
}
