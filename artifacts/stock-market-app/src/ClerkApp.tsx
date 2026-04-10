import { useState, useEffect, useRef } from "react";
import { Switch, Route, useLocation } from "wouter";
import { QueryClient, QueryClientProvider, useQueryClient } from "@tanstack/react-query";
import { ClerkProvider, SignIn, SignUp, useSignIn, useClerk, useUser, useAuth } from "@clerk/react";
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
import { useCustomAuth } from "@/context/CustomAuthContext";
import { setTokenGetter } from "@/lib/api";
import { LayoutShell } from "@/LayoutShell";
import { LogOut } from "lucide-react";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
});

const clerkPubKey   = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY as string;
const clerkProxyUrl = import.meta.env.VITE_CLERK_PROXY_URL as string | undefined;
const basePath      = import.meta.env.BASE_URL.replace(/\/$/, "");

function stripBase(path: string): string {
  return basePath && path.startsWith(basePath)
    ? path.slice(basePath.length) || "/"
    : path;
}


// ── User profile — Clerk version ─────────────────────────────────────────────

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


// ── Clerk-aware Settings wrapper ──────────────────────────────────────────────

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


// ── Layout with Clerk profile ─────────────────────────────────────────────────

function Layout({ children }: { children: React.ReactNode }) {
  return <LayoutShell ProfileComponent={ClerkUserProfile}>{children}</LayoutShell>;
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


// ── Token injector ────────────────────────────────────────────────────────────

function ClerkTokenInjector() {
  const { getToken }           = useAuth();
  const { token: customToken } = useCustomAuth();
  const queryClient            = useQueryClient();
  const prevUserRef            = useRef<string | null | undefined>(undefined);
  const { user }               = useUser();

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


// ── Sign-in / sign-up pages ───────────────────────────────────────────────────

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


// ── Google sign-in button ─────────────────────────────────────────────────────

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


// ── Gate ──────────────────────────────────────────────────────────────────────

function ClerkGate() {
  const { isSignedIn, isLoaded } = useUser();
  const { user: customUser }     = useCustomAuth();

  if (!isLoaded) return null;

  const isAuthenticated = isSignedIn || !!customUser;

  if (!isAuthenticated) {
    return (
      <LoginPage
        showGoogle={true}
        onGoogleSignIn={undefined}
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


// ── Root Clerk app (default export) ──────────────────────────────────────────

export default function ClerkProviderWithRoutes() {
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
            <ClerkGate />
          </Route>
        </Switch>
      </QueryClientProvider>
    </ClerkProvider>
  );
}
