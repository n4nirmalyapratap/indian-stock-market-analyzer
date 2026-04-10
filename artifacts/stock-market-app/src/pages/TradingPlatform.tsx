import { useState, useRef, useCallback, useEffect, forwardRef, useImperativeHandle } from "react";
import { useSearch, useLocation } from "wouter";
import {
  BarChart2,
  LayoutTemplate, PanelRight, X, Search,
  ChevronDown, Calendar,
} from "lucide-react";
import ChartPanel, { type DrawingTool, type Drawing, type ChartType } from "@/components/trading/ChartPanel";
import WatchlistPanel, { type WatchlistPanelHandle } from "@/components/trading/WatchlistPanel";
import LeftDrawingBar from "@/components/trading/LeftDrawingBar";
import { useTheme } from "@/context/ThemeContext";

// ─── Symbol catalogue ────────────────────────────────────────────────────────
const SYMBOLS = [
  // ── NSE Broad Market Indices ────────────────────────────────────────────────
  { symbol: "NIFTY 50",               name: "Nifty 50 Index (NSE)",               type: "index" },
  { symbol: "NIFTY NEXT 50",          name: "Nifty Next 50 Index (NSE)",          type: "index" },
  { symbol: "NIFTY 100",              name: "Nifty 100 Index (NSE)",              type: "index" },
  { symbol: "NIFTY 200",              name: "Nifty 200 Index (NSE)",              type: "index" },
  { symbol: "NIFTY 500",              name: "Nifty 500 Index (NSE)",              type: "index" },
  { symbol: "NIFTY MIDCAP 50",        name: "Nifty Midcap 50 Index (NSE)",        type: "index" },
  { symbol: "NIFTY MIDCAP 100",       name: "Nifty Midcap 100 Index (NSE)",       type: "index" },
  { symbol: "NIFTY MIDCAP 150",       name: "Nifty Midcap 150 Index (NSE)",       type: "index" },
  { symbol: "NIFTY MIDCAP SELECT",    name: "Nifty Midcap Select Index (NSE)",    type: "index" },
  { symbol: "NIFTY SMALLCAP 50",      name: "Nifty Smallcap 50 Index (NSE)",      type: "index" },
  { symbol: "NIFTY SMALLCAP 100",     name: "Nifty Smallcap 100 Index (NSE)",     type: "index" },
  { symbol: "NIFTY SMALLCAP 250",     name: "Nifty Smallcap 250 Index (NSE)",     type: "index" },
  { symbol: "NIFTY MICROCAP 250",     name: "Nifty Microcap 250 Index (NSE)",     type: "index" },
  { symbol: "NIFTY LARGEMIDCAP 250",  name: "Nifty LargeMidcap 250 Index (NSE)", type: "index" },
  // ── NSE Sectoral Indices ────────────────────────────────────────────────────
  { symbol: "NIFTY BANK",             name: "Nifty Bank Index (NSE)",             type: "index" },
  { symbol: "NIFTY FIN SERVICE",      name: "Nifty Financial Services (NSE)",     type: "index" },
  { symbol: "NIFTY IT",               name: "Nifty IT Index (NSE)",               type: "index" },
  { symbol: "NIFTY AUTO",             name: "Nifty Auto Index (NSE)",             type: "index" },
  { symbol: "NIFTY PHARMA",           name: "Nifty Pharma Index (NSE)",           type: "index" },
  { symbol: "NIFTY FMCG",             name: "Nifty FMCG Index (NSE)",             type: "index" },
  { symbol: "NIFTY METAL",            name: "Nifty Metal Index (NSE)",            type: "index" },
  { symbol: "NIFTY REALTY",           name: "Nifty Realty Index (NSE)",           type: "index" },
  { symbol: "NIFTY ENERGY",           name: "Nifty Energy Index (NSE)",           type: "index" },
  { symbol: "NIFTY INFRA",            name: "Nifty Infrastructure Index (NSE)",   type: "index" },
  { symbol: "NIFTY PSU BANK",         name: "Nifty PSU Bank Index (NSE)",         type: "index" },
  { symbol: "NIFTY MNC",              name: "Nifty MNC Index (NSE)",              type: "index" },
  { symbol: "NIFTY MEDIA",            name: "Nifty Media Index (NSE)",            type: "index" },
  { symbol: "NIFTY HEALTHCARE",       name: "Nifty Healthcare Index (NSE)",       type: "index" },
  { symbol: "NIFTY COMMODITIES",      name: "Nifty Commodities Index (NSE)",      type: "index" },
  { symbol: "NIFTY SERVICES SECTOR",  name: "Nifty Services Sector (NSE)",        type: "index" },
  { symbol: "NIFTY CPSE",             name: "Nifty CPSE Index (NSE)",             type: "index" },
  { symbol: "NIFTY PSE",              name: "Nifty PSE Index (NSE)",              type: "index" },
  { symbol: "NIFTY OIL & GAS",        name: "Nifty Oil & Gas Index (NSE)",        type: "index" },
  { symbol: "NIFTY CONSUMER DURABLES",name: "Nifty Consumer Durables (NSE)",      type: "index" },
  { symbol: "NIFTY INDIA CONSUMPTION",name: "Nifty India Consumption (NSE)",      type: "index" },
  { symbol: "NIFTY INDIA DIGITAL",    name: "Nifty India Digital (NSE)",          type: "index" },
  { symbol: "NIFTY INDIA DEFENCE",    name: "Nifty India Defence (NSE)",          type: "index" },
  // ── NSE Strategy / Thematic ────────────────────────────────────────────────
  { symbol: "INDIA VIX",              name: "India Volatility Index (NSE)",       type: "index" },
  { symbol: "NIFTY ALPHA 50",         name: "Nifty Alpha 50 (NSE)",              type: "index" },
  { symbol: "NIFTY50 VALUE 20",       name: "Nifty 50 Value 20 (NSE)",           type: "index" },
  // ── BSE Broad Market Indices ────────────────────────────────────────────────
  { symbol: "SENSEX",                 name: "BSE Sensex 30",                      type: "index" },
  { symbol: "BSE 100",                name: "BSE 100 Index",                      type: "index" },
  { symbol: "BSE 200",                name: "BSE 200 Index",                      type: "index" },
  { symbol: "BSE 500",                name: "BSE 500 Index",                      type: "index" },
  { symbol: "BSE MIDCAP",             name: "BSE Midcap Index",                   type: "index" },
  { symbol: "BSE SMALLCAP",           name: "BSE Smallcap Index",                 type: "index" },
  { symbol: "BSE LARGECAP",           name: "BSE Largecap Index",                 type: "index" },
  // ── BSE Sectoral Indices ────────────────────────────────────────────────────
  { symbol: "BANKEX",                 name: "BSE Bankex",                         type: "index" },
  { symbol: "BSE IT",                 name: "BSE IT Index",                       type: "index" },
  { symbol: "BSE HEALTHCARE",         name: "BSE Healthcare Index",               type: "index" },
  { symbol: "BSE AUTO",               name: "BSE Auto Index",                     type: "index" },
  { symbol: "BSE FMCG",               name: "BSE FMCG Index",                     type: "index" },
  { symbol: "BSE METAL",              name: "BSE Metal Index",                    type: "index" },
  { symbol: "BSE REALTY",             name: "BSE Realty Index",                   type: "index" },
  { symbol: "BSE ENERGY",             name: "BSE Energy Index",                   type: "index" },
  { symbol: "BSE POWER",              name: "BSE Power Index",                    type: "index" },
  { symbol: "BSE CAPITAL GOODS",      name: "BSE Capital Goods Index",            type: "index" },
  { symbol: "BSE CONSUMER DURABLES",  name: "BSE Consumer Durables Index",        type: "index" },
  { symbol: "BSE TECK",               name: "BSE Teck Index",                     type: "index" },
  { symbol: "BSE OIL & GAS",          name: "BSE Oil & Gas Index",                type: "index" },
  { symbol: "BSE UTILITIES",          name: "BSE Utilities Index",                type: "index" },
  { symbol: "BSE FINANCE",            name: "BSE Finance Index",                  type: "index" },
  { symbol: "BSE INDUSTRIALS",        name: "BSE Industrials Index",              type: "index" },
  { symbol: "BSE TELECOM",            name: "BSE Telecom Index",                  type: "index" },
  { symbol: "BSE COMMODITIES",        name: "BSE Commodities Index",              type: "index" },
  // ── Nifty 50 Constituents ───────────────────────────────────────────────────
  { symbol: "RELIANCE",    name: "Reliance Industries",          type: "stock"  },
  { symbol: "TCS",         name: "Tata Consultancy Services",    type: "stock"  },
  { symbol: "HDFCBANK",    name: "HDFC Bank",                    type: "stock"  },
  { symbol: "INFY",        name: "Infosys",                      type: "stock"  },
  { symbol: "ICICIBANK",   name: "ICICI Bank",                   type: "stock"  },
  { symbol: "HINDUNILVR",  name: "Hindustan Unilever",           type: "stock"  },
  { symbol: "ITC",         name: "ITC Limited",                  type: "stock"  },
  { symbol: "SBIN",        name: "State Bank of India",          type: "stock"  },
  { symbol: "BHARTIARTL",  name: "Bharti Airtel",                type: "stock"  },
  { symbol: "KOTAKBANK",   name: "Kotak Mahindra Bank",          type: "stock"  },
  { symbol: "BAJFINANCE",  name: "Bajaj Finance",                type: "stock"  },
  { symbol: "AXISBANK",    name: "Axis Bank",                    type: "stock"  },
  { symbol: "MARUTI",      name: "Maruti Suzuki",                type: "stock"  },
  { symbol: "HCLTECH",     name: "HCL Technologies",             type: "stock"  },
  { symbol: "WIPRO",       name: "Wipro",                        type: "stock"  },
  { symbol: "TITAN",       name: "Titan Company",                type: "stock"  },
  { symbol: "SUNPHARMA",   name: "Sun Pharmaceuticals",          type: "stock"  },
  { symbol: "ADANIENT",    name: "Adani Enterprises",            type: "stock"  },
  { symbol: "ADANIPORTS",  name: "Adani Ports",                  type: "stock"  },
  { symbol: "ASIANPAINT",  name: "Asian Paints",                 type: "stock"  },
  { symbol: "BAJAJFINSV",  name: "Bajaj Finserv",                type: "stock"  },
  { symbol: "BPCL",        name: "BPCL",                         type: "stock"  },
  { symbol: "BRITANNIA",   name: "Britannia Industries",         type: "stock"  },
  { symbol: "CIPLA",       name: "Cipla",                        type: "stock"  },
  { symbol: "COALINDIA",   name: "Coal India",                   type: "stock"  },
  { symbol: "DIVISLAB",    name: "Divi's Laboratories",          type: "stock"  },
  { symbol: "DRREDDY",     name: "Dr. Reddy's Laboratories",     type: "stock"  },
  { symbol: "EICHERMOT",   name: "Eicher Motors",                type: "stock"  },
  { symbol: "GRASIM",      name: "Grasim Industries",            type: "stock"  },
  { symbol: "HDFCLIFE",    name: "HDFC Life Insurance",          type: "stock"  },
  { symbol: "HEROMOTOCO",  name: "Hero MotoCorp",                type: "stock"  },
  { symbol: "HINDALCO",    name: "Hindalco Industries",          type: "stock"  },
  { symbol: "INDUSINDBK",  name: "IndusInd Bank",                type: "stock"  },
  { symbol: "JSWSTEEL",    name: "JSW Steel",                    type: "stock"  },
  { symbol: "LT",          name: "Larsen & Toubro",              type: "stock"  },
  { symbol: "LTIM",        name: "LTIMindtree",                  type: "stock"  },
  { symbol: "NESTLEIND",   name: "Nestle India",                 type: "stock"  },
  { symbol: "NTPC",        name: "NTPC",                         type: "stock"  },
  { symbol: "ONGC",        name: "Oil and Natural Gas Corp",     type: "stock"  },
  { symbol: "POWERGRID",   name: "Power Grid Corp",              type: "stock"  },
  { symbol: "SBILIFE",     name: "SBI Life Insurance",           type: "stock"  },
  { symbol: "TATAMOTORS",  name: "Tata Motors",                  type: "stock"  },
  { symbol: "TATASTEEL",   name: "Tata Steel",                   type: "stock"  },
  { symbol: "TECHM",       name: "Tech Mahindra",                type: "stock"  },
  { symbol: "TRENT",       name: "Trent Limited",                type: "stock"  },
  { symbol: "ULTRACEMCO",  name: "UltraTech Cement",             type: "stock"  },
  { symbol: "ZOMATO",      name: "Zomato",                       type: "stock"  },
  { symbol: "PAYTM",       name: "Paytm (One97)",                type: "stock"  },
  { symbol: "NYKAA",       name: "FSN E-Commerce (Nykaa)",       type: "stock"  },
  { symbol: "PIDILITIND",  name: "Pidilite Industries",          type: "stock"  },
  { symbol: "HAVELLS",     name: "Havells India",                type: "stock"  },
  { symbol: "MUTHOOTFIN",  name: "Muthoot Finance",              type: "stock"  },
  { symbol: "BANDHANBNK",  name: "Bandhan Bank",                 type: "stock"  },
];

