import { useState } from "react";
import { PageHeader, PillTabs, FeatureLocked } from "../_shared";
import { Rocket } from "lucide-react";

type Status = "open" | "upcoming" | "listed";

export default function Ipo() {
  const [status, setStatus] = useState<Status>("open");
  return (
    <div>
      <PageHeader title="IPO Calendar"
        info="Mainboard and SME IPOs — open issues, upcoming launches, and recent listings" />
      <div className="mb-4">
        <PillTabs value={status} onChange={(v) => setStatus(v as Status)} options={[
          { value: "open", label: "Open Now" },
          { value: "upcoming", label: "Upcoming" },
          { value: "listed", label: "Recently Listed" },
        ]}/>
      </div>
      <FeatureLocked
        icon={<Rocket className="w-6 h-6" />}
        title="IPO calendar & subscription tracker"
        whatIsThis="The IPO tab will show every Indian mainboard and SME IPO with its price band, lot size, GMP (grey-market premium), live subscription numbers, listing date, and listing-day performance. Best-in-class data for retail IPO participants."
        sourceName="Chittorgarh"
        sourceUrl="https://www.chittorgarh.com/report/ipo-list-current-year/64/all/"
        expectedColumns={["Issue Name", "Open Date", "Close Date", "Price Band", "Lot Size", "Issue Size", "GMP", "Subscription ×"]}
      />
    </div>
  );
}
