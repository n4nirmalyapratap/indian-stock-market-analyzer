import { ReactNode } from "react";
import { Info, Loader2 } from "lucide-react";

export function PageHeader({ title, subtitle, info, right }: {
  title: string; subtitle?: string; info?: string; right?: ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-4 mb-4">
      <div>
        <div className="flex items-center gap-2">
          <h1 className="text-xl md:text-2xl font-bold text-gray-900 dark:text-white">{title}</h1>
          {info && <Info className="w-4 h-4 text-gray-400" aria-label={info} />}
        </div>
        {subtitle && <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">{subtitle}</p>}
      </div>
      {right && <div className="flex items-center gap-2 flex-wrap">{right}</div>}
    </div>
  );
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div className={`rounded-xl border border-gray-100 dark:border-white/[0.05] bg-white dark:bg-gray-900 ${className}`}>
      {children}
    </div>
  );
}

export function PillTabs<T extends string>({ value, onChange, options }: {
  value: T; onChange: (v: T) => void; options: { value: T; label: string }[];
}) {
  return (
    <div className="inline-flex flex-wrap gap-1.5">
      {options.map(o => (
        <button
          key={o.value}
          onClick={() => onChange(o.value)}
          className={`px-3.5 py-1.5 rounded-lg text-xs font-medium transition border
            ${o.value === value
              ? "bg-indigo-500 text-white border-indigo-500"
              : "bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700"}`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Dropdown<T extends string>({ label, value, onChange, options }: {
  label?: string;
  value: T;
  onChange: (v: T) => void;
  options: { value: T; label: string }[];
}) {
  return (
    <div className="inline-flex items-center gap-1.5 text-xs text-gray-600 dark:text-gray-400 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg px-3 py-1.5">
      {label && <span>{label}</span>}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value as T)}
        className="bg-transparent text-indigo-600 dark:text-indigo-400 font-semibold outline-none cursor-pointer pr-1"
      >
        {options.map(o => (
          <option key={o.value} value={o.value} className="bg-white dark:bg-gray-800 text-gray-900 dark:text-white">
            {o.label}
          </option>
        ))}
      </select>
    </div>
  );
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-20 text-gray-500 dark:text-gray-400 gap-2">
      <Loader2 className="w-6 h-6 animate-spin text-indigo-500" />
      <p className="text-sm">{label}</p>
    </div>
  );
}

export function EmptyState({ title, message, icon }: { title: string; message: string; icon?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center py-20 text-center px-4">
      {icon && <div className="mb-3 text-gray-400">{icon}</div>}
      <h3 className="text-base font-semibold text-gray-700 dark:text-gray-300">{title}</h3>
      <p className="text-sm text-gray-500 dark:text-gray-400 mt-1 max-w-md">{message}</p>
    </div>
  );
}

export function ErrorState({ message }: { message: string }) {
  return (
    <div className="rounded-xl border border-red-200 dark:border-red-500/30 bg-red-50 dark:bg-red-500/10 p-4 text-sm text-red-700 dark:text-red-300">
      {message}
    </div>
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
