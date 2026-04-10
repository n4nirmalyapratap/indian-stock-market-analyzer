import { useEffect } from "react";
import { Switch, Route, Router as WouterRouter } from "wouter";
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
import OptionsStrategyTester from "@/pages/OptionsStrategyTester";
import SettingsPage from "@/pages/SettingsPage";
import NotFound from "@/pages/not-found";
import TradingPlatform from "@/pages/TradingPlatform";
import SectorDetail from "@/pages/SectorDetail";
import NewsFeed from "@/pages/NewsFeed";
import LoginPage from "@/pages/LoginPage";
import GlobalAssistant from "@/components/GlobalAssistant";
import { ThemeProvider } from "@/context/ThemeContext";
import { CustomAuthProvider, useCustomAuth } from "@/context/CustomAuthContext";
import { setTokenGetter } from "@/lib/api";
import { LayoutShell } from "@/LayoutShell";
import { LogOut } from "lucide-react";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
});

const basePath = import.meta.env.BASE_URL.replace(/\/$/, "");


// ── User profile ──────────────────────────────────────────────────────────────

function UserProfile({ open }: { open: boolean }) {
  const { user, logout } = useCustomAuth();
  if (!user) return null;

  const initials = (user.name || user.email)
    .split(" ").map((n: string) => n[0]).join("").toUpperCase().slice(0, 2);

  if (!open) {
    return (
      <button
        onClick={logout}
        title="Sign out"
        className="w-full flex justify-center py-2 text-gray-400 hover:text-red-400 transition"
      >
        <LogOut className="w-4 h-4" />
      </button>
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
        <button
          onClick={logout}
          title="Sign out"
          className="text-gray-400 hover:text-red-400 transition flex-shrink-0"
        >
          <LogOut className="w-3.5 h-3.5" />
        </button>
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
        <Route path="/news"            component={NewsFeed} />
        <Route path="/stocks"          component={StockLookup} />
        <Route path="/patterns"        component={Patterns} />
        <Route path="/scanners"        component={Scanners} />
        <Route path="/hydra"           component={HydraAlpha} />
        <Route path="/options"         component={OptionsStrategyTester} />
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
    if (token) setTokenGetter(async () => token!);
  }, [token]);
  return null;
}


// ── Auth gate ─────────────────────────────────────────────────────────────────

function AuthGate() {
  const { user, token } = useCustomAuth();

  if (!user || !token) {
    return <LoginPage />;
  }

  return (
    <>
      <TokenInjector />
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
