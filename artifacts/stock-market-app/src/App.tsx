import { useState, useEffect, useRef } from "react";
import { Switch, Route, Router as WouterRouter, Link, useLocation, Redirect } from "wouter";
import { QueryClient, QueryClientProvider, useQueryClient } from "@tanstack/react-query";
import { ClerkProvider, SignIn, SignUp, Show, useClerk, useUser, useAuth } from "@clerk/react";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import ChartView from "@/pages/ChartView";
import Dashboard from "@/pages/Dashboard";
import Sectors from "@/pages/Sectors";
import StockLookup from "@/pages/StockLookup";
import Patterns from "@/pages/Patterns";
import Scanners from "@/pages/Scanners";
import WhatsAppBot from "@/pages/WhatsAppBot";
import TelegramBot from "@/pages/TelegramBot";
import HydraAlpha from "@/pages/HydraAlpha";
import OptionsStrategyTester from "@/pages/OptionsStrategyTester";
import SettingsPage from "@/pages/SettingsPage";
import NotFound from "@/pages/not-found";
import TradingPlatform from "@/pages/TradingPlatform";
import SectorDetail from "@/pages/SectorDetail";
import NewsFeed from "@/pages/NewsFeed";
import LandingPage from "@/pages/LandingPage";
import GlobalAssistant from "@/components/GlobalAssistant";
import { ThemeProvider, useTheme } from "@/context/ThemeContext";
import { setTokenGetter } from "@/lib/api";
import {
  LayoutDashboard, BarChart3, Search, Scan, Filter,
  MessageCircle, Send, Brain, TrendingUp, CandlestickChart,
  Settings, ChevronRight, ChevronLeft, ChevronDown, Sun, Moon,
  Newspaper, LogOut, User,
} from "lucide-react";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
});

const clerkPubKey = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;
const clerkProxyUrl = import.meta.env.VITE_CLERK_PROXY_URL;
const basePath = import.meta.env.BASE_URL.replace(/\/$/, "");

if (!clerkPubKey) {
  throw new Error("Missing VITE_CLERK_PUBLISHABLE_KEY");
}

function stripBase(path: string): string {
  return basePath && path.startsWith(basePath)
    ? path.slice(basePath.length) || "/"
    : path;
}

