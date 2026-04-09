import { useState, useEffect, useCallback, useRef, forwardRef, useImperativeHandle } from "react";
import { Plus, Trash2, ChevronDown, Check, X, Pencil } from "lucide-react";

export interface WatchlistItem {
  symbol: string;
  price?: number;
  pChange?: number;
  company?: string;
}

export interface Watchlist {
  id: string;
  name: string;
  symbols: string[];
}

export interface WatchlistPanelHandle {
  addSymbol: (sym: string) => void;
}

interface StockDetail {
  companyName?: string;
  lastPrice?: number;
  currentPrice?: number;
  pChange?: number;
  open?: number;
  dayHigh?: number;
  dayLow?: number;
  previousClose?: number;
  volume?: number;
  fiftyTwoWeekHigh?: number;
  fiftyTwoWeekLow?: number;
  marketCap?: number;
  trailingPE?: number;
  dividendYield?: number;
}

const STORAGE_KEY = "tv_watchlists_v2";

function loadWatchlists(): Watchlist[] {
  try {
    const s = localStorage.getItem(STORAGE_KEY);
    if (s) return JSON.parse(s);
  } catch {}
  return [
    { id: "default", name: "Nifty 50", symbols: ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "SBIN", "BHARTIARTL", "KOTAKBANK", "BAJFINANCE", "AXISBANK"] },
    { id: "tech",    name: "Tech",     symbols: ["TCS", "INFY", "WIPRO", "HCLTECH", "TECHM", "LTIM"] },
  ];
}

function saveWatchlists(lists: Watchlist[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(lists));
}

function fmtVol(v: number): string {
  if (v >= 1e9) return (v / 1e9).toFixed(2) + "B";
  if (v >= 1e6) return (v / 1e6).toFixed(2) + "M";
  if (v >= 1e3) return (v / 1e3).toFixed(1) + "K";
  return String(v);
}

function fmtCrore(v: number): string {
  if (v >= 1e7) return "₹" + (v / 1e7).toFixed(2) + " Cr";
  if (v >= 1e5) return "₹" + (v / 1e5).toFixed(2) + " L";
  return "₹" + v.toLocaleString("en-IN");
}

interface Props {
  onSymbolSelect: (symbol: string) => void;
  activeSymbol: string;
  onRequestAdd: () => void;
}

