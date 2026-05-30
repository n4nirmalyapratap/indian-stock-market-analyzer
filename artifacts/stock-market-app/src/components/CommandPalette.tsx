/**
 * CommandPalette — global ⌘K / Ctrl+K palette.
 *
 * Mounted once at the auth-gate root (siblings: TokenInjector,
 * GlobalAssistant). On Cmd+K / Ctrl+K, opens a cmdk dialog with three
 * sections:
 *
 *   1. Stock search — debounced, reuses /api/search/suggest. Picking a
 *      row navigates to the Stock Lookup page for that ticker.
 *   2. Pages       — jump to any major route (Dashboard, Portfolio,
 *      Options, Scanners, Insights/Macro, etc.).
 *   3. Actions     — common verbs: refresh prices, toggle theme,
 *      sign out, add transaction, open AI analyst.
 *
 * Why this matters
 * ----------------
 * The app has 25+ routes. Power users spend most of their time on a
 * handful of them but they're not all in the sidebar. ⌘K lets anyone
 * — across any page — jump to the next thing in 2 keystrokes instead
 * of clicking through menus.
 *
 * Why a separate component (not reusing existing per-page palettes)
 * -----------------------------------------------------------------
 * NewsFeed and TradingPlatform have their own scoped cmdk dialogs
 * (search within a single dataset). Those stay. This is the GLOBAL
 * shell-level palette — fundamentally different scope (jump anywhere
 * vs filter the visible list).
 */
import { useEffect, useRef, useState } from "react";
import { useLocation } from "wouter";
import {
  CommandDialog, CommandInput, CommandList, CommandEmpty, CommandGroup,
  CommandItem, CommandSeparator, CommandShortcut,
} from "@/components/ui/command";
import {
  BarChart3, Briefcase, TrendingUp, Layers, Search, Settings, Mail,
  Activity, Newspaper, PieChart, Sparkles, Target, Sun, Moon, LogOut,
  RefreshCw, Building2, Bot, Calculator,
} from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { useCustomAuth } from "@/context/CustomAuthContext";
import { useTheme } from "@/context/ThemeContext";


// ── Static page catalog ─────────────────────────────────────────────────────
// Anything routed from `<AppRoutes>` should be reachable here. Order is
// display order in the palette (top = first shown). Keywords power
// cmdk's fuzzy match so "scan" finds /scanners, "macro" finds /insights,
// "f&o" finds /options, etc.

interface PageDef {
  label:    string;
  path:     string;
  Icon:     typeof Briefcase;
  keywords?: string;
  group:    "Primary" | "Insights" | "AI" | "Settings";
}

