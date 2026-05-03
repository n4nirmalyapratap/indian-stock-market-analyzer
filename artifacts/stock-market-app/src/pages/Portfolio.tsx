import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  api,
  Portfolio as PortfolioMeta,
  PortfolioHolding,
  PortfolioOptimizeResult,
  PortfolioRiskResult,
  PortfolioPerformance,
  PortfolioValuation,
  PortfolioImportResult,
} from "@/lib/api";
import {
  Briefcase, Plus, Trash2, Upload, RefreshCw, Loader2,
  TrendingUp, TrendingDown, AlertTriangle, Activity, PieChart as PieIcon,
  ShieldAlert, Target, BarChart3, X, Edit3,
} from "lucide-react";
import {
  ResponsiveContainer, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  PieChart, Pie, Cell, ScatterChart, Scatter, ZAxis, Legend, Line, ComposedChart,
} from "recharts";

// ── Helpers ──────────────────────────────────────────────────────────────────

const fmtINR = (n: number) =>
  new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 }).format(Math.round(n || 0));
const fmtPct = (n: number, d = 2) =>
  `${n >= 0 ? "+" : ""}${(n || 0).toFixed(d)}%`;
const fmtNum = (n: number | null | undefined, d = 2) =>
  n == null ? "—" : Number(n).toFixed(d);

const TONE = {
  pos:  "text-emerald-600 dark:text-emerald-400",
  neg:  "text-rose-600   dark:text-rose-400",
  mute: "text-gray-500   dark:text-gray-400",
};
const tone = (n: number) => (n >= 0 ? TONE.pos : TONE.neg);

const SECTOR_COLORS = [
  "#6366f1", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6",
  "#06b6d4", "#ec4899", "#14b8a6", "#f97316", "#84cc16",
  "#0ea5e9", "#a855f7",
];

const TABS = [
  { key: "holdings",   label: "Holdings",    icon: Briefcase  },
  { key: "allocation", label: "Allocation",  icon: PieIcon    },
  { key: "risk",       label: "Risk",        icon: ShieldAlert },
  { key: "optimizer",  label: "Optimizer",   icon: Target     },
  { key: "performance",label: "Performance", icon: Activity   },
] as const;
type TabKey = typeof TABS[number]["key"];

// ── Page ────────────────────────────────────────────────────────────────────

export default function PortfolioPage() {
  const qc = useQueryClient();
  const [activePid, setActivePid] = useState<string | null>(null);
  const [tab, setTab] = useState<TabKey>("holdings");

  const portfoliosQ = useQuery({ queryKey: ["portfolios"], queryFn: api.portfolios });

  const portfolios = portfoliosQ.data?.portfolios ?? [];
  useEffect(() => {
    if (!activePid && portfolios.length > 0) setActivePid(portfolios[0].id);
  }, [portfolios, activePid]);

  const createMut = useMutation({
    mutationFn: api.createPortfolio,
    onSuccess: (p) => {
      qc.invalidateQueries({ queryKey: ["portfolios"] });
      setActivePid(p.id);
    },
  });
  const deleteMut = useMutation({
    mutationFn: api.deletePortfolio,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["portfolios"] });
      setActivePid(null);
    },
  });

  // Loading shell
  if (portfoliosQ.isLoading) {
    return <div className="p-12 text-center text-gray-400 flex items-center justify-center gap-2">
      <Loader2 className="w-4 h-4 animate-spin" /> Loading portfolios…
    </div>;
  }

  // Empty state
  if (portfolios.length === 0) {
    return <EmptyState onCreate={(name, cash) => createMut.mutate({ name, cash })} />;
  }

  return (
    <div className="max-w-7xl mx-auto space-y-4">
      <Header
        portfolios={portfolios}
        activePid={activePid}
        onSelect={setActivePid}
        onCreate={() => {
          const name = window.prompt("Portfolio name?", "My Portfolio");
          if (name) createMut.mutate({ name });
        }}
        onDelete={(pid) => {
          if (window.confirm("Delete this portfolio? Trades will be lost.")) deleteMut.mutate(pid);
        }}
      />

      {activePid && <>
        <KpiStrip pid={activePid} />

        <div className="border-b border-gray-200 dark:border-white/10 flex gap-1 overflow-x-auto">
          {TABS.map(t => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`flex items-center gap-1.5 px-3 py-2 text-sm font-medium border-b-2 transition whitespace-nowrap
                ${tab === t.key
                  ? "border-indigo-500 text-indigo-600 dark:text-indigo-300"
                  : "border-transparent text-gray-500 hover:text-gray-900 dark:hover:text-gray-200"}`}
            >
              <t.icon className="w-4 h-4" /> {t.label}
            </button>
          ))}
        </div>

        {tab === "holdings"    && <HoldingsTab pid={activePid} />}
        {tab === "allocation"  && <AllocationTab pid={activePid} />}
        {tab === "risk"        && <RiskTab pid={activePid} />}
        {tab === "optimizer"   && <OptimizerTab pid={activePid} />}
        {tab === "performance" && <PerformanceTab pid={activePid} />}
      </>}
    </div>
  );
}

// ── Empty state ──────────────────────────────────────────────────────────────

