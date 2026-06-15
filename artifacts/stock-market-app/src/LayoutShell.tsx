import { useState, useEffect, useRef, ComponentType, ReactNode } from "react";
import { Link, useLocation } from "wouter";
import { useTheme } from "@/context/ThemeContext";
import { useCustomAuth } from "@/context/CustomAuthContext";
import { BrandLogo } from "@/components/BrandLogo";
import {
  LayoutDashboard, BarChart3, Search, Scan, Filter,
  Microscope, Brain, TrendingUp, CandlestickChart,
  Settings, ChevronRight, ChevronLeft, Sun, Moon,
  Newspaper, Gauge, Sparkles, Users, Briefcase, Calculator,
  LogOut, Mail, Compass,
} from "lucide-react";

export const MAIN_NAV = [
  { path: "/",           label: "Dashboard",       icon: LayoutDashboard },
  { path: "/trading",    label: "Chart Studio",    icon: CandlestickChart },
  { path: "/sectors",    label: "Market Sectors",  icon: BarChart3 },
  { path: "/rotation",   label: "Sector Rotation", icon: Compass },
  { path: "/insights",   label: "Insights",        icon: Sparkles },
  { path: "/sentiment",  label: "Sentiment",       icon: Gauge },
  { path: "/news",       label: "News Feed",       icon: Newspaper },
  { path: "/stocks",     label: "Stock Lookup",    icon: Search },
  { path: "/dcf",        label: "DCF Value",       icon: Calculator },
  { path: "/agents",     label: "Investor Council",icon: Users },
  { path: "/ai-analyst", label: "Deep AI Analyst", icon: Microscope },
  { path: "/patterns",   label: "Patterns",        icon: Scan },
  { path: "/scanners",   label: "Scanners",        icon: Filter },
  { path: "/hydra",      label: "AI Analyzer",     icon: Brain },
  { path: "/options",    label: "Options Tester",  icon: TrendingUp },
  { path: "/portfolio",  label: "Portfolio",       icon: Briefcase },
  { path: "/email-digest", label: "Email Digest",  icon: Mail },
];

