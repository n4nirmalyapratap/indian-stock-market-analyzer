import { ReactNode, ReactElement, cloneElement, isValidElement, useState, useRef, useEffect, useMemo } from "react";
import { Info, Loader2, Lock, ExternalLink, ChevronDown, Check } from "lucide-react";
import { createPortal } from "react-dom";
import { useTheme } from "@/context/ThemeContext";

/** Reactively detect dark mode.
 *
 *  Subscribes to ThemeContext (which is updated *synchronously* during the
 *  theme-toggle View Transition) instead of using a MutationObserver on
 *  `html.dark`. The MO approach fired async after commit, which meant
 *  recharts and other inline-styled consumers were captured by the View
 *  Transitions snapshot with stale colours — the ripple played but the
 *  charts didn't actually change. Reading from context guarantees every
 *  consumer re-renders with the new palette inside the same paint. */
export function useIsDark(): boolean {
  return useTheme().theme === "dark";
}

/** App-wide chart palette derived from Tailwind's gray/indigo scales so
 *  Recharts (which uses inline styles, not Tailwind classes) matches the
 *  surrounding app in both light and dark mode. */
export function useChartPalette() {
  const dark = useIsDark();
  return useMemo(() => ({
    border: dark ? "#374151" : "#e5e7eb",  // gray-700 / gray-200
    muted:  dark ? "#9ca3af" : "#6b7280",  // gray-400 / gray-500
    text:   dark ? "#f9fafb" : "#111827",  // gray-50  / gray-900
    surf:   dark ? "#1f2937" : "#ffffff",  // gray-800 / white
    accent: dark ? "#818cf8" : "#4f46e5",  // indigo-400 / indigo-600
    fii:    dark ? "#a78bfa" : "#7c3aed",  // violet-400 / violet-600 (FII bars)
    dii:    dark ? "#fb923c" : "#ea580c",  // orange-400 / orange-600 (DII bars)
    line:   dark ? "#60a5fa" : "#2563eb",  // blue-400 / blue-600 (Nifty line)
    pos:    dark ? "#4ade80" : "#16a34a",  // green-400 / green-600
    neg:    dark ? "#f87171" : "#dc2626",  // red-400 / red-600
  }), [dark]);
}

/* ──────────────────────────────────────────────────────────────────────────
 * Insights design language — uses the same Tailwind utilities as the rest
 * of the app (Dashboard, Sectors, Sentiment, etc.) so the section feels
 * native, not bolted on:
 *   surface  : bg-white dark:bg-gray-800
 *   page     : bg-gray-50 dark:bg-gray-950 (provided by LayoutShell)
 *   border   : border-gray-100 dark:border-gray-700/800
 *   text     : text-gray-900 dark:text-white   (primary)
 *              text-gray-500 dark:text-gray-400 (muted)
 *   active   : indigo-50/500-20 + indigo-700/300
 *   primary  : indigo-600 dark:indigo-400
 * ────────────────────────────────────────────────────────────────────── */

export function PageHeader({ title, subtitle, info, right }: {
  title: string; subtitle?: string; info?: string; right?: ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-4 mb-4 flex-wrap">
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <h1 className="text-xl md:text-2xl font-bold text-gray-900 dark:text-white">{title}</h1>
          {info && <Info className="w-4 h-4 text-gray-400 dark:text-gray-500" aria-label={info} />}
        </div>
        {subtitle && <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">{subtitle}</p>}
      </div>
      {right && <div className="flex items-center gap-2 flex-wrap">{right}</div>}
    </div>
  );
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div className={`rounded-xl border border-gray-100 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-sm ${className}`}>
      {children}
    </div>
  );
}

