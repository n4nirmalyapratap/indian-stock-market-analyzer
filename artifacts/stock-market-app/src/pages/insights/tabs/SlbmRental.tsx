import { PageHeader, FeatureLocked } from "../_shared";
import { Repeat } from "lucide-react";

export default function SlbmRental() {
  return (
    <div>
      <PageHeader title="Stock Rental via SLBM"
        info="Securities Lending and Borrowing Mechanism — earn yield by lending your shares" />
      <FeatureLocked
        icon={<Repeat className="w-6 h-6" />}
        title="SLBM stock rental yields"
        whatIsThis="The Securities Lending & Borrowing Mechanism (SLBM) lets long-term shareholders rent out their holdings to short-sellers and arbitrageurs in exchange for an annualised lending fee. NSE publishes lending rates and open interest for each eligible scrip every evening."
        sourceName="NSE India"
        sourceUrl="https://www.nseindia.com/products-services/securities-lending-borrowing-mechanism"
        expectedColumns={["Symbol", "Lending Rate %", "Open Interest", "Last Traded", "Demand", "Volume"]}
      />
    </div>
  );
}
