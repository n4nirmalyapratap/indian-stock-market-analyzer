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
import NotFound from "@/pages/not-found";
import { LayoutDashboard, BarChart3, Search, Scan, Filter, MessageCircle, Send, Brain } from "lucide-react";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
});

const NAV = [
  { path: "/", label: "Dashboard", icon: LayoutDashboard },
  { path: "/sectors", label: "Market Sectors", icon: BarChart3 },
  { path: "/stocks", label: "Stock Lookup", icon: Search },
  { path: "/patterns", label: "Patterns", icon: Scan },
  { path: "/scanners", label: "Scanners", icon: Filter },
  { path: "/whatsapp", label: "WhatsApp Bot", icon: MessageCircle },
  { path: "/telegram", label: "Telegram Bot", icon: Send },
  { path: "/hydra", label: "AI Analyzer", icon: Brain },
];

function Layout({ children }: { children: React.ReactNode }) {
  const [loc] = useLocation();
  return (
    <div className="min-h-screen bg-gray-50 flex">
      <aside className="w-56 bg-white border-r border-gray-100 shadow-sm flex-shrink-0 hidden md:flex flex-col">
        <div className="px-4 py-5 border-b border-gray-100">
          <div className="flex items-center gap-2.5">
            <img src="/niftynodes-logo.png" alt="NiftyNodes" className="w-9 h-9 rounded-full object-cover" />
            <div>
              <p className="font-bold text-gray-900 text-sm">Nifty Node</p>
              <p className="text-xs text-gray-400">Indian Stock Market</p>
            </div>
          </div>
        </div>
        <nav className="flex-1 px-2 py-3 space-y-0.5">
          {NAV.map(({ path, label, icon: Icon }) => {
            const active = loc === path || (path !== "/" && loc.startsWith(path));
            return (
              <Link
                key={path}
                href={path}
                className={`flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition ${active ? "bg-indigo-50 text-indigo-700 font-medium" : "text-gray-600 hover:bg-gray-50 hover:text-gray-900"}`}
              >
                <Icon className={`w-4 h-4 ${active ? "text-indigo-600" : "text-gray-400"}`} />
                {label}
              </Link>
            );
          })}
        </nav>
        <div className="px-4 py-3 border-t border-gray-100">
          <p className="text-xs text-gray-400 leading-relaxed">End-of-day data. NSE primary, Yahoo Finance fallback.</p>
        </div>
      </aside>

      <div className="flex-1 flex flex-col min-w-0">
        <div className="md:hidden bg-white border-b border-gray-100 px-4 py-3 flex items-center gap-2">
          <img src="/niftynodes-logo.png" alt="NiftyNodes" className="w-7 h-7 rounded-full object-cover" />
          <span className="font-bold text-gray-900 text-sm">Nifty Node</span>
        </div>
        <div className="md:hidden bg-white border-b border-gray-100 px-2 py-2 flex gap-1 overflow-x-auto">
          {NAV.map(({ path, label, icon: Icon }) => {
            const active = loc === path || (path !== "/" && loc.startsWith(path));
            return (
              <Link
                key={path}
                href={path}
                className={`flex flex-col items-center gap-0.5 px-3 py-1.5 rounded-lg text-xs transition flex-shrink-0 ${active ? "bg-indigo-50 text-indigo-700 font-medium" : "text-gray-500"}`}
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
        <Route path="/" component={Dashboard} />
        <Route path="/sectors" component={Sectors} />
        <Route path="/stocks" component={StockLookup} />
        <Route path="/patterns" component={Patterns} />
        <Route path="/scanners" component={Scanners} />
        <Route path="/whatsapp" component={WhatsAppBot} />
        <Route path="/telegram" component={TelegramBot} />
        <Route path="/hydra" component={HydraAlpha} />
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
