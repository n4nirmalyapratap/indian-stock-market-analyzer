import { useState, useRef, useCallback, useEffect, forwardRef, useImperativeHandle } from "react";
import {
  BarChart2, TrendingUp, Minus, Square, Eraser,
  LayoutTemplate, PanelRight, X, Search, Minus as Divider,
  ChevronDown, Crosshair, Calendar,
} from "lucide-react";
import ChartPanel, { type DrawingTool, type Drawing, type ChartType } from "@/components/trading/ChartPanel";
import WatchlistPanel from "@/components/trading/WatchlistPanel";

// ─── Symbol catalogue ────────────────────────────────────────────────────────
const SYMBOLS = [
  { symbol: "NIFTY 50",    name: "Nifty 50 Index",               type: "index"  },
  { symbol: "BANKNIFTY",   name: "Bank Nifty Index",             type: "index"  },
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

// ─── Drawing tools ───────────────────────────────────────────────────────────
const DRAW_TOOLS: { tool: DrawingTool; icon: React.ReactNode; label: string }[] = [
  { tool: "none",      icon: <Crosshair size={14} />,    label: "Cursor"    },
  { tool: "trendline", icon: <TrendingUp size={14} />,   label: "Trend Line" },
  { tool: "hline",     icon: <Minus size={14} />,        label: "H-Line"    },
  { tool: "vline",     icon: <Divider size={14} className="rotate-90" />, label: "V-Line" },
  { tool: "rectangle", icon: <Square size={14} />,       label: "Rectangle" },
  { tool: "eraser",    icon: <Eraser size={14} />,       label: "Eraser"    },
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

// ─── Symbol Search (API-backed — full universe) ───────────────────────────────
interface SearchResult { symbol: string; name: string }

export interface SymbolSearchHandle { open: (char?: string) => void }

const SymbolSearch = forwardRef<SymbolSearchHandle, { onSelect: (sym: string) => void; placeholder?: string }>(
function SymbolSearch({ onSelect, placeholder }, fwdRef) {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const debounce = useRef<ReturnType<typeof setTimeout> | null>(null);

  useImperativeHandle(fwdRef, () => ({
    open: (char?: string) => {
      if (char) {
        setQ(char);
        setOpen(true);
        handleChange(char);
      } else {
        setOpen(true);
      }
      requestAnimationFrame(() => inputRef.current?.focus());
    },
  }));

  useEffect(() => {
    function handler(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  function handleChange(val: string) {
    setQ(val);
    setOpen(true);
    if (debounce.current) clearTimeout(debounce.current);
    if (!val.trim()) { setResults([]); return; }
    debounce.current = setTimeout(async () => {
      setLoading(true);
      try {
        const res = await fetch(`/api/stocks/search?q=${encodeURIComponent(val.trim())}`);
        if (res.ok) {
          const data = await res.json();
          setResults(data.results ?? []);
        }
      } catch { setResults([]); }
      finally { setLoading(false); }
    }, 180);
  }

  const INDEX_SYMS = new Set(["NIFTY 50", "NIFTY50", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY"]);

  return (
    <div ref={ref} className="relative">
      <div className="flex items-center gap-1.5 bg-gray-800 border border-gray-700 rounded px-2 py-1 focus-within:border-indigo-500 transition-colors">
        <Search size={13} className="text-gray-500" />
        <input
          ref={inputRef}
          value={q}
          onChange={e => handleChange(e.target.value)}
          onFocus={() => { setOpen(true); if (q) handleChange(q); }}
          placeholder={placeholder ?? "Search symbol…"}
          className="bg-transparent text-white text-xs placeholder-gray-600 focus:outline-none w-36"
          onKeyDown={e => {
            if (e.key === "Enter" && results[0]) { onSelect(results[0].symbol); setQ(""); setOpen(false); }
            if (e.key === "Escape") { setOpen(false); inputRef.current?.blur(); }
          }}
        />
        {loading && <div className="w-3 h-3 border border-indigo-400 border-t-transparent rounded-full animate-spin" />}
        {q && !loading && <button onClick={() => { setQ(""); setResults([]); setOpen(false); }} className="text-gray-600 hover:text-white"><X size={11} /></button>}
      </div>
      {open && results.length > 0 && (
        <div className="absolute top-full left-0 mt-1 z-50 bg-gray-900 border border-gray-700 rounded shadow-2xl w-80 max-h-80 overflow-y-auto">
          {results.map(s => (
            <button
              key={s.symbol}
              className="w-full flex items-center gap-3 px-3 py-2 hover:bg-gray-800 text-left group"
              onClick={() => { onSelect(s.symbol); setQ(""); setResults([]); setOpen(false); }}
            >
              <div className="min-w-0 flex-1">
                <div className="text-sm font-semibold text-white group-hover:text-indigo-300">{s.symbol}</div>
                {s.name && <div className="text-xs text-gray-500 truncate">{s.name}</div>}
              </div>
              <span className={`shrink-0 text-[10px] px-1.5 py-0.5 rounded ${INDEX_SYMS.has(s.symbol) ? "bg-purple-900/50 text-purple-300" : "bg-gray-800 text-gray-400"}`}>
                {INDEX_SYMS.has(s.symbol) ? "INDEX" : "NSE"}
              </span>
            </button>
          ))}
        </div>
      )}
      {open && q.length > 0 && results.length === 0 && !loading && (
        <div className="absolute top-full left-0 mt-1 z-50 bg-gray-900 border border-gray-700 rounded shadow-2xl w-80 px-4 py-3">
          <p className="text-xs text-gray-500">No results for "{q}"</p>
        </div>
      )}
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
}: {
  chartType: ChartType;
  onSelect: (t: ChartType) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const current = CHART_TYPE_GROUPS.flatMap(g => g.items).find(i => i.type === chartType);

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
        className={`flex items-center gap-1 px-2.5 py-1 rounded text-xs font-semibold transition-colors border ${
          open
            ? "bg-indigo-600 text-white border-indigo-500"
            : "bg-gray-800/80 text-gray-200 border-gray-700 hover:border-gray-500 hover:text-white"
        }`}
      >
        <span className="font-mono text-[13px] leading-none">{current?.icon ?? "🕯"}</span>
        <ChevronDown size={11} className={`transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {open && (
        <div
          className="absolute top-full left-0 mt-1 z-50 rounded-lg shadow-2xl border border-gray-700/80 min-w-[200px]"
          style={{ background: "#1e2130" }}
        >
          <div className="px-4 pt-3 pb-2 border-b border-gray-700/60">
            <span className="text-[11px] font-semibold text-gray-400 uppercase tracking-wider">Chart Type</span>
          </div>
          <div className="p-2">
            {CHART_TYPE_GROUPS.map(({ group, items }) => (
              <div key={group} className="mb-1">
                <div className="px-2 py-1 text-[10px] font-semibold text-gray-500 uppercase tracking-wider">{group}</div>
                {items.map(item => (
                  <button
                    key={item.type}
                    onClick={() => { onSelect(item.type); setOpen(false); }}
                    className={`w-full flex items-center gap-3 px-3 py-1.5 rounded text-xs transition-colors ${
                      chartType === item.type
                        ? "bg-indigo-600 text-white"
                        : "text-gray-300 hover:bg-gray-700 hover:text-white"
                    }`}
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
}: {
  intervalIdx: number;
  onSelect: (idx: number) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const current = INTERVALS[intervalIdx];

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
        className={`flex items-center gap-1 px-2.5 py-1 rounded text-xs font-semibold transition-colors border ${
          open
            ? "bg-indigo-600 text-white border-indigo-500"
            : "bg-gray-800/80 text-gray-200 border-gray-700 hover:border-gray-500 hover:text-white"
        }`}
      >
        {current.label}
        <ChevronDown size={11} className={`transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {/* Dropdown panel */}
      {open && (
        <div
          className="absolute top-full left-0 mt-1 z-50 rounded-lg shadow-2xl border border-gray-700/80"
          style={{ background: "#1e2130", minWidth: 260 }}
        >
          {/* Header */}
          <div className="px-4 pt-3 pb-2 border-b border-gray-700/60">
            <span className="text-[11px] font-semibold text-gray-400 uppercase tracking-wider">Interval</span>
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
                  <span className="text-[11px] text-gray-500 w-14 shrink-0">{group}</span>
                  {/* Interval buttons */}
                  <div className="flex items-center gap-1 flex-wrap">
                    {items.map(({ idx, entry }) => (
                      <button
                        key={entry.label}
                        onClick={() => { onSelect(idx); setOpen(false); }}
                        className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                          idx === intervalIdx
                            ? "bg-indigo-600 text-white"
                            : "text-gray-300 hover:bg-gray-700 hover:text-white"
                        }`}
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
  const [panels, setPanels] = useState<PanelState[]>([makePanel("RELIANCE")]);
  const [activePanelId, setActivePanelId] = useState(panels[0].id);
  const [intervalIdx, setIntervalIdx] = useState(7); // default: 1D
  const [chartType, setChartType] = useState<ChartType>("candles");
  const [drawingTool, setDrawingTool] = useState<DrawingTool>("none");
  const [indicators, setIndicators] = useState<Set<string>>(new Set(["ema21"]));
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

  const searchRef = useRef<SymbolSearchHandle>(null);

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

      // Printable character (no modifier) — open symbol search like TradingView
      if (!e.ctrlKey && !e.metaKey && !e.altKey && e.key.length === 1 && !inInput) {
        searchRef.current?.open(e.key);
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [activePanelId]);

  const activePanel = panels.find(p => p.id === activePanelId) ?? panels[0];

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

  return (
    <div className="flex flex-col h-full" style={{ background: "#0f1117" }}>
      {/* ── Toolbar ─────────────────────────────────────────────────────────── */}
      <div className="flex items-center gap-2 px-3 py-1.5 border-b border-gray-800 bg-[#131722] shrink-0 flex-wrap">

        {/* Symbol search */}
        <SymbolSearch ref={searchRef} onSelect={setSymbolForActivePanel} placeholder={activePanel?.symbol ?? "Search…"} />

        {/* Interval selector — dropdown like TradingView */}
        <IntervalSelector intervalIdx={intervalIdx} onSelect={handleIntervalSelect} />

        {/* Chart type selector */}
        <ChartTypeSelector chartType={chartType} onSelect={setChartType} />

        <div className="w-px h-5 bg-gray-700" />

        {/* Drawing tools */}
        <div className="flex items-center gap-0.5 bg-gray-800/60 rounded p-0.5">
          {DRAW_TOOLS.map(({ tool, icon, label }) => (
            <button
              key={tool}
              onClick={() => setDrawingTool(t => t === tool ? "none" : tool)}
              title={label}
              className={`w-7 h-7 flex items-center justify-center rounded transition-colors ${drawingTool === tool ? "bg-indigo-600 text-white" : "text-gray-400 hover:text-white hover:bg-gray-700"}`}
            >
              {icon}
            </button>
          ))}
          <button
            onClick={clearDrawings}
            title="Clear all drawings on active chart"
            disabled={!activePanel?.drawings?.length}
            className={`text-xs px-2 py-0.5 rounded transition-colors ${activePanel?.drawings?.length ? "text-red-400 hover:text-white hover:bg-red-600/30" : "text-gray-700 cursor-not-allowed"}`}
          >
            Clear
          </button>
        </div>

        <div className="w-px h-5 bg-gray-700" />

        {/* Indicators */}
        <div className="relative">
          <button
            onClick={() => setShowIndMenu(v => !v)}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded text-xs transition-colors ${showIndMenu ? "bg-indigo-600 text-white" : "bg-gray-800 text-gray-300 hover:text-white"}`}
          >
            <BarChart2 size={13} /> Indicators
            {indicators.size > 0 && (
              <span className="bg-indigo-500 text-white text-[10px] rounded-full px-1.5 py-0.5">{indicators.size}</span>
            )}
          </button>
          {showIndMenu && (
            <div className="absolute top-full left-0 mt-1 z-50 bg-gray-900 border border-gray-700 rounded shadow-2xl p-3 w-52">
              <div className="text-[11px] text-gray-500 font-semibold mb-2">Moving Averages</div>
              {IND_OPTS.map(opt => (
                <label key={opt.key} className="flex items-center gap-2.5 py-1 cursor-pointer group">
                  <div className={`w-4 h-4 rounded border flex items-center justify-center transition-colors ${indicators.has(opt.key) ? "bg-indigo-600 border-indigo-600" : "border-gray-600 group-hover:border-gray-400"}`}>
                    {indicators.has(opt.key) && <div className="w-2 h-2 bg-white rounded-sm" />}
                  </div>
                  <input type="checkbox" checked={indicators.has(opt.key)} onChange={() => toggleIndicator(opt.key)} className="hidden" />
                  <div className="w-3 h-0.5 rounded" style={{ background: opt.color }} />
                  <span className="text-xs text-gray-300 group-hover:text-white">{opt.label}</span>
                </label>
              ))}
              <div className="border-t border-gray-700 mt-2 pt-2">
                <div className="text-[11px] text-gray-500 font-semibold mb-2">Oscillators</div>
                {[
                  { key: "rsi", label: "RSI (14)", active: showRSI, toggle: () => setShowRSI(v => !v) },
                  { key: "macd", label: "MACD (12,26,9)", active: showMACD, toggle: () => setShowMACD(v => !v) },
                ].map(opt => (
                  <label key={opt.key} className="flex items-center gap-2.5 py-1 cursor-pointer group">
                    <div
                      onClick={opt.toggle}
                      className={`w-4 h-4 rounded border flex items-center justify-center transition-colors ${opt.active ? "bg-indigo-600 border-indigo-600" : "border-gray-600 group-hover:border-gray-400"}`}
                    >
                      {opt.active && <div className="w-2 h-2 bg-white rounded-sm" />}
                    </div>
                    <span className="text-xs text-gray-300 group-hover:text-white">{opt.label}</span>
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
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded text-xs transition-colors ${showLayouts ? "bg-indigo-600 text-white" : "bg-gray-800 text-gray-300 hover:text-white"}`}
          >
            <LayoutTemplate size={13} /> Layout
          </button>
          {showLayouts && (
            <div className="absolute top-full right-0 mt-1 z-50 bg-gray-900 border border-gray-700 rounded shadow-2xl p-2 flex gap-1">
              {LAYOUTS.map(l => (
                <button
                  key={l.mode}
                  onClick={() => setLayout(l.mode)}
                  title={l.label}
                  className={`w-9 h-9 flex items-center justify-center rounded transition-colors ${layoutMode === l.mode ? "bg-indigo-600 text-white" : "text-gray-400 hover:text-white hover:bg-gray-800"}`}
                >
                  {l.icon}
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="ml-auto flex items-center gap-2">
          {/* Watchlist toggle */}
          <button
            onClick={() => setShowWatchlist(v => !v)}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded text-xs transition-colors ${showWatchlist ? "bg-indigo-600 text-white" : "bg-gray-800 text-gray-300 hover:text-white"}`}
          >
            <PanelRight size={13} /> Watchlist
          </button>
        </div>
      </div>

      {/* ── Chart area ──────────────────────────────────────────────────────── */}
      <div className="flex flex-1 min-h-0 overflow-hidden">
        {/* Charts grid */}
        <div className={`flex-1 min-w-0 ${getGridClass()} p-1 gap-1`} style={{ minHeight: 0, height: "100%" }}>
          {visiblePanels.map((panel) => (
            <div key={panel.id} className={layoutMode === "4" ? "min-h-0 min-w-0 overflow-hidden" : "flex-1 min-h-0 min-w-0 overflow-hidden"}>
              <ChartPanel
                panelId={panel.id}
                symbol={panel.symbol}
                symbolName={SYMBOLS.find(s => s.symbol === panel.symbol)?.name}
                periodCfg={customPeriodCfg ?? INTERVALS[intervalIdx]}
                drawingTool={drawingTool}
                chartType={chartType}
                indicators={indicators}
                showRSI={showRSI}
                showMACD={showMACD}
                isActive={panel.id === activePanelId}
                drawings={panel.drawings}
                onDrawingAdd={(d) => addDrawing(panel.id, d)}
                onDrawingErase={(id) => eraseDrawing(panel.id, id)}
                onClearDrawings={() => clearDrawings()}
                onActivate={() => setActivePanelId(panel.id)}
              />
            </div>
          ))}
        </div>

        {/* Watchlist */}
        {showWatchlist && (
          <WatchlistPanel
            onSymbolSelect={setSymbolForActivePanel}
            activeSymbol={activePanel?.symbol ?? ""}
          />
        )}
      </div>

      {/* ── Bottom range bar ─────────────────────────────────────────────────── */}
      <div className="relative flex items-center justify-between px-3 py-1 border-t border-gray-800 bg-[#131722] shrink-0">
        {/* Range buttons + calendar */}
        <div className="flex items-center gap-0.5">
          {RANGES.map(r => (
            <button
              key={r.label}
              onClick={() => applyRange(r)}
              className={`px-2 py-0.5 rounded text-[11px] font-medium transition-colors ${
                activeRange === r.label
                  ? "bg-indigo-600 text-white"
                  : "text-gray-400 hover:text-white hover:bg-gray-800"
              }`}
            >
              {r.label}
            </button>
          ))}
          <div className="relative ml-1">
            <button
              onClick={() => setShowCalendar(v => !v)}
              title="Custom date range"
              className={`flex items-center gap-1 px-2 py-0.5 rounded text-[11px] transition-colors ${
                activeRange === "custom"
                  ? "bg-indigo-600 text-white"
                  : "text-gray-400 hover:text-white hover:bg-gray-800"
              }`}
            >
              <Calendar size={12} />
            </button>
            {showCalendar && (
              <div className="absolute bottom-full mb-2 left-0 z-50 bg-gray-900 border border-gray-700 rounded shadow-2xl p-3 flex flex-col gap-2" style={{ minWidth: 240 }}>
                <div className="text-xs text-gray-400 font-medium">Custom range</div>
                <div className="flex items-center gap-2">
                  <label className="text-[11px] text-gray-400 w-10">From</label>
                  <input
                    type="date"
                    value={calStart}
                    onChange={e => setCalStart(e.target.value)}
                    className="flex-1 bg-gray-800 text-gray-200 rounded px-2 py-0.5 text-xs border border-gray-700 focus:outline-none focus:border-indigo-500"
                  />
                </div>
                <div className="flex items-center gap-2">
                  <label className="text-[11px] text-gray-400 w-10">To</label>
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

        {/* Live IST clock */}
        <div className="flex items-center gap-3 text-[11px] text-gray-400 font-mono select-none">
          <span className="text-gray-200">{clock}</span>
          <span>UTC+5:30</span>
        </div>
      </div>
    </div>
  );
}