function EmptyState({ onCreate }: { onCreate: (name: string, cash: number) => void }) {
  const [name, setName] = useState("My Portfolio");
  const [cash, setCash] = useState(100000);
  return (
    <div className="max-w-md mx-auto mt-20 p-6 bg-white dark:bg-gray-900 border border-gray-100 dark:border-white/10 rounded-xl text-center space-y-4">
      <Briefcase className="w-10 h-10 text-indigo-500 mx-auto" />
      <h2 className="text-lg font-bold text-gray-900 dark:text-white">Create your first portfolio</h2>
      <p className="text-sm text-gray-500">Track your Indian-equity holdings, run risk metrics, and rebalance toward an optimal allocation.</p>
      <input
        value={name} onChange={(e) => setName(e.target.value)}
        className="w-full px-3 py-2 text-sm bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-white/10 rounded"
        placeholder="Portfolio name"
      />
      <input
        type="number" value={cash} onChange={(e) => setCash(parseFloat(e.target.value) || 0)}
        className="w-full px-3 py-2 text-sm bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-white/10 rounded"
        placeholder="Starting cash (₹)"
      />
      <button
        onClick={() => onCreate(name, cash)}
        className="w-full bg-indigo-600 hover:bg-indigo-700 text-white py-2 text-sm font-medium rounded"
      >
        Create portfolio
      </button>
    </div>
  );
}

// ── Header (portfolio selector + actions) ────────────────────────────────────

