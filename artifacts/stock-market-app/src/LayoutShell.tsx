import { useState, useEffect, ComponentType, ReactNode } from "react";
import { Link, useLocation } from "wouter";
import { useTheme } from "@/context/ThemeContext";
import { BrandLogo } from "@/components/BrandLogo";
import {
  LayoutDashboard, BarChart3, Search, Scan, Filter,
  Microscope,
  Brain, TrendingUp, CandlestickChart,
  Settings, ChevronRight, ChevronLeft, Sun, Moon,
  Newspaper, Gauge, Sparkles, Users, Briefcase, Calculator,
} from "lucide-react";

export const MAIN_NAV = [
  { path: "/",           label: "Dashboard",      icon: LayoutDashboard },
  { path: "/trading",    label: "Chart Studio",   icon: CandlestickChart },
  { path: "/sectors",    label: "Market Sectors", icon: BarChart3 },
  { path: "/insights",   label: "Insights",       icon: Sparkles },
  { path: "/sentiment",  label: "Sentiment",      icon: Gauge },
  { path: "/news",       label: "News Feed",      icon: Newspaper },
  { path: "/stocks",     label: "Stock Lookup",   icon: Search },
  { path: "/dcf",        label: "DCF Value",      icon: Calculator },
  { path: "/agents",     label: "Investor Council", icon: Users },
  { path: "/ai-analyst", label: "Deep AI Analyst", icon: Microscope },
  { path: "/patterns",   label: "Patterns",       icon: Scan },
  { path: "/scanners",   label: "Scanners",       icon: Filter },
  { path: "/hydra",      label: "AI Analyzer",    icon: Brain },
  { path: "/options",    label: "Options Tester", icon: TrendingUp },
  { path: "/portfolio",  label: "Portfolio",      icon: Briefcase },
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


function ThemeIconButton({ size = 15 }: { size?: number }) {
  const { theme, toggleWithRipple } = useTheme();
  const isDark = theme === "dark";
  return (
    <button
      onClick={(e) => toggleWithRipple(e.clientX, e.clientY)}
      title={isDark ? "Switch to light mode" : "Switch to dark mode"}
      className="w-8 h-8 flex items-center justify-center rounded-lg transition
        text-gray-400 dark:text-gray-500
        hover:text-indigo-600 dark:hover:text-indigo-400
        hover:bg-white dark:hover:bg-gray-800/70"
    >
      {isDark
        ? <Sun  style={{ width: size, height: size }} />
        : <Moon style={{ width: size, height: size }} />}
    </button>
  );
}


function TopBar() {
  const [loc] = useLocation();
  const isSettings = loc === "/settings";
  const isFullscreen =
    loc.startsWith("/trading") ||
    loc.startsWith("/chart") ||
    loc.startsWith("/insights/heatmap");

  const settingsClass = `w-8 h-8 flex items-center justify-center rounded-lg transition
    hover:bg-white dark:hover:bg-gray-800/70
    ${isSettings
      ? "text-indigo-600 dark:text-indigo-400 bg-indigo-50 dark:bg-indigo-500/20"
      : "text-gray-400 dark:text-gray-500 hover:text-indigo-600 dark:hover:text-indigo-400"
    }`;

  /* Fullscreen views (Chart Studio, Chart, Heatmap) — float the controls as a
     pill overlay in the top-right so they take ZERO vertical space and don't
     push the drawing bar or chart canvas out of bounds. */
  if (isFullscreen) {
    return (
      <div className="hidden md:flex absolute top-2 right-3 z-50 items-center gap-0.5
        bg-white/90 dark:bg-gray-900/90 backdrop-blur-sm
        rounded-xl px-0.5 py-0.5 shadow-sm
        border border-gray-200/60 dark:border-white/[0.08]">
        <ThemeIconButton />
        <Link href="/settings" title="Settings" className={settingsClass}>
          <Settings className="w-[15px] h-[15px]" />
        </Link>
      </div>
    );
  }

  /* Regular pages — inline bar that takes 40px of height */
  return (
    <div className="hidden md:flex h-10 flex-shrink-0 items-center justify-end gap-0.5 px-4">
      <ThemeIconButton />
      <Link href="/settings" title="Settings" className={settingsClass}>
        <Settings className="w-[15px] h-[15px]" />
      </Link>
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

  useEffect(() => { localStorage.setItem("sidebar-open", String(open)); }, [open]);

  return (
    <div className="h-screen bg-gray-50 dark:bg-gray-950 flex overflow-hidden">

      {/* ── Sidebar ───────────────────────────────────────────────────────── */}
      <aside className={`hidden md:flex flex-col bg-white dark:bg-gray-950 border-r border-gray-100 dark:border-white/[0.05] flex-shrink-0
        transition-all duration-200 ease-in-out ${open ? "w-52" : "w-[52px]"}`}>

        {/* Brand */}
        <div className={`flex items-center gap-2.5 border-b border-gray-100 dark:border-white/[0.05] flex-shrink-0 h-[57px]
          ${open ? "px-4" : "justify-center"}`}>
          <BrandLogo className="w-8 h-8 rounded-full object-cover flex-shrink-0" />
          {open && (
            <div className="overflow-hidden">
              <p className="font-bold text-gray-900 dark:text-white text-sm whitespace-nowrap">Nifty Node</p>
              <p className="text-xs text-gray-400 dark:text-gray-500 whitespace-nowrap">Indian Stock Market</p>
            </div>
          )}
        </div>

        {/* Nav items — scrollbar hidden via CSS */}
        <nav className="sidebar-nav flex-1 py-2 space-y-0.5 overflow-y-auto overflow-x-hidden">
          {MAIN_NAV.map((item) => (
            <NavLink key={item.path} {...item} open={open} />
          ))}
        </nav>

        {/* Bottom — profile + collapse only */}
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
          <ThemeIconButton size={16} />
          <Link
            href="/settings"
            title="Settings"
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

        {/* Desktop top-right controls */}
        <TopBar />

        <main className={`flex-1 overflow-auto bg-gray-50 dark:bg-gray-950 ${(loc.startsWith("/trading") || loc.startsWith("/chart") || loc.startsWith("/insights/heatmap")) ? "p-0 overflow-hidden" : "p-4 md:p-6 md:pt-2"}`}>
          {children}
        </main>
      </div>
    </div>
  );
}