export function NavLink({ path, label, icon: Icon, open, indent = false }: {
  path: string; label: string; icon: ComponentType<{ className?: string }>; open: boolean; indent?: boolean;
}) {
  const [loc] = useLocation();
  const active = loc === path || (path !== "/" && loc.startsWith(path));
  return (
    <Link
      href={path}
      title={!open ? label : undefined}
      className={`flex items-center gap-2.5 transition rounded-lg mx-1.5
        ${indent && open ? "pl-7 pr-2.5 py-1" : open ? "px-2.5 py-1.5" : "px-0 py-1.5 justify-center"}
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


function LogoMenu({ open: sidebarOpen }: { open: boolean }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const { theme, toggleWithRipple } = useTheme();
  const { logout } = useCustomAuth();
  const isDark = theme === "dark";
  const [loc] = useLocation();
  const isSettings = loc === "/settings";

  useEffect(() => {
    function onOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    }
    if (menuOpen) document.addEventListener("mousedown", onOutside);
    return () => document.removeEventListener("mousedown", onOutside);
  }, [menuOpen]);

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setMenuOpen(o => !o)}
        title="Menu"
        className={`cursor-pointer w-full flex items-center gap-2.5 border-b border-gray-100 dark:border-white/[0.05] flex-shrink-0 h-[57px]
          transition hover:bg-gray-50 dark:hover:bg-gray-800/50
          ${sidebarOpen ? "px-4" : "justify-center"}
          ${menuOpen ? "bg-gray-50 dark:bg-gray-800/50" : ""}`}
      >
        <BrandLogo className="w-8 h-8 rounded-full object-cover flex-shrink-0" />
        {sidebarOpen && (
          <div className="overflow-hidden flex-1 text-left">
            <p className="font-bold text-gray-900 dark:text-white text-sm whitespace-nowrap">Nifty Node</p>
            <p className="text-xs text-gray-400 dark:text-gray-500 whitespace-nowrap">Indian Stock Market</p>
          </div>
        )}
      </button>

      {menuOpen && (
        <div className={`absolute z-50 top-[calc(100%+4px)] left-2
          w-52 rounded-xl border border-gray-200 dark:border-white/[0.08]
          bg-white dark:bg-gray-900 shadow-xl shadow-black/10 dark:shadow-black/40
          py-1.5 overflow-hidden`}
        >
          <p className="px-3 pt-0.5 pb-1.5 text-[10px] font-semibold uppercase tracking-widest text-gray-400 dark:text-gray-500">
            Preferences
          </p>

          <button
            onClick={(e) => { toggleWithRipple(e.clientX, e.clientY); setMenuOpen(false); }}
            className="w-full flex items-center gap-2.5 px-3 py-2 text-sm
              text-gray-700 dark:text-gray-300
              hover:bg-indigo-50 dark:hover:bg-indigo-500/10
              hover:text-indigo-700 dark:hover:text-indigo-300 transition"
          >
            {isDark
              ? <Sun  className="w-4 h-4 text-amber-500" />
              : <Moon className="w-4 h-4 text-indigo-500" />}
            <span>{isDark ? "Light mode" : "Dark mode"}</span>
          </button>

          <Link
            href="/settings"
            onClick={() => setMenuOpen(false)}
            className={`flex items-center gap-2.5 px-3 py-2 text-sm transition
              ${isSettings
                ? "text-indigo-700 dark:text-indigo-300 bg-indigo-50 dark:bg-indigo-500/10"
                : "text-gray-700 dark:text-gray-300 hover:bg-indigo-50 dark:hover:bg-indigo-500/10 hover:text-indigo-700 dark:hover:text-indigo-300"
              }`}
          >
            <Settings className="w-4 h-4" />
            <span>Settings</span>
          </Link>

          <div className="my-1 mx-3 border-t border-gray-100 dark:border-white/[0.06]" />

          <button
            onClick={() => { setMenuOpen(false); logout(); }}
            className="w-full flex items-center gap-2.5 px-3 py-2 text-sm transition
              text-red-500 dark:text-red-400
              hover:bg-red-50 dark:hover:bg-red-500/10"
          >
            <LogOut className="w-4 h-4" />
            <span>Log out</span>
          </button>
        </div>
      )}
    </div>
  );
}


export function LayoutShell({
  children,
  ProfileComponent,
}: {
  children: ReactNode;
  ProfileComponent: ComponentType<{ open: boolean }>;
}) {
  const [loc]  = useLocation();
  const [open, setOpen] = useState(() => localStorage.getItem("sidebar-open") === "true");
  const { theme, toggleWithRipple } = useTheme();
  const isDark = theme === "dark";

  useEffect(() => { localStorage.setItem("sidebar-open", String(open)); }, [open]);

  return (
    <div className="h-screen bg-gray-50 dark:bg-gray-950 flex overflow-hidden">

      {/* ── Sidebar ───────────────────────────────────────────────────────── */}
      <aside className={`hidden md:flex flex-col bg-white dark:bg-gray-950 border-r border-gray-100 dark:border-white/[0.05] flex-shrink-0
        transition-all duration-200 ease-in-out ${open ? "w-52" : "w-[52px]"}`}>

        {/* Logo — click to open preferences popover */}
        <LogoMenu open={open} />

        {/* Nav items */}
        <nav className="sidebar-nav flex-1 py-2 space-y-0.5 overflow-y-auto overflow-x-hidden">
          {MAIN_NAV.map((item) => (
            <NavLink key={item.path} {...item} open={open} />
          ))}
        </nav>

        {/* Bottom — profile + collapse */}
        <div className="py-2 flex-shrink-0">
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

      {/* ── Main content ──────────────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col min-w-0 bg-gray-50 dark:bg-gray-950 relative">

        {/* Mobile top bar */}
        <div className="md:hidden bg-white dark:bg-gray-900 border-b border-gray-100 dark:border-gray-800 px-4 py-3 flex items-center gap-2">
          <BrandLogo className="w-7 h-7 rounded-full object-cover" />
          <span className="font-bold text-gray-900 dark:text-white text-sm flex-1">Nifty Node</span>
          <button
            onClick={(e) => toggleWithRipple(e.clientX, e.clientY)}
            className="w-8 h-8 flex items-center justify-center rounded-lg text-gray-400 hover:text-indigo-600 transition"
          >
            {isDark ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
          </button>
          <Link
            href="/settings"
            className="w-8 h-8 flex items-center justify-center rounded-lg text-gray-400 hover:text-indigo-600 transition"
          >
            <Settings className="w-4 h-4" />
          </Link>
        </div>

        {/* Mobile nav tabs */}
        <div className="md:hidden bg-white dark:bg-gray-900 border-b border-gray-100 dark:border-gray-800 px-2 py-2 flex gap-1 overflow-x-auto">
          {MAIN_NAV.map(({ path, label, icon: Icon }) => {
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

        <main className={`flex-1 overflow-auto bg-gray-50 dark:bg-gray-950
          ${(loc.startsWith("/trading") || loc.startsWith("/chart") || loc.startsWith("/insights/heatmap"))
            ? "p-0 overflow-hidden"
            : "p-4 md:p-6"}`}
        >
          {children}
        </main>
      </div>
    </div>
  );
}
