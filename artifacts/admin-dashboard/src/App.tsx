import { useState, useEffect, useCallback } from "react";
import { Switch, Route, Router as WouterRouter, Link, useLocation } from "wouter";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import NotFound from "@/pages/not-found";
import AppStatus from "@/pages/AppStatus";
import UsersPage from "@/pages/UsersPage";
import LogsPage from "@/pages/LogsPage";
import WhatsAppBot from "@/pages/WhatsAppBot";
import TelegramBot from "@/pages/TelegramBot";
import LoginPage from "@/pages/LoginPage";
import SebiAuditPage from "@/pages/SebiAuditPage";
import BugReportsPage from "@/pages/BugReportsPage";
import { getAdminToken, clearAdminToken } from "@/lib/api";
import {
  Activity, Users, Terminal, MessageCircle, Send,
  ChevronLeft, ChevronRight, LogOut, ShieldAlert, ShieldCheck, Bug,
} from "lucide-react";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Never retry a 401 — the token is gone; retry once for other errors
      retry: (failureCount, error: any) => error?.status === 401 ? false : failureCount < 1,
      refetchOnWindowFocus: false,
    },
  },
});

const basePath = import.meta.env.BASE_URL.replace(/\/$/, "");

const NAV = [
  { path: "/",          label: "App Status",   icon: Activity      },
  { path: "/users",     label: "Users",        icon: Users         },
  { path: "/whatsapp",  label: "WhatsApp Bot", icon: MessageCircle },
  { path: "/telegram",  label: "Telegram Bot", icon: Send          },
  { path: "/logs",      label: "Logs",         icon: Terminal      },
  { path: "/bugs",      label: "Bug Tracker",  icon: Bug           },
  { path: "/sebi",      label: "SEBI Audit",   icon: ShieldCheck   },
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

function Layout({ children, onSignOut }: { children: React.ReactNode; onSignOut: () => void }) {
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
          <button
            onClick={onSignOut}
            title="Sign out"
            className={`w-full flex items-center gap-2.5 rounded-lg transition py-2
              ${open ? "px-2.5 w-[calc(100%-12px)] mx-1.5" : "px-0 justify-center"}
              text-gray-400 hover:text-red-500 hover:bg-red-50`}
          >
            <LogOut className="w-4 h-4 flex-shrink-0" />
            {open && <span className="text-sm font-medium whitespace-nowrap">Sign out</span>}
          </button>
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
          <button onClick={onSignOut} className="text-gray-400 hover:text-red-500 transition">
            <LogOut className="w-4 h-4" />
          </button>
        </div>
        <MobileNav />
        <main className="flex-1 overflow-auto p-4 md:p-6">
          {children}
        </main>
      </div>
    </div>
  );
}

function AppRoutes({ onSignOut }: { onSignOut: () => void }) {
  return (
    <Layout onSignOut={onSignOut}>
      <Switch>
        <Route path="/"         component={AppStatus} />
        <Route path="/users"    component={UsersPage} />
        <Route path="/whatsapp" component={() => <WhatsAppBot />} />
        <Route path="/telegram" component={() => <TelegramBot />} />
        <Route path="/logs"     component={LogsPage} />
        <Route path="/bugs"     component={BugReportsPage} />
        <Route path="/sebi"     component={SebiAuditPage} />
        <Route component={NotFound} />
      </Switch>
    </Layout>
  );
}

function AdminApp() {
  const [token, setToken] = useState<string | null>(() => getAdminToken());

  const handleSignOut = useCallback(() => {
    clearAdminToken();
    setToken(null);
    queryClient.clear();
  }, []);

  function handleLogin(t: string) {
    setToken(t);
    queryClient.clear();
  }

  // Auto-detect expired/invalid session: any 401 from any query → back to login
  useEffect(() => {
    return queryClient.getQueryCache().subscribe((event) => {
      if (event.type === "updated") {
        const err = event.query.state.error as any;
        if (err?.status === 401) {
          handleSignOut();
        }
      }
    });
  }, [handleSignOut]);

  if (!token) {
    return <LoginPage onLogin={handleLogin} />;
  }

  return <AppRoutes onSignOut={handleSignOut} />;
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <WouterRouter base={basePath}>
          <AdminApp />
        </WouterRouter>
        <Toaster />
      </TooltipProvider>
    </QueryClientProvider>
  );
}

export default App;
