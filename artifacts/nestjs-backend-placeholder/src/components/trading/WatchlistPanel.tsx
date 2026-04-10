import { useState, useEffect, useCallback, useRef, forwardRef, useImperativeHandle } from "react";
import { Plus, Trash2, ChevronDown, Check, X, Pencil, Star } from "lucide-react";

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

const STORAGE_KEY = "tv_watchlists_v3";

function loadWatchlists(): Watchlist[] {
  try {
    const s = localStorage.getItem(STORAGE_KEY);
    if (s) return JSON.parse(s);
    // migrate from v2
    const old = localStorage.getItem("tv_watchlists_v2");
    if (old) return JSON.parse(old);
  } catch {}
  return [
    { id: "default", name: "Nifty 50",  symbols: ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "SBIN", "BHARTIARTL", "KOTAKBANK", "BAJFINANCE", "AXISBANK"] },
    { id: "tech",    name: "Tech Pack", symbols: ["TCS", "INFY", "WIPRO", "HCLTECH", "TECHM", "LTIM"] },
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
  theme: "dark" | "light";
}

const WatchlistPanel = forwardRef<WatchlistPanelHandle, Props>(
function WatchlistPanel({ onSymbolSelect, activeSymbol, onRequestAdd, theme }, ref) {
  const d = theme === "dark";

  const C = {
    bg:        d ? "#0d1117"                 : "#f0f3fa",
    panelBor:  d ? "rgba(255,255,255,0.07)" : "#d1d5db",
    hdrBg:     d ? "#131720"                : "#e8ecf5",
    hdrBor:    d ? "rgba(255,255,255,0.06)" : "#d1d5db",
    dropBg:    d ? "#1a1e2e"                : "#ffffff",
    dropBor:   d ? "rgba(255,255,255,0.10)" : "#d1d5db",
    itemBor:   d ? "rgba(255,255,255,0.04)" : "rgba(0,0,0,0.05)",
    itemHov:   d ? "rgba(255,255,255,0.05)" : "rgba(0,0,0,0.04)",
    activeRow: d ? "rgba(99,102,241,0.12)"  : "rgba(99,102,241,0.08)",
    sym:       d ? "#f0f2f8"                : "#131722",
    co:        d ? "#5b6678"                : "#94a3b8",
    muted:     d ? "#4b5563"                : "#94a3b8",
    inp:       d ? "rgba(255,255,255,0.08)" : "rgba(0,0,0,0.07)",
    inpTxt:    d ? "#f0f2f8"                : "#131722",
    divider:   d ? "rgba(255,255,255,0.06)" : "rgba(0,0,0,0.08)",
    detTopBor: d ? "rgba(255,255,255,0.15)" : "rgba(0,0,0,0.15)",
    detBg:     d ? "#0b0f1a"                : "#e8ecf5",
    detVal:    d ? "#d1d4dc"                : "#374151",
    detLbl:    d ? "#4b5563"                : "#9ca3af",
    badge:     d ? "rgba(255,255,255,0.06)" : "rgba(0,0,0,0.06)",
  };

  const [watchlists, setWatchlists]   = useState<Watchlist[]>(loadWatchlists);
  const [activeId, setActiveId]       = useState(watchlists[0]?.id ?? "default");
  const [prices, setPrices]           = useState<Record<string, WatchlistItem>>({});
  const [showMenu, setShowMenu]       = useState(false);
  const [editingId, setEditingId]     = useState<string | null>(null);
  const [editVal, setEditVal]         = useState("");
  const [newListMode, setNewListMode] = useState(false);
  const [newListName, setNewListName] = useState("");
  const [stockDetail, setStockDetail] = useState<StockDetail | null>(null);
  const [addedFlash, setAddedFlash]   = useState<string | null>(null);

  const menuRef     = useRef<HTMLDivElement>(null);
  const fetchGenRef = useRef(0);

  const activeWL = watchlists.find(w => w.id === activeId) ?? watchlists[0];

  useImperativeHandle(ref, () => ({
    addSymbol: (sym: string) => {
      const upper = sym.trim().toUpperCase();
      if (!upper || !activeWL) return;
      let alreadyExists = false;
      setWatchlists(prev => {
        const wl = prev.find(w => w.id === activeId);
        if (wl?.symbols.includes(upper)) { alreadyExists = true; return prev; }
        const updated = prev.map(w =>
          w.id === activeId ? { ...w, symbols: [...w.symbols, upper] } : w
        );
        saveWatchlists(updated);
        return updated;
      });
      if (!alreadyExists) {
        const gen = ++fetchGenRef.current;
        fetchSingle(upper, gen);
      }
      // flash feedback
      setAddedFlash(upper);
      setTimeout(() => setAddedFlash(null), 1800);
    },
  }));

  // Close dropdown on outside click
  useEffect(() => {
    if (!showMenu) return;
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setShowMenu(false);
        setEditingId(null);
        setNewListMode(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [showMenu]);

  const fetchSingle = useCallback(async (sym: string, gen: number) => {
    try {
      const r = await fetch(`/api/stocks/${sym}`);
      if (fetchGenRef.current !== gen || !r.ok) return;
      const data = await r.json();
      if (fetchGenRef.current !== gen) return;
      setPrices(prev => ({
        ...prev,
        [sym]: { symbol: sym, price: data.lastPrice ?? data.currentPrice, pChange: data.pChange, company: data.companyName ?? sym },
      }));
    } catch {}
  }, []);

  // Parallel batch loader — 5 at a time, no artificial delay
  const fetchPrices = useCallback(async (symbols: string[], gen: number) => {
    const BATCH = 5;
    for (let i = 0; i < symbols.length; i += BATCH) {
      if (fetchGenRef.current !== gen) return;
      const batch = symbols.slice(i, i + BATCH);
      await Promise.all(batch.map(sym => fetchSingle(sym, gen)));
    }
  }, [fetchSingle]);

  useEffect(() => {
    if (!activeWL) return;
    const gen = ++fetchGenRef.current;
    fetchPrices(activeWL.symbols, gen);
  }, [activeWL?.id, activeWL?.symbols.join(",")]);

  // Fetch stock details for the symbol currently on the chart
  useEffect(() => {
    if (!activeSymbol) return;
    let cancelled = false;
    setStockDetail(null);
    fetch(`/api/stocks/${activeSymbol}`)
      .then(r => r.ok ? r.json() : null)
      .then(data => { if (!cancelled && data) setStockDetail(data); })
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
    setEditingId(null);
  }

  function saveRename(id: string) {
    if (!editVal.trim()) { setEditingId(null); return; }
    save(watchlists.map(w => w.id === id ? { ...w, name: editVal.trim() } : w));
    setEditingId(null);
  }

  const detailPrice  = stockDetail?.lastPrice ?? stockDetail?.currentPrice;
  const detailChange = stockDetail?.pChange;
  const detailUp     = (detailChange ?? 0) >= 0;
  const detailColor  = detailUp ? "#26a69a" : "#ef5350";

  const detailRows: [string, string][] = ([
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
  ] as [string, string | undefined][]).filter(([, v]) => v !== undefined) as [string, string][];

  return (
    <div
      className="flex flex-col h-full select-none"
      style={{ width: 230, background: C.bg, borderLeft: `1px solid ${C.panelBor}` }}
    >

      {/* ── Header ── */}
      <div className="relative shrink-0" ref={menuRef} style={{ background: C.hdrBg, borderBottom: `1px solid ${C.hdrBor}` }}>
        <div className="flex items-center gap-0.5 px-2 py-2">
          <button
            onClick={() => { setShowMenu(v => !v); if (showMenu) { setEditingId(null); setNewListMode(false); } }}
            className="flex items-center gap-2 flex-1 min-w-0 px-2 py-1.5 rounded-lg transition-colors text-left"
            onMouseEnter={e => (e.currentTarget.style.background = C.itemHov)}
            onMouseLeave={e => (e.currentTarget.style.background = "")}
          >
            <Star size={12} style={{ color: "#6366f1", fill: "#6366f1" }} className="shrink-0" />
            <span className="flex-1 text-[13px] font-semibold truncate" style={{ color: C.sym }}>
              {activeWL?.name ?? "Watchlist"}
            </span>
            <span
              className="text-[10px] font-medium px-1.5 py-0.5 rounded-full shrink-0"
              style={{ background: C.badge, color: C.muted }}
            >
              {activeWL?.symbols.length ?? 0}
            </span>
            <ChevronDown size={11} className={`shrink-0 transition-transform ${showMenu ? "rotate-180" : ""}`} style={{ color: C.muted }} />
          </button>

          <button
            onClick={onRequestAdd}
            title="Add symbol (or Alt+W to add chart symbol)"
            className="shrink-0 w-7 h-7 flex items-center justify-center rounded-lg transition-colors"
            style={{ color: C.muted }}
            onMouseEnter={e => { (e.currentTarget as HTMLElement).style.color = "#6366f1"; (e.currentTarget as HTMLElement).style.background = "rgba(99,102,241,0.12)"; }}
            onMouseLeave={e => { (e.currentTarget as HTMLElement).style.color = C.muted; (e.currentTarget as HTMLElement).style.background = ""; }}
          >
            <Plus size={15} />
          </button>
        </div>

        {/* ── Dropdown ── */}
        {showMenu && (
          <div
            className="absolute top-full left-0 right-0 z-50 py-1.5 shadow-2xl rounded-b-xl"
            style={{ background: C.dropBg, border: `1px solid ${C.dropBor}`, borderTop: "none" }}
          >
            {watchlists.map(wl => (
              <div key={wl.id}>
                {editingId === wl.id ? (
                  /* ── Rename row ── */
                  <div
                    className="flex items-center gap-1.5 px-3 py-1.5"
                    onClick={e => e.stopPropagation()}
                  >
                    <input
                      autoFocus
                      value={editVal}
                      onChange={e => setEditVal(e.target.value)}
                      onKeyDown={e => {
                        if (e.key === "Enter") saveRename(wl.id);
                        if (e.key === "Escape") setEditingId(null);
                      }}
                      className="flex-1 text-xs rounded-lg px-2 py-1.5 focus:outline-none min-w-0"
                      style={{ background: C.inp, color: C.inpTxt, border: "1px solid rgba(99,102,241,0.4)" }}
                    />
                    <button
                      onClick={() => saveRename(wl.id)}
                      title="Save"
                      className="w-6 h-6 flex items-center justify-center rounded-lg transition-colors text-emerald-400 hover:text-emerald-300 hover:bg-emerald-400/10 shrink-0"
                    >
                      <Check size={12} />
                    </button>
                    <button
                      onClick={() => setEditingId(null)}
                      title="Cancel"
                      className="w-6 h-6 flex items-center justify-center rounded-lg transition-colors hover:bg-white/5 shrink-0"
                      style={{ color: C.muted }}
                    >
                      <X size={12} />
                    </button>
                  </div>
                ) : (
                  /* ── Normal row ── */
                  <div
                    className="group flex items-center gap-2 px-3 py-2 cursor-pointer transition-colors"
                    style={wl.id === activeId
                      ? { color: "#818cf8", background: "rgba(99,102,241,0.1)" }
                      : { color: C.muted }}
                    onClick={() => { setActiveId(wl.id); setShowMenu(false); setNewListMode(false); setEditingId(null); }}
                    onMouseEnter={e => { if (wl.id !== activeId) (e.currentTarget as HTMLElement).style.background = C.itemHov; }}
                    onMouseLeave={e => { if (wl.id !== activeId) (e.currentTarget as HTMLElement).style.background = ""; }}
                  >
                    <Star size={10} className="shrink-0"
                      style={wl.id === activeId ? { color: "#6366f1", fill: "#6366f1" } : { color: C.muted }} />
                    <span className="flex-1 text-xs font-medium truncate">{wl.name}</span>
                    <span className="text-[10px] opacity-60 shrink-0">{wl.symbols.length}</span>
                    <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button
                        onClick={e => { e.stopPropagation(); setEditingId(wl.id); setEditVal(wl.name); }}
                        title="Rename"
                        className="w-5 h-5 flex items-center justify-center rounded transition-colors hover:text-indigo-400"
                        style={{ color: C.muted }}
                      >
                        <Pencil size={9} />
                      </button>
                      {watchlists.length > 1 && (
                        <button
                          onClick={e => { e.stopPropagation(); deleteList(wl.id); }}
                          title="Delete list"
                          className="w-5 h-5 flex items-center justify-center rounded transition-colors hover:text-red-400"
                          style={{ color: C.muted }}
                        >
                          <Trash2 size={9} />
                        </button>
                      )}
                    </div>
                  </div>
                )}
              </div>
            ))}

            <div className="mx-3 my-1" style={{ height: 1, background: C.divider }} />

            {newListMode ? (
              <div className="flex items-center gap-1.5 px-3 py-1.5">
                <input
                  autoFocus
                  value={newListName}
                  onChange={e => setNewListName(e.target.value)}
                  onKeyDown={e => { if (e.key === "Enter") createList(); if (e.key === "Escape") setNewListMode(false); }}
                  placeholder="List name…"
                  className="flex-1 text-xs rounded-lg px-2 py-1.5 focus:outline-none min-w-0"
                  style={{ background: C.inp, color: C.inpTxt, border: "1px solid rgba(99,102,241,0.4)" }}
                />
                <button onClick={createList} className="w-6 h-6 flex items-center justify-center rounded-lg text-emerald-400 hover:text-emerald-300 hover:bg-emerald-400/10 shrink-0 transition-colors">
                  <Check size={12} />
                </button>
                <button onClick={() => setNewListMode(false)} className="w-6 h-6 flex items-center justify-center rounded-lg hover:bg-white/5 shrink-0 transition-colors" style={{ color: C.muted }}>
                  <X size={12} />
                </button>
              </div>
            ) : (
              <button
                onClick={e => { e.stopPropagation(); setNewListMode(true); setEditingId(null); }}
                className="flex items-center gap-2 w-full px-4 py-2 text-xs transition-colors"
                style={{ color: "#818cf8" }}
                onMouseEnter={e => (e.currentTarget.style.background = "rgba(99,102,241,0.08)")}
                onMouseLeave={e => (e.currentTarget.style.background = "")}
              >
                <Plus size={11} /> New watchlist
              </button>
            )}
          </div>
        )}
      </div>

      {/* ── Flash banner (Alt+W added) ── */}
      {addedFlash && (
        <div
          className="shrink-0 flex items-center justify-center gap-1.5 py-1.5 text-[11px] font-medium transition-all"
          style={{ background: "rgba(99,102,241,0.15)", color: "#a5b4fc", borderBottom: `1px solid rgba(99,102,241,0.2)` }}
        >
          <Check size={11} /> {addedFlash} added to {activeWL?.name}
        </div>
      )}

      {/* ── Symbol list ── */}
      <div className="flex-1 overflow-y-auto" style={{ scrollbarWidth: "none" }}>
        {activeWL?.symbols.map((sym, idx) => {
          const info = prices[sym];
          const up   = (info?.pChange ?? 0) >= 0;
          const isOn = sym === activeSymbol;
          const pct  = info?.pChange;

          return (
            <div
              key={sym}
              onClick={() => onSymbolSelect(sym)}
              className="group relative flex items-center gap-2 px-3 cursor-pointer transition-colors"
              style={{
                paddingTop: 8, paddingBottom: 8,
                background: isOn ? C.activeRow : undefined,
                borderBottom: idx < (activeWL?.symbols.length ?? 0) - 1 ? `1px solid ${C.itemBor}` : "none",
              }}
              onMouseEnter={e => { if (!isOn) (e.currentTarget as HTMLElement).style.background = C.itemHov; }}
              onMouseLeave={e => { if (!isOn) (e.currentTarget as HTMLElement).style.background = ""; }}
            >
              {/* Active indicator stripe */}
              {isOn && <div className="absolute left-0 top-2 bottom-2 w-[2px] rounded-r" style={{ background: "#6366f1" }} />}

              {/* Symbol + company */}
              <div className="flex-1 min-w-0">
                <div className="text-[12px] font-semibold leading-tight truncate" style={{ color: C.sym }}>{sym}</div>
                {info?.company && (
                  <div className="text-[10px] leading-tight truncate mt-0.5" style={{ color: C.co }}>
                    {info.company}
                  </div>
                )}
                {!info && (
                  <div className="text-[10px] mt-0.5 animate-pulse" style={{ color: C.muted }}>Loading…</div>
                )}
              </div>

              {/* Price + % change pill */}
              <div className="text-right shrink-0 flex flex-col items-end gap-0.5">
                {info?.price != null ? (
                  <>
                    <div className="text-[12px] font-semibold leading-tight" style={{ color: C.sym }}>
                      ₹{info.price.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </div>
                    {pct != null && (
                      <div
                        className="text-[10px] font-semibold px-1.5 py-0.5 rounded-full leading-none"
                        style={{
                          background: up ? "rgba(38,166,154,0.15)" : "rgba(239,83,80,0.15)",
                          color:      up ? "#26a69a"               : "#ef5350",
                        }}
                      >
                        {up ? "+" : ""}{pct.toFixed(2)}%
                      </div>
                    )}
                  </>
                ) : (
                  <div className="w-12 h-4 rounded animate-pulse" style={{ background: C.badge }} />
                )}
              </div>

              {/* Remove button */}
              <button
                onClick={e => { e.stopPropagation(); removeSymbol(sym); }}
                className="absolute right-1 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 transition-opacity w-5 h-5 flex items-center justify-center rounded-md hover:text-red-400"
                style={{ color: C.muted, background: d ? "rgba(15,17,23,0.9)" : "rgba(240,243,250,0.95)" }}
              >
                <X size={10} />
              </button>
            </div>
          );
        })}

        {activeWL?.symbols.length === 0 && (
          <div className="flex flex-col items-center justify-center py-10 px-4 gap-2">
            <Star size={24} style={{ color: C.muted }} />
            <p className="text-xs text-center" style={{ color: C.muted }}>
              No stocks yet.<br />Click <strong>+</strong> or press <kbd className="px-1 py-0.5 rounded text-[10px]" style={{ background: C.badge }}>Alt+W</kbd> to add.
            </p>
          </div>
        )}
      </div>

      {/* ── Divider between list and details ── */}
      {stockDetail && detailRows.length > 0 && (
        <div style={{ height: 2, background: d ? "rgba(99,102,241,0.35)" : "rgba(99,102,241,0.25)", flexShrink: 0 }} />
      )}

      {/* ── Stock details panel ── */}
      {stockDetail && detailRows.length > 0 && (
        <div
          className="shrink-0 overflow-y-auto"
          style={{ maxHeight: 210, background: C.detBg, scrollbarWidth: "none" }}
        >
          <div className="px-3 pt-3 pb-1">
            {/* Symbol label */}
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-[10px] font-bold uppercase tracking-widest" style={{ color: "#6366f1" }}>
                {activeSymbol}
              </span>
              {stockDetail.companyName && (
                <span className="text-[9px] truncate ml-2 max-w-[100px]" style={{ color: C.detLbl }}>
                  {stockDetail.companyName}
                </span>
              )}
            </div>

            {/* Price + change */}
            {detailPrice != null && (
              <div className="flex items-baseline gap-2 mb-2.5">
                <span className="text-base font-bold" style={{ color: detailColor }}>
                  ₹{detailPrice.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </span>
                {detailChange != null && (
                  <span
                    className="text-[11px] font-semibold px-1.5 py-0.5 rounded-full"
                    style={{ background: detailUp ? "rgba(38,166,154,0.15)" : "rgba(239,83,80,0.15)", color: detailColor }}
                  >
                    {detailUp ? "+" : ""}{detailChange.toFixed(2)}%
                  </span>
                )}
              </div>
            )}

            {/* Metric grid */}
            <div className="grid grid-cols-2 gap-x-3 gap-y-1.5">
              {detailRows.map(([label, value]) => (
                <div key={label} className="flex flex-col gap-0.5">
                  <span className="text-[9px] uppercase tracking-wider" style={{ color: C.detLbl }}>{label}</span>
                  <span className="text-[11px] font-semibold" style={{ color: C.detVal }}>{value}</span>
                </div>
              ))}
            </div>
          </div>
          <div className="pb-3" />
        </div>
      )}
    </div>
  );
});

export default WatchlistPanel;