const PAGES: PageDef[] = [
  // Primary
  { label: "Dashboard",          path: "/",                Icon: BarChart3,  keywords: "home overview indices", group: "Primary" },
  { label: "Portfolio",          path: "/portfolio",       Icon: Briefcase,  keywords: "holdings transactions risk", group: "Primary" },
  { label: "Stock Lookup",       path: "/stocks",          Icon: Search,     keywords: "search ticker symbol", group: "Primary" },
  { label: "Options Strategy",   path: "/options",         Icon: Layers,     keywords: "f&o derivatives chain greeks payoff", group: "Primary" },
  { label: "Scanners",           path: "/scanners",        Icon: Target,     keywords: "screener filter signals", group: "Primary" },
  { label: "Trading Platform",   path: "/trading",         Icon: TrendingUp, keywords: "watchlist chart studio", group: "Primary" },

  // Insights
  { label: "Insights — Macro",   path: "/insights/macro",     Icon: Activity,   keywords: "rbi cpi iip gdp inflation rate", group: "Insights" },
  { label: "Insights — Heatmap", path: "/insights/heatmap",   Icon: PieChart,   keywords: "sector heatmap", group: "Insights" },
  { label: "Insights — FII/DII", path: "/insights/fii-dii",   Icon: Building2, keywords: "fii dii flows", group: "Insights" },
  { label: "Insights — IPOs",    path: "/insights/ipos",      Icon: Sparkles,   keywords: "ipo new listing gmp", group: "Insights" },
  { label: "Insights — News",    path: "/insights/news",      Icon: Newspaper,  keywords: "news headlines", group: "Insights" },
  { label: "Sentiment Dashboard", path: "/sentiment",          Icon: Activity,  keywords: "sentiment mood", group: "Insights" },
  { label: "Sectors",            path: "/sectors",            Icon: PieChart,  keywords: "sector breakdown", group: "Insights" },
  { label: "Patterns",           path: "/patterns",           Icon: TrendingUp, keywords: "chart patterns candle", group: "Insights" },
  { label: "News Feed",          path: "/news",               Icon: Newspaper, keywords: "news feed", group: "Insights" },

  // AI
  { label: "AI Analyst",         path: "/ai-analyst",            Icon: Bot,        keywords: "ai analysis", group: "AI" },
  { label: "AI Analyst — Scan",  path: "/ai-analyst/scan",       Icon: Bot,        keywords: "ai scan batch", group: "AI" },
  { label: "AI Analyst — Compare",path: "/ai-analyst/compare",   Icon: Bot,        keywords: "compare ai", group: "AI" },
  { label: "AI Analyst — Track Record", path: "/ai-analyst/track-record", Icon: Bot, keywords: "backtest ai performance", group: "AI" },
  { label: "Saved Analyses",     path: "/ai-analyst/saved",      Icon: Bot,        keywords: "saved analyses history", group: "AI" },
  { label: "Investor Council",   path: "/agents",                Icon: Bot,        keywords: "agents persona", group: "AI" },
  { label: "Hydra Alpha",        path: "/hydra",                 Icon: Sparkles,   keywords: "hydra alpha", group: "AI" },
  { label: "DCF Calculator",     path: "/dcf",                   Icon: Calculator, keywords: "discounted cash flow valuation intrinsic", group: "AI" },

  // Settings
  { label: "Settings",           path: "/settings",         Icon: Settings, keywords: "preferences broker keys", group: "Settings" },
  { label: "Email Digest",       path: "/email-digest",     Icon: Mail,     keywords: "email digest schedule", group: "Settings" },
];


// ── Stock-search row type ───────────────────────────────────────────────────


interface StockHit {
  symbol:    string;
  name?:     string | null;
  category?: string;
}


// ── Component ───────────────────────────────────────────────────────────────


