/**
 * <StockCombobox> — reusable autocomplete input for NSE tickers.
 *
 * Drop-in replacement for a plain `<input>` wherever the app asks the user
 * to type a stock symbol. Calls `/api/search/suggest` with a debounced
 * query and shows ranked suggestions (exact ticker → ticker prefix → name
 * prefix → contains → fuzzy).
 *
 * Designed to fail open: if the suggest endpoint errors or returns nothing,
 * the input behaves exactly like a plain text field — Enter still submits
 * whatever the user typed.
 *
 * Used by:
 *   - AIAnalyst page (single ticker)
 *   - AIAnalystCompare (two tickers)
 *   - StockLookup
 *   - DCF
 *   - InvestorCouncil
 *   - Portfolio Add-transaction modal
 *   - Anywhere else a symbol is entered
 */
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { Search } from "lucide-react";
import { useCustomAuth } from "@/context/CustomAuthContext";

export type StockSuggestion = {
  symbol:     string;
  name?:      string | null;
  category?:  string;
  sub_sector?: string | null;
};

type Props = {
  value:        string;
  onChange:     (v: string) => void;
  /** Fired with the picked suggestion when the user clicks one or presses Enter on a highlighted row. */
  onSelect?:    (s: StockSuggestion) => void;
  /** Submit handler — fired on Enter when no suggestion is highlighted. Lets parent code "go" without a pick. */
  onSubmit?:    () => void;
  placeholder?: string;
  className?:   string;
  /** Optional id forwarded to the underlying input (for label htmlFor). */
  inputId?:     string;
  autoFocus?:   boolean;
  disabled?:    boolean;
  /** Cap on the number of suggestions to fetch. Backend defaults to 10. */
  maxResults?:  number;
  /** Show the leading magnifier icon. Defaults to true. */
  showIcon?:    boolean;
};

const DEBOUNCE_MS = 200;
const ABORT_REASON = "stock-combobox-superseded";

