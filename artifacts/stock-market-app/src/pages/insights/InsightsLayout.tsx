import { useLocation } from "wouter";
import {
  LayoutGrid, BarChart3, FileText, PieChart, Briefcase,
  Activity, Repeat, Users, Ban, Truck, LineChart, Rocket,
  Search,
} from "lucide-react";
import HeatmapTab from "./tabs/Heatmap";
import FiiDiiTab from "./tabs/FiiDii";
import CompanyFilingsTab from "./tabs/CompanyFilings";
import MfHoldingsTab from "./tabs/MfHoldings";
import BulkBlockDealsTab from "./tabs/BulkBlockDeals";
import SignalsTab from "./tabs/Signals";
import SlbmRentalTab from "./tabs/SlbmRental";
import MtfInsightsTab from "./tabs/MtfInsights";
import FoBanTab from "./tabs/FoBan";
import TopDeliveriesTab from "./tabs/TopDeliveries";
import MarketValuationTab from "./tabs/MarketValuation";
import IpoTab from "./tabs/Ipo";

const TABS = [
  { slug: "heatmap",          label: "Heatmap",               icon: LayoutGrid,  Component: HeatmapTab },
  { slug: "fii-dii",          label: "FII/DII Data",          icon: BarChart3,   Component: FiiDiiTab },
  { slug: "company-filings",  label: "Company Filings",       icon: FileText,    Component: CompanyFilingsTab },
  { slug: "mf-holdings",      label: "MF Holdings",           icon: PieChart,    Component: MfHoldingsTab },
  { slug: "bulk-block-deals", label: "Bulk/Block Deals",      icon: Briefcase,   Component: BulkBlockDealsTab },
  { slug: "signals",          label: "Signals",               icon: Activity,    Component: SignalsTab },
  { slug: "slbm-rental",      label: "Stock Rental via SLBM", icon: Repeat,      Component: SlbmRentalTab },
  { slug: "mtf-insights",     label: "MTF Insights",          icon: Users,       Component: MtfInsightsTab },
  { slug: "fo-ban",           label: "F&O Ban - MWPL",        icon: Ban,         Component: FoBanTab },
  { slug: "top-deliveries",   label: "Top Deliveries",        icon: Truck,       Component: TopDeliveriesTab },
  { slug: "market-valuation", label: "Market Valuation",      icon: LineChart,   Component: MarketValuationTab },
  { slug: "ipo",              label: "IPO",                   icon: Rocket,      Component: IpoTab },
] as const;

const DEFAULT_SLUG = "heatmap";

export default function InsightsLayout() {
  const [loc, navigate] = useLocation();
  const rest = loc.replace(/^\/insights\/?/, "").split("/")[0];
  const slug = rest || DEFAULT_SLUG;
  const active = TABS.find(t => t.slug === slug) || TABS[0];
  const ActiveComponent = active.Component;

  return (
    <div className="flex gap-4 md:gap-6 min-h-[calc(100vh-12rem)]">
      {/* Inner left sidebar (desktop) — same Card vibe as the rest of the app */}
      <aside className="hidden md:flex flex-col w-56 lg:w-60 rounded-xl border border-card-border bg-card text-card-foreground shadow-sm flex-shrink-0 sticky top-4 self-start max-h-[calc(100vh-2rem)]">
        <div className="px-4 py-3 border-b border-card-border flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center">
            <Search className="w-4 h-4 text-primary" />
          </div>
          <h2 className="font-bold text-foreground text-sm">Insights</h2>
        </div>
        <nav className="flex-1 overflow-y-auto py-1.5">
          {TABS.map(({ slug: s, label, icon: Icon }) => {
            const isActive = s === slug;
            return (
              <button
                key={s}
                type="button"
                onClick={() => navigate(`/insights/${s}`)}
                className={`w-full text-left flex items-center gap-2.5 px-3 py-2 mx-1.5 my-0.5 rounded-md text-sm transition cursor-pointer
                  ${isActive
                    ? "bg-primary/10 text-primary font-semibold"
                    : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"}`}
              >
                <Icon className={`w-4 h-4 flex-shrink-0 ${isActive ? "text-primary" : ""}`} />
                <span className="flex-1 truncate">{label}</span>
              </button>
            );
          })}
        </nav>
      </aside>

      {/* Mobile tab pills (top of content) */}
      <div className="md:hidden -mx-4 px-2 py-2 flex gap-1 overflow-x-auto sticky top-0 z-20 bg-background/80 backdrop-blur border-b border-card-border">
        {TABS.map(({ slug: s, label }) => (
          <button
            key={s}
            type="button"
            onClick={() => navigate(`/insights/${s}`)}
            className={`px-3 py-1.5 text-xs whitespace-nowrap rounded-lg flex-shrink-0 transition
              ${s === slug ? "bg-primary text-primary-foreground" : "text-muted-foreground bg-card border border-card-border hover:bg-accent"}`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Content area */}
      <main className="flex-1 min-w-0">
        <ActiveComponent key={slug} />
      </main>
    </div>
  );
}
