import { useState, useEffect, useRef } from "react";
import { Switch, Route, Router as WouterRouter, Link, useLocation } from "wouter";
import { QueryClient, QueryClientProvider, useQueryClient } from "@tanstack/react-query";
import { ClerkProvider, SignIn, Show, useClerk, useUser, useAuth } from "@clerk/react";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import NotFound from "@/pages/not-found";
import AppStatus from "@/pages/AppStatus";
import UsersPage from "@/pages/UsersPage";
import LogsPage from "@/pages/LogsPage";
import WhatsAppBot from "@/pages/WhatsAppBot";
import TelegramBot from "@/pages/TelegramBot";
import { setTokenGetter } from "@/lib/api";
import {
  Activity, Users, Terminal, MessageCircle, Send,
  ChevronLeft, ChevronRight, LogOut, ShieldAlert,
} from "lucide-react";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
});

const clerkPubKey = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;
const clerkProxyUrl = import.meta.env.VITE_CLERK_PROXY_URL;
const basePath = import.meta.env.BASE_URL.replace(/\/$/, "");

if (!clerkPubKey) throw new Error("Missing VITE_CLERK_PUBLISHABLE_KEY");

const ADMIN_EMAIL = import.meta.env.VITE_ADMIN_EMAIL || "";

function stripBase(path: string) {
  return basePath && path.startsWith(basePath) ? path.slice(basePath.length) || "/" : path;
}

const NAV = [
  { path: "/",          label: "App Status",   icon: Activity      },
  { path: "/users",     label: "Users",        icon: Users         },
  { path: "/whatsapp",  label: "WhatsApp Bot", icon: MessageCircle },
  { path: "/telegram",  label: "Telegram Bot", icon: Send          },
  { path: "/logs",      label: "Logs",         icon: Terminal      },
];

function NavLink({ path, label, icon: Icon, open }: {
  path: string; label: string; icon: React.ElementType; open: boolean;
}) {
  const [loc] = useLocation();
  const active = loc === path || (path !== "/" && loc.startsWith(path));
  return (
    <Link
      href={path}
      title={!open ? label : undefined}
      className={`flex items-center gap-2.5 transition rounded-lg mx-1.5
        ${open ? "px-2.5 py-2" : "px-0 py-2 justify-center"}
        ${active
          ? "bg-indigo-50 text-indigo-700"
          : "text-gray-500 hover:bg-gray-50 hover:text-gray-900"
        }`}
    >
      <Icon className={`flex-shrink-0 w-[18px] h-[18px] ${active ? "text-indigo-600" : ""}`} />
      {open && <span className="font-medium text-sm whitespace-nowrap">{label}</span>}
    </Link>
  );
}