// ─── Interval / timeframe configs ─────────────────────────────────────────────
interface IntervalEntry { label: string; p: string; i: string }

const INTERVALS: IntervalEntry[] = [
  { label: "1m",  p: "1d",   i: "1m"  },
  { label: "2m",  p: "1d",   i: "2m"  },
  { label: "5m",  p: "2d",   i: "5m"  },
  { label: "15m", p: "5d",   i: "15m" },
  { label: "30m", p: "1mo",  i: "30m" },
  { label: "1H",  p: "1mo",  i: "60m" },
  { label: "2H",  p: "3mo",  i: "90m" },
  { label: "1D",  p: "1y",   i: "1d"  },
  { label: "1W",  p: "5y",   i: "1wk" },
  { label: "1M",  p: "5y",   i: "1mo" },
];

// Groups shown in the dropdown — labels must match INTERVALS[n].label
const INTERVAL_GROUPS: { group: string; labels: string[] }[] = [
  { group: "Minutes", labels: ["1m", "2m", "5m", "15m", "30m"] },
  { group: "Hours",   labels: ["1H", "2H"] },
  { group: "Days",    labels: ["1D"] },
  { group: "Weeks",   labels: ["1W"] },
  { group: "Months",  labels: ["1M"] },
];

// ─── Range-selector presets (bottom bar) ──────────────────────────────────────
interface RangeEntry { label: string; p: string; i: string; start?: string; end?: string }