export function PillTabs({ value, onChange, options }: {
  value: string; onChange: (v: string) => void; options: { value: string; label: string }[];
}) {
  return (
    <div className="inline-flex flex-wrap gap-1.5">
      {options.map(o => (
        <button
          key={o.value}
          onClick={() => onChange(o.value)}
          className={`px-3.5 py-1.5 rounded-lg text-xs font-medium transition border whitespace-nowrap
            ${o.value === value
              ? "bg-indigo-600 text-white border-indigo-600 dark:bg-indigo-500 dark:border-indigo-500"
              : "bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700"}`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Dropdown({ label, value, onChange, options }: {
  label?: string;
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <label className="inline-flex items-center gap-2 text-xs bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg px-3 py-2 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700 transition shadow-sm">
      {label && <span className="text-gray-500 dark:text-gray-400">{label}</span>}
      <span className="relative inline-flex items-center">
        <select
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="appearance-none bg-transparent text-indigo-600 dark:text-indigo-400 font-semibold outline-none cursor-pointer pr-5"
        >
          {options.map(o => (
            <option key={o.value} value={o.value} className="bg-white dark:bg-gray-800 text-gray-900 dark:text-white">
              {o.label}
            </option>
          ))}
        </select>
        <svg className="w-3.5 h-3.5 text-indigo-600 dark:text-indigo-400 pointer-events-none absolute right-0" viewBox="0 0 20 20" fill="currentColor"><path fillRule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 11.06l3.71-3.83a.75.75 0 111.08 1.04l-4.25 4.39a.75.75 0 01-1.08 0L5.21 8.27a.75.75 0 01.02-1.06z" clipRule="evenodd"/></svg>
      </span>
    </label>
  );
}

/**
 * MenuDropdown — accessible portal-based combobox/listbox with keyboard nav.
 *
 * Behaviour notes:
 * - Scrolling INSIDE the dropdown's own list does NOT close the menu.
 * - The menu only auto-prepends a "Clear selection" row when `clearable` is
 *   true AND a value is currently selected.
 * - Positions itself with `position: fixed` and clamps to a viewport-safe
 *   rectangle (margin = 8px on every side); flips above when no room below.
 * - Keyboard: Arrow Up/Down moves the highlight, Home/End jump, Enter
 *   selects, Escape closes.
 * - ARIA: trigger uses combobox role; menu uses listbox; rows use option
 *   role with aria-selected. Active row is announced via aria-activedescendant.
 */
export function MenuDropdown({
  label, value, options, onChange, placeholder = "Select…", clearable = false,
  minButtonWidth = 0, maxButtonWidth = 280, customButton, renderOption, searchPlaceholder,
}: {
  label?: string;
  value: string;
  options: { value: string; label: string }[];
  onChange: (v: string) => void;
  placeholder?: string;
  clearable?: boolean;
  minButtonWidth?: number;
  maxButtonWidth?: number;
  /** Custom row renderer — receives the option and selected state. */
  renderOption?: (opt: { value: string; label: string }, selected: boolean) => ReactNode;
  /** Override the search box placeholder. */
  searchPlaceholder?: string;
  /**
   * Optional custom trigger element. When provided, this element fully
   * replaces the default styled button. The component clones it to inject
   * the click/keyboard handlers, ref, and ARIA combobox attributes — so the
   * caller only needs to render visual content (icon + label), not wire up
   * dropdown behaviour.
   */
  customButton?: ReactElement;
}) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [active, setActive] = useState(0);
  const btnRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState({ top: 0, left: 0, width: 240 });
  const id = useMemo(() => `mdd-${Math.random().toString(36).slice(2, 8)}`, []);

  const current = options.find(o => o.value === value);

  const baseOptions = useMemo(() => {
    const list = (q
      ? options.filter(o => o.label.toLowerCase().includes(q.toLowerCase()))
      : options
    ).slice(0, 300);
    if (clearable && value && !q) {
      return [{ value: "", label: "Clear selection", _clear: true as const }, ...list];
    }
    return list;
  }, [options, q, value, clearable]);

  useEffect(() => { setActive(0); }, [q, open]);

  useEffect(() => {
    if (!open) return;
    const computePosition = () => {
      const r = btnRef.current?.getBoundingClientRect();
      if (!r) return;
      const margin = 8;
      const vw = window.innerWidth;
      const vh = window.innerHeight;
      const want = Math.max(r.width, 260);
      const width = Math.min(want, vw - margin * 2);
      const left = Math.max(margin, Math.min(r.left, vw - width - margin));
      const spaceBelow = vh - r.bottom - margin;
      const flipUp = spaceBelow < 220 && r.top > spaceBelow;
      let top: number;
      if (flipUp) {
        // Anchor the menu's BOTTOM 6px above the button. Use the menu's
        // actual rendered height when available so a 5-item menu sits flush
        // to the button instead of leaving the old "max 420px" gap.
        const measured = menuRef.current?.getBoundingClientRect().height;
        const h = measured && measured > 0 ? measured : Math.min(420, r.top - margin);
        top = Math.max(margin, r.top - 6 - h);
      } else {
        top = r.bottom + 6;
      }
      setPos({ top, left, width });
    };
    computePosition();
    // Re-measure once the menu has actually rendered so the upward flip
    // snaps to the real height (first pass uses an estimate).
    const raf = requestAnimationFrame(computePosition);
    return () => cancelAnimationFrame(raf);
  }, [open, baseOptions.length]);

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      const t = e.target as Node;
      if (btnRef.current?.contains(t) || menuRef.current?.contains(t)) return;
      setOpen(false);
    };
    const onScroll = (e: Event) => {
      // Don't close when scrolling INSIDE the dropdown's own list.
      const t = e.target as Node | null;
      if (t && menuRef.current?.contains(t)) return;
      setOpen(false);
    };
    const onResize = () => setOpen(false);
    document.addEventListener("mousedown", onClick);
    window.addEventListener("scroll", onScroll, true);
    window.addEventListener("resize", onResize);
    return () => {
      document.removeEventListener("mousedown", onClick);
      window.removeEventListener("scroll", onScroll, true);
      window.removeEventListener("resize", onResize);
    };
  }, [open]);

  useEffect(() => {
    if (!open || !listRef.current) return;
    const el = listRef.current.querySelector<HTMLElement>(`[data-idx="${active}"]`);
    el?.scrollIntoView({ block: "nearest" });
  }, [active, open]);

  const select = (v: string) => { onChange(v); setOpen(false); setQ(""); };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (!open) {
      if (e.key === "ArrowDown" || e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        setOpen(true);
      }
      return;
    }
    if (e.key === "Escape") { e.preventDefault(); setOpen(false); btnRef.current?.focus(); return; }
    if (e.key === "ArrowDown") { e.preventDefault(); setActive(a => Math.min(baseOptions.length - 1, a + 1)); return; }
    if (e.key === "ArrowUp")   { e.preventDefault(); setActive(a => Math.max(0, a - 1)); return; }
    if (e.key === "Home")      { e.preventDefault(); setActive(0); return; }
    if (e.key === "End")       { e.preventDefault(); setActive(baseOptions.length - 1); return; }
    if (e.key === "Enter")     { e.preventDefault(); const o = baseOptions[active]; if (o) select(o.value); return; }
  };

  const display = current?.label || placeholder;
  const showSearch = options.length > 8;

  // Shared trigger props injected into either the default button or a
  // caller-provided customButton via cloneElement.
  const triggerProps = {
    ref: btnRef,
    id,
    type: "button" as const,
    onClick: () => setOpen(o => !o),
    onKeyDown,
    title: display,
    role: "combobox" as const,
    "aria-haspopup": "listbox" as const,
    "aria-expanded": open,
    "aria-controls": open ? `${id}-list` : undefined,
    "aria-activedescendant": open ? `${id}-opt-${active}` : undefined,
  };

  return (
    <>
      {customButton && isValidElement(customButton) ? (
        cloneElement(customButton as ReactElement<Record<string, unknown>>, triggerProps as Record<string, unknown>)
      ) : (
        <button
          {...triggerProps}
          style={{ minWidth: minButtonWidth, maxWidth: maxButtonWidth }}
          className="inline-flex items-center gap-2 text-xs bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg px-3 py-2 hover:bg-gray-50 dark:hover:bg-gray-700 transition shadow-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500"
        >
          {label && <span className="text-gray-500 dark:text-gray-400 flex-shrink-0">{label}</span>}
          <span className={`font-semibold truncate text-left flex-1 min-w-0 ${current ? "text-indigo-600 dark:text-indigo-400" : "text-gray-500 dark:text-gray-400"}`}>{display}</span>
          <ChevronDown className={`w-3.5 h-3.5 text-indigo-600 dark:text-indigo-400 flex-shrink-0 transition-transform ${open ? "rotate-180" : ""}`} />
        </button>
      )}
      {open && createPortal(
        <div
          ref={menuRef}
          style={{
            position: "fixed",
            top: pos.top,
            left: pos.left,
            width: pos.width,
            maxHeight: "min(420px, 60vh)",
            // Inline backgroundColor so no portal/dark-mode/global rule can
            // make the menu translucent. `colorScheme` lets the browser pick
            // the right form-control colors automatically.
            backgroundColor: document.documentElement.classList.contains("dark") ? "#1e293b" : "#ffffff",
            colorScheme: document.documentElement.classList.contains("dark") ? "dark" : "light",
          }}
          className="z-[1000] rounded-xl border border-gray-200 dark:border-gray-700 text-gray-900 dark:text-white shadow-2xl overflow-hidden flex flex-col"
        >
          {showSearch && (
            <input
              autoFocus
              value={q}
              onChange={e => setQ(e.target.value)}
              onKeyDown={onKeyDown}
              placeholder={searchPlaceholder || "Search…"}
              aria-label={`Search ${label || "options"}`}
              className="w-full text-sm px-3 py-2 border-b border-gray-200 dark:border-gray-700 bg-transparent outline-none flex-shrink-0 placeholder:text-gray-400 text-gray-900 dark:text-white"
            />
          )}
          <div ref={listRef} role="listbox" id={`${id}-list`} className="overflow-y-auto py-1 flex-1">
            {baseOptions.map((o, idx) => {
              const sel = o.value === value;
              const isClear = "_clear" in o;
              const focused = idx === active;
              return (
                <button
                  key={`${o.value}-${idx}`}
                  id={`${id}-opt-${idx}`}
                  type="button"
                  role="option"
                  data-idx={idx}
                  aria-selected={sel}
                  onMouseEnter={() => setActive(idx)}
                  onClick={() => select(o.value)}
                  className={`w-full text-left text-sm px-3.5 py-2 flex items-center justify-between gap-2 transition
                    ${focused ? "bg-gray-100 dark:bg-gray-700" : ""}
                    ${sel
                      ? "bg-indigo-50 dark:bg-indigo-500/15 text-indigo-700 dark:text-indigo-300 font-semibold"
                      : isClear
                      ? "text-gray-500 dark:text-gray-400 italic"
                      : "text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700"}`}
                >
                  {renderOption && !isClear ? (
                    <div className="flex-1 min-w-0">{renderOption(o, sel)}</div>
                  ) : (
                    <span className="truncate">{o.label}</span>
                  )}
                  {sel && <Check className="w-4 h-4 text-indigo-600 dark:text-indigo-400 flex-shrink-0" />}
                </button>
              );
            })}
            {baseOptions.length === 0 && <div className="px-3 py-3 text-xs text-gray-500 dark:text-gray-400">No matches</div>}
          </div>
        </div>,
        document.body,
      )}
    </>
  );
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-20 text-gray-500 dark:text-gray-400 gap-2">
      <Loader2 className="w-6 h-6 animate-spin text-indigo-600 dark:text-indigo-400" />
      <p className="text-sm">{label}</p>
    </div>
  );
}