function UserProfile({ open }: { open: boolean }) {
  const { user } = useUser();
  const { signOut } = useClerk();
  if (!user) return null;
  const name = user.fullName || user.firstName || user.emailAddresses[0]?.emailAddress || "Admin";
  const initials = name.split(" ").map((n: string) => n[0]).join("").toUpperCase().slice(0, 2);
  if (!open) {
    return (
      <button onClick={() => signOut({ redirectUrl: "/" })} title="Sign out"
        className="w-full flex justify-center py-2 text-gray-400 hover:text-red-400 transition">
        <LogOut className="w-4 h-4" />
      </button>
    );
  }
  return (
    <div className="mx-1.5 mb-1">
      <div className="flex items-center gap-2.5 px-2.5 py-2 rounded-lg bg-gray-50">
        {user.imageUrl ? (
          <img src={user.imageUrl} alt={name} className="w-7 h-7 rounded-full object-cover flex-shrink-0" />
        ) : (
          <div className="w-7 h-7 rounded-full bg-indigo-500 flex items-center justify-center text-white text-xs font-bold flex-shrink-0">
            {initials}
          </div>
        )}
        <div className="flex-1 min-w-0">
          <p className="text-xs font-medium text-gray-900 truncate">{name}</p>
          <p className="text-[10px] text-gray-400 truncate">{user.emailAddresses[0]?.emailAddress}</p>
        </div>
        <button onClick={() => signOut({ redirectUrl: "/" })} title="Sign out"
          className="text-gray-400 hover:text-red-400 transition flex-shrink-0">
          <LogOut className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
}

function MobileNav() {
  const [loc] = useLocation();
  return (
    <div className="md:hidden bg-white border-b border-gray-100 px-2 py-2 flex gap-1 overflow-x-auto">
      {NAV.map(({ path, label, icon: Icon }) => {
        const active = loc === path || (path !== "/" && loc.startsWith(path));
        return (
          <Link key={path} href={path}
            className={`flex flex-col items-center gap-0.5 px-3 py-1.5 rounded-lg text-xs transition flex-shrink-0
              ${active ? "bg-indigo-50 text-indigo-700 font-medium" : "text-gray-500"}`}>
            <Icon className="w-4 h-4" />
            {label}
          </Link>
        );
      })}
    </div>
  );
}

function Layout({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(() => localStorage.getItem("admin-sidebar") !== "false");
  useEffect(() => { localStorage.setItem("admin-sidebar", String(open)); }, [open]);

  return (
    <div className="h-screen bg-gray-50 flex overflow-hidden">
      <aside className={`hidden md:flex flex-col bg-white border-r border-gray-100 flex-shrink-0
        transition-all duration-200 ease-in-out ${open ? "w-52" : "w-[52px]"}`}>
        <div className={`flex items-center gap-2.5 border-b border-gray-100 flex-shrink-0 h-[57px]
          ${open ? "px-4" : "justify-center"}`}>
          <div className="w-8 h-8 rounded-full bg-indigo-600 flex items-center justify-center flex-shrink-0">
            <ShieldAlert className="w-4 h-4 text-white" />
          </div>
          {open && (
            <div className="overflow-hidden">
              <p className="font-bold text-gray-900 text-sm whitespace-nowrap">Admin Panel</p>
              <p className="text-xs text-gray-400 whitespace-nowrap">Nifty Node</p>
            </div>
          )}
        </div>

        <nav className="flex-1 py-2 space-y-0.5 overflow-y-auto overflow-x-hidden">
          {NAV.map(item => <NavLink key={item.path} {...item} open={open} />)}
        </nav>

        <div className="border-t border-gray-100 py-2 flex-shrink-0">
          <UserProfile open={open} />
          <button
            onClick={() => setOpen(o => !o)}
            className={`w-full flex items-center gap-2.5 rounded-lg transition py-2 mt-0.5
              ${open ? "px-2.5 w-[calc(100%-12px)] mx-1.5" : "px-0 justify-center"}
              text-gray-400 hover:text-indigo-600 hover:bg-gray-50`}
          >
            {open ? <ChevronLeft className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
            {open && <span className="text-xs font-medium text-gray-400 whitespace-nowrap">Collapse</span>}
          </button>
        </div>
      </aside>

      <div className="flex-1 flex flex-col min-w-0">
        <div className="md:hidden bg-white border-b border-gray-100 px-4 py-3 flex items-center gap-3">
          <div className="w-7 h-7 rounded-full bg-indigo-600 flex items-center justify-center">
            <ShieldAlert className="w-4 h-4 text-white" />
          </div>
          <span className="font-bold text-gray-900 text-sm flex-1">Admin Panel</span>
        </div>
        <MobileNav />
        <main className="flex-1 overflow-auto p-4 md:p-6">
          {children}
        </main>
      </div>
    </div>
  );
}

function AdminGate({ children }: { children: React.ReactNode }) {
  const { user } = useUser();
  const email = user?.emailAddresses[0]?.emailAddress ?? "";
  const role = (user?.publicMetadata as any)?.role;

  const isAdmin = role === "admin" || (ADMIN_EMAIL && email === ADMIN_EMAIL) || !ADMIN_EMAIL;

  if (!isAdmin) {
    return (
      <div className="min-h-screen bg-gray-50 flex flex-col items-center justify-center">
        <div className="bg-white rounded-2xl border border-red-100 shadow-sm p-10 max-w-sm w-full text-center">
          <ShieldAlert className="w-12 h-12 text-red-400 mx-auto mb-4" />
          <h2 className="text-lg font-bold text-gray-900 mb-2">Access Denied</h2>
          <p className="text-sm text-gray-500 mb-5">
            You don't have admin privileges. Contact the administrator to grant access.
          </p>
          <p className="text-xs text-gray-400 font-mono">{email}</p>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}

function AuthTokenInjector() {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  const { user } = useUser();
  const prevRef = useRef<string | null | undefined>(undefined);

  useEffect(() => { setTokenGetter(getToken); }, [getToken]);

  useEffect(() => {
    const id = user?.id ?? null;
    if (prevRef.current !== undefined && prevRef.current !== id) qc.clear();
    prevRef.current = id;
  }, [user?.id, qc]);

  return null;
}

function AdminSignIn() {
  return (
    <div className="min-h-screen bg-gray-950 flex flex-col items-center justify-center py-12 px-4">
      <div className="mb-8 flex flex-col items-center">
        <div className="w-12 h-12 rounded-full bg-indigo-600 flex items-center justify-center mb-3">
          <ShieldAlert className="w-6 h-6 text-white" />
        </div>
        <p className="text-white font-bold text-lg">Admin Panel</p>
        <p className="text-gray-400 text-sm">Nifty Node — Restricted Access</p>
      </div>
      <SignIn
        routing="path"
        path={`${basePath}/sign-in`}
        fallbackRedirectUrl={`${basePath}/`}
      />
    </div>
  );
}

function AppRoutes() {
  return (
    <AdminGate>
      <Layout>
        <Switch>
          <Route path="/"         component={AppStatus} />
          <Route path="/users"    component={UsersPage} />
          <Route path="/whatsapp" component={() => <WhatsAppBot />} />
          <Route path="/telegram" component={() => <TelegramBot />} />
          <Route path="/logs"     component={LogsPage} />
          <Route component={NotFound} />
        </Switch>
      </Layout>
    </AdminGate>
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
          <Route path="/sign-in/*?" component={AdminSignIn} />
          <Route>
            <Show when="signed-in">
              <AuthTokenInjector />
              <AppRoutes />
            </Show>
            <Show when="signed-out">
              <AdminSignIn />
            </Show>
          </Route>
        </Switch>
      </QueryClientProvider>
    </ClerkProvider>
  );
}

function App() {
  return (
    <TooltipProvider>
      <WouterRouter base={basePath}>
        <ClerkProviderWithRoutes />
      </WouterRouter>
      <Toaster />
    </TooltipProvider>
  );
}

export default App;
