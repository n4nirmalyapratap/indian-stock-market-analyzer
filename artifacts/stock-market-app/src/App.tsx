import { lazy, Suspense, useState, useEffect } from "react";
import { Switch, Route, Router as WouterRouter, Link, useLocation } from "wouter";
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

// Lazily import ALL of @clerk/react — only loaded when a key is configured.
// This prevents Clerk from trying to fetch its browser SDK from a CDN when
// running in environments (Docker/offline) where Clerk is not configured.
const ClerkApp = lazy(() => import("./ClerkApp"));

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
});

const clerkPubKey = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY as string | undefined;
const basePath    = import.meta.env.BASE_URL.replace(/\/$/, "");


// ── User profile — custom-auth only ──────────────────────────────────────────

function CustomOnlyUserProfile({ open }: { open: boolean }) {
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


// ── Layout (no-Clerk variant) ─────────────────────────────────────────────────

function LayoutNoClerk({ children }: { children: React.ReactNode }) {
  return <LayoutShell ProfileComponent={CustomOnlyUserProfile}>{children}</LayoutShell>;
}


// ── Routes (no Clerk) ─────────────────────────────────────────────────────────

function AppRoutesNoClerk() {
  return (
    <LayoutNoClerk>
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
    </LayoutNoClerk>
  );
}


// ── Token injector (no Clerk) ─────────────────────────────────────────────────

function CustomTokenInjector() {
  const { token } = useCustomAuth();
  useEffect(() => {
    if (token) setTokenGetter(async () => token!);
  }, [token]);
  return null;
}


// ── App flow when Clerk is NOT configured ─────────────────────────────────────

function NoClerkGate() {
  const { user, token } = useCustomAuth();

  if (!user || !token) {
    return <LoginPage showGoogle={false} />;
  }

  return (
    <>
      <CustomTokenInjector />
      <AppRoutesNoClerk />
      <GlobalAssistant />
    </>
  );
}

function AppWithoutClerk() {
  return (
    <QueryClientProvider client={queryClient}>
      <NoClerkGate />
    </QueryClientProvider>
  );
}


// ── Root ──────────────────────────────────────────────────────────────────────

function App() {
  return (
    <ThemeProvider>
      <CustomAuthProvider>
        <TooltipProvider>
          <WouterRouter base={basePath}>
            {clerkPubKey
              ? <Suspense fallback={null}><ClerkApp /></Suspense>
              : <AppWithoutClerk />
            }
          </WouterRouter>
          <Toaster />
        </TooltipProvider>
      </CustomAuthProvider>
    </ThemeProvider>
  );
}

export default App;
