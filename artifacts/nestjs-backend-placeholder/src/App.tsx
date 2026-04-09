import { useState, useEffect, useRef } from "react";
import { Switch, Route, Router as WouterRouter, Link, useLocation } from "wouter";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import Dashboard from "@/pages/Dashboard";
import Sectors from "@/pages/Sectors";
import StockLookup from "@/pages/StockLookup";
import Patterns from "@/pages/Patterns";
import Scanners from "@/pages/Scanners";
import WhatsAppBot from "@/pages/WhatsAppBot";
import TelegramBot from "@/pages/TelegramBot";
import HydraAlpha from "@/pages/HydraAlpha";
import OptionsStrategyTester from "@/pages/OptionsStrategyTester";
import NotFound from "@/pages/not-found";
import {
  LayoutDashboard, BarChart3, Search, Scan, Filter,
  MessageCircle, Send, Brain, TrendingUp,
  Settings, Pin, PinOff, ChevronRight, X
} from "lucide-react";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
});

const MAIN_NAV = [
  { path: "/",         label: "Dashboard",      icon: LayoutDashboard },
  { path: "/sectors",  label: "Market Sectors", icon: BarChart3 },
  { path: "/stocks",   label: "Stock Lookup",   icon: Search },
  { path: "/patterns", label: "Patterns",       icon: Scan },
  { path: "/scanners", label: "Scanners",       icon: Filter },
  { path: "/hydra",    label: "AI Analyzer",    icon: Brain },
  { path: "/options",  label: "Options Tester", icon: TrendingUp },
];

const SETTINGS_NAV = [
  { path: "/whatsapp", label: "WhatsApp Bot", icon: MessageCircle },
  { path: "/telegram", label: "Telegram Bot", icon: Send },
];