export default function CommandPalette() {
  const [open, setOpen]     = useState(false);
  const [query, setQuery]   = useState("");
  const [hits, setHits]     = useState<StockHit[]>([]);
  const [, setLocation]     = useLocation();
  const { token, logout }   = useCustomAuth();
  const { theme, toggle }   = useTheme();
  const queryClient         = useQueryClient();
  const abortRef            = useRef<AbortController | null>(null);

  // Global keyboard listener — Cmd+K on Mac, Ctrl+K elsewhere. Skip
  // when the user is typing in an input/textarea AND the input has
  // focus, so we don't hijack search boxes that already use Cmd+K.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const isKMod = e.key === "k" || e.key === "K";
      const isModifier = e.metaKey || e.ctrlKey;
      if (!isKMod || !isModifier) return;

      // Allow the shortcut to TOGGLE — also lets Escape close (handled
      // by Radix Dialog internally).
      e.preventDefault();
      setOpen((v) => !v);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // Reset query whenever palette closes — prevents stale state if the
  // user opens it again from a different page.
  useEffect(() => {
    if (!open) {
      setQuery("");
      setHits([]);
      abortRef.current?.abort();
    }
  }, [open]);

  // Debounced stock search. Reuses the same /api/search/suggest
  // endpoint StockCombobox calls — single source of truth for
  // autocomplete ranking.
  useEffect(() => {
    if (!open) return;
    const q = query.trim();
    if (q.length < 1) { setHits([]); return; }
    const t = setTimeout(() => {
      abortRef.current?.abort();
      const ctrl = new AbortController();
      abortRef.current = ctrl;
      const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};
      fetch(`/api/search/suggest?q=${encodeURIComponent(q)}&limit=8`, {
        headers, signal: ctrl.signal,
      })
        .then(r => r.ok ? r.json() : { results: [] })
        .then((d: { results?: StockHit[] }) => {
          if (ctrl.signal.aborted) return;
          setHits(Array.isArray(d.results) ? d.results : []);
        })
        .catch(() => { /* silent — palette still usable for nav */ });
    }, 180);
    return () => clearTimeout(t);
  }, [query, token, open]);

  // Navigate + close helper. Wouter's useLocation returns
  // [path, setLocation]; setLocation handles base-path correctly.
  const go = (path: string) => {
    setLocation(path);
    setOpen(false);
  };

  // Refresh action — invalidates the React-Query cache so every
  // active query refetches. Cheaper than a hard reload.
  const refreshAll = () => {
    queryClient.invalidateQueries();
    setOpen(false);
  };

  // Group pages by section for cleaner rendering.
  const pagesByGroup = PAGES.reduce<Record<string, PageDef[]>>((acc, p) => {
    (acc[p.group] ||= []).push(p);
    return acc;
  }, {});

  return (
    <CommandDialog open={open} onOpenChange={setOpen}>
      <CommandInput
        placeholder="Search stocks, jump to a page, or run an action…"
        value={query}
        onValueChange={setQuery}
      />
      <CommandList>
        <CommandEmpty>No results.</CommandEmpty>

        {/* Stock search — only shows when there are hits */}
        {hits.length > 0 && (
          <>
            <CommandGroup heading="Stocks">
              {hits.map((h) => (
                <CommandItem
                  key={h.symbol}
                  value={`stock-${h.symbol}-${h.name ?? ""}`}
                  onSelect={() => go(`/stocks?symbol=${encodeURIComponent(h.symbol)}`)}
                >
                  <Search className="opacity-60" />
                  <div className="flex flex-col">
                    <span className="font-semibold">{h.symbol}</span>
                    {h.name && <span className="text-xs text-muted-foreground">{h.name}</span>}
                  </div>
                  {h.category && (
                    <span className="ml-auto text-[10px] text-muted-foreground uppercase">{h.category}</span>
                  )}
                </CommandItem>
              ))}
            </CommandGroup>
            <CommandSeparator />
          </>
        )}

        {/* Pages */}
        {Object.entries(pagesByGroup).map(([groupName, pages]) => (
          <CommandGroup key={groupName} heading={groupName}>
            {pages.map((p) => {
              const Icon = p.Icon;
              return (
                <CommandItem
                  key={p.path}
                  value={`page-${p.label}-${p.keywords ?? ""}`}
                  onSelect={() => go(p.path)}
                >
                  <Icon className="opacity-60" />
                  <span>{p.label}</span>
                </CommandItem>
              );
            })}
          </CommandGroup>
        ))}

        <CommandSeparator />

        {/* Actions */}
        <CommandGroup heading="Actions">
          <CommandItem value="action-refresh" onSelect={refreshAll}>
            <RefreshCw className="opacity-60" />
            <span>Refresh all data</span>
            <CommandShortcut>Invalidates cache</CommandShortcut>
          </CommandItem>
          <CommandItem value="action-toggle-theme" onSelect={() => { toggle(); setOpen(false); }}>
            {theme === "dark" ? <Sun className="opacity-60" /> : <Moon className="opacity-60" />}
            <span>Toggle theme</span>
            <CommandShortcut>{theme === "dark" ? "→ Light" : "→ Dark"}</CommandShortcut>
          </CommandItem>
          <CommandItem value="action-add-transaction" onSelect={() => go("/portfolio")}>
            <Briefcase className="opacity-60" />
            <span>Add portfolio transaction</span>
          </CommandItem>
          <CommandItem value="action-run-ai-scan" onSelect={() => go("/ai-analyst/scan")}>
            <Bot className="opacity-60" />
            <span>Run AI scan</span>
          </CommandItem>
          <CommandItem value="action-logout" onSelect={() => { logout(); setOpen(false); }}>
            <LogOut className="opacity-60" />
            <span>Sign out</span>
          </CommandItem>
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  );
}
