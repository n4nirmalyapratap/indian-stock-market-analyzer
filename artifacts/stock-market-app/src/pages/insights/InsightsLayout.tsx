import { useLocation } from "wouter";
import {
  LayoutGrid, BarChart3, FileText, PieChart, Briefcase,
  Activity, Repeat, Users, Ban, Truck, LineChart, Rocket,
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

/**
 * InsightsLayout — uses the SAME visual language as the rest of the app
 * (Dashboard, Sectors, Sentiment) so it feels integrated:
 *   surface  : bg-white dark:bg-gray-800
 *   page bg  : bg-gray-50 dark:bg-gray-950 (provided by LayoutShell <main>)
 *   borders  : border-gray-100 dark:border-gray-700
 *   active   : bg-indigo-50 dark:bg-indigo-500/20 + text-indigo-700/300
 *   muted    : text-gray-500 dark:text-gray-400
 *
 * Layout details that prevent horizontal scroll:
 *   - Outer flex wrapper has `min-w-0` so flex children can shrink.
 *   - <main> has `flex-1 min-w-0 overflow-x-hidden` so wide tables/charts
 *     stay clipped to the available width instead of pushing the page.
 */
export default function InsightsLayout() {
  const [loc, navigate] = useLocation();
  const rest = loc.replace(/^\/insights\/?/, "").split("/")[0];
  const slug = rest || DEFAULT_SLUG;
  const active = TABS.find(t => t.slug === slug) || TABS[0];
  const ActiveComponent = active.Component;

  return (
    <div className="flex gap-4 md:gap-6 min-w-0">
      {/* Inner left sidebar (desktop) — same surface/spacing as the app's other cards */}
      <aside className="hidden md:flex flex-col w-56 lg:w-60 rounded-xl border border-gray-100 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-sm flex-shrink-0 sticky top-4 self-start max-h-[calc(100vh-2rem)]">
        <div className="px-4 py-3 border-b border-gray-100 dark:border-gray-700">
          <h2 className="font-bold text-gray-900 dark:text-white text-sm">Insights</h2>
          <p className="text-[11px] text-gray-500 dark:text-gray-400 mt-0.5">Market intelligence</p>
        </div>
        <nav className="flex-1 overflow-y-auto py-2">
          {TABS.map(({ slug: s, label, icon: Icon }) => {
            const isActive = s === slug;
            return (
              <button
                key={s}
                type="button"
                onClick={() => navigate(`/insights/${s}`)}
                className={`w-full text-left flex items-center gap-2.5 px-3 py-2 mx-2 my-0.5 rounded-lg text-sm transition cursor-pointer
                  ${isActive
                    ? "bg-indigo-50 dark:bg-indigo-500/20 text-indigo-700 dark:text-indigo-300 font-semibold"
                    : "text-gray-500 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700/50 hover:text-gray-900 dark:hover:text-white"}`}
              >
                <Icon className={`w-4 h-4 flex-shrink-0 ${isActive ? "text-indigo-600 dark:text-indigo-400" : ""}`} />
                <span className="flex-1 truncate">{label}</span>
              </button>
            );
          })}
        </nav>
      </aside>

      {/* Mobile horizontal pill scroller */}
      <div className="md:hidden -mx-4 px-2 py-2 flex gap-1 overflow-x-auto sticky top-0 z-20 bg-gray-50/80 dark:bg-gray-950/80 backdrop-blur border-b border-gray-100 dark:border-gray-800">
        {TABS.map(({ slug: s, label }) => (
          <button
            key={s}
            type="button"
            onClick={() => navigate(`/insights/${s}`)}
            className={`px-3 py-1.5 text-xs whitespace-nowrap rounded-lg flex-shrink-0 transition
              ${s === slug
                ? "bg-indigo-600 text-white dark:bg-indigo-500"
                : "text-gray-500 dark:text-gray-400 bg-white dark:bg-gray-800 border border-gray-100 dark:border-gray-700"}`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Content area — `min-w-0` lets it shrink instead of overflowing */}
      <main className="flex-1 min-w-0 overflow-x-hidden">
        <ActiveComponent key={slug} />
      </main>
    </div>
  );
}