export function StockCombobox({
  value, onChange, onSelect, onSubmit,
  placeholder = "Search symbol or company…",
  className = "",
  inputId,
  autoFocus,
  disabled,
  maxResults = 10,
  showIcon = true,
}: Props) {
  const { token } = useCustomAuth();
  const fallbackId = useId();
  const id = inputId ?? `stockbox-${fallbackId}`;
  const listboxId = `${id}-listbox`;

  const [open, setOpen]                 = useState(false);
  const [suggestions, setSuggestions]   = useState<StockSuggestion[]>([]);
  const [highlightIdx, setHighlightIdx] = useState(-1);
  const [loading, setLoading]           = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Debounced fetch — uses AbortController so a fast typist doesn't get
  // a stale older response overwriting newer suggestions.
  useEffect(() => {
    const q = value.trim();
    if (q.length < 1) {
      setSuggestions([]);
      setLoading(false);
      return;
    }
    const timer = setTimeout(() => {
      abortRef.current?.abort(ABORT_REASON);
      const ctrl = new AbortController();
      abortRef.current = ctrl;
      setLoading(true);
      const headers: Record<string, string> = token
        ? { Authorization: `Bearer ${token}` }
        : {};
      fetch(
        `/api/search/suggest?q=${encodeURIComponent(q)}&limit=${maxResults}`,
        { headers, signal: ctrl.signal },
      )
        .then(r => r.ok ? r.json() : { results: [] })
        .then((d: { results?: StockSuggestion[] }) => {
          if (ctrl.signal.aborted) return;
          setSuggestions(Array.isArray(d.results) ? d.results : []);
          setHighlightIdx(-1);
        })
        .catch(() => {
          // Network error / aborted — fail silently; the input still works.
        })
        .finally(() => {
          if (!ctrl.signal.aborted) setLoading(false);
        });
    }, DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [value, token, maxResults]);

  // Close dropdown on outside click.
  useEffect(() => {
    if (!open) return;
    const onDocClick = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [open]);

  const pick = (s: StockSuggestion) => {
    onChange(s.symbol);
    setOpen(false);
    setHighlightIdx(-1);
    onSelect?.(s);
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      if (suggestions.length === 0) return;
      setOpen(true);
      setHighlightIdx(idx => Math.min(idx + 1, suggestions.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlightIdx(idx => Math.max(idx - 1, -1));
    } else if (e.key === "Enter") {
      if (highlightIdx >= 0 && suggestions[highlightIdx]) {
        e.preventDefault();
        pick(suggestions[highlightIdx]);
      } else if (onSubmit) {
        onSubmit();
        setOpen(false);
      }
    } else if (e.key === "Escape") {
      setOpen(false);
      setHighlightIdx(-1);
    }
  };

  const showDropdown = open && suggestions.length > 0;

  // Memoise the display text so the dropdown doesn't flicker as React renders.
  const displayedSuggestions = useMemo(() => suggestions, [suggestions]);

  return (
    <div ref={wrapRef} className={`relative ${className}`}>
      <div className="relative">
        {showIcon && (
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400 pointer-events-none" />
        )}
        <input
          id={id}
          role="combobox"
          aria-autocomplete="list"
          aria-expanded={showDropdown}
          aria-controls={listboxId}
          aria-activedescendant={highlightIdx >= 0 ? `${listboxId}-opt-${highlightIdx}` : undefined}
          type="text"
          autoComplete="off"
          spellCheck={false}
          value={value}
          disabled={disabled}
          autoFocus={autoFocus}
          placeholder={placeholder}
          onFocus={() => { if (suggestions.length > 0) setOpen(true); }}
          onChange={(e) => {
            // Force uppercase — every NSE ticker is uppercase, and it makes
            // matching against the in-memory symbol list cheaper.
            const upper = e.target.value.toUpperCase();
            onChange(upper);
            setOpen(true);
          }}
          onKeyDown={onKeyDown}
          className={`w-full ${showIcon ? "pl-8" : "pl-3"} pr-3 py-2 text-sm font-mono bg-white dark:bg-gray-900 border border-gray-200 dark:border-white/10 rounded focus:border-indigo-400 focus:ring-1 focus:ring-indigo-400 outline-none disabled:opacity-60`}
        />
        {loading && (
          <div className="absolute right-2.5 top-1/2 -translate-y-1/2 w-3 h-3 rounded-full border-2 border-indigo-500 border-r-transparent animate-spin" />
        )}
      </div>
      {showDropdown && (
        <ul
          id={listboxId}
          role="listbox"
          className="absolute z-30 left-0 right-0 mt-1 max-h-72 overflow-y-auto bg-white dark:bg-gray-900 border border-gray-200 dark:border-white/10 rounded-lg shadow-lg"
        >
          {displayedSuggestions.map((s, i) => (
            <li
              key={s.symbol}
              id={`${listboxId}-opt-${i}`}
              role="option"
              aria-selected={i === highlightIdx}
              onMouseEnter={() => setHighlightIdx(i)}
              onMouseDown={(e) => {
                // mousedown (not click) so we beat the input's blur.
                e.preventDefault();
                pick(s);
              }}
              className={`px-3 py-2 cursor-pointer text-sm flex items-center justify-between gap-2 ${
                i === highlightIdx
                  ? "bg-indigo-50 dark:bg-indigo-500/20"
                  : "hover:bg-gray-50 dark:hover:bg-gray-800/60"
              }`}
            >
              <div className="min-w-0 flex-1">
                <div className="font-mono font-medium text-gray-900 dark:text-gray-100">
                  {s.symbol}
                </div>
                {s.name && (
                  <div className="text-xs text-gray-500 truncate">{s.name}</div>
                )}
                {s.sub_sector && (
                  <div className="text-[10px] text-indigo-500 dark:text-indigo-400 truncate">{s.sub_sector}</div>
                )}
              </div>
              {s.category && (
                <span className="text-[10px] uppercase tracking-wide text-gray-400 flex-shrink-0">
                  {s.category}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