export function EmptyState({ title, message, icon }: { title: string; message: string; icon?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center py-20 text-center px-4">
      {icon && <div className="mb-3 text-gray-400 dark:text-gray-500">{icon}</div>}
      <h3 className="text-base font-semibold text-gray-900 dark:text-white">{title}</h3>
      <p className="text-sm text-gray-500 dark:text-gray-400 mt-1 max-w-md">{message}</p>
    </div>
  );
}

export function ErrorState({ message }: { message: string }) {
  return (
    <div className="rounded-xl border border-red-200 dark:border-red-900/50 bg-red-50 dark:bg-red-900/20 p-4 text-sm text-red-700 dark:text-red-300">
      {message}
    </div>
  );
}

/**
 * FeatureLocked — honest empty state for data feeds we can't currently
 * reach from this hosting environment (NSE / Moneycontrol / Chittorgarh
 * restrict automated access from cloud IP ranges). Shows what would appear
 * here, and links to the upstream source so the user can view it directly.
 */
export function FeatureLocked({
  title, sourceName, sourceUrl, whatIsThis, expectedColumns, icon,
}: {
  title: string;
  sourceName: string;
  sourceUrl: string;
  whatIsThis: string;
  expectedColumns?: string[];
  icon?: ReactNode;
}) {
  return (
    <Card className="p-6 md:p-8 max-w-3xl mx-auto">
      <div className="flex items-start gap-4">
        <div className="w-12 h-12 rounded-xl bg-amber-100 dark:bg-amber-500/10 text-amber-600 dark:text-amber-400 flex items-center justify-center flex-shrink-0 ring-1 ring-amber-200 dark:ring-amber-500/20">
          {icon || <Lock className="w-6 h-6" />}
        </div>
        <div className="flex-1 min-w-0">
          <h3 className="text-lg font-bold text-gray-900 dark:text-white">{title}</h3>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1.5 leading-relaxed">{whatIsThis}</p>

          <div className="mt-4 rounded-lg bg-amber-50 dark:bg-amber-500/5 border border-amber-200 dark:border-amber-500/20 p-3">
            <p className="text-xs font-semibold text-amber-700 dark:text-amber-300 uppercase tracking-wide">Why is this empty?</p>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1 leading-relaxed">
              The upstream source (<span className="font-medium text-gray-900 dark:text-white">{sourceName}</span>) blocks
              automated requests from this hosting region. The integration is built — once a routable
              source is configured, this view will populate automatically.
            </p>
          </div>

          {expectedColumns && expectedColumns.length > 0 && (
            <div className="mt-4">
              <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-1.5">What you'll see here</p>
              <div className="flex flex-wrap gap-1.5">
                {expectedColumns.map(c => (
                  <span key={c} className="text-[11px] px-2 py-1 rounded-md bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 border border-gray-200 dark:border-gray-600">
                    {c}
                  </span>
                ))}
              </div>
            </div>
          )}

          <a
            href={sourceUrl}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 mt-5 text-xs font-medium text-indigo-600 dark:text-indigo-400 hover:underline"
          >
            View on {sourceName} <ExternalLink className="w-3.5 h-3.5" />
          </a>
        </div>
      </div>
    </Card>
  );
}

export function fmtNum(n: number | null | undefined, dec = 2) {
  if (n == null || isNaN(n)) return "—";
  return new Intl.NumberFormat("en-IN", { minimumFractionDigits: dec, maximumFractionDigits: dec }).format(n);
}

export function fmtChange(n: number | null | undefined, suffix = "%") {
  if (n == null || isNaN(n)) return "—";
  const sign = n >= 0 ? "+" : "";
  return `${sign}${n.toFixed(2)}${suffix}`;
}