function Layout({ children }: { children: React.ReactNode }) {
  const [loc] = useLocation();
  const [locked, setLocked]       = useState(() => localStorage.getItem("sidebar-locked") === "true");
  const [hovered, setHovered]     = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const settingsRef = useRef<HTMLDivElement>(null);

  const expanded = locked || hovered;

  useEffect(() => {
    localStorage.setItem("sidebar-locked", String(locked));
  }, [locked]);

  // Close settings popover on outside click
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (settingsRef.current && !settingsRef.current.contains(e.target as Node)) {
        setSettingsOpen(false);
      }
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const inSettings = SETTINGS_NAV.some(({ path }) => loc === path);

  return (
    <div className="min-h-screen bg-gray-50 flex">

      {/* ── Sidebar (desktop) ─────────────────────────────────────────── */}
      <aside
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
        className={`hidden md:flex flex-col bg-white border-r border-gray-100 shadow-sm flex-shrink-0
          transition-all duration-200 ease-in-out overflow-hidden
          ${expanded ? "w-52" : "w-[52px]"}`}
      >
        {/* Logo */}
        <div className={`flex items-center gap-2.5 border-b border-gray-100 flex-shrink-0
          ${expanded ? "px-4 py-4" : "px-0 py-4 justify-center"}`}>
          <img
            src="/niftynodes-logo.png"
            alt="NiftyNodes"
            className="w-8 h-8 rounded-full object-cover flex-shrink-0"
          />
          {expanded && (
            <div className="overflow-hidden">
              <p className="font-bold text-gray-900 text-sm whitespace-nowrap">Nifty Node</p>
              <p className="text-xs text-gray-400 whitespace-nowrap">Indian Stock Market</p>
            </div>
          )}
        </div>

        {/* Main nav */}
        <nav className="flex-1 py-2 space-y-0.5 overflow-hidden">
          {MAIN_NAV.map(({ path, label, icon: Icon }) => {
            const active = loc === path || (path !== "/" && loc.startsWith(path));
            return (
              <Link
                key={path}
                href={path}
                title={!expanded ? label : undefined}
                className={`flex items-center gap-2.5 transition rounded-lg mx-1.5
                  ${expanded ? "px-2.5 py-2" : "px-0 py-2 justify-center"}
                  ${active
                    ? "bg-indigo-50 text-indigo-700"
                    : "text-gray-500 hover:bg-gray-50 hover:text-gray-800"
                  }`}
              >
                <Icon className={`w-[18px] h-[18px] flex-shrink-0 ${active ? "text-indigo-600" : ""}`} />
                {expanded && (
                  <span className="text-sm font-medium whitespace-nowrap overflow-hidden">
                    {label}
                  </span>
                )}
              </Link>
            );
          })}
        </nav>

        {/* Bottom actions */}
        <div className={`border-t border-gray-100 py-2 space-y-0.5 flex-shrink-0`}>
          {/* Settings / bots */}
          <div ref={settingsRef} className="relative mx-1.5">
            <button
              onClick={() => setSettingsOpen(o => !o)}
              title={!expanded ? "Settings" : undefined}
              className={`w-full flex items-center gap-2.5 rounded-lg transition py-2
                ${expanded ? "px-2.5" : "px-0 justify-center"}
                ${inSettings || settingsOpen
                  ? "bg-indigo-50 text-indigo-700"
                  : "text-gray-500 hover:bg-gray-50 hover:text-gray-800"
                }`}
            >
              <Settings className="w-[18px] h-[18px] flex-shrink-0" />
              {expanded && <span className="text-sm font-medium">Settings</span>}
              {expanded && (
                <ChevronRight className={`w-3.5 h-3.5 ml-auto transition-transform ${settingsOpen ? "rotate-90" : ""}`} />
              )}
            </button>

            {/* Settings pop-out */}
            {settingsOpen && (
              <div className={`absolute bottom-full mb-1 bg-white rounded-xl shadow-lg border border-gray-200 py-1.5 z-50 min-w-[180px]
                ${expanded ? "left-0" : "left-12"}`}>
                <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-wide px-3 pt-1 pb-1.5">
                  Integrations
                </p>
                {SETTINGS_NAV.map(({ path, label, icon: Icon }) => {
                  const active = loc === path;
                  return (
                    <Link
                      key={path}
                      href={path}
                      onClick={() => setSettingsOpen(false)}
                      className={`flex items-center gap-2.5 px-3 py-2 text-sm transition
                        ${active ? "text-indigo-700 bg-indigo-50" : "text-gray-600 hover:bg-gray-50 hover:text-gray-900"}`}
                    >
                      <Icon className="w-4 h-4 flex-shrink-0" />
                      {label}
                    </Link>
                  );
                })}
              </div>
            )}
          </div>

          {/* Lock / unlock pin */}
          <button
            onClick={() => setLocked(l => !l)}
            title={locked ? "Unpin sidebar" : "Pin sidebar open"}
            className={`w-full flex items-center gap-2.5 rounded-lg transition py-2 mx-1.5
              ${expanded ? "px-2.5 w-[calc(100%-12px)]" : "px-0 justify-center w-[calc(100%-12px)]"}
              text-gray-400 hover:text-indigo-600 hover:bg-gray-50`}
          >
            {locked
              ? <PinOff className="w-[16px] h-[16px] flex-shrink-0" />
              : <Pin    className="w-[16px] h-[16px] flex-shrink-0" />}
            {expanded && (
              <span className="text-xs font-medium whitespace-nowrap">
                {locked ? "Unpin sidebar" : "Pin sidebar open"}
              </span>
            )}
          </button>
        </div>
      </aside>

      {/* ── Content ────────────────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col min-w-0">

        {/* Mobile header */}
        <div className="md:hidden bg-white border-b border-gray-100 px-4 py-3 flex items-center gap-2">
          <img src="/niftynodes-logo.png" alt="NiftyNodes" className="w-7 h-7 rounded-full object-cover" />
          <span className="font-bold text-gray-900 text-sm">Nifty Node</span>
        </div>

        {/* Mobile nav strip */}
        <div className="md:hidden bg-white border-b border-gray-100 px-2 py-2 flex gap-1 overflow-x-auto">
          {[...MAIN_NAV, ...SETTINGS_NAV].map(({ path, label, icon: Icon }) => {
            const active = loc === path || (path !== "/" && loc.startsWith(path));
            return (
              <Link
                key={path}
                href={path}
                className={`flex flex-col items-center gap-0.5 px-3 py-1.5 rounded-lg text-xs transition flex-shrink-0
                  ${active ? "bg-indigo-50 text-indigo-700 font-medium" : "text-gray-500"}`}
              >
                <Icon className="w-4 h-4" />
                {label}
              </Link>
            );
          })}
        </div>

        <main className="flex-1 p-4 md:p-6 overflow-auto">
          {children}
        </main>
      </div>
    </div>
  );
}

function Router() {
  return (
    <Layout>
      <Switch>
        <Route path="/"         component={Dashboard} />
        <Route path="/sectors"  component={Sectors} />
        <Route path="/stocks"   component={StockLookup} />
        <Route path="/patterns" component={Patterns} />
        <Route path="/scanners" component={Scanners} />
        <Route path="/whatsapp" component={WhatsAppBot} />
        <Route path="/telegram" component={TelegramBot} />
        <Route path="/hydra"    component={HydraAlpha} />
        <Route path="/options"  component={OptionsStrategyTester} />
        <Route component={NotFound} />
      </Switch>
    </Layout>
  );
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <WouterRouter base={import.meta.env.BASE_URL.replace(/\/$/, "")}>
          <Router />
        </WouterRouter>
        <Toaster />
      </TooltipProvider>
    </QueryClientProvider>
  );
}

export default App;