const WatchlistPanel = forwardRef<WatchlistPanelHandle, Props>(
function WatchlistPanel({ onSymbolSelect, activeSymbol, onRequestAdd }, ref) {
  const [watchlists, setWatchlists]   = useState<Watchlist[]>(loadWatchlists);
  const [activeId, setActiveId]       = useState(watchlists[0]?.id ?? "default");
  const [prices, setPrices]           = useState<Record<string, WatchlistItem>>({});
  const [showMenu, setShowMenu]       = useState(false);
  const [editingId, setEditingId]     = useState<string | null>(null);
  const [editVal, setEditVal]         = useState("");
  const [newListMode, setNewListMode] = useState(false);
  const [newListName, setNewListName] = useState("");
  const [stockDetail, setStockDetail] = useState<StockDetail | null>(null);

  const menuRef     = useRef<HTMLDivElement>(null);
  const fetchGenRef = useRef(0);

  const activeWL = watchlists.find(w => w.id === activeId) ?? watchlists[0];

  // Expose addSymbol to parent via ref
  useImperativeHandle(ref, () => ({
    addSymbol: (sym: string) => {
      const upper = sym.trim().toUpperCase();
      if (!upper || !activeWL) return;
      setWatchlists(prev => {
        const updated = prev.map(w =>
          w.id === activeId && !w.symbols.includes(upper)
            ? { ...w, symbols: [...w.symbols, upper] }
            : w
        );
        saveWatchlists(updated);
        return updated;
      });
      const gen = ++fetchGenRef.current;
      fetchPrices([upper], gen);
    },
  }));

  // Close dropdown on outside click
  useEffect(() => {
    if (!showMenu) return;
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setShowMenu(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [showMenu]);

  const fetchPrices = useCallback(async (symbols: string[], gen: number) => {
    for (const sym of symbols) {
      if (fetchGenRef.current !== gen) return;
      try {
        const r = await fetch(`/api/stocks/${sym}`);
        if (fetchGenRef.current !== gen) return;
        if (!r.ok) continue;
        const d = await r.json();
        if (fetchGenRef.current !== gen) return;
        setPrices(prev => ({
          ...prev,
          [sym]: { symbol: sym, price: d.lastPrice ?? d.currentPrice, pChange: d.pChange, company: d.companyName ?? sym },
        }));
      } catch {}
      await new Promise(r => setTimeout(r, 120));
    }
  }, []);

  useEffect(() => {
    if (!activeWL) return;
    const gen = ++fetchGenRef.current;
    fetchPrices(activeWL.symbols, gen);
  }, [activeWL?.id, activeWL?.symbols.join(",")]);

  // Fetch stock details for the active symbol (updates whenever chart symbol changes)
  useEffect(() => {
    if (!activeSymbol) return;
    let cancelled = false;
    fetch(`/api/stocks/${activeSymbol}`)
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (!cancelled && d) setStockDetail(d); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [activeSymbol]);

  function save(lists: Watchlist[]) { setWatchlists(lists); saveWatchlists(lists); }

  function removeSymbol(sym: string) {
    save(watchlists.map(w => w.id === activeWL?.id ? { ...w, symbols: w.symbols.filter(s => s !== sym) } : w));
  }

  function createList() {
    const name = newListName.trim() || `List ${watchlists.length + 1}`;
    const wl: Watchlist = { id: Date.now().toString(), name, symbols: [] };
    save([...watchlists, wl]);
    setActiveId(wl.id);
    setNewListName(""); setNewListMode(false); setShowMenu(false);
  }

  function deleteList(id: string) {
    const updated = watchlists.filter(w => w.id !== id);
    save(updated);
    if (activeId === id) setActiveId(updated[0]?.id ?? "");
  }

  function renameList() {
    if (!editingId) return;
    save(watchlists.map(w => w.id === editingId ? { ...w, name: editVal.trim() || w.name } : w));
    setEditingId(null);
  }

  const detailPrice = stockDetail?.lastPrice ?? stockDetail?.currentPrice;
  const detailChange = stockDetail?.pChange;
  const detailUp = (detailChange ?? 0) >= 0;
  const detailColor = detailUp ? "#26a69a" : "#ef5350";

  const detailRows: [string, string | undefined][] = [
    ["Open",       stockDetail?.open != null ? `₹${stockDetail.open.toFixed(2)}` : undefined],
    ["High",       stockDetail?.dayHigh != null ? `₹${stockDetail.dayHigh.toFixed(2)}` : undefined],
    ["Low",        stockDetail?.dayLow != null ? `₹${stockDetail.dayLow.toFixed(2)}` : undefined],
    ["Prev Close", stockDetail?.previousClose != null ? `₹${stockDetail.previousClose.toFixed(2)}` : undefined],
    ["52W High",   stockDetail?.fiftyTwoWeekHigh != null ? `₹${stockDetail.fiftyTwoWeekHigh.toFixed(2)}` : undefined],
    ["52W Low",    stockDetail?.fiftyTwoWeekLow != null ? `₹${stockDetail.fiftyTwoWeekLow.toFixed(2)}` : undefined],
    ["Volume",     stockDetail?.volume != null ? fmtVol(stockDetail.volume) : undefined],
    ["Mkt Cap",    stockDetail?.marketCap != null ? fmtCrore(stockDetail.marketCap) : undefined],
    ["P/E",        stockDetail?.trailingPE != null ? stockDetail.trailingPE.toFixed(2) : undefined],
    ["Div Yield",  stockDetail?.dividendYield != null ? (stockDetail.dividendYield * 100).toFixed(2) + "%" : undefined],
  ].filter(([, v]) => v !== undefined) as [string, string][];

  return (
    <div
      className="flex flex-col h-full select-none"
      style={{ width: 220, background: "#0f1117", borderLeft: "1px solid #1e2130" }}
    >

      {/* ── Header: watchlist name + + button ── */}
      <div className="relative shrink-0" ref={menuRef}>
        <div className="flex items-center px-1 py-1 gap-0.5">
          <button
            onClick={() => setShowMenu(v => !v)}
            className="flex items-center gap-1.5 flex-1 min-w-0 px-3 py-2 rounded hover:bg-white/5 transition-colors text-left"
          >
            {editingId === activeId ? (
              <input
                autoFocus
                value={editVal}
                onChange={e => setEditVal(e.target.value)}
                onKeyDown={e => { if (e.key === "Enter") renameList(); if (e.key === "Escape") setEditingId(null); }}
                onClick={e => e.stopPropagation()}
                className="flex-1 bg-white/10 text-white text-sm rounded px-2 py-0.5 focus:outline-none"
              />
            ) : (
              <>
                <span className="flex-1 text-sm font-semibold text-white truncate">{activeWL?.name ?? "Watchlist"}</span>
                <ChevronDown size={12} className={`text-gray-500 shrink-0 transition-transform ${showMenu ? "rotate-180" : ""}`} />
              </>
            )}
          </button>

          {/* + button — opens the search modal in watchlist-add mode */}
          <button
            onClick={onRequestAdd}
            title="Add symbol to watchlist"
            className="shrink-0 w-7 h-7 flex items-center justify-center rounded text-gray-500 hover:text-white hover:bg-white/8 transition-colors"
          >
            <Plus size={15} />
          </button>
        </div>

        {/* Dropdown */}
        {showMenu && (
          <div className="absolute top-full left-0 right-0 z-50 py-1 rounded-b-lg shadow-2xl" style={{ background: "#1a1d27", border: "1px solid rgba(255,255,255,0.08)", borderTop: "none" }}>
            {watchlists.map(wl => (
              <div
                key={wl.id}
                onClick={() => { setActiveId(wl.id); setShowMenu(false); setNewListMode(false); }}
                className={`flex items-center gap-2 px-4 py-2 cursor-pointer text-xs transition-colors ${wl.id === activeId ? "text-indigo-400 bg-indigo-500/10" : "text-gray-400 hover:bg-white/5 hover:text-white"}`}
              >
                <span className="flex-1 truncate">{wl.name}</span>
                <button
                  onClick={e => { e.stopPropagation(); setEditingId(wl.id); setEditVal(wl.name); setShowMenu(false); }}
                  className="text-gray-600 hover:text-white p-0.5 rounded"
                >
                  <Pencil size={10} />
                </button>
                {watchlists.length > 1 && (
                  <button
                    onClick={e => { e.stopPropagation(); deleteList(wl.id); }}
                    className="text-gray-600 hover:text-red-400 p-0.5 rounded"
                  >
                    <Trash2 size={10} />
                  </button>
                )}
              </div>
            ))}

            <div className="mx-3 my-1" style={{ height: 1, background: "rgba(255,255,255,0.07)" }} />

            {newListMode ? (
              <div className="flex items-center gap-1 px-3 py-1.5">
                <input
                  autoFocus
                  value={newListName}
                  onChange={e => setNewListName(e.target.value)}
                  onKeyDown={e => { if (e.key === "Enter") createList(); if (e.key === "Escape") setNewListMode(false); }}
                  placeholder="List name…"
                  className="flex-1 bg-white/10 text-white text-xs rounded px-2 py-1 focus:outline-none placeholder-gray-600 min-w-0"
                />
                <button onClick={createList} className="text-green-400 hover:text-green-300 p-0.5"><Check size={12} /></button>
                <button onClick={() => setNewListMode(false)} className="text-gray-500 hover:text-white p-0.5"><X size={12} /></button>
              </div>
            ) : (
              <button
                onClick={e => { e.stopPropagation(); setNewListMode(true); }}
                className="flex items-center gap-2 w-full px-4 py-2 text-xs text-indigo-400 hover:text-indigo-300 hover:bg-white/5 transition-colors"
              >
                <Plus size={11} /> New watchlist
              </button>
            )}
          </div>
        )}
      </div>

      {/* ── Symbol list ── */}
      <div className="flex-1 overflow-y-auto" style={{ scrollbarWidth: "none" }}>
        {activeWL?.symbols.map((sym, idx) => {
          const info  = prices[sym];
          const up    = (info?.pChange ?? 0) >= 0;
          const isOn  = sym === activeSymbol;
          return (
            <div
              key={sym}
              onClick={() => onSymbolSelect(sym)}
              className="group relative flex items-center gap-3 px-4 cursor-pointer transition-colors"
              style={{
                paddingTop: 9, paddingBottom: 9,
                background: isOn ? "rgba(99,102,241,0.12)" : undefined,
                borderBottom: idx < (activeWL?.symbols.length ?? 0) - 1 ? "1px solid rgba(255,255,255,0.04)" : "none",
              }}
              onMouseEnter={e => { if (!isOn) (e.currentTarget as HTMLElement).style.background = "rgba(255,255,255,0.04)"; }}
              onMouseLeave={e => { if (!isOn) (e.currentTarget as HTMLElement).style.background = ""; }}
            >
              {isOn && <div className="absolute left-0 top-2 bottom-2 w-[2px] rounded-r" style={{ background: "#6366f1" }} />}

              <div className="flex-1 min-w-0">
                <div className="text-xs font-semibold text-white truncate">{sym}</div>
                {info?.company && (
                  <div className="text-[10px] truncate mt-0.5" style={{ color: "#4b5563" }}>{info.company}</div>
                )}
              </div>

              <div className="text-right shrink-0">
                {info?.price != null ? (
                  <>
                    <div className="text-xs text-white font-medium">
                      ₹{info.price.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </div>
                    <div className={`text-[10px] font-medium mt-0.5 ${up ? "text-emerald-400" : "text-red-400"}`}>
                      {up ? "+" : ""}{info.pChange?.toFixed(2)}%
                    </div>
                  </>
                ) : (
                  <div className="text-[11px]" style={{ color: "#374151" }}>—</div>
                )}
              </div>

              <button
                onClick={e => { e.stopPropagation(); removeSymbol(sym); }}
                className="absolute right-1 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 transition-opacity p-1 rounded text-gray-600 hover:text-red-400"
              >
                <X size={10} />
              </button>
            </div>
          );
        })}
      </div>

      {/* ── Stock details panel ── */}
      {stockDetail && detailRows.length > 0 && (
        <div className="shrink-0 overflow-y-auto" style={{ maxHeight: 200, borderTop: "1px solid rgba(255,255,255,0.07)", scrollbarWidth: "none" }}>
          <div className="px-4 pt-3 pb-1">
            <div className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider mb-2">
              {activeSymbol} Details
            </div>
            {detailPrice != null && (
              <div className="flex items-baseline gap-1.5 mb-2">
                <span className="text-sm font-bold" style={{ color: detailColor }}>
                  ₹{detailPrice.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </span>
                {detailChange != null && (
                  <span className="text-[11px] font-medium" style={{ color: detailColor }}>
                    {detailUp ? "+" : ""}{detailChange.toFixed(2)}%
                  </span>
                )}
              </div>
            )}
            <div className="flex flex-col gap-[5px]">
              {detailRows.map(([label, value]) => (
                <div key={label} className="flex items-center justify-between gap-2">
                  <span className="text-[10px] text-gray-500 shrink-0">{label}</span>
                  <span className="text-[10px] text-gray-300 text-right truncate">{value}</span>
                </div>
              ))}
            </div>
          </div>
          <div className="pb-2" />
        </div>
      )}
    </div>
  );
});

export default WatchlistPanel;
