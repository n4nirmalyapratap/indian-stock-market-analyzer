import { useState, useEffect, useCallback } from "react";
import { Plus, Trash2, ChevronDown, Edit3, Check, X } from "lucide-react";

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
    { id: "tech", name: "Tech Stocks", symbols: ["TCS", "INFY", "WIPRO", "HCLTECH", "TECHM", "LTIM"] },
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
  const [watchlists, setWatchlists] = useState<Watchlist[]>(loadWatchlists);
  const [activeId, setActiveId] = useState(watchlists[0]?.id ?? "default");
  const [prices, setPrices] = useState<Record<string, WatchlistItem>>({});
  const [addInput, setAddInput] = useState("");
  const [editingName, setEditingName] = useState<string | null>(null);
  const [editNameVal, setEditNameVal] = useState("");
  const [showDDList, setShowDDList] = useState(false);
  const [showAddWL, setShowAddWL] = useState(false);
  const [newWLName, setNewWLName] = useState("");

  const activeWL = watchlists.find(w => w.id === activeId) ?? watchlists[0];

  const fetchPrices = useCallback(async (symbols: string[]) => {
    for (const sym of symbols) {
      if (prices[sym]) continue;
      try {
        const r = await fetch(`/api/stocks/${sym}`);
        if (!r.ok) continue;
        const d = await r.json();
        setPrices(prev => ({
          ...prev,
          [sym]: {
            symbol: sym,
            price: d.lastPrice ?? d.currentPrice,
            pChange: d.pChange,
            company: d.companyName ?? sym,
          }
        }));
      } catch {}
      await new Promise(r => setTimeout(r, 150));
    }
  }, []);

  useEffect(() => {
    if (activeWL) fetchPrices(activeWL.symbols);
  }, [activeWL?.symbols?.join(",")]);

  function save(lists: Watchlist[]) {
    setWatchlists(lists);
    saveWatchlists(lists);
  }

  function addSymbol() {
    const sym = addInput.trim().toUpperCase();
    if (!sym || !activeWL) return;
    if (activeWL.symbols.includes(sym)) { setAddInput(""); return; }
    const updated = watchlists.map(w =>
      w.id === activeWL.id ? { ...w, symbols: [...w.symbols, sym] } : w
    );
    save(updated);
    setAddInput("");
    fetchPrices([sym]);
  }

  function removeSymbol(sym: string) {
    const updated = watchlists.map(w =>
      w.id === activeWL?.id ? { ...w, symbols: w.symbols.filter(s => s !== sym) } : w
    );
    save(updated);
  }

  function addWatchlist() {
    const name = newWLName.trim() || `List ${watchlists.length + 1}`;
    const newWL: Watchlist = { id: Date.now().toString(), name, symbols: [] };
    const updated = [...watchlists, newWL];
    save(updated);
    setActiveId(newWL.id);
    setNewWLName(""); setShowAddWL(false);
  }

  function deleteWatchlist(id: string) {
    const updated = watchlists.filter(w => w.id !== id);
    save(updated);
    if (activeId === id) setActiveId(updated[0]?.id ?? "");
    setShowDDList(false);
  }

  function renameWatchlist() {
    const updated = watchlists.map(w => w.id === activeId ? { ...w, name: editNameVal.trim() || w.name } : w);
    save(updated);
    setEditingName(null);
  }

  return (
    <div className="flex flex-col h-full bg-[#131722] border-l border-gray-800 select-none" style={{ width: 220 }}>
      {/* Watchlist selector header */}
      <div className="flex items-center gap-1 px-2 py-2 border-b border-gray-800">
        <div className="relative flex-1">
          <button
            className="flex items-center gap-1 text-xs font-semibold text-gray-300 hover:text-white w-full"
            onClick={() => setShowDDList(v => !v)}
          >
            {editingName === activeId ? (
              <input
                autoFocus
                value={editNameVal}
                onChange={e => setEditNameVal(e.target.value)}
                onKeyDown={e => { if (e.key === "Enter") renameWatchlist(); if (e.key === "Escape") setEditingName(null); }}
                className="bg-gray-800 text-white rounded px-1 py-0.5 text-xs w-full"
                onClick={e => e.stopPropagation()}
              />
            ) : (
              <>
                <span className="truncate">{activeWL?.name ?? "Watchlist"}</span>
                <ChevronDown size={12} className="ml-auto shrink-0" />
              </>
            )}
          </button>
          {showDDList && (
            <div className="absolute top-full left-0 z-50 mt-1 bg-gray-900 border border-gray-700 rounded shadow-xl w-48">
              {watchlists.map(wl => (
                <div
                  key={wl.id}
                  className={`flex items-center justify-between px-3 py-1.5 text-xs cursor-pointer hover:bg-gray-800 ${wl.id === activeId ? "text-indigo-400" : "text-gray-300"}`}
                  onClick={() => { setActiveId(wl.id); setShowDDList(false); }}
                >
                  <span className="truncate">{wl.name}</span>
                  <div className="flex gap-1 ml-2">
                    <button onClick={e => { e.stopPropagation(); setEditingName(wl.id); setEditNameVal(wl.name); setShowDDList(false); }} className="hover:text-white">
                      <Edit3 size={10} />
                    </button>
                    {watchlists.length > 1 && (
                      <button onClick={e => { e.stopPropagation(); deleteWatchlist(wl.id); }} className="hover:text-red-400">
                        <Trash2 size={10} />
                      </button>
                    )}
                  </div>
                </div>
              ))}
              <div className="border-t border-gray-700 px-3 py-1.5">
                {showAddWL ? (
                  <div className="flex gap-1">
                    <input autoFocus value={newWLName} onChange={e => setNewWLName(e.target.value)}
                      onKeyDown={e => { if (e.key === "Enter") addWatchlist(); if (e.key === "Escape") setShowAddWL(false); }}
                      placeholder="List name…" className="bg-gray-800 text-white rounded px-1.5 py-1 text-xs flex-1 min-w-0" />
                    <button onClick={addWatchlist} className="text-green-400 hover:text-green-300"><Check size={12} /></button>
                    <button onClick={() => setShowAddWL(false)} className="text-gray-500 hover:text-white"><X size={12} /></button>
                  </div>
                ) : (
                  <button onClick={() => setShowAddWL(true)} className="flex items-center gap-1 text-xs text-indigo-400 hover:text-indigo-300">
                    <Plus size={11} /> New watchlist
                  </button>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Symbol list */}
      <div className="flex-1 overflow-y-auto">
        {activeWL?.symbols.map(sym => {
          const info = prices[sym];
          const up = (info?.pChange ?? 0) >= 0;
          const isSelected = sym === activeSymbol;
          return (
            <div
              key={sym}
              onClick={() => onSymbolSelect(sym)}
              className={`flex items-center justify-between px-3 py-2 cursor-pointer border-b border-gray-800/50 hover:bg-gray-800/60 group transition-colors ${isSelected ? "bg-indigo-900/30 border-l-2 border-l-indigo-500" : ""}`}
            >
              <div className="flex-1 min-w-0">
                <div className="text-xs font-semibold text-white truncate">{sym}</div>
                <div className="text-[10px] text-gray-500 truncate">{info?.company ?? ""}</div>
              </div>
              <div className="text-right ml-2 shrink-0">
                {info?.price != null ? (
                  <>
                    <div className="text-xs text-white">₹{info.price.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</div>
                    <div className={`text-[10px] ${up ? "text-green-400" : "text-red-400"}`}>
                      {up ? "+" : ""}{info.pChange?.toFixed(2)}%
                    </div>
                  </>
                ) : (
                  <div className="text-[10px] text-gray-600">—</div>
                )}
              </div>
              <button
                onClick={e => { e.stopPropagation(); removeSymbol(sym); }}
                className="ml-1 opacity-0 group-hover:opacity-100 text-gray-600 hover:text-red-400 transition-opacity"
              >
                <X size={11} />
              </button>
            </div>
          );
        })}
      </div>

      {/* Add symbol */}
      <div className="border-t border-gray-800 p-2">
        <div className="flex gap-1">
          <input
            value={addInput}
            onChange={e => setAddInput(e.target.value.toUpperCase())}
            onKeyDown={e => { if (e.key === "Enter") addSymbol(); }}
            placeholder="Add symbol…"
            className="flex-1 bg-gray-800 text-white text-xs rounded px-2 py-1.5 placeholder-gray-600 border border-gray-700 focus:border-indigo-500 focus:outline-none min-w-0"
          />
          <button onClick={addSymbol} className="bg-indigo-600 hover:bg-indigo-500 text-white rounded px-2 py-1.5">
            <Plus size={14} />
          </button>
        </div>
      </div>
    </div>
  );
}