function getYTDStart(): string {
  return `${new Date().getFullYear()}-01-01`;
}
function getTodayStr(): string {
  return new Date().toISOString().slice(0, 10);
}

const RANGES: RangeEntry[] = [
  { label: "1D",  p: "1d",  i: "5m"  },
  { label: "5D",  p: "5d",  i: "15m" },
  { label: "1M",  p: "1mo", i: "1d"  },
  { label: "3M",  p: "3mo", i: "1d"  },
  { label: "6M",  p: "6mo", i: "1d"  },
  { label: "YTD", p: "ytd", i: "1d"  }, // resolved dynamically
  { label: "1Y",  p: "1y",  i: "1d"  },
  { label: "All", p: "5y",  i: "1wk" },
];

// ─── Layout modes ────────────────────────────────────────────────────────────
type LayoutMode = "1" | "2h" | "2v" | "4";

const LAYOUTS: { mode: LayoutMode; label: string; icon: React.ReactNode; panels: number }[] = [
  { mode: "1",  label: "Single",       icon: <div className="w-4 h-4 border border-current rounded-sm" />, panels: 1 },
  { mode: "2h", label: "Side by Side", icon: <div className="flex gap-0.5 w-4 h-4"><div className="flex-1 border border-current rounded-sm" /><div className="flex-1 border border-current rounded-sm" /></div>, panels: 2 },
  { mode: "2v", label: "Top / Bottom", icon: <div className="flex flex-col gap-0.5 w-4 h-4"><div className="flex-1 border border-current rounded-sm" /><div className="flex-1 border border-current rounded-sm" /></div>, panels: 2 },
  { mode: "4",  label: "2×2 Grid",     icon: <div className="grid grid-cols-2 gap-0.5 w-4 h-4"><div className="border border-current rounded-sm" /><div className="border border-current rounded-sm" /><div className="border border-current rounded-sm" /><div className="border border-current rounded-sm" /></div>, panels: 4 },
];

// ─── Indicators ──────────────────────────────────────────────────────────────
const IND_OPTS = [
  { key: "ema9",   label: "EMA 9",   color: "#f59e0b" },
  { key: "ema21",  label: "EMA 21",  color: "#6366f1" },
  { key: "ema50",  label: "EMA 50",  color: "#10b981" },
  { key: "ema200", label: "EMA 200", color: "#ef4444" },
  { key: "sma50",  label: "SMA 50",  color: "#a78bfa" },
  { key: "bb",     label: "BB (20)", color: "#3b82f6" },
];


function uid() { return Math.random().toString(36).slice(2, 9); }

interface PanelState {
  id: string;
  symbol: string;
  drawings: Drawing[];
}

function makePanel(symbol: string): PanelState {
  return { id: uid(), symbol, drawings: [] };
}

// ─── Symbol Search Modal (TradingView-style full-screen popup) ────────────────
interface SearchResult { symbol: string; name: string }

type SearchMode = "chart" | "watchlist";

export interface SearchModalHandle {
  open: (opts?: { char?: string; mode?: SearchMode }) => void;
}

