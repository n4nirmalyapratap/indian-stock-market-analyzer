import { useState, useEffect, useRef } from "react";
import { Switch, Route, Router as WouterRouter, Link, useLocation, Redirect } from "wouter";
import { QueryClient, QueryClientProvider, useQueryClient } from "@tanstack/react-query";
import { ClerkProvider, SignIn, SignUp, useSignIn, useClerk, useUser, useAuth } from "@clerk/react";
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
import SettingsPage, { ClerkUserInfo } from "@/pages/SettingsPage";
import NotFound from "@/pages/not-found";
import TradingPlatform from "@/pages/TradingPlatform";
import SectorDetail from "@/pages/SectorDetail";
import NewsFeed from "@/pages/NewsFeed";
import LoginPage from "@/pages/LoginPage";
import GlobalAssistant from "@/components/GlobalAssistant";
import { ThemeProvider, useTheme } from "@/context/ThemeContext";
import { CustomAuthProvider, useCustomAuth } from "@/context/CustomAuthContext";
import { setTokenGetter } from "@/lib/api";
import {
  LayoutDashboard, BarChart3, Search, Scan, Filter,
  Brain, TrendingUp, CandlestickChart,
  Settings, ChevronRight, ChevronLeft, ChevronDown, Sun, Moon,
  Newspaper, LogOut,
} from "lucide-react";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
});

const clerkPubKey  = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY as string | undefined;
const clerkProxyUrl = import.meta.env.VITE_CLERK_PROXY_URL as string | undefined;
const basePath     = import.meta.env.BASE_URL.replace(/\/$/, "");

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

const SETTINGS_NAV: { path: string; label: string; icon: React.ElementType }[] = [];


// ── Nav link ──────────────────────────────────────────────────────────────────

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


// ── Theme toggle ──────────────────────────────────────────────────────────────

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


// ── User profile — Clerk version (only inside ClerkProvider) ──────────────────

function ClerkUserProfile({ open }: { open: boolean }) {
  const { user, isLoaded } = useUser();
  const { signOut }        = useClerk();
  const { user: customUser, logout: customLogout } = useCustomAuth();

  const isClerk  = isLoaded && !!user;
  const isCustom = !isClerk && !!customUser;

  if (!isClerk && !isCustom) return null;

  const displayName = isClerk
    ? (user!.fullName || user!.firstName || user!.emailAddresses[0]?.emailAddress || "User")
    : (customUser!.name || customUser!.email);

  const email = isClerk
    ? user!.emailAddresses[0]?.emailAddress
    : customUser!.email;

  const avatarUrl = isClerk ? user!.imageUrl : null;
  const initials  = displayName.split(" ").map((n: string) => n[0]).join("").toUpperCase().slice(0, 2);
  const handleSignOut = isClerk ? () => signOut({ redirectUrl: "/" }) : customLogout;

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
          <img src={avatarUrl} alt={displayName} className="w-7 h-7 rounded-full object-cover flex-shrink-0" />
        ) : (
          <div className="w-7 h-7 rounded-full bg-indigo-500 flex items-center justify-center text-white text-xs font-bold flex-shrink-0">
            {initials}
          </div>
        )}
        <div className="flex-1 min-w-0">
          <p className="text-xs font-medium text-gray-900 dark:text-white truncate">{displayName}</p>
          <p className="text-[10px] text-gray-400 truncate">{email}</p>
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


// ── User profile — custom-auth only (no Clerk hooks) ─────────────────────────

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


// ── Sidebar layout shell ──────────────────────────────────────────────────────

