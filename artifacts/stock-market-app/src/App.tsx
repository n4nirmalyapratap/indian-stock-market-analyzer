import { useEffect } from "react";
import { Switch, Route, Router as WouterRouter, useLocation } from "wouter";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import ChartView from "@/pages/ChartView";
import Dashboard from "@/pages/Dashboard";
import Sectors from "@/pages/Sectors";
import StockLookup from "@/pages/StockLookup";
import Patterns from "@/pages/Patterns";
import Scanners from "@/pages/Scanners";
import HydraAlpha from "@/pages/HydraAlpha";
import InvestorCouncil from "@/pages/InvestorCouncil";
import OptionsStrategyTester from "@/pages/OptionsStrategyTester";
import SettingsPage from "@/pages/SettingsPage";
import Portfolio from "@/pages/Portfolio";
import DCF from "@/pages/DCF";
import NotFound from "@/pages/not-found";
import TradingPlatform from "@/pages/TradingPlatform";
import SectorDetail from "@/pages/SectorDetail";
import NewsFeed from "@/pages/NewsFeed";
import SentimentDashboard from "@/pages/SentimentDashboard";
import LoginPage from "@/pages/LoginPage";
import InsightsLayout from "@/pages/insights/InsightsLayout";
import AIAnalyst from "@/pages/AIAnalyst";
import AIAnalystCompare from "@/pages/AIAnalystCompare";
import AIAnalystScan from "@/pages/AIAnalystScan";
import AIAnalystTrackRecord from "@/pages/AIAnalystTrackRecord";
import SavedAnalyses from "@/pages/SavedAnalyses";
import GlobalAssistant from "@/components/GlobalAssistant";
import { ThemeProvider } from "@/context/ThemeContext";
import { CustomAuthProvider, useCustomAuth } from "@/context/CustomAuthContext";
import { setTokenGetter } from "@/lib/api";
import { useMarketStateBoundary } from "@/lib/marketData";
import { LayoutShell } from "@/LayoutShell";

const queryClient = new QueryClient({
  // refetchOnWindowFocus defaults to true so any market-data query (even
  // ones not yet migrated to marketDataQueryOptions) re-validates against
  // the official close when the user returns to the tab.
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: true } },
});

const basePath = import.meta.env.BASE_URL.replace(/\/$/, "");


// ── User profile ──────────────────────────────────────────────────────────────

function UserProfile({ open }: { open: boolean }) {
  const { user } = useCustomAuth();
  if (!user) return null;

  const initials = (user.name || user.email)
    .split(" ").map((n: string) => n[0]).join("").toUpperCase().slice(0, 2);

  if (!open) {
    return (
      <div className="w-full flex justify-center py-2">
        <div className="w-7 h-7 rounded-full bg-indigo-500 flex items-center justify-center text-white text-xs font-bold">
          {initials}
        </div>
      </div>
    );
  }

  return (
    <div className="mx-1.5 mb-1">
      <div className="flex items-center gap-2.5 px-2.5 py-2 rounded-lg bg-gray-50 dark:bg-gray-800/50">
        <div className="w-7 h-7 rounded-full bg-indigo-500 flex items-center justify-center text-white text-xs font-bold flex-shrink-0">
          {initials}
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-xs font-medium text-gray-900 dark:text-white truncate">{user.name || "User"}</p>
          <p className="text-[10px] text-gray-400 truncate">{user.email}</p>
        </div>
      </div>
    </div>
  );
}


// ── Layout ────────────────────────────────────────────────────────────────────

function Layout({ children }: { children: React.ReactNode }) {
  return <LayoutShell ProfileComponent={UserProfile}>{children}</LayoutShell>;
}


// ── Routes ────────────────────────────────────────────────────────────────────