function Header({
  portfolios, activePid, onSelect, onCreate, onDelete,
}: {
  portfolios: PortfolioMeta[]; activePid: string | null;
  onSelect: (id: string) => void; onCreate: () => void; onDelete: (id: string) => void;
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div className="flex items-center gap-2">
        <Briefcase className="w-5 h-5 text-indigo-500" />
        <h1 className="text-xl font-bold text-gray-900 dark:text-white">Portfolio Manager</h1>
      </div>
      <div className="flex items-center gap-2">
        <select
          value={activePid ?? ""}
          onChange={(e) => onSelect(e.target.value)}
          className="px-3 py-1.5 text-sm bg-white dark:bg-gray-900 border border-gray-200 dark:border-white/10 rounded"
        >
          {portfolios.map(p => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </select>
        <button onClick={onCreate}
          className="flex items-center gap-1 px-3 py-1.5 text-sm bg-indigo-600 hover:bg-indigo-700 text-white rounded">
          <Plus className="w-3.5 h-3.5" /> New
        </button>
        {activePid && (
          <button onClick={() => onDelete(activePid)} title="Delete portfolio"
            className="p-1.5 text-gray-400 hover:text-rose-500 border border-gray-200 dark:border-white/10 rounded">
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        )}
      </div>
    </div>
  );
}

// ── KPI strip ────────────────────────────────────────────────────────────────

function useValuation(pid: string) {
  return useQuery({
    queryKey: ["portfolio-valuation", pid],
    queryFn:  () => api.portfolioValuation(pid),
    refetchInterval: 60_000,
  });
}

function Kpi({ label, value, sub, accent }: { label: string; value: string; sub?: string; accent?: string }) {
  return (
    <div className="bg-white dark:bg-gray-900 border border-gray-100 dark:border-white/10 rounded-xl px-4 py-3">
      <p className="text-[11px] text-gray-500 uppercase tracking-wide">{label}</p>
      <p className={`text-lg font-bold ${accent ?? "text-gray-900 dark:text-white"}`}>{value}</p>
      {sub && <p className={`text-xs ${accent ?? TONE.mute}`}>{sub}</p>}
    </div>
  );
}

function KpiStrip({ pid }: { pid: string }) {
  const v = useValuation(pid);
  const t = v.data?.totals;
  if (v.isLoading || !t) return (
    <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
      {Array.from({ length: 5 }).map((_, i) =>
        <div key={i} className="h-16 bg-gray-100 dark:bg-gray-800/40 rounded-xl animate-pulse" />)}
    </div>
  );
  return (
    <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
      <Kpi label="Total Equity"  value={`₹${fmtINR(t.totalEquity)}`}
           sub={`Cash ₹${fmtINR(t.cash)}`} />
      <Kpi label="Market Value"  value={`₹${fmtINR(t.marketValue)}`}
           sub={`Invested ₹${fmtINR(t.investedValue)}`} />
      <Kpi label="Day P&L"       value={`₹${fmtINR(t.dayPnl)}`}
           sub={fmtPct(t.dayPnlPct)} accent={tone(t.dayPnl)} />
      <Kpi label="Unrealised P&L" value={`₹${fmtINR(t.unrealisedPnl)}`}
           sub={fmtPct(t.unrealisedPnlPct)} accent={tone(t.unrealisedPnl)} />
      <Kpi label="Realised + Div." value={`₹${fmtINR(t.realisedPnl + t.dividendsRcvd)}`}
           sub={`Div ₹${fmtINR(t.dividendsRcvd)}`} accent={tone(t.realisedPnl + t.dividendsRcvd)} />
    </div>
  );
}

// ── Holdings tab ─────────────────────────────────────────────────────────────

function HoldingsTab({ pid }: { pid: string }) {
  const qc = useQueryClient();
  const v = useValuation(pid);
  const [showAdd, setShowAdd] = useState(false);
  const [showImport, setShowImport] = useState(false);

  const delTx = useMutation({
    mutationFn: (txId: string) => api.deletePortfolioTx(pid, txId),
    onSuccess:  () => {
      qc.invalidateQueries({ queryKey: ["portfolio-valuation", pid] });
      qc.invalidateQueries({ queryKey: ["portfolio-tx", pid] });
    },
  });
  const txQ = useQuery({
    queryKey: ["portfolio-tx", pid],
    queryFn:  () => api.portfolioTransactions(pid),
  });

  if (v.isLoading) return <div className="p-8 text-center text-gray-400">
    <Loader2 className="w-4 h-4 animate-spin inline mr-2" /> Valuing portfolio…
  </div>;
  if (v.isError) return <ErrorBox msg={(v.error as Error).message} />;

  const holdings = v.data?.holdings ?? [];
  const concentration = v.data?.concentration ?? [];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2 justify-end">
        <button onClick={() => setShowImport(true)}
          className="flex items-center gap-1 px-3 py-1.5 text-sm bg-white dark:bg-gray-900 border border-gray-200 dark:border-white/10 rounded hover:bg-gray-50 dark:hover:bg-gray-800">
          <Upload className="w-3.5 h-3.5" /> Import CSV
        </button>
        <button onClick={() => setShowAdd(true)}
          className="flex items-center gap-1 px-3 py-1.5 text-sm bg-indigo-600 hover:bg-indigo-700 text-white rounded">
          <Plus className="w-3.5 h-3.5" /> Add transaction
        </button>
        <button onClick={() => v.refetch()}
          className="p-1.5 text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 border border-gray-200 dark:border-white/10 rounded">
          <RefreshCw className={`w-3.5 h-3.5 ${v.isFetching ? "animate-spin" : ""}`} />
        </button>
      </div>

      {concentration.length > 0 && (
        <div className="bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/30 rounded-lg p-3 flex items-start gap-2">
          <AlertTriangle className="w-4 h-4 text-amber-600 dark:text-amber-400 mt-0.5 flex-shrink-0" />
          <div className="text-sm text-amber-800 dark:text-amber-200">
            <span className="font-semibold">Concentration risk:</span>{" "}
            {concentration.map((c) => `${c.symbol} (${(c.weight * 100).toFixed(1)}%)`).join(", ")}
            {" "}is over 25% of the portfolio.
          </div>
        </div>
      )}

      {holdings.length === 0 ? (
        <div className="p-12 text-center text-gray-400 bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-white/10">
          No open positions yet — add a transaction or import a tradebook CSV.
        </div>
      ) : (
        <div className="bg-white dark:bg-gray-900 border border-gray-100 dark:border-white/10 rounded-xl overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 dark:bg-gray-800/50 text-gray-500 text-xs">
              <tr>
                <th className="text-left px-3 py-2">Symbol</th>
                <th className="text-right px-3 py-2">Qty</th>
                <th className="text-right px-3 py-2">Avg Cost</th>
                <th className="text-right px-3 py-2">LTP</th>
                <th className="text-right px-3 py-2">Day P&L</th>
                <th className="text-right px-3 py-2">Mkt Value</th>
                <th className="text-right px-3 py-2">Unrealised</th>
                <th className="text-right px-3 py-2">Weight</th>
                <th className="px-3 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {holdings.map((h: PortfolioHolding) => (
                <tr key={h.symbol} className="border-t border-gray-100 dark:border-white/5 hover:bg-gray-50 dark:hover:bg-gray-800/30">
                  <td className="px-3 py-2">
                    <div className="font-semibold text-gray-900 dark:text-white">{h.symbol}</div>
                    <div className="text-[11px] text-gray-400 truncate max-w-[14rem]">{h.companyName ?? h.sector}</div>
                  </td>
                  <td className="text-right px-3 py-2">{h.qty}</td>
                  <td className="text-right px-3 py-2">₹{fmtNum(h.avgCost)}</td>
                  <td className="text-right px-3 py-2">₹{fmtNum(h.lastPrice)}</td>
                  <td className={`text-right px-3 py-2 ${tone(h.dayPnl)}`}>
                    {h.dayPnl >= 0 ? <TrendingUp className="inline w-3 h-3" /> : <TrendingDown className="inline w-3 h-3" />} ₹{fmtINR(h.dayPnl)}
                    <div className="text-[11px]">{fmtPct(h.dayPnlPct)}</div>
                  </td>
                  <td className="text-right px-3 py-2">₹{fmtINR(h.marketValue)}</td>
                  <td className={`text-right px-3 py-2 ${tone(h.unrealisedPnl)}`}>
                    ₹{fmtINR(h.unrealisedPnl)}
                    <div className="text-[11px]">{fmtPct(h.unrealisedPnlPct)}</div>
                  </td>
                  <td className="text-right px-3 py-2">{(h.weight * 100).toFixed(1)}%</td>
                  <td className="px-3 py-2 text-right text-gray-400">
                    {h.marketCapBucket && <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-800">{h.marketCapBucket}</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <TransactionList
        txs={txQ.data?.transactions ?? []}
        loading={txQ.isLoading}
        onDelete={(id) => delTx.mutate(id)}
      />

      {showAdd && (
        <AddTxModal pid={pid} onClose={() => setShowAdd(false)} />
      )}
      {showImport && (
        <ImportCsvModal pid={pid} onClose={() => setShowImport(false)} />
      )}
    </div>
  );
}

function TransactionList({ txs, loading, onDelete }: {
  txs: any[]; loading: boolean; onDelete: (id: string) => void;
}) {
  if (loading) return null;
  if (txs.length === 0) return null;
  return (
    <details className="bg-white dark:bg-gray-900 border border-gray-100 dark:border-white/10 rounded-xl">
      <summary className="cursor-pointer px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300">
        Transactions ({txs.length})
      </summary>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead className="bg-gray-50 dark:bg-gray-800/50 text-gray-500">
            <tr>
              <th className="text-left px-3 py-1.5">Date</th>
              <th className="text-left px-3 py-1.5">Symbol</th>
              <th className="text-left px-3 py-1.5">Side</th>
              <th className="text-right px-3 py-1.5">Qty</th>
              <th className="text-right px-3 py-1.5">Price</th>
              <th className="text-right px-3 py-1.5">Fees</th>
              <th className="text-left px-3 py-1.5">Source</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {txs.map((t) => (
              <tr key={t.id} className="border-t border-gray-100 dark:border-white/5">
                <td className="px-3 py-1.5">{String(t.tradedAt).slice(0, 10)}</td>
                <td className="px-3 py-1.5 font-medium">{t.symbol}</td>
                <td className={`px-3 py-1.5 font-semibold ${
                  t.side === "BUY" ? TONE.pos : t.side === "SELL" ? TONE.neg : TONE.mute
                }`}>{t.side}</td>
                <td className="px-3 py-1.5 text-right">{t.qty}</td>
                <td className="px-3 py-1.5 text-right">₹{fmtNum(t.price)}</td>
                <td className="px-3 py-1.5 text-right">₹{fmtNum(t.fees)}</td>
                <td className="px-3 py-1.5 text-gray-400">{t.source}</td>
                <td className="px-3 py-1.5 text-right">
                  <button onClick={() => onDelete(t.id)} className="text-gray-400 hover:text-rose-500">
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}

// ── Add transaction modal ────────────────────────────────────────────────────

function Modal({ children, onClose, title }: { children: React.ReactNode; onClose: () => void; title: string }) {
  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
      <div className="bg-white dark:bg-gray-900 rounded-xl shadow-2xl w-full max-w-md max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100 dark:border-white/10">
          <h3 className="font-semibold text-gray-900 dark:text-white">{title}</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="p-4">{children}</div>
      </div>
    </div>
  );
}

function AddTxModal({ pid, onClose }: { pid: string; onClose: () => void }) {
  const qc = useQueryClient();
  const [form, setForm] = useState({
    symbol: "", side: "BUY" as "BUY" | "SELL" | "DIVIDEND",
    qty: 0, price: 0, fees: 0, tradedAt: new Date().toISOString().slice(0, 10),
  });
  const mut = useMutation({
    mutationFn: () => api.addPortfolioTx(pid, {
      ...form,
      symbol: form.symbol.trim().toUpperCase(),
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["portfolio-valuation", pid] });
      qc.invalidateQueries({ queryKey: ["portfolio-tx", pid] });
      onClose();
    },
  });

  return (
    <Modal onClose={onClose} title="Add transaction">
      <div className="space-y-3">
        <input value={form.symbol} onChange={(e) => setForm(f => ({ ...f, symbol: e.target.value }))}
          placeholder="Symbol (e.g. RELIANCE)"
          className="w-full px-3 py-2 text-sm bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-white/10 rounded" />
        <div className="grid grid-cols-3 gap-2">
          {(["BUY", "SELL", "DIVIDEND"] as const).map(s => (
            <button key={s} onClick={() => setForm(f => ({ ...f, side: s }))}
              className={`px-3 py-2 text-sm rounded font-medium border ${
                form.side === s
                  ? "bg-indigo-600 text-white border-indigo-600"
                  : "bg-gray-50 dark:bg-gray-800 border-gray-200 dark:border-white/10 text-gray-700 dark:text-gray-300"
              }`}>{s}</button>
          ))}
        </div>
        <div className="grid grid-cols-2 gap-2">
          <input type="number" step="any" value={form.qty}
            onChange={(e) => setForm(f => ({ ...f, qty: parseFloat(e.target.value) || 0 }))}
            placeholder="Qty"
            className="px-3 py-2 text-sm bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-white/10 rounded" />
          <input type="number" step="any" value={form.price}
            onChange={(e) => setForm(f => ({ ...f, price: parseFloat(e.target.value) || 0 }))}
            placeholder={form.side === "DIVIDEND" ? "Per-share dividend ₹" : "Price ₹"}
            className="px-3 py-2 text-sm bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-white/10 rounded" />
          <input type="number" step="any" value={form.fees}
            onChange={(e) => setForm(f => ({ ...f, fees: parseFloat(e.target.value) || 0 }))}
            placeholder="Fees ₹"
            className="px-3 py-2 text-sm bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-white/10 rounded" />
          <input type="date" value={form.tradedAt}
            onChange={(e) => setForm(f => ({ ...f, tradedAt: e.target.value }))}
            className="px-3 py-2 text-sm bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-white/10 rounded" />
        </div>
        {mut.isError && <p className="text-xs text-rose-500">{(mut.error as Error).message}</p>}
        <button onClick={() => mut.mutate()} disabled={!form.symbol || !form.qty || !form.price || mut.isPending}
          className="w-full py-2 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-sm font-medium rounded">
          {mut.isPending ? <Loader2 className="w-4 h-4 animate-spin inline" /> : "Add transaction"}
        </button>
      </div>
    </Modal>
  );
}

// ── CSV import modal ─────────────────────────────────────────────────────────

function ImportCsvModal({ pid, onClose }: { pid: string; onClose: () => void }) {
  const qc = useQueryClient();
  const [csv, setCsv] = useState("");
  const [pickedFile, setPickedFile] = useState<File | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const [result, setResult] = useState<(PortfolioImportResult & { source_filename?: string }) | null>(null);

  // .xlsx is binary — must go via multipart upload.  CSV/TXT can either go
  // via paste-textarea (legacy JSON path) or via file upload.  Routing on
  // pickedFile preserves both flows.
  const mut = useMutation({
    mutationFn: () => pickedFile
      ? api.importPortfolioFile(pid, pickedFile)
      : api.importPortfolioCsv(pid, csv),
    onSuccess: (res) => {
      setResult(res);
      qc.invalidateQueries({ queryKey: ["portfolio-valuation", pid] });
      qc.invalidateQueries({ queryKey: ["portfolio-tx", pid] });
    },
  });

  const onFile = (f: File) => {
    setPickedFile(f);
    // Binary spreadsheet formats — never try to read as text.  Match the
    // backend allow-list (.xlsx, .xlsm) so .xlsm doesn't fall into the
    // FileReader text path and arrive as garbled UTF-8.
    const isBinarySheet = /\.(xlsx|xlsm)$/i.test(f.name);
    if (isBinarySheet) {
      setCsv(`[Excel file selected: ${f.name} — will be uploaded as-is]`);
    } else {
      const r = new FileReader();
      r.onload = (e) => setCsv(String(e.target?.result ?? ""));
      r.readAsText(f);
    }
  };

  return (
    <Modal onClose={onClose} title="Import tradebook (CSV or Excel)">
      <div className="space-y-3">
        <p className="text-xs text-gray-500">
          Drop in a Zerodha Console export, an Upstox tradebook, or any
          CSV/XLSX with
          <code className="mx-1 px-1 bg-gray-100 dark:bg-gray-800 rounded">symbol, side, qty, price, date</code>
          columns.
        </p>
        <input ref={fileRef} type="file"
          accept=".csv,.xlsx,.xlsm,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          className="hidden"
          onChange={(e) => e.target.files?.[0] && onFile(e.target.files[0])} />
        <button onClick={() => fileRef.current?.click()}
          className="w-full px-3 py-2 text-sm bg-gray-50 dark:bg-gray-800 border border-dashed border-gray-300 dark:border-white/15 rounded hover:bg-gray-100 dark:hover:bg-gray-800/70">
          <Upload className="w-3.5 h-3.5 inline mr-1" />
          {pickedFile ? `Selected: ${pickedFile.name}` : "Choose CSV or Excel file…"}
        </button>
        <textarea
          value={csv} onChange={(e) => { setCsv(e.target.value); setPickedFile(null); }}
          placeholder="…or paste CSV content here"
          rows={8}
          className="w-full px-3 py-2 text-xs font-mono bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-white/10 rounded"
        />
        {result && (
          <div className="text-xs bg-gray-50 dark:bg-gray-800/40 border border-gray-200 dark:border-white/10 rounded p-2 space-y-1">
            {result.source_filename && <p>File: <span className="font-medium">{result.source_filename}</span></p>}
            <p>Format detected: <span className="font-medium">{result.format}</span></p>
            <p>Rows parsed: <span className="font-medium">{result.rowsParsed}</span> · inserted: <span className="font-medium text-emerald-500">{result.rowsInserted}</span></p>
            {result.errors.length > 0 && (
              <details>
                <summary className="cursor-pointer text-amber-500">{result.errors.length} warnings</summary>
                <ul className="list-disc pl-4 max-h-24 overflow-y-auto">
                  {result.errors.slice(0, 20).map((e, i) => <li key={i}>{e}</li>)}
                </ul>
              </details>
            )}
          </div>
        )}
        <div className="flex gap-2">
          <button onClick={() => mut.mutate()}
            disabled={(!csv.trim() && !pickedFile) || mut.isPending}
            className="flex-1 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-sm font-medium rounded">
            {mut.isPending ? <Loader2 className="w-4 h-4 animate-spin inline" /> : "Import"}
          </button>
          <button onClick={onClose}
            className="px-4 py-2 text-sm border border-gray-200 dark:border-white/10 rounded">Close</button>
        </div>
      </div>
    </Modal>
  );
}

// ── Allocation tab ───────────────────────────────────────────────────────────

function AllocationTab({ pid }: { pid: string }) {
  const v = useValuation(pid);
  if (v.isLoading) return <Loading />;
  const a = v.data?.allocation;
  if (!a || ((a.sector?.length ?? 0) === 0 && (a.marketCap?.length ?? 0) === 0)) {
    return <div className="p-8 text-center text-gray-400">Add holdings to see allocation breakdowns.</div>;
  }
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <AllocationCard title="By Sector"      slices={a.sector} />
      <AllocationCard title="By Market Cap"  slices={a.marketCap} />
    </div>
  );
}

function AllocationCard({ title, slices }: { title: string; slices: { label: string; value: number; weight: number }[] }) {
  return (
    <div className="bg-white dark:bg-gray-900 border border-gray-100 dark:border-white/10 rounded-xl p-4">
      <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-2">{title}</h3>
      <div className="h-64">
        <ResponsiveContainer>
          <PieChart>
            <Pie data={slices} dataKey="value" nameKey="label" outerRadius={90} innerRadius={45} paddingAngle={2}>
              {slices.map((_, i) => <Cell key={i} fill={SECTOR_COLORS[i % SECTOR_COLORS.length]} />)}
            </Pie>
            <Tooltip formatter={(v: any) => `₹${fmtINR(Number(v))}`} />
          </PieChart>
        </ResponsiveContainer>
      </div>
      <ul className="space-y-1 mt-2">
        {slices.map((s, i) => (
          <li key={s.label} className="flex items-center justify-between text-xs">
            <span className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full" style={{ background: SECTOR_COLORS[i % SECTOR_COLORS.length] }} />
              <span className="text-gray-700 dark:text-gray-300">{s.label}</span>
            </span>
            <span className="font-medium text-gray-900 dark:text-white">{(s.weight * 100).toFixed(1)}%</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

// ── Risk tab ─────────────────────────────────────────────────────────────────

function RiskTab({ pid }: { pid: string }) {
  const [confidence, setConfidence] = useState(0.95);
  const [horizonDays, setHorizonDays] = useState(1);
  const [risk, setRisk] = useState<PortfolioRiskResult | null>(null);
  const mut = useMutation({
    mutationFn: () => api.portfolioRisk(pid, { confidence, horizonDays, lookbackDays: 365 }),
    onSuccess:  (r) => setRisk(r),
  });
  useEffect(() => { mut.mutate(); /* eslint-disable-next-line */ }, [pid]);

  return (
    <div className="space-y-4">
      <div className="bg-white dark:bg-gray-900 border border-gray-100 dark:border-white/10 rounded-xl p-3 flex flex-wrap items-end gap-3">
        <label className="text-xs">
          <span className="block text-gray-500">Confidence</span>
          <select value={confidence} onChange={(e) => setConfidence(parseFloat(e.target.value))}
            className="px-2 py-1 text-sm bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-white/10 rounded">
            <option value={0.90}>90%</option><option value={0.95}>95%</option><option value={0.99}>99%</option>
          </select>
        </label>
        <label className="text-xs">
          <span className="block text-gray-500">Horizon (days)</span>
          <input type="number" value={horizonDays} min={1} max={30}
            onChange={(e) => setHorizonDays(parseInt(e.target.value) || 1)}
            className="w-20 px-2 py-1 text-sm bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-white/10 rounded" />
        </label>
        <button onClick={() => mut.mutate()} disabled={mut.isPending}
          className="px-3 py-1.5 text-sm bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white rounded">
          {mut.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin inline" /> : "Recompute"}
        </button>
      </div>

      {!risk && mut.isPending && <Loading />}
      {risk && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Kpi label={`VaR ${((risk.var.confidence ?? confidence) * 100).toFixed(0)}%`}
                 value={`₹${fmtINR(Number(risk.var.valueAtRisk ?? 0))}`}
                 sub={`${fmtNum(Number(risk.var.varPct ?? 0))}%`} accent={TONE.neg} />
            <Kpi label="CVaR (Tail Loss)"
                 value={`${fmtNum(Number(risk.var.cvarPct ?? 0))}%`} accent={TONE.neg} />
            <Kpi label="Sharpe (portfolio)"
                 value={fmtNum(risk.portfolio.sharpe, 2)}
                 sub={`σ ${fmtNum(risk.portfolio.annualVolatility, 2)}%`} />
            <Kpi label="Sortino (portfolio)"
                 value={fmtNum(risk.portfolio.sortino, 2)}
                 sub={`Max DD ${fmtNum(risk.portfolio.maxDrawdownPct, 2)}%`} />
          </div>

          <div className="bg-white dark:bg-gray-900 border border-gray-100 dark:border-white/10 rounded-xl overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 dark:bg-gray-800/50 text-gray-500 text-xs">
                <tr>
                  <th className="text-left px-3 py-2">Symbol</th>
                  <th className="text-right px-3 py-2">Weight</th>
                  <th className="text-right px-3 py-2">Sharpe</th>
                  <th className="text-right px-3 py-2">Sortino</th>
                  <th className="text-right px-3 py-2">Annual σ</th>
                  <th className="text-right px-3 py-2">Max DD</th>
                </tr>
              </thead>
              <tbody>
                {risk.perPosition.map(p => (
                  <tr key={p.symbol} className="border-t border-gray-100 dark:border-white/5">
                    <td className="px-3 py-2 font-semibold">{p.symbol}</td>
                    <td className="text-right px-3 py-2">{(p.weight * 100).toFixed(1)}%</td>
                    <td className="text-right px-3 py-2">{fmtNum(p.sharpe, 2)}</td>
                    <td className="text-right px-3 py-2">{fmtNum(p.sortino, 2)}</td>
                    <td className="text-right px-3 py-2">{fmtNum(p.annualVolatility, 2)}%</td>
                    <td className="text-right px-3 py-2 text-rose-500">{fmtNum(p.maxDrawdownPct, 2)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
      {mut.isError && <ErrorBox msg={(mut.error as Error).message} />}
    </div>
  );
}

// ── Optimizer tab ────────────────────────────────────────────────────────────

function OptimizerTab({ pid }: { pid: string }) {
  const [method, setMethod] = useState<"markowitz" | "cvar" | "min_vol">("markowitz");
  const [universe, setUniverse] = useState("");
  const [confidence, setConfidence] = useState(0.95);
  const [opt, setOpt] = useState<PortfolioOptimizeResult | null>(null);

  const mut = useMutation({
    mutationFn: () => api.portfolioOptimize(pid, {
      method, confidence,
      universe: universe.split(/[,\s]+/).map(s => s.trim()).filter(Boolean),
    }),
    onSuccess: (r) => setOpt(r),
  });

  return (
    <div className="space-y-4">
      <div className="bg-white dark:bg-gray-900 border border-gray-100 dark:border-white/10 rounded-xl p-3 space-y-3">
        <div className="flex flex-wrap items-end gap-3">
          <label className="text-xs">
            <span className="block text-gray-500">Method</span>
            <select value={method} onChange={(e) => setMethod(e.target.value as any)}
              className="px-2 py-1 text-sm bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-white/10 rounded">
              <option value="markowitz">Markowitz (Max Sharpe)</option>
              <option value="min_vol">Min Variance</option>
              <option value="cvar">Min CVaR</option>
            </select>
          </label>
          {method === "cvar" && (
            <label className="text-xs">
              <span className="block text-gray-500">Confidence</span>
              <select value={confidence} onChange={(e) => setConfidence(parseFloat(e.target.value))}
                className="px-2 py-1 text-sm bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-white/10 rounded">
                <option value={0.90}>90%</option><option value={0.95}>95%</option><option value={0.99}>99%</option>
              </select>
            </label>
          )}
          <label className="text-xs flex-1 min-w-[14rem]">
            <span className="block text-gray-500">Add tickers to universe (optional)</span>
            <input value={universe} onChange={(e) => setUniverse(e.target.value)}
              placeholder="HDFCBANK, INFY, TCS …"
              className="w-full px-2 py-1 text-sm bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-white/10 rounded" />
          </label>
          <button onClick={() => mut.mutate()} disabled={mut.isPending}
            className="px-3 py-1.5 text-sm bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white rounded">
            {mut.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin inline" /> : "Optimize"}
          </button>
        </div>
        <p className="text-[11px] text-gray-500">
          Long-only, fully-invested. Markowitz uses 252-day log returns; CVaR uses
          historical-simulation Rockafellar-Uryasev. Trades below ₹100 notional are filtered.
        </p>
      </div>

      {mut.isError && <ErrorBox msg={(mut.error as Error).message} />}
      {!opt && mut.isPending && <Loading />}
      {opt && <OptimizerResult opt={opt} />}
    </div>
  );
}

function OptimizerResult({ opt }: { opt: PortfolioOptimizeResult }) {
  const frontierData = opt.frontier?.frontier?.map(p => ({
    risk: p.volatility * 100, ret: p.expectedReturn * 100, sharpe: p.sharpe,
  })) ?? [];
  const tangency = opt.frontier?.maxSharpe
    ? [{ risk: opt.frontier.maxSharpe.volatility * 100, ret: opt.frontier.maxSharpe.expectedReturn * 100 }]
    : [];
  const minVol = opt.frontier?.minVol
    ? [{ risk: opt.frontier.minVol.volatility * 100, ret: opt.frontier.minVol.expectedReturn * 100 }]
    : [];

  const targetEntries = Object.entries(opt.targetWeights).sort((a, b) => b[1] - a[1]);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
      {opt.frontier ? (
        <div className="lg:col-span-2 bg-white dark:bg-gray-900 border border-gray-100 dark:border-white/10 rounded-xl p-4">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-2">Efficient Frontier</h3>
          <div className="h-72">
            <ResponsiveContainer>
              <ScatterChart margin={{ top: 10, right: 20, left: 0, bottom: 10 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#94a3b820" />
                <XAxis dataKey="risk" name="Volatility" unit="%" tick={{ fontSize: 11 }}
                  label={{ value: "Annual Volatility (%)", position: "insideBottom", offset: -5, fontSize: 11 }} />
                <YAxis dataKey="ret" name="Return" unit="%" tick={{ fontSize: 11 }}
                  label={{ value: "Expected Return (%)", angle: -90, position: "insideLeft", fontSize: 11 }} />
                <ZAxis range={[60, 60]} />
                <Tooltip cursor={{ strokeDasharray: "3 3" }}
                  formatter={(v: any, n: any) => [`${Number(v).toFixed(2)}%`, n]} />
                <Scatter name="Frontier" data={frontierData} fill="#6366f1" />
                <Scatter name="Max Sharpe" data={tangency} fill="#10b981" shape="star" />
                <Scatter name="Min Vol" data={minVol} fill="#f59e0b" shape="diamond" />
                <Legend />
              </ScatterChart>
            </ResponsiveContainer>
          </div>
        </div>
      ) : (
        <div className="lg:col-span-2 bg-white dark:bg-gray-900 border border-gray-100 dark:border-white/10 rounded-xl p-4">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-2">CVaR-Optimal Portfolio</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Kpi label="Expected Return"  value={`${fmtNum(opt.result?.expectedReturn ? opt.result.expectedReturn * 100 : null, 2)}%`} accent={TONE.pos} />
            <Kpi label="Volatility"       value={`${fmtNum(opt.result?.volatility    ? opt.result.volatility    * 100 : null, 2)}%`} />
            <Kpi label="CVaR (daily)"     value={`${fmtNum(opt.result?.cvarPct, 2)}%`} accent={TONE.neg} />
            <Kpi label="Sharpe"           value={fmtNum(opt.result?.sharpe, 2)} />
          </div>
        </div>
      )}

      <div className="bg-white dark:bg-gray-900 border border-gray-100 dark:border-white/10 rounded-xl p-4">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-2">Target Weights</h3>
        <ul className="space-y-1.5 max-h-72 overflow-y-auto pr-1">
          {targetEntries.map(([sym, w]) => (
            <li key={sym} className="flex items-center justify-between text-sm">
              <span className="font-medium text-gray-900 dark:text-white">{sym}</span>
              <div className="flex items-center gap-2 flex-1 ml-3">
                <div className="flex-1 h-1.5 bg-gray-100 dark:bg-gray-800 rounded">
                  <div className="h-full bg-indigo-500 rounded" style={{ width: `${Math.max(0, Math.min(100, w * 100))}%` }} />
                </div>
                <span className="text-xs font-semibold text-gray-700 dark:text-gray-300 w-10 text-right">
                  {(w * 100).toFixed(1)}%
                </span>
              </div>
            </li>
          ))}
        </ul>
      </div>

      <div className="lg:col-span-3 bg-white dark:bg-gray-900 border border-gray-100 dark:border-white/10 rounded-xl p-4">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-2 flex items-center gap-2">
          <Edit3 className="w-4 h-4 text-indigo-500" /> Suggested Rebalance Trades
          <span className="text-[11px] text-gray-400 font-normal">
            (current equity ₹{fmtINR(opt.equity)})
          </span>
        </h3>
        {opt.trades.length === 0 ? (
          <p className="text-sm text-gray-500">Already balanced — no trades suggested above the ₹100 threshold.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 dark:bg-gray-800/50 text-gray-500 text-xs">
                <tr>
                  <th className="text-left  px-3 py-2">Symbol</th>
                  <th className="text-left  px-3 py-2">Action</th>
                  <th className="text-right px-3 py-2">Qty</th>
                  <th className="text-right px-3 py-2">Price</th>
                  <th className="text-right px-3 py-2">Notional</th>
                  <th className="text-right px-3 py-2">Current → Target</th>
                </tr>
              </thead>
              <tbody>
                {opt.trades.map((t) => (
                  <tr key={t.symbol} className="border-t border-gray-100 dark:border-white/5">
                    <td className="px-3 py-2 font-semibold">{t.symbol}</td>
                    <td className={`px-3 py-2 font-bold ${t.side === "BUY" ? TONE.pos : TONE.neg}`}>{t.side}</td>
                    <td className="text-right px-3 py-2">{t.qty}</td>
                    <td className="text-right px-3 py-2">₹{fmtNum(t.price)}</td>
                    <td className="text-right px-3 py-2">₹{fmtINR(t.notional)}</td>
                    <td className="text-right px-3 py-2">
                      <span className="text-gray-500">{(t.currentWeight * 100).toFixed(1)}%</span>
                      {" → "}
                      <span className="font-medium text-indigo-500">{(t.targetWeight * 100).toFixed(1)}%</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Performance tab ──────────────────────────────────────────────────────────

function PerformanceTab({ pid }: { pid: string }) {
  const [benchmark, setBenchmark] = useState("NIFTY 50");
  const [days, setDays] = useState(365);
  const q = useQuery<PortfolioPerformance>({
    queryKey: ["portfolio-performance", pid, benchmark, days],
    queryFn:  () => api.portfolioPerformance(pid, benchmark, days),
  });

  const merged = useMemo(() => {
    if (!q.data) return [];
    const benchMap = new Map(q.data.benchmarkSeries.map(b => [b.date, b.value]));
    return q.data.series.map(p => ({
      date: p.date,
      equity: p.equity,
      benchmark: benchMap.get(p.date),
    }));
  }, [q.data]);

  return (
    <div className="space-y-4">
      <div className="bg-white dark:bg-gray-900 border border-gray-100 dark:border-white/10 rounded-xl p-3 flex flex-wrap items-end gap-3">
        <label className="text-xs">
          <span className="block text-gray-500">Benchmark</span>
          <select value={benchmark} onChange={(e) => setBenchmark(e.target.value)}
            className="px-2 py-1 text-sm bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-white/10 rounded">
            <option>NIFTY 50</option>
            <option>NIFTY BANK</option>
            <option>NIFTY MIDCAP 100</option>
            <option>NIFTY SMALLCAP 100</option>
          </select>
        </label>
        <label className="text-xs">
          <span className="block text-gray-500">Lookback (days)</span>
          <select value={days} onChange={(e) => setDays(parseInt(e.target.value))}
            className="px-2 py-1 text-sm bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-white/10 rounded">
            <option value={90}>3M</option><option value={180}>6M</option>
            <option value={365}>1Y</option><option value={730}>2Y</option>
          </select>
        </label>
      </div>
      <div className="bg-white dark:bg-gray-900 border border-gray-100 dark:border-white/10 rounded-xl p-4">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-2 flex items-center gap-2">
          <BarChart3 className="w-4 h-4 text-indigo-500" /> Equity vs {q.data?.benchmark ?? benchmark}
        </h3>
        {q.isLoading ? <Loading /> : merged.length === 0 ? (
          <p className="text-sm text-gray-500">Need transaction history to draw an equity curve.</p>
        ) : (
          <div className="h-80">
            <ResponsiveContainer>
              <ComposedChart data={merged} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="eqGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%"  stopColor="#6366f1" stopOpacity={0.4} />
                    <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#94a3b820" />
                <XAxis dataKey="date" tick={{ fontSize: 10 }} minTickGap={40} />
                <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => `₹${fmtINR(v)}`} />
                <Tooltip formatter={(v: any) => `₹${fmtINR(Number(v))}`} />
                <Legend />
                <Area type="monotone" dataKey="equity"    name="Portfolio" stroke="#6366f1" fill="url(#eqGrad)" />
                <Line type="monotone" dataKey="benchmark" name={q.data?.benchmark ?? benchmark} stroke="#f59e0b" dot={false} strokeDasharray="4 4" />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Misc helpers ─────────────────────────────────────────────────────────────

function Loading() {
  return (
    <div className="p-12 text-center text-gray-400 flex items-center justify-center gap-2">
      <Loader2 className="w-4 h-4 animate-spin" /> Crunching numbers…
    </div>
  );
}

function ErrorBox({ msg }: { msg: string }) {
  return (
    <div className="bg-rose-50 dark:bg-rose-500/10 border border-rose-200 dark:border-rose-500/30 rounded-lg p-3 flex items-start gap-2">
      <AlertTriangle className="w-4 h-4 text-rose-600 dark:text-rose-400 mt-0.5 flex-shrink-0" />
      <div className="text-sm text-rose-800 dark:text-rose-200">{msg}</div>
    </div>
  );
}

