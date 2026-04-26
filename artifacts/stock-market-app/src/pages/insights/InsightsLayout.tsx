import { useLocation } from "wouter";
import {
  LayoutGrid, BarChart3, FileText, PieChart, Briefcase,
  Activity, Repeat, Users, Ban, Truck, LineChart, Rocket,
  ChevronRight, Search,
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
  // Parse the slug straight off the URL — robust, no wouter pattern surprises.
  const [loc, navigate] = useLocation();
  const rest = loc.replace(/^\/insights\/?/, "").split("/")[0];
  const slug = rest || DEFAULT_SLUG;
  const active = TABS.find(t => t.slug === slug) || TABS[0];
  const ActiveComponent = active.Component;

  return (
    <div className="-m-4 md:-m-6 min-h-[calc(100vh-57px)] md:min-h-screen flex bg-gray-50 dark:bg-gray-950">
      {/* Inner left sidebar (desktop) */}
      <aside className="hidden md:flex flex-col w-60 border-r border-gray-100 dark:border-white/[0.05] bg-white dark:bg-gray-900 flex-shrink-0 sticky top-0 self-start max-h-screen">
        <div className="px-5 py-4 border-b border-gray-100 dark:border-white/[0.05] flex items-center gap-2">
          <div className="w-9 h-9 rounded-full bg-indigo-50 dark:bg-indigo-500/10 flex items-center justify-center">
            <Search className="w-4 h-4 text-indigo-500" />
          </div>
          <h2 className="font-bold text-gray-900 dark:text-white">Insights</h2>
        </div>
        <nav className="flex-1 overflow-y-auto py-2">
          {TABS.map(({ slug: s, label, icon: Icon }) => {
            const isActive = s === slug;
            return (
              <button
                key={s}
                type="button"
                onClick={() => navigate(`/insights/${s}`)}
                className={`w-full text-left flex items-center gap-3 px-4 py-2.5 mx-2 my-0.5 rounded-lg text-sm transition group cursor-pointer
                  ${isActive
                    ? "bg-indigo-50 dark:bg-indigo-500/15 text-indigo-700 dark:text-indigo-300 font-semibold"
                    : "text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800/60"}`}
              >
                <Icon className={`w-4 h-4 flex-shrink-0 ${isActive ? "text-indigo-600 dark:text-indigo-400" : ""}`} />
                <span className="flex-1 truncate">{label}</span>
                {isActive && <ChevronRight className="w-4 h-4 text-indigo-500" />}
              </button>
            );
          })}
        </nav>
      </aside>

      {/* Mobile tab pills (top of content) */}
      <div className="md:hidden bg-white dark:bg-gray-900 border-b border-gray-100 dark:border-white/[0.05] px-2 py-2 flex gap-1 overflow-x-auto sticky top-0 z-20">
        {TABS.map(({ slug: s, label }) => (
          <button
            key={s}
            type="button"
            onClick={() => navigate(`/insights/${s}`)}
            className={`px-3 py-1.5 text-xs whitespace-nowrap rounded-lg flex-shrink-0 transition
              ${s === slug ? "bg-indigo-500 text-white" : "text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700"}`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Content area */}
      <main className="flex-1 min-w-0 p-4 md:p-6">
        <ActiveComponent key={slug} />
      </main>
    </div>
  );
}