function AppRoutes() {
  return (
    <Layout>
      <Switch>
        <Route path="/"                component={Dashboard} />
        <Route path="/trading"         component={TradingPlatform} />
        <Route path="/sectors/:sectorId" component={SectorDetail} />
        <Route path="/sectors"          component={Sectors} />
        <Route path="/insights/:tab*"   component={InsightsLayout} />
        <Route path="/insights"         component={InsightsLayout} />
        <Route path="/news"            component={NewsFeed} />
        <Route path="/sentiment"       component={SentimentDashboard} />
        <Route path="/stocks"          component={StockLookup} />
        <Route path="/patterns"        component={Patterns} />
        <Route path="/scanners"        component={Scanners} />
        <Route path="/hydra"           component={HydraAlpha} />
        <Route path="/agents/:symbol"  component={InvestorCouncil} />
        <Route path="/agents"          component={InvestorCouncil} />
        <Route path="/ai-analyst/saved"        component={SavedAnalyses} />
        <Route path="/ai-analyst/scan"         component={AIAnalystScan} />
        <Route path="/ai-analyst/compare"      component={AIAnalystCompare} />
        <Route path="/ai-analyst/track-record" component={AIAnalystTrackRecord} />
        <Route path="/ai-analyst/:ticker"      component={AIAnalyst} />
        <Route path="/ai-analyst"      component={AIAnalyst} />
        <Route path="/options"         component={OptionsStrategyTester} />
        <Route path="/portfolio"       component={Portfolio} />
        <Route path="/dcf"             component={DCF} />
        <Route path="/settings"        component={SettingsPage} />
        <Route path="/chart/:symbol"   component={ChartView} />
        <Route component={NotFound} />
      </Switch>
    </Layout>
  );
}


// ── Token injector ────────────────────────────────────────────────────────────

function TokenInjector() {
  const { token } = useCustomAuth();
  useEffect(() => {
    // Always update the getter so logout (token === null) actually clears
    // the closure. Without this, the API client kept returning the previous
    // token after logout for one render cycle.
    setTokenGetter(async () => token);
  }, [token]);
  return null;
}


// ── 401 auto-logout listener ──────────────────────────────────────────────────
// If any React Query call fails with 401 (stale JWT, server-side secret
// rotation, account disabled, etc.) we clear the auth state and bounce the
// user back to the Google sign-in screen instead of leaving them looking at
// an empty dashboard while the network panel fills with 401s.

function AuthErrorListener() {
  const { logout } = useCustomAuth();
  useEffect(() => {
    return queryClient.getQueryCache().subscribe((event) => {
      if (event.type !== "updated") return;
      const action = (event as { action?: { type?: string } }).action;
      if (action?.type !== "error") return;
      const err = event.query.state.error as { status?: number } | null;
      if (err?.status === 401) {
        logout();
      }
    });
  }, [logout]);
  return null;
}

// Watches IST market open/closed boundary and invalidates all React-Query
// caches at the transition so post-close pages snap to the sealed EOD close.
function MarketStateBoundary() {
  useMarketStateBoundary();
  return null;
}


// ── Auth gate ─────────────────────────────────────────────────────────────────

function AuthGate() {
  const { user, token } = useCustomAuth();
  const [path, navigate] = useLocation();

  if (!user || !token) {
    return <LoginPage />;
  }

  // Logged in but sitting on /login — redirect to the real root immediately
  if (path === "/login") {
    navigate("/", { replace: true });
    return null;
  }

  return (
    <>
      <TokenInjector />
      <AuthErrorListener />
      <MarketStateBoundary />
      <AppRoutes />
      <GlobalAssistant />
    </>
  );
}


// ── Root ──────────────────────────────────────────────────────────────────────

function App() {
  return (
    <ThemeProvider>
      <CustomAuthProvider>
        <TooltipProvider>
          <WouterRouter base={basePath}>
            <QueryClientProvider client={queryClient}>
              <AuthGate />
            </QueryClientProvider>
          </WouterRouter>
          <Toaster />
        </TooltipProvider>
      </CustomAuthProvider>
    </ThemeProvider>
  );
}

export default App;