const INDEX_SYMS = new Set(["NIFTY 50", "NIFTY50", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY"]);

const SearchModal = forwardRef<SearchModalHandle, {
  onSelectChart: (sym: string) => void;
  onSelectWatchlist: (sym: string) => void;
}>(function SearchModal({ onSelectChart, onSelectWatchlist }, fwdRef) {
  const [open, setOpen]       = useState(false);
  const [mode, setMode]       = useState<SearchMode>("chart");
  const [q, setQ]             = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [activeIdx, setActiveIdx] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const debounce = useRef<ReturnType<typeof setTimeout> | null>(null);

  useImperativeHandle(fwdRef, () => ({
    open: (opts) => {
      setMode(opts?.mode ?? "chart");
      const char = opts?.char ?? "";
      setQ(char);
      setResults([]);
      setActiveIdx(0);
      setOpen(true);
      if (char) doSearch(char);
      requestAnimationFrame(() => inputRef.current?.focus());
    },
  }));

  function close() { setOpen(false); setQ(""); setResults([]); }

  function doSearch(val: string) {
    if (debounce.current) clearTimeout(debounce.current);
    if (!val.trim()) { setResults([]); return; }
    debounce.current = setTimeout(async () => {
      setLoading(true);
      try {
        const res = await fetch(`/api/stocks/search?q=${encodeURIComponent(val.trim())}`);
        if (res.ok) { const d = await res.json(); setResults(d.results ?? []); setActiveIdx(0); }
      } catch { setResults([]); }
      finally { setLoading(false); }
    }, 160);
  }

  function handleSelect(sym: string) {
    if (mode === "watchlist") onSelectWatchlist(sym);
    else onSelectChart(sym);
    close();
  }

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[200] flex items-start justify-center"
      style={{ paddingTop: "10vh", background: "rgba(0,0,0,0.55)", backdropFilter: "blur(3px)" }}
      onMouseDown={e => { if (e.target === e.currentTarget) close(); }}
    >
      <div
        className="w-full mx-4 rounded-2xl overflow-hidden flex flex-col shadow-2xl"
        style={{ maxWidth: 620, maxHeight: "72vh", background: "#1a1d27", border: "1px solid rgba(255,255,255,0.09)" }}
      >
        {/* Search input row */}
        <div className="flex items-center gap-3 px-5 py-4 border-b" style={{ borderColor: "rgba(255,255,255,0.07)" }}>
          <Search size={17} className="text-gray-500 shrink-0" />
          <input
            ref={inputRef}
            value={q}
            onChange={e => { setQ(e.target.value); doSearch(e.target.value); }}
            placeholder={mode === "watchlist" ? "Search to add to watchlist…" : "Search symbol or company…"}
            className="flex-1 bg-transparent text-white text-base placeholder-gray-600 focus:outline-none"
            onKeyDown={e => {
              if (e.key === "ArrowDown") { e.preventDefault(); setActiveIdx(i => Math.min(i + 1, results.length - 1)); }
              if (e.key === "ArrowUp")   { e.preventDefault(); setActiveIdx(i => Math.max(i - 1, 0)); }
              if (e.key === "Enter" && results[activeIdx]) handleSelect(results[activeIdx].symbol);
              if (e.key === "Escape") close();
            }}
          />
          {loading && <div className="w-4 h-4 border-2 border-indigo-400/60 border-t-indigo-400 rounded-full animate-spin shrink-0" />}
          {q && !loading && (
            <button onClick={() => { setQ(""); setResults([]); inputRef.current?.focus(); }} className="shrink-0 text-gray-600 hover:text-white transition-colors">
              <X size={15} />
            </button>
          )}
          {mode === "watchlist" && (
            <span className="shrink-0 text-[11px] px-2.5 py-1 rounded-full font-medium" style={{ background: "rgba(99,102,241,0.2)", color: "#a5b4fc", border: "1px solid rgba(99,102,241,0.3)" }}>
              + Watchlist
            </span>
          )}
          <button onClick={close} className="shrink-0 text-gray-600 hover:text-white transition-colors ml-1">
            <X size={17} />
          </button>
        </div>

        {/* Results list */}
        <div className="flex-1 overflow-y-auto" style={{ scrollbarWidth: "none" }}>
          {results.length > 0 && results.map((s, i) => (
            <button
              key={s.symbol}
              onClick={() => handleSelect(s.symbol)}
              onMouseEnter={() => setActiveIdx(i)}
              className={`w-full flex items-center gap-4 px-5 py-3 text-left transition-colors ${
                i === activeIdx ? "bg-indigo-500/15" : "hover:bg-white/5"
              }`}
            >
              <div className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0 text-[11px] font-bold"
                style={{ background: "rgba(255,255,255,0.06)", color: "#9ca3af" }}>
                {s.symbol.slice(0, 2)}
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-sm font-semibold text-white">{s.symbol}</div>
                {s.name && <div className="text-xs text-gray-500 truncate mt-0.5">{s.name}</div>}
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <span className="text-[10px] px-1.5 py-0.5 rounded font-mono"
                  style={{ background: "rgba(255,255,255,0.06)", color: "#6b7280" }}>
                  {INDEX_SYMS.has(s.symbol) ? "INDEX" : "NSE"}
                </span>
              </div>
            </button>
          ))}

          {q && !loading && results.length === 0 && (
            <div className="flex flex-col items-center justify-center py-14 gap-2">
              <Search size={28} className="text-gray-700" />
              <p className="text-sm text-gray-500">No results for <span className="text-gray-300">"{q}"</span></p>
            </div>
          )}

          {!q && (
            <div className="flex flex-col items-center justify-center py-14 gap-2">
              <Search size={28} className="text-gray-700" />
              <p className="text-sm text-gray-600">
                {mode === "watchlist" ? "Search a symbol to add to your watchlist" : "Type a symbol or company name"}
              </p>
              <p className="text-xs text-gray-700 mt-1">Press <kbd className="px-1.5 py-0.5 rounded bg-gray-800 text-gray-500 font-mono text-[11px]">↑↓</kbd> to navigate · <kbd className="px-1.5 py-0.5 rounded bg-gray-800 text-gray-500 font-mono text-[11px]">Enter</kbd> to select · <kbd className="px-1.5 py-0.5 rounded bg-gray-800 text-gray-500 font-mono text-[11px]">Esc</kbd> to close</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
});

// ─── Chart Type definitions ───────────────────────────────────────────────────
interface ChartTypeEntry { type: ChartType; label: string; icon: string }

const CHART_TYPE_GROUPS: { group: string; items: ChartTypeEntry[] }[] = [
  {
    group: "OHLC",
    items: [
      { type: "candles",      label: "Candles",          icon: "🕯" },
      { type: "hollow",       label: "Hollow candles",   icon: "◻" },
      { type: "bars",         label: "Bars",             icon: "┤" },
      { type: "ha",           label: "Heikin Ashi",      icon: "🕯" },
    ],
  },
  {
    group: "Line",
    items: [
      { type: "line",         label: "Line",             icon: "∕" },
      { type: "line_markers", label: "Line + markers",   icon: "∕•" },
      { type: "step",         label: "Step line",        icon: "⌐" },
    ],
  },
  {
    group: "Area / Bar",
    items: [
      { type: "area",         label: "Area",             icon: "▲" },
      { type: "baseline",     label: "Baseline",         icon: "⊟" },
      { type: "columns",      label: "Columns",          icon: "▋" },
    ],
  },
];

// ─── Chart Type Selector dropdown ─────────────────────────────────────────────
function ChartTypeSelector({
  chartType,
  onSelect,
  theme,
}: {
  chartType: ChartType;
  onSelect: (t: ChartType) => void;
  theme: "dark" | "light";
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const current = CHART_TYPE_GROUPS.flatMap(g => g.items).find(i => i.type === chartType);
  const d = theme === "dark";
  const C = {
    btnBg:  d ? "rgba(30,38,50,0.85)" : "rgba(15,23,42,0.06)",
    btnBor: d ? "#374151" : "#cbd5e1",
    btnTxt: d ? "#e5e7eb" : "#0f172a",
    dropBg: d ? "#1e2130" : "#ffffff",
    dropBor: d ? "#374151" : "#cbd5e1",
    secTxt: d ? "#6b7280" : "#94a3b8",
    itemTxt: d ? "#d1d5db" : "#334155",
    itemHov: d ? "rgba(255,255,255,0.07)" : "rgba(0,0,0,0.05)",
  };

  useEffect(() => {
    function handler(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(v => !v)}
        title="Chart type"
        className="flex items-center gap-1 px-2.5 py-1 rounded text-xs font-semibold transition-colors"
        style={open
          ? { background: "#6366f1", color: "#ffffff", border: "1px solid #6366f1" }
          : { background: C.btnBg, color: C.btnTxt, border: `1px solid ${C.btnBor}` }}
      >
        <span className="font-mono text-[13px] leading-none">{current?.icon ?? "🕯"}</span>
        <ChevronDown size={11} className={`transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {open && (
        <div
          className="absolute top-full left-0 mt-1 z-50 rounded-lg shadow-2xl min-w-[200px]"
          style={{ background: C.dropBg, border: `1px solid ${C.dropBor}` }}
        >
          <div className="px-4 pt-3 pb-2" style={{ borderBottom: `1px solid ${C.dropBor}` }}>
            <span className="text-[11px] font-semibold uppercase tracking-wider" style={{ color: C.secTxt }}>Chart Type</span>
          </div>
          <div className="p-2">
            {CHART_TYPE_GROUPS.map(({ group, items }) => (
              <div key={group} className="mb-1">
                <div className="px-2 py-1 text-[10px] font-semibold uppercase tracking-wider" style={{ color: C.secTxt }}>{group}</div>
                {items.map(item => (
                  <button
                    key={item.type}
                    onClick={() => { onSelect(item.type); setOpen(false); }}
                    className="w-full flex items-center gap-3 px-3 py-1.5 rounded text-xs transition-colors"
                    style={chartType === item.type
                      ? { background: "#6366f1", color: "#ffffff" }
                      : { color: C.itemTxt }}
                  >
                    <span className="font-mono w-5 text-center text-[13px] leading-none">{item.icon}</span>
                    <span>{item.label}</span>
                  </button>
                ))}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Interval Selector dropdown (TradingView-style) ──────────────────────────
function IntervalSelector({
  intervalIdx,
  onSelect,
  theme,
}: {
  intervalIdx: number;
  onSelect: (idx: number) => void;
  theme: "dark" | "light";
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const current = INTERVALS[intervalIdx];
  const d = theme === "dark";
  const C = {
    btnBg:   d ? "rgba(30,38,50,0.85)" : "rgba(15,23,42,0.06)",
    btnBor:  d ? "#374151" : "#cbd5e1",
    btnTxt:  d ? "#e5e7eb" : "#0f172a",
    dropBg:  d ? "#1e2130" : "#ffffff",
    dropBor: d ? "#374151" : "#cbd5e1",
    secTxt:  d ? "#6b7280" : "#94a3b8",
    itemTxt: d ? "#d1d5db" : "#334155",
  };

  useEffect(() => {
    function handler(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  return (
    <div ref={ref} className="relative">
      {/* Trigger button */}
      <button
        onClick={() => setOpen(v => !v)}
        className="flex items-center gap-1 px-2.5 py-1 rounded text-xs font-semibold transition-colors"
        style={open
          ? { background: "#6366f1", color: "#ffffff", border: "1px solid #6366f1" }
          : { background: C.btnBg, color: C.btnTxt, border: `1px solid ${C.btnBor}` }}
      >
        {current.label}
        <ChevronDown size={11} className={`transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {/* Dropdown panel */}
      {open && (
        <div
          className="absolute top-full left-0 mt-1 z-50 rounded-lg shadow-2xl"
          style={{ background: C.dropBg, border: `1px solid ${C.dropBor}`, minWidth: 260 }}
        >
          {/* Header */}
          <div className="px-4 pt-3 pb-2" style={{ borderBottom: `1px solid ${C.dropBor}` }}>
            <span className="text-[11px] font-semibold uppercase tracking-wider" style={{ color: C.secTxt }}>Interval</span>
          </div>

          {/* Groups */}
          <div className="p-3 flex flex-col gap-2">
            {INTERVAL_GROUPS.map(({ group, labels }) => {
              const items = labels.map(lbl => {
                const idx = INTERVALS.findIndex(iv => iv.label === lbl);
                return idx >= 0 ? { idx, entry: INTERVALS[idx] } : null;
              }).filter(Boolean) as { idx: number; entry: IntervalEntry }[];

              return (
                <div key={group} className="flex items-center gap-3">
                  {/* Group label */}
                  <span className="text-[11px] w-14 shrink-0" style={{ color: C.secTxt }}>{group}</span>
                  {/* Interval buttons */}
                  <div className="flex items-center gap-1 flex-wrap">
                    {items.map(({ idx, entry }) => (
                      <button
                        key={entry.label}
                        onClick={() => { onSelect(idx); setOpen(false); }}
                        className="px-2.5 py-1 rounded text-xs font-medium transition-colors"
                        style={idx === intervalIdx
                          ? { background: "#6366f1", color: "#ffffff" }
                          : { color: C.itemTxt }}
                      >
                        {entry.label}
                      </button>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Main Component ───────────────────────────────────────────────────────────
export default function TradingPlatform() {
  const [layoutMode, setLayoutMode] = useState<LayoutMode>("1");
  const [panels, setPanels] = useState<PanelState[]>(() => {
    const params = new URLSearchParams(window.location.search);
    const sym = params.get("symbol")?.toUpperCase() || "RELIANCE";
    return [makePanel(sym)];
  });
  const [activePanelId, setActivePanelId] = useState(panels[0].id);
  const [intervalIdx, setIntervalIdx] = useState(7); // default: 1D
  const [chartType, setChartType] = useState<ChartType>("candles");
  const { theme } = useTheme();
  const [drawingTool, setDrawingTool] = useState<string>("none");
  const [indicators, setIndicators] = useState<Set<string>>(new Set());
  const [showRSI, setShowRSI] = useState(false);
  const [showMACD, setShowMACD] = useState(false);
  const [showWatchlist, setShowWatchlist] = useState(true);
  const [showLayouts, setShowLayouts] = useState(false);
  const [showIndMenu, setShowIndMenu] = useState(false);

  const [customPeriodCfg, setCustomPeriodCfg] = useState<{ p: string; i: string; start?: string; end?: string } | null>(null);
  const [activeRange, setActiveRange] = useState<string | null>(null);
  const [showCalendar, setShowCalendar] = useState(false);
  const [calStart, setCalStart] = useState("");
  const [calEnd, setCalEnd] = useState("");
  const [clock, setClock] = useState("");

  const searchRef    = useRef<SearchModalHandle>(null);
  const watchlistRef = useRef<WatchlistPanelHandle>(null);

  // ── Back-navigation: show back button only when opened from another page ─────
  const [, navigate] = useLocation();
  const cameFromLink = useRef(!!new URLSearchParams(window.location.search).get("symbol"));

  // ── Sync symbol from URL ?symbol= query param ───────────────────────────────
  const search = useSearch();
  useEffect(() => {
    const params = new URLSearchParams(search);
    const sym = params.get("symbol")?.toUpperCase();
    if (!sym) return;
    setPanels(prev => {
      const active = prev.find(p => p.id === activePanelId) ?? prev[0];
      if (active.symbol === sym) return prev;
      return prev.map(p => p.id === active.id ? { ...p, symbol: sym } : p);
    });
  }, [search]);

  // ── Live IST clock ─────────────────────────────────────────────────────────
  useEffect(() => {
    function tick() {
      const now = new Date();
      const ist = new Date(now.getTime() + 5.5 * 3600 * 1000);
      const hh = String(ist.getUTCHours()).padStart(2, "0");
      const mm = String(ist.getUTCMinutes()).padStart(2, "0");
      const ss = String(ist.getUTCSeconds()).padStart(2, "0");
      setClock(`${hh}:${mm}:${ss}`);
    }
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  // Reset customPeriod when user picks from the interval dropdown
  function handleIntervalSelect(idx: number) {
    setIntervalIdx(idx);
    setCustomPeriodCfg(null);
    setActiveRange(null);
    setShowCalendar(false);
  }

  function applyRange(r: RangeEntry) {
    if (r.label === "YTD") {
      setCustomPeriodCfg({ p: "1y", i: r.i, start: getYTDStart(), end: getTodayStr() });
    } else {
      setCustomPeriodCfg({ p: r.p, i: r.i });
    }
    setActiveRange(r.label);
    setShowCalendar(false);
  }

  function applyCustomRange() {
    if (!calStart || !calEnd) return;
    setCustomPeriodCfg({ p: "1y", i: INTERVALS[intervalIdx].i, start: calStart, end: calEnd });
    setActiveRange("custom");
    setShowCalendar(false);
  }

  // ── Global keyboard shortcuts ──────────────────────────────────────────────
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const tag = (e.target as HTMLElement).tagName;
      const inInput = tag === "INPUT" || tag === "TEXTAREA";

      // Ctrl/Cmd+Z — undo last drawing on active panel
      if ((e.ctrlKey || e.metaKey) && e.key === "z") {
        if (inInput) return;
        e.preventDefault();
        setPanels(prev => prev.map(p =>
          p.id === activePanelId ? { ...p, drawings: p.drawings.slice(0, -1) } : p
        ));
        return;
      }

      // Printable character (no modifier) — open symbol search modal like TradingView
      if (!e.ctrlKey && !e.metaKey && !e.altKey && e.key.length === 1 && !inInput) {
        searchRef.current?.open({ char: e.key, mode: "chart" });
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [activePanelId]);

  const activePanel = panels.find(p => p.id === activePanelId) ?? panels[0];

  // Alt+W → add active chart symbol to the current watchlist
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    const sym = activePanel?.symbol;
    function handler(e: KeyboardEvent) {
      if (e.altKey && (e.key === "w" || e.key === "W") && sym) {
        e.preventDefault();
        watchlistRef.current?.addSymbol(sym);
      }
    }
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [activePanel?.symbol]);

  function setLayout(mode: LayoutMode) {
    const cfg = LAYOUTS.find(l => l.mode === mode)!;
    setLayoutMode(mode);
    setShowLayouts(false);
    if (panels.length < cfg.panels) {
      const extra = Array.from({ length: cfg.panels - panels.length }, (_, i) =>
        makePanel(SYMBOLS[i + 1]?.symbol ?? "TCS")
      );
      setPanels(prev => [...prev, ...extra]);
    }
  }

  function setSymbolForActivePanel(sym: string) {
    setPanels(prev => prev.map(p => p.id === activePanelId ? { ...p, symbol: sym } : p));
  }

  function addDrawing(panelId: string, drawing: Drawing) {
    setPanels(prev => prev.map(p =>
      p.id === panelId ? { ...p, drawings: [...p.drawings, drawing] } : p
    ));
  }

  function eraseDrawing(panelId: string, id: string) {
    setPanels(prev => prev.map(p =>
      p.id === panelId ? { ...p, drawings: p.drawings.filter(d => d.id !== id) } : p
    ));
  }

  function clearDrawings() {
    setPanels(prev => prev.map(p =>
      p.id === activePanelId ? { ...p, drawings: [] } : p
    ));
  }

  function updateDrawing(panelId: string, id: string, shape: Record<string, unknown>) {
    setPanels(prev => prev.map(p =>
      p.id === panelId
        ? { ...p, drawings: p.drawings.map(d => d.id === id ? { ...d, shape } : d) }
        : p
    ));
  }

  function toggleIndicator(key: string) {
    setIndicators(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key); else next.add(key);
      return next;
    });
  }

  const visiblePanels = panels.slice(0, LAYOUTS.find(l => l.mode === layoutMode)!.panels);

  function getGridClass() {
    if (layoutMode === "2h") return "flex flex-row gap-1";
    if (layoutMode === "2v") return "flex flex-col gap-1";
    if (layoutMode === "4")  return "grid grid-cols-2 grid-rows-2 gap-1";
    return "flex flex-col";
  }

  const isDark = theme === "dark";
  const PT = {
    rootBg:   isDark ? "#0f1117"               : "#f1f5f9",
    barBg:    isDark ? "#131722"               : "#ffffff",
    barBor:   isDark ? "rgba(255,255,255,0.04)" : "#e2e8f0",
    dropBg:   isDark ? "#1e2130"               : "#ffffff",
    dropBor:  isDark ? "#374151"               : "#cbd5e1",
    secTxt:   isDark ? "#6b7280"               : "#94a3b8",
    itemTxt:  isDark ? "#d1d5db"               : "#334155",
    btnBg:    isDark ? "rgba(30,38,50,0.85)"   : "rgba(15,23,42,0.06)",
    btnBor:   isDark ? "#374151"               : "#cbd5e1",
    btnTxt:   isDark ? "#e5e7eb"               : "#0f172a",
    divider:  isDark ? "rgba(255,255,255,0.07)" : "#e2e8f0",
    iconTxt:  isDark ? "#9ca3af"               : "#475569",
  };

  return (
    <div className="flex flex-col h-full" style={{ background: PT.rootBg }}>
      {/* ── Toolbar ─────────────────────────────────────────────────────────── */}
      <div className="flex items-center gap-2 px-3 py-1.5 shrink-0 flex-wrap" style={{ background: PT.barBg, borderBottom: `1px solid ${PT.barBor}` }}>

        {/* Back button — only when opened via ?symbol= from another page */}
        {cameFromLink.current && (
          <button
            onClick={() => window.history.back()}
            title="Go back"
            className="flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium transition-colors"
            style={{ background: PT.btnBg, border: `1px solid ${PT.btnBor}`, color: PT.btnTxt }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M19 12H5M12 5l-7 7 7 7"/>
            </svg>
            Back
          </button>
        )}

        {/* Symbol name button — opens modal search (chart mode) */}
        <button
          onClick={() => searchRef.current?.open({ mode: "chart" })}
          className="flex items-center gap-2 rounded px-3 py-1.5 transition-colors"
          style={{ background: PT.btnBg, border: `1px solid ${PT.btnBor}` }}
        >
          <span className="text-sm font-bold tracking-wide" style={{ color: PT.btnTxt }}>{activePanel?.symbol ?? "—"}</span>
          <Search size={12} style={{ color: PT.iconTxt }} />
        </button>

        {/* Interval selector — dropdown like TradingView */}
        <IntervalSelector intervalIdx={intervalIdx} onSelect={handleIntervalSelect} theme={theme} />

        {/* Chart type selector */}
        <ChartTypeSelector chartType={chartType} onSelect={setChartType} theme={theme} />

        <div className="w-px h-5" style={{ background: PT.divider }} />

        {/* Indicators */}
        <div className="relative">
          <button
            onClick={() => setShowIndMenu(v => !v)}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded text-xs transition-colors"
            style={showIndMenu ? { background: "#6366f1", color: "#ffffff" } : { background: PT.btnBg, color: PT.itemTxt }}
          >
            <BarChart2 size={13} /> Indicators
            {indicators.size > 0 && (
              <span className="bg-indigo-500 text-white text-[10px] rounded-full px-1.5 py-0.5">{indicators.size}</span>
            )}
          </button>
          {showIndMenu && (
            <div className="absolute top-full left-0 mt-1 z-50 rounded shadow-2xl p-3 w-52" style={{ background: PT.dropBg, border: `1px solid ${PT.dropBor}` }}>
              <div className="text-[11px] font-semibold mb-2" style={{ color: PT.secTxt }}>Moving Averages</div>
              {IND_OPTS.map(opt => (
                <label key={opt.key} className="flex items-center gap-2.5 py-1 cursor-pointer group">
                  <div className={`w-4 h-4 rounded border flex items-center justify-center transition-colors ${indicators.has(opt.key) ? "bg-indigo-600 border-indigo-600" : "border-gray-600 group-hover:border-gray-400"}`}>
                    {indicators.has(opt.key) && <div className="w-2 h-2 rounded-sm" style={{ background: "#fff" }} />}
                  </div>
                  <input type="checkbox" checked={indicators.has(opt.key)} onChange={() => toggleIndicator(opt.key)} className="hidden" />
                  <div className="w-3 h-0.5 rounded" style={{ background: opt.color }} />
                  <span className="text-xs" style={{ color: PT.itemTxt }}>{opt.label}</span>
                </label>
              ))}
              <div className="mt-2 pt-2" style={{ borderTop: `1px solid ${PT.dropBor}` }}>
                <div className="text-[11px] font-semibold mb-2" style={{ color: PT.secTxt }}>Oscillators</div>
                {[
                  { key: "rsi", label: "RSI (14)", active: showRSI, toggle: () => setShowRSI(v => !v) },
                  { key: "macd", label: "MACD (12,26,9)", active: showMACD, toggle: () => setShowMACD(v => !v) },
                ].map(opt => (
                  <label key={opt.key} className="flex items-center gap-2.5 py-1 cursor-pointer group">
                    <div
                      onClick={opt.toggle}
                      className={`w-4 h-4 rounded border flex items-center justify-center transition-colors ${opt.active ? "bg-indigo-600 border-indigo-600" : "border-gray-600 group-hover:border-gray-400"}`}
                    >
                      {opt.active && <div className="w-2 h-2 rounded-sm" style={{ background: "#fff" }} />}
                    </div>
                    <span className="text-xs" style={{ color: PT.itemTxt }}>{opt.label}</span>
                  </label>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Layout selector */}
        <div className="relative">
          <button
            onClick={() => setShowLayouts(v => !v)}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded text-xs transition-colors"
            style={showLayouts ? { background: "#6366f1", color: "#ffffff" } : { background: PT.btnBg, color: PT.itemTxt }}
          >
            <LayoutTemplate size={13} /> Layout
          </button>
          {showLayouts && (
            <div className="absolute top-full right-0 mt-1 z-50 rounded shadow-2xl p-2 flex gap-1" style={{ background: PT.dropBg, border: `1px solid ${PT.dropBor}` }}>
              {LAYOUTS.map(l => (
                <button
                  key={l.mode}
                  onClick={() => setLayout(l.mode)}
                  title={l.label}
                  className="w-9 h-9 flex items-center justify-center rounded transition-colors"
                  style={layoutMode === l.mode ? { background: "#6366f1", color: "#ffffff" } : { color: PT.iconTxt }}
                >
                  {l.icon}
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="ml-auto flex items-center gap-1">
          {/* Watchlist toggle — TradingView-style icon button */}
          <button
            onClick={() => setShowWatchlist(v => !v)}
            title={showWatchlist ? "Hide watchlist" : "Show watchlist"}
            className="relative w-8 h-8 flex items-center justify-center rounded transition-all"
            style={showWatchlist
              ? { color: "#818cf8", background: "rgba(99,102,241,0.12)" }
              : { color: PT.iconTxt }}
          >
            <PanelRight size={15} />
            {showWatchlist && (
              <span className="absolute bottom-0.5 left-1/2 -translate-x-1/2 w-1 h-1 rounded-full bg-indigo-400" />
            )}
          </button>
        </div>
      </div>

      {/* ── Chart area ──────────────────────────────────────────────────────── */}
      <div className="flex flex-1 min-h-0 overflow-hidden">

        {/* Left drawing sidebar */}
        <LeftDrawingBar
          activeTool={drawingTool}
          onToolSelect={setDrawingTool}
          onClearDrawings={clearDrawings}
          hasDrawings={!!(activePanel?.drawings?.length)}
          isDark={isDark}
        />

        {/* Chart column: grid + bottom bar (clock stays inside chart area) */}
        <div className="flex-1 flex flex-col min-w-0 min-h-0 overflow-hidden">
          {/* Charts grid */}
          <div className={`flex-1 min-w-0 min-h-0 ${getGridClass()} p-1 gap-1`}>
            {visiblePanels.map((panel) => (
              <div key={panel.id} className={layoutMode === "4" ? "min-h-0 min-w-0 overflow-hidden" : "flex-1 min-h-0 min-w-0 overflow-hidden"}>
                <ChartPanel
                  panelId={panel.id}
                  symbol={panel.symbol}
                  symbolName={SYMBOLS.find(s => s.symbol === panel.symbol)?.name}
                  periodCfg={customPeriodCfg ?? INTERVALS[intervalIdx]}
                  drawingTool={(((): DrawingTool => {
                    const DIRECT: DrawingTool[] = [
                      "none","trendline","ray","extendedline",
                      "hline","hray","vline","crossline",
                      "rectangle","circle","ellipse",
                      "parallelch","pitchfork",
                      "fibretracement","fibextension","fibtimezone","fibfan",
                      "gannfan","gannbox",
                      "longposition","shortposition",
                      "cycliclines",
                      "arrowmarker","arrowmarkup","arrowmarkdown",
                      "flag","measure","note","eraser",
                    ];
                    if (DIRECT.includes(drawingTool as DrawingTool)) return drawingTool as DrawingTool;
                    const MAP: Record<string, DrawingTool> = {
                      // Lines aliases
                      "infoline":          "trendline",
                      "trendangle":        "trendline",
                      // Channel aliases
                      "regtrend":          "trendline",
                      "flattop":           "hline",
                      "disjointch":        "parallelch",
                      // Pitchfork aliases
                      "schiffpitch":       "pitchfork",
                      "pitchfan":          "pitchfork",
                      // Fibonacci aliases
                      "fibcircles":        "circle",
                      "fibspiral":         "fibretracement",
                      "fibwedge":          "fibretracement",
                      "fibchannel":        "parallelch",
                      // Gann aliases
                      "gannsquare":        "gannbox",
                      "gannsquarefixed":   "gannbox",
                      // Pattern aliases (simplified to trendline)
                      "abcd":              "trendline",
                      "cypher":            "trendline",
                      "headshoulders":     "trendline",
                      "trianglepat":       "rectangle",
                      "threedrives":       "trendline",
                      // Elliott aliases
                      "elliottimpulse":    "trendline",
                      "elliottcorrection": "trendline",
                      "elliotttriangle":   "trendline",
                      "elliottdouble":     "trendline",
                      "elliotttriple":     "trendline",
                      // Cycles aliases
                      "timecycles":        "cycliclines",
                      "sineline":          "trendline",
                      // Forecast aliases
                      "positionforecast":  "longposition",
                      "barpattern":        "rectangle",
                      "sector":            "rectangle",
                      // Volume aliases
                      "anchoredvwap":      "vline",
                      "fixedrangevolume":  "rectangle",
                      "anchoredvolume":    "rectangle",
                      // Brush aliases
                      "brush":             "trendline",
                      "highlighter":       "rectangle",
                      // Arrow aliases
                      "arrow":             "arrowmarker",
                      // Shape aliases
                      "rotatedrectangle":  "rectangle",
                      "path":              "trendline",
                      "curve":             "extendedline",
                      "arc":               "circle",
                      "polyline":          "trendline",
                      "triangleshape":     "rectangle",
                      // Text/annotation aliases
                      "text":              "note",
                      "pricenote":         "note",
                      "pin":               "flag",
                      "callout":           "note",
                    };
                    return MAP[drawingTool] ?? "none";
                  })())}
                  chartType={chartType}
                  indicators={indicators}
                  showRSI={showRSI}
                  showMACD={showMACD}
                  isActive={panel.id === activePanelId}
                  drawings={panel.drawings}
                  onDrawingAdd={(d) => addDrawing(panel.id, d)}
                  onDrawingErase={(id) => eraseDrawing(panel.id, id)}
                  onDrawingUpdate={(id, shape) => updateDrawing(panel.id, id, shape)}
                  onClearDrawings={() => clearDrawings()}
                  onActivate={() => setActivePanelId(panel.id)}
                  onDrawingDone={() => setDrawingTool("none")}
                  theme={theme}
                />
              </div>
            ))}
          </div>

          {/* ── Bottom range bar (chart area only — clock lives here) ── */}
          <div className="relative flex items-center justify-between px-3 py-1 shrink-0" style={{ background: PT.barBg, borderTop: `1px solid ${PT.barBor}` }}>
            {/* Range buttons + calendar */}
            <div className="flex items-center gap-0.5">
              {RANGES.map(r => (
                <button
                  key={r.label}
                  onClick={() => applyRange(r)}
                  className="px-2 py-0.5 rounded text-[11px] font-medium transition-colors"
                  style={activeRange === r.label
                    ? { background: "#6366f1", color: "#ffffff" }
                    : { color: PT.iconTxt }}
                >
                  {r.label}
                </button>
              ))}
              <div className="relative ml-1">
                <button
                  onClick={() => setShowCalendar(v => !v)}
                  title="Custom date range"
                  className="flex items-center gap-1 px-2 py-0.5 rounded text-[11px] transition-colors"
                  style={activeRange === "custom"
                    ? { background: "#6366f1", color: "#ffffff" }
                    : { color: PT.iconTxt }}
                >
                  <Calendar size={12} />
                </button>
                {showCalendar && (
                  <div className="absolute bottom-full mb-2 left-0 z-50 rounded shadow-2xl p-3 flex flex-col gap-2" style={{ minWidth: 240, background: PT.dropBg, border: `1px solid ${PT.dropBor}` }}>
                    <div className="text-xs font-medium" style={{ color: PT.secTxt }}>Custom range</div>
                    <div className="flex items-center gap-2">
                      <label className="text-[11px] w-10" style={{ color: PT.secTxt }}>From</label>
                      <input
                        type="date"
                        value={calStart}
                        onChange={e => setCalStart(e.target.value)}
                        className="flex-1 bg-gray-800 text-gray-200 rounded px-2 py-0.5 text-xs border border-gray-700 focus:outline-none focus:border-indigo-500"
                      />
                    </div>
                    <div className="flex items-center gap-2">
                      <label className="text-[11px] w-10" style={{ color: PT.secTxt }}>To</label>
                      <input
                        type="date"
                        value={calEnd}
                        onChange={e => setCalEnd(e.target.value)}
                        className="flex-1 bg-gray-800 text-gray-200 rounded px-2 py-0.5 text-xs border border-gray-700 focus:outline-none focus:border-indigo-500"
                      />
                    </div>
                    <button
                      onClick={applyCustomRange}
                      disabled={!calStart || !calEnd}
                      className="mt-0.5 w-full py-1 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-white text-xs rounded transition-colors"
                    >
                      Apply
                    </button>
                  </div>
                )}
              </div>
            </div>

            {/* Live IST clock — now inside chart panel area, not watchlist */}
            <div className="flex items-center gap-2 select-none">
              <span className="font-mono text-[12px] tracking-wide tabular-nums" style={{ color: PT.itemTxt }}>{clock}</span>
              <span className="font-mono text-[12px]" style={{ color: PT.secTxt }}>UTC+5:30</span>
            </div>
          </div>
        </div>

        {/* Watchlist */}
        {showWatchlist && (
          <WatchlistPanel
            ref={watchlistRef}
            onSymbolSelect={setSymbolForActivePanel}
            activeSymbol={activePanel?.symbol ?? ""}
            onRequestAdd={() => searchRef.current?.open({ mode: "watchlist" })}
            theme={theme}
          />
        )}
      </div>

      {/* ── Symbol Search Modal (shared — chart mode or watchlist-add mode) ── */}
      <SearchModal
        ref={searchRef}
        onSelectChart={setSymbolForActivePanel}
        onSelectWatchlist={(sym) => watchlistRef.current?.addSymbol(sym)}
      />
    </div>
  );
}
