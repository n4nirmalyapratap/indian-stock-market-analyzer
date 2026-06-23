import { useLocation } from "wouter";
import {
  LayoutGrid, BarChart3, FileText, PieChart, Briefcase,
  Ban, Truck, LineChart, Rocket, CalendarClock,
  Globe, ArrowLeft, ChevronRight, Zap,
} from "lucide-react";
import HeatmapTab from "./tabs/Heatmap";
import FiiDiiTab from "./tabs/FiiDii";
import CompanyFilingsTab from "./tabs/CompanyFilings";
import MfHoldingsTab from "./tabs/MfHoldings";
import BulkBlockDealsTab from "./tabs/BulkBlockDeals";
import CorpEventsTab from "./tabs/CorpEvents";
import FoBanTab from "./tabs/FoBan";
import TopDeliveriesTab from "./tabs/TopDeliveries";
import MarketValuationTab from "./tabs/MarketValuation";
import IpoTab from "./tabs/Ipo";
import MacroTab from "./tabs/Macro";
import EarningsRadarTab from "./tabs/EarningsRadar";

const TABS = [
  {
    slug: "macro",
    label: "Macro Pulse",
    description: "RBI repo rate, CPI, IIP, USD/INR, India 10Y and Brent — all in one place.",
    icon: Globe,
    Component: MacroTab,
    color: "text-teal-500",
    bg: "bg-teal-50 dark:bg-teal-500/10"
  },
  {
    slug: "heatmap",
    label: "Heatmap",
    description: "Visual representation of market performance across sectors and indices.",
    icon: LayoutGrid,
    Component: HeatmapTab,
    color: "text-orange-500",
    bg: "bg-orange-50 dark:bg-orange-500/10"
  },
  {
    slug: "fii-dii",
    label: "FII/DII Data",
    description: "Track institutional buying and selling activity in the Indian markets.",
    icon: BarChart3,
    Component: FiiDiiTab,
    color: "text-blue-500",
    bg: "bg-blue-50 dark:bg-blue-500/10"
  },
  {
    slug: "top-deliveries",
    label: "Top Deliveries",
    description: "Highest-conviction names by delivery % — long-term accumulation signal.",
    icon: Truck,
    Component: TopDeliveriesTab,
    color: "text-violet-500",
    bg: "bg-violet-50 dark:bg-violet-500/10"
  },
  {
    slug: "ipo",
    label: "IPO Center",
    description: "Upcoming and current Initial Public Offerings with key details.",
    icon: Rocket,
    Component: IpoTab,
    color: "text-pink-500",
    bg: "bg-pink-50 dark:bg-pink-500/10"
  },
  {
    slug: "company-filings",
    label: "Company Filings",
    description: "Stay updated with the latest corporate announcements and BSE filings.",
    icon: FileText,
    Component: CompanyFilingsTab,
    color: "text-emerald-500",
    bg: "bg-emerald-50 dark:bg-emerald-500/10"
  },
  {
    slug: "earnings-radar",
    label: "Earnings Radar",
    description: "Live earnings beat/miss scanner — scores quarterly results on revenue, PAT, OPM and quality.",
    icon: Zap,
    Component: EarningsRadarTab,
    color: "text-yellow-500",
    bg: "bg-yellow-50 dark:bg-yellow-500/10"
  },
  {
    slug: "mf-holdings",
    label: "MF Holdings",
    description: "Analyze mutual fund portfolios and their top stock holdings.",
    icon: PieChart,
    Component: MfHoldingsTab,
    color: "text-purple-500",
    bg: "bg-purple-50 dark:bg-purple-500/10"
  },
  {
    slug: "bulk-block-deals",
    label: "Bulk/Block Deals",
    description: "Monitor large scale transactions by major market participants.",
    icon: Briefcase,
    Component: BulkBlockDealsTab,
    color: "text-indigo-500",
    bg: "bg-indigo-50 dark:bg-indigo-500/10"
  },
  {
    slug: "corp-events",
    label: "Corp. Events",
    description: "Dividends, results, splits, board meetings and other scheduled corporate actions.",
    icon: CalendarClock,
    Component: CorpEventsTab,
    color: "text-amber-500",
    bg: "bg-amber-50 dark:bg-amber-500/10"
  },
  {
    slug: "fo-ban",
    label: "F&O Ban - MWPL",
    description: "Stocks currently in the F&O ban period based on market-wide position limits.",
    icon: Ban,
    Component: FoBanTab,
    color: "text-red-500",
    bg: "bg-red-50 dark:bg-red-500/10"
  },
  {
    slug: "market-valuation",
    label: "Index Comparison",
    description: "Historical PE, PB, and Yield analysis for major market indices.",
    icon: LineChart,
    Component: MarketValuationTab,
    color: "text-violet-500",
    bg: "bg-violet-50 dark:bg-violet-500/10"
  },
] as const;

export default function InsightsLayout() {
  const [loc, navigate] = useLocation();
  const rest = loc.replace(/^\/insights\/?/, "").split("/")[0];
  const activeSlug = rest || "";
  const active = TABS.find(t => t.slug === activeSlug);
  const isHeatmap = activeSlug === "heatmap";

  if (!active) {
    return (
      <div className="max-w-7xl mx-auto">
        <header className="mb-8">
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Market Insights</h1>
          <p className="text-gray-500 dark:text-gray-400 mt-1">
            Deep-dive analytics and institutional data for the Indian Stock Market.
          </p>
        </header>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4 md:gap-6">
          {TABS.map((item) => {
            const Icon = item.icon;
            return (
              <button
                key={item.slug}
                onClick={() => navigate(`/insights/${item.slug}`)}
                className="group flex flex-col p-5 bg-white dark:bg-gray-800 rounded-2xl border border-gray-100 dark:border-gray-700 shadow-sm hover:shadow-md hover:-translate-y-1 transition-all text-left"
              >
                <div className={`w-12 h-12 rounded-xl ${item.bg} flex items-center justify-center mb-4 group-hover:scale-110 transition-transform`}>
                  <Icon className={`w-6 h-6 ${item.color}`} />
                </div>
                <h3 className="font-bold text-gray-900 dark:text-white mb-1 flex items-center justify-between">
                  {item.label}
                  <ChevronRight className="w-4 h-4 text-gray-300 group-hover:text-indigo-500 transition-colors" />
                </h3>
                <p className="text-sm text-gray-500 dark:text-gray-400 leading-relaxed">
                  {item.description}
                </p>
              </button>
            );
          })}
        </div>
      </div>
    );
  }

  const ActiveComponent = active.Component;
  const ActiveIcon = active.icon;

  return (
    <div className={`flex flex-col min-w-0 ${isHeatmap ? "h-full relative" : "gap-4"}`}>
      {/* Refined Navigation (Heatmap uses internal Command Center back button) */}
      {!isHeatmap && (
        <div className="flex items-center gap-3 py-2">
          <button
            onClick={() => navigate("/insights")}
            className="p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-full text-gray-500 dark:text-gray-400 transition-colors"
          >
            <ArrowLeft className="w-5 h-5" />
          </button>
          <h2 className="font-bold text-gray-900 dark:text-white text-xl">
            {active.label}
          </h2>
        </div>
      )}

      {/* Content area */}
      <main className={`flex-1 min-w-0 ${isHeatmap ? "min-h-0 overflow-hidden flex flex-col" : "overflow-x-hidden"}`}>
        <ActiveComponent key={active.slug} />
      </main>
    </div>
  );
}

