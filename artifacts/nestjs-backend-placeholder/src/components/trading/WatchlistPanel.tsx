import { useState, useEffect, useCallback, useRef } from "react";
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

interface Props {
  onSymbolSelect: (symbol: string) => void;
  activeSymbol: string;
}

export default function WatchlistPanel({ onSymbolSelect, activeSymbol }: Props) {
  const [watchlists, setWatchlists]   = useState<Watchlist[]>(loadWatchlists);
  const [activeId, setActiveId]       = useState(watchlists[0]?.id ?? "default");
  const [prices, setPrices]           = useState<Record<string, WatchlistItem>>({});
  const [addInput, setAddInput]       = useState("");
  const [showMenu, setShowMenu]       = useState(false);
  const [editingId, setEditingId]     = useState<string | null>(null);
  const [editVal, setEditVal]         = useState("");
  const [newListMode, setNewListMode] = useState(false);
  const [newListName, setNewListName] = useState("");
  const menuRef      = useRef<HTMLDivElement>(null);
  const addRef       = useRef<HTMLInputElement>(null);
  const fetchGenRef  = useRef(0);

  const activeWL = watchlists.find(w => w.id === activeId) ?? watchlists[0];

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
      if (fetchGenRef.current !== gen) return; // stale — abandon
      try {
        const r = await fetch(`/api/stocks/${sym}`);
        if (fetchGenRef.current !== gen) return; // stale after await
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

  function save(lists: Watchlist[]) { setWatchlists(lists); saveWatchlists(lists); }

  function addSymbol() {
    const sym = addInput.trim().toUpperCase();
    if (!sym || !activeWL || activeWL.symbols.includes(sym)) { setAddInput(""); return; }
    save(watchlists.map(w => w.id === activeWL.id ? { ...w, symbols: [...w.symbols, sym] } : w));
    setAddInput("");
    const gen = ++fetchGenRef.current;
    fetchPrices([sym], gen);
  }

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

  return (
    <div className="flex flex-col h-full select-none" style={{ width: 220, background: "#0f1117" }}>

      {/* ── Header: watchlist switcher ── */}
      <div className="relative shrink-0" ref={menuRef}>
        <button
          onClick={() => setShowMenu(v => !v)}
          className="flex items-center gap-2 w-full px-4 py-3 text-left hover:bg-white/5 transition-colors group"
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
              <ChevronDown size={13} className={`text-gray-500 transition-transform ${showMenu ? "rotate-180" : ""}`} />
            </>
          )}
        </button>

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
                  className="opacity-0 hover:opacity-100 group-hover:opacity-60 text-gray-500 hover:text-white p-0.5 rounded"
                  style={{ opacity: undefined }}
                  onMouseEnter={e => (e.currentTarget.style.opacity = "1")}
                  onMouseLeave={e => (e.currentTarget.style.opacity = "")}
                >
                  <Pencil size={10} />
                </button>
                {watchlists.length > 1 && (
                  <button
                    onClick={e => { e.stopPropagation(); deleteList(wl.id); }}
                    className="text-gray-600 hover:text-red-400 p-0.5 rounded"
                    onMouseEnter={e => (e.currentTarget.style.opacity = "1")}
                    onMouseLeave={e => (e.currentTarget.style.opacity = "")}
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
              {/* Active indicator — thin left highlight only */}
              {isOn && <div className="absolute left-0 top-2 bottom-2 w-[2px] rounded-r" style={{ background: "#6366f1" }} />}

              {/* Symbol & company */}
              <div className="flex-1 min-w-0">
                <div className="text-xs font-semibold text-white truncate">{sym}</div>
                {info?.company && (
                  <div className="text-[10px] truncate mt-0.5" style={{ color: "#4b5563" }}>{info.company}</div>
                )}
              </div>

              {/* Price & change */}
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

              {/* Remove button (appears on hover) */}
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

      {/* ── Add symbol ── */}
      <div className="shrink-0 px-3 py-3" style={{ borderTop: "1px solid rgba(255,255,255,0.06)" }}>
        <div className="flex items-center gap-2 rounded-lg px-3 py-2" style={{ background: "rgba(255,255,255,0.06)" }}>
          <input
            ref={addRef}
            value={addInput}
            onChange={e => setAddInput(e.target.value.toUpperCase())}
            onKeyDown={e => { if (e.key === "Enter") addSymbol(); }}
            placeholder="Add symbol…"
            className="flex-1 bg-transparent text-xs text-white placeholder-gray-600 focus:outline-none min-w-0"
          />
          <button
            onClick={addSymbol}
            className="shrink-0 text-indigo-400 hover:text-indigo-300 transition-colors"
          >
            <Plus size={14} />
          </button>
        </div>
      </div>
    </div>
  );
}