const MAIN_NAV = [
  { path: "/",         label: "Dashboard",      icon: LayoutDashboard },
  { path: "/trading",  label: "Chart Studio",   icon: CandlestickChart },
  { path: "/sectors",  label: "Market Sectors", icon: BarChart3 },
  { path: "/news",     label: "News Feed",      icon: Newspaper },
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

function NavLink({ path, label, icon: Icon, open, indent = false }: {
  path: string; label: string; icon: React.ElementType; open: boolean; indent?: boolean;
}) {
  const [loc] = useLocation();
  const active = loc === path || (path !== "/" && loc.startsWith(path));
  return (
    <Link
      href={path}
      title={!open ? label : undefined}
      className={`flex items-center gap-2.5 transition rounded-lg mx-1.5
        ${indent && open ? "pl-7 pr-2.5 py-1.5" : open ? "px-2.5 py-2" : "px-0 py-2 justify-center"}
        ${active
          ? "bg-indigo-50 dark:bg-indigo-500/20 text-indigo-700 dark:text-indigo-300"
          : "text-gray-500 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800 hover:text-gray-900 dark:hover:text-white"
        }`}
    >
      <Icon className={`flex-shrink-0 ${indent ? "w-4 h-4" : "w-[18px] h-[18px]"} ${active ? "text-indigo-600 dark:text-indigo-400" : ""}`} />
      {open && <span className={`font-medium whitespace-nowrap ${indent ? "text-xs" : "text-sm"}`}>{label}</span>}
    </Link>
  );
}

function ThemeToggle({ open }: { open: boolean }) {
  const { theme, toggleWithRipple } = useTheme();
  const isDark = theme === "dark";
  return (
    <button
      onClick={(e) => toggleWithRipple(e.clientX, e.clientY)}
      title={isDark ? "Switch to light mode" : "Switch to dark mode"}
      className={`w-full flex items-center gap-2.5 rounded-lg transition py-2
        ${open ? "px-2.5 mx-1.5 w-[calc(100%-12px)]" : "px-0 justify-center"}
        text-gray-400 dark:text-gray-500 hover:text-indigo-600 dark:hover:text-indigo-400 hover:bg-gray-50 dark:hover:bg-gray-800`}
    >
      {isDark
        ? <Sun  className="w-4 h-4 flex-shrink-0" />
        : <Moon className="w-4 h-4 flex-shrink-0" />}
      {open && <span className="text-xs font-medium whitespace-nowrap">{isDark ? "Light mode" : "Dark mode"}</span>}
    </button>
  );
}

function UserProfile({ open }: { open: boolean }) {
  const { user, isLoaded } = useUser();
  const { signOut } = useClerk();

  if (!isLoaded || !user) return null;

  const name = user.fullName || user.firstName || user.emailAddresses[0]?.emailAddress || "User";
  const initials = name.split(" ").map((n: string) => n[0]).join("").toUpperCase().slice(0, 2);
  const avatarUrl = user.imageUrl;

  const handleSignOut = () => signOut({ redirectUrl: "/" });

  if (!open) {
    return (
      <button
        onClick={handleSignOut}
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
        {avatarUrl ? (
          <img src={avatarUrl} alt={name} className="w-7 h-7 rounded-full object-cover flex-shrink-0" />
        ) : (
          <div className="w-7 h-7 rounded-full bg-indigo-500 flex items-center justify-center text-white text-xs font-bold flex-shrink-0">
            {initials}
          </div>
        )}
        <div className="flex-1 min-w-0">
          <p className="text-xs font-medium text-gray-900 dark:text-white truncate">{name}</p>
          <p className="text-[10px] text-gray-400 truncate">{user.emailAddresses[0]?.emailAddress}</p>
        </div>
        <button
          onClick={handleSignOut}
          title="Sign out"
          className="text-gray-400 hover:text-red-400 transition flex-shrink-0"
        >
          <LogOut className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
}

function Layout({ children }: { children: React.ReactNode }) {
  const [loc] = useLocation();
  const [open, setOpen]           = useState(() => localStorage.getItem("sidebar-open") === "true");
  const [settingsOpen, setSettingsOpen] = useState(false);

  useEffect(() => { localStorage.setItem("sidebar-open", String(open)); }, [open]);

  useEffect(() => {
    if (SETTINGS_NAV.some(({ path }) => loc === path)) setSettingsOpen(true);
  }, [loc]);

  const inSettings = SETTINGS_NAV.some(({ path }) => loc === path) || loc === "/settings";

  return (
    <div className="h-screen bg-gray-50 dark:bg-gray-950 flex overflow-hidden">

      {/* ── Sidebar ─────────────────────────────────────────────────────── */}
      <aside className={`hidden md:flex flex-col bg-white dark:bg-gray-950 border-r border-gray-100 dark:border-white/[0.05] flex-shrink-0
        transition-all duration-200 ease-in-out ${open ? "w-52" : "w-[52px]"}`}>

        {/* Logo */}
        <div className={`flex items-center gap-2.5 border-b border-gray-100 dark:border-white/[0.05] flex-shrink-0 h-[57px]
          ${open ? "px-4" : "justify-center"}`}>
          <img src="/niftynodes-logo.png" alt="NiftyNodes" className="w-8 h-8 rounded-full object-cover flex-shrink-0" />
          {open && (
            <div className="overflow-hidden">
              <p className="font-bold text-gray-900 dark:text-white text-sm whitespace-nowrap">Nifty Node</p>
              <p className="text-xs text-gray-400 dark:text-gray-500 whitespace-nowrap">Indian Stock Market</p>
            </div>
          )}
        </div>

        {/* Main nav */}
        <nav className="flex-1 py-2 space-y-0.5 overflow-y-auto overflow-x-hidden">
          {MAIN_NAV.map((item) => (
            <NavLink key={item.path} {...item} open={open} />
          ))}
        </nav>

        {/* Bottom: Settings + theme + user + toggle */}
        <div className="border-t border-gray-100 dark:border-white/[0.05] py-2 flex-shrink-0">

          {open ? (
            <div className="space-y-0.5">
              <button
                onClick={() => setSettingsOpen(s => !s)}
                className={`w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg mx-1.5 transition
                  ${inSettings
                    ? "bg-indigo-50 dark:bg-indigo-500/20 text-indigo-700 dark:text-indigo-300"
                    : "text-gray-500 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800 hover:text-gray-900 dark:hover:text-white"}
                  w-[calc(100%-12px)]`}
              >
                <Settings className="w-[18px] h-[18px] flex-shrink-0" />
                <span className="text-sm font-medium flex-1 text-left">Settings</span>
                <ChevronDown className={`w-3.5 h-3.5 transition-transform duration-150 ${settingsOpen ? "rotate-180" : ""}`} />
              </button>
              {settingsOpen && (
                <div className="space-y-0.5 pb-0.5">
                  {SETTINGS_NAV.map((item) => (
                    <NavLink key={item.path} {...item} open={open} indent />
                  ))}
                </div>
              )}
            </div>
          ) : (
            <NavLink path="/settings" label="Settings" icon={Settings} open={false} />
          )}

          <ThemeToggle open={open} />
          <UserProfile open={open} />

          <button
            onClick={() => setOpen(o => !o)}
            title={open ? "Collapse sidebar" : "Expand sidebar"}
            className={`w-full flex items-center gap-2.5 rounded-lg transition py-2 mt-0.5
              ${open ? "px-2.5 w-[calc(100%-12px)] mx-1.5" : "px-0 justify-center"}
              text-gray-400 dark:text-gray-500 hover:text-indigo-600 dark:hover:text-indigo-400 hover:bg-gray-50 dark:hover:bg-gray-800`}
          >
            {open
              ? <ChevronLeft  className="w-4 h-4 flex-shrink-0" />
              : <ChevronRight className="w-4 h-4 flex-shrink-0" />}
            {open && <span className="text-xs font-medium text-gray-400 dark:text-gray-500 whitespace-nowrap">Collapse</span>}
          </button>
        </div>
      </aside>

      {/* ── Content ─────────────────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col min-w-0 bg-gray-50 dark:bg-gray-950">

        {/* Mobile header */}
        <div className="md:hidden bg-white dark:bg-gray-900 border-b border-gray-100 dark:border-gray-800 px-4 py-3 flex items-center gap-2">
          <img src="/niftynodes-logo.png" alt="NiftyNodes" className="w-7 h-7 rounded-full object-cover" />
          <span className="font-bold text-gray-900 dark:text-white text-sm flex-1">Nifty Node</span>
          <ThemeToggle open={false} />
        </div>

        {/* Mobile nav strip */}
        <div className="md:hidden bg-white dark:bg-gray-900 border-b border-gray-100 dark:border-gray-800 px-2 py-2 flex gap-1 overflow-x-auto">
          {[...MAIN_NAV, { path: "/settings", label: "Settings", icon: Settings }].map(({ path, label, icon: Icon }) => {
            const active = loc === path || (path !== "/" && loc.startsWith(path));
            return (
              <Link key={path} href={path}
                className={`flex flex-col items-center gap-0.5 px-3 py-1.5 rounded-lg text-xs transition flex-shrink-0
                  ${active ? "bg-indigo-50 dark:bg-indigo-500/20 text-indigo-700 dark:text-indigo-300 font-medium" : "text-gray-500 dark:text-gray-400"}`}
              >
                <Icon className="w-4 h-4" />
                {label}
              </Link>
            );
          })}
        </div>

        <main className={`flex-1 overflow-auto bg-gray-50 dark:bg-gray-950 ${(loc.startsWith("/trading") || loc.startsWith("/chart")) ? "p-0 overflow-hidden" : "p-4 md:p-6"}`}>
          {children}
        </main>
      </div>
    </div>
  );
}

function AuthTokenInjector() {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();
  const prevUserRef = useRef<string | null | undefined>(undefined);
  const { user } = useUser();

  useEffect(() => {
    setTokenGetter(getToken);
  }, [getToken]);

  useEffect(() => {
    const userId = user?.id ?? null;
    if (prevUserRef.current !== undefined && prevUserRef.current !== userId) {
      queryClient.clear();
    }
    prevUserRef.current = userId;
  }, [user?.id, queryClient]);

  return null;
}

function SignInPage() {
  // To update login providers, app branding, or OAuth settings use the Auth
  // pane in the workspace toolbar. More information can be found in the Replit docs.
  return (
    <div className="min-h-screen bg-gray-950 flex flex-col items-center justify-center py-12 px-4">
      <div className="mb-8 flex flex-col items-center">
        <img src="/niftynodes-logo.png" alt="NiftyNodes" className="w-12 h-12 rounded-full object-cover mb-3" />
        <p className="text-white font-bold text-lg">Nifty Node</p>
        <p className="text-gray-400 text-sm">Indian Stock Market Analysis</p>
      </div>
      <SignIn
        routing="path"
        path={`${basePath}/sign-in`}
        signUpUrl={`${basePath}/sign-up`}
        fallbackRedirectUrl={`${basePath}/`}
      />
    </div>
  );
}

function SignUpPage() {
  // To update login providers, app branding, or OAuth settings use the Auth
  // pane in the workspace toolbar. More information can be found in the Replit docs.
  return (
    <div className="min-h-screen bg-gray-950 flex flex-col items-center justify-center py-12 px-4">
      <div className="mb-8 flex flex-col items-center">
        <img src="/niftynodes-logo.png" alt="NiftyNodes" className="w-12 h-12 rounded-full object-cover mb-3" />
        <p className="text-white font-bold text-lg">Nifty Node</p>
        <p className="text-gray-400 text-sm">Indian Stock Market Analysis</p>
      </div>
      <SignUp
        routing="path"
        path={`${basePath}/sign-up`}
        signInUrl={`${basePath}/sign-in`}
        fallbackRedirectUrl={`${basePath}/`}
      />
    </div>
  );
}

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
        <Route path="/whatsapp"        component={() => <WhatsAppBot />} />
        <Route path="/telegram"        component={() => <TelegramBot />} />
        <Route path="/hydra"           component={HydraAlpha} />
        <Route path="/options"         component={OptionsStrategyTester} />
        <Route path="/settings"        component={SettingsPage} />
        <Route path="/chart/:symbol"   component={ChartView} />
        <Route component={NotFound} />
      </Switch>
    </Layout>
  );
}

function ClerkProviderWithRoutes() {
  const [, setLocation] = useLocation();

  return (
    <ClerkProvider
      publishableKey={clerkPubKey}
      proxyUrl={clerkProxyUrl}
      routerPush={(to) => setLocation(stripBase(to))}
      routerReplace={(to) => setLocation(stripBase(to), { replace: true })}
    >
      <QueryClientProvider client={queryClient}>
        <Switch>
          <Route path="/sign-in/*?" component={SignInPage} />
          <Route path="/sign-up/*?" component={SignUpPage} />
          <Route>
            <Show when="signed-in">
              <AuthTokenInjector />
              <AppRoutes />
              <GlobalAssistant />
            </Show>
            <Show when="signed-out">
              <LandingPage />
            </Show>
          </Route>
        </Switch>
      </QueryClientProvider>
    </ClerkProvider>
  );
}

function App() {
  return (
    <ThemeProvider>
      <TooltipProvider>
        <WouterRouter base={basePath}>
          <ClerkProviderWithRoutes />
        </WouterRouter>
        <Toaster />
      </TooltipProvider>
    </ThemeProvider>
  );
}

export default App;
