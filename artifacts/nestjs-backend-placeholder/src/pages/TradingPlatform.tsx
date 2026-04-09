import { useState, useRef, useCallback, useEffect } from "react";
import {
  BarChart2, TrendingUp, Minus, Square, Eraser, RefreshCw,
  LayoutTemplate, PanelRight, X, Search, Minus as Divider,
  ChevronLeft, ChevronRight, Crosshair,
} from "lucide-react";
import ChartPanel, { type DrawingTool, type Drawing } from "@/components/trading/ChartPanel";
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

// ─── Period configs ──────────────────────────────────────────────────────────
const PERIODS = [
  { label: "1D",  p: "1d",  i: "5m"  },
  { label: "1W",  p: "5d",  i: "15m" },
  { label: "1M",  p: "1mo", i: "1d"  },
  { label: "3M",  p: "3mo", i: "1d"  },
  { label: "6M",  p: "6mo", i: "1d"  },
  { label: "1Y",  p: "1y",  i: "1wk" },
  { label: "2Y",  p: "2y",  i: "1wk" },
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

// ─── Symbol Search ────────────────────────────────────────────────────────────
function SymbolSearch({ onSelect, placeholder }: { onSelect: (sym: string) => void; placeholder?: string }) {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const filtered = q.length > 0
    ? SYMBOLS.filter(s =>
        s.symbol.includes(q.toUpperCase()) || s.name.toLowerCase().includes(q.toLowerCase())
      ).slice(0, 10)
    : [];

  useEffect(() => {
    function handler(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  return (
    <div ref={ref} className="relative">
      <div className="flex items-center gap-1.5 bg-gray-800 border border-gray-700 rounded px-2 py-1 focus-within:border-indigo-500 transition-colors">
        <Search size={13} className="text-gray-500" />
        <input
          value={q}
          onChange={e => { setQ(e.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)}
          placeholder={placeholder ?? "Search symbol…"}
          className="bg-transparent text-white text-xs placeholder-gray-600 focus:outline-none w-36"
          onKeyDown={e => {
            if (e.key === "Enter" && filtered[0]) { onSelect(filtered[0].symbol); setQ(""); setOpen(false); }
            if (e.key === "Escape") setOpen(false);
          }}
        />
        {q && <button onClick={() => { setQ(""); setOpen(false); }} className="text-gray-600 hover:text-white"><X size={11} /></button>}
      </div>
      {open && filtered.length > 0 && (
        <div className="absolute top-full left-0 mt-1 z-50 bg-gray-900 border border-gray-700 rounded shadow-2xl w-72 max-h-72 overflow-y-auto">
          {filtered.map(s => (
            <button
              key={s.symbol}
              className="w-full flex items-center gap-3 px-3 py-2 hover:bg-gray-800 text-left group"
              onClick={() => { onSelect(s.symbol); setQ(""); setOpen(false); }}
            >
              <div>
                <div className="text-sm font-semibold text-white group-hover:text-indigo-300">{s.symbol}</div>
                <div className="text-xs text-gray-500">{s.name}</div>
              </div>
              <span className={`ml-auto text-[10px] px-1.5 py-0.5 rounded ${s.type === "index" ? "bg-purple-900/50 text-purple-300" : "bg-gray-800 text-gray-400"}`}>
                {s.type === "index" ? "INDEX" : "NSE"}
              </span>
            </button>
          ))}
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
  const [periodIdx, setPeriodIdx] = useState(2);
  const [drawingTool, setDrawingTool] = useState<DrawingTool>("none");
  const [indicators, setIndicators] = useState<Set<string>>(new Set(["ema21"]));
  const [showRSI, setShowRSI] = useState(false);
  const [showMACD, setShowMACD] = useState(false);
  const [showWatchlist, setShowWatchlist] = useState(true);
  const [showLayouts, setShowLayouts] = useState(false);
  const [showIndMenu, setShowIndMenu] = useState(false);

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
        <SymbolSearch onSelect={setSymbolForActivePanel} placeholder={activePanel?.symbol ?? "Search…"} />

        {/* Period selector */}
        <div className="flex items-center gap-0.5 bg-gray-800/60 rounded p-0.5">
          {PERIODS.map((p, i) => (
            <button
              key={p.label}
              onClick={() => setPeriodIdx(i)}
              className={`px-2 py-0.5 text-xs rounded transition-colors ${i === periodIdx ? "bg-indigo-600 text-white" : "text-gray-400 hover:text-white"}`}
            >
              {p.label}
            </button>
          ))}
        </div>

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
          {activePanel?.drawings?.length > 0 && (
            <button onClick={clearDrawings} title="Clear all drawings" className="text-xs text-red-400 hover:text-red-300 px-2">
              Clear
            </button>
          )}
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
                periodCfg={PERIODS[periodIdx]}
                drawingTool={drawingTool}
                indicators={indicators}
                showRSI={showRSI}
                showMACD={showMACD}
                isActive={panel.id === activePanelId}
                drawings={panel.drawings}
                onDrawingAdd={(d) => addDrawing(panel.id, d)}
                onDrawingErase={(id) => eraseDrawing(panel.id, id)}
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
    </div>
  );
}