function LayoutShell({
  children,
  ProfileComponent,
}: {
  children: React.ReactNode;
  ProfileComponent: React.ComponentType<{ open: boolean }>;
}) {
  const [loc]  = useLocation();
  const [open, setOpen] = useState(() => localStorage.getItem("sidebar-open") === "true");
  const [settingsOpen, setSettingsOpen] = useState(false);

  useEffect(() => { localStorage.setItem("sidebar-open", String(open)); }, [open]);
  useEffect(() => {
    if (SETTINGS_NAV.some(({ path }) => loc === path)) setSettingsOpen(true);
  }, [loc]);

  const inSettings = SETTINGS_NAV.some(({ path }) => loc === path) || loc === "/settings";

  return (
    <div className="h-screen bg-gray-50 dark:bg-gray-950 flex overflow-hidden">

      <aside className={`hidden md:flex flex-col bg-white dark:bg-gray-950 border-r border-gray-100 dark:border-white/[0.05] flex-shrink-0
        transition-all duration-200 ease-in-out ${open ? "w-52" : "w-[52px]"}`}>

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

        <nav className="flex-1 py-2 space-y-0.5 overflow-y-auto overflow-x-hidden">
          {MAIN_NAV.map((item) => (
            <NavLink key={item.path} {...item} open={open} />
          ))}
        </nav>

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
          <ProfileComponent open={open} />

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

      <div className="flex-1 flex flex-col min-w-0 bg-gray-50 dark:bg-gray-950">
        <div className="md:hidden bg-white dark:bg-gray-900 border-b border-gray-100 dark:border-gray-800 px-4 py-3 flex items-center gap-2">
          <img src="/niftynodes-logo.png" alt="NiftyNodes" className="w-7 h-7 rounded-full object-cover" />
          <span className="font-bold text-gray-900 dark:text-white text-sm flex-1">Nifty Node</span>
          <ThemeToggle open={false} />
        </div>

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

function Layout({ children }: { children: React.ReactNode }) {
  return <LayoutShell ProfileComponent={ClerkUserProfile}>{children}</LayoutShell>;
}

function LayoutNoClerk({ children }: { children: React.ReactNode }) {
  return <LayoutShell ProfileComponent={CustomOnlyUserProfile}>{children}</LayoutShell>;
}


// ── Clerk-aware Settings wrapper (must be inside ClerkProvider) ───────────────

function SettingsWithClerk() {
  const { user }    = useUser();
  const { signOut } = useClerk();

  const clerkUser: ClerkUserInfo | undefined = user ? {
    name:      user.fullName || user.firstName || user.emailAddresses[0]?.emailAddress || "User",
    email:     user.emailAddresses[0]?.emailAddress || "",
    imageUrl:  user.imageUrl,
    joinedAt:  user.createdAt ? new Date(user.createdAt).getTime() : undefined,
  } : undefined;

  return (
    <SettingsPage
      clerkUser={clerkUser}
      onSignOut={() => signOut({ redirectUrl: "/" })}
    />
  );
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
        <Route path="/settings"        component={SettingsWithClerk} />
        <Route path="/chart/:symbol"   component={ChartView} />
        <Route component={NotFound} />
      </Switch>
    </Layout>
  );
}

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


// ── Token injectors ───────────────────────────────────────────────────────────

/** Used when Clerk is present — prefers custom token if set, falls back to Clerk. */
function ClerkTokenInjector() {
  const { getToken }            = useAuth();
  const { token: customToken }  = useCustomAuth();
  const queryClient             = useQueryClient();
  const prevUserRef             = useRef<string | null | undefined>(undefined);
  const { user }                = useUser();

  useEffect(() => {
    if (customToken) {
      setTokenGetter(async () => customToken);
    } else {
      setTokenGetter(getToken);
    }
  }, [getToken, customToken]);

  useEffect(() => {
    const userId = user?.id ?? null;
    if (prevUserRef.current !== undefined && prevUserRef.current !== userId) {
      queryClient.clear();
    }
    prevUserRef.current = userId;
  }, [user?.id, queryClient]);

  return null;
}

/** Used when Clerk is NOT present — sets custom token directly. */
function CustomTokenInjector() {
  const { token } = useCustomAuth();
  useEffect(() => {
    if (token) setTokenGetter(async () => token!);
  }, [token]);
  return null;
}


// ── Clerk sign-in / sign-up pages (Clerk's hosted components) ─────────────────

function SignInPage() {
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


// ── Google sign-in button (uses Clerk hook — only inside ClerkProvider) ───────

function GoogleSignInButton({ onStart }: { onStart?: () => void }) {
  const { signIn } = useSignIn();
  const [loading, setLoading] = useState(false);

  const handleClick = async () => {
    setLoading(true);
    onStart?.();
    try {
      await signIn?.authenticateWithRedirect({
        strategy:            "oauth_google",
        redirectUrl:         `${basePath || ""}/sso-callback`,
        redirectUrlComplete: `${basePath || ""}/`,
      });
    } catch {
      setLoading(false);
    }
  };

  return (
    <button
      onClick={handleClick}
      disabled={loading}
      className="w-full flex items-center justify-center gap-3 px-4 py-2.5 rounded-lg border border-gray-700 bg-gray-800 hover:bg-gray-700 hover:border-gray-600 text-white text-sm font-medium transition disabled:opacity-60 disabled:cursor-not-allowed"
    >
      {loading ? (
        <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
      ) : (
        <svg className="w-4 h-4" viewBox="0 0 24 24">
          <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
          <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
          <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
          <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
        </svg>
      )}
      Continue with Google
    </button>
  );
}


// ── App gate when Clerk IS configured ─────────────────────────────────────────

function ClerkGate() {
  const { isSignedIn, isLoaded } = useUser();
  const { user: customUser }     = useCustomAuth();

  if (!isLoaded) return null; // wait for Clerk to resolve

  const isAuthenticated = isSignedIn || !!customUser;

  if (!isAuthenticated) {
    return (
      <LoginPage
        showGoogle={true}
        onGoogleSignIn={undefined} // rendered via GoogleSignInButton inside LoginPage area
        googleButton={<GoogleSignInButton />}
      />
    );
  }

  return (
    <>
      <ClerkTokenInjector />
      <AppRoutes />
      <GlobalAssistant />
    </>
  );
}

function ClerkProviderWithRoutes() {
  const [, setLocation] = useLocation();

  return (
    <ClerkProvider
      publishableKey={clerkPubKey!}
      proxyUrl={clerkProxyUrl}
      routerPush={(to) => setLocation(stripBase(to))}
      routerReplace={(to) => setLocation(stripBase(to), { replace: true })}
    >
      <QueryClientProvider client={queryClient}>
        <Switch>
          <Route path="/sign-in/*?" component={SignInPage} />
          <Route path="/sign-up/*?" component={SignUpPage} />
          <Route>
            <ClerkGate />
          </Route>
        </Switch>
      </QueryClientProvider>
    </ClerkProvider>
  );
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
              ? <ClerkProviderWithRoutes />
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
