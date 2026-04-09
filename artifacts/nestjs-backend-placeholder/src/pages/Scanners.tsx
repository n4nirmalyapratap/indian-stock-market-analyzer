import { useState, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type ConditionSide, type Condition, type Scanner, type ScanResult, type ScannerCreateInput } from "@/lib/api";
import {
  Play, Plus, Trash2, Save, TrendingUp, TrendingDown,
  Zap, AlertCircle, CheckCircle2, X, Copy, Edit2,
  Filter, BarChart2, Loader2, Target,
} from "lucide-react";
import ChartButton from "@/components/ChartButton";

// ─── Indicator Definitions ───────────────────────────────────────────────────

const INDICATOR_GROUPS = [
  { label: "Price",           color: "blue",   items: [
    { value: "CLOSE",       label: "Close",          hasPeriod: false },
    { value: "OPEN",        label: "Open",           hasPeriod: false },
    { value: "HIGH",        label: "High",           hasPeriod: false },
    { value: "LOW",         label: "Low",            hasPeriod: false },
    { value: "PREV_CLOSE",  label: "Prev Close",     hasPeriod: false },
    { value: "CHANGE_PCT",  label: "Change %",       hasPeriod: false },
  ]},
  { label: "Volume",          color: "cyan",   items: [
    { value: "VOLUME",       label: "Volume",         hasPeriod: false },
    { value: "AVG_VOLUME",   label: "Avg Volume",     hasPeriod: true, defaultPeriod: 20 },
    { value: "VOLUME_RATIO", label: "Volume Ratio %", hasPeriod: false },
  ]},
  { label: "Moving Averages", color: "green",  items: [
    { value: "EMA", label: "EMA", hasPeriod: true, defaultPeriod: 20 },
    { value: "SMA", label: "SMA", hasPeriod: true, defaultPeriod: 20 },
  ]},
  { label: "Oscillators",     color: "purple", items: [
    { value: "RSI",         label: "RSI",         hasPeriod: true, defaultPeriod: 14 },
    { value: "MACD",        label: "MACD Line",   hasPeriod: false },
    { value: "MACD_SIGNAL", label: "MACD Signal", hasPeriod: false },
    { value: "MACD_HIST",   label: "MACD Hist",   hasPeriod: false },
  ]},
  { label: "Bollinger Bands", color: "orange", items: [
    { value: "BB_UPPER", label: "BB Upper",  hasPeriod: true, defaultPeriod: 20 },
    { value: "BB_MID",   label: "BB Middle", hasPeriod: true, defaultPeriod: 20 },
    { value: "BB_LOWER", label: "BB Lower",  hasPeriod: true, defaultPeriod: 20 },
  ]},
  { label: "Volatility",      color: "red",    items: [
    { value: "ATR", label: "ATR", hasPeriod: true, defaultPeriod: 14 },
  ]},
  { label: "Market",          color: "teal",   items: [
    { value: "HIGH_52W",     label: "52W High",        hasPeriod: false },
    { value: "LOW_52W",      label: "52W Low",         hasPeriod: false },
    { value: "PCT_52W_HIGH", label: "% from 52W High", hasPeriod: false },
    { value: "PCT_52W_LOW",  label: "% from 52W Low",  hasPeriod: false },
  ]},
  { label: "Constant Value",  color: "gray",   items: [
    { value: "NUMBER", label: "Number", hasPeriod: false, isNumber: true },
  ]},
];

interface IndicatorItem {
  value: string; label: string; hasPeriod: boolean;
  defaultPeriod?: number; isNumber?: boolean;
  group: string; color: string;
}
const ALL_INDICATORS: IndicatorItem[] = INDICATOR_GROUPS.flatMap(g =>
  g.items.map(i => ({ ...i, group: g.label, color: g.color }))
);

// Color map for indicator categories
const CAT_COLORS: Record<string, { bg: string; text: string; border: string }> = {
  blue:   { bg: "bg-blue-50",   text: "text-blue-700",   border: "border-blue-200"   },
  cyan:   { bg: "bg-cyan-50",   text: "text-cyan-700",   border: "border-cyan-200"   },
  green:  { bg: "bg-green-50",  text: "text-green-700",  border: "border-green-200"  },
  purple: { bg: "bg-purple-50", text: "text-purple-700", border: "border-purple-200" },
  orange: { bg: "bg-orange-50", text: "text-orange-700", border: "border-orange-200" },
  red:    { bg: "bg-red-50",    text: "text-red-700",    border: "border-red-200"    },
  teal:   { bg: "bg-teal-50",   text: "text-teal-700",   border: "border-teal-200"   },
  gray:   { bg: "bg-gray-50",   text: "text-gray-700",   border: "border-gray-200"   },
};

const OPERATORS = [
  { value: "gt",            label: "Greater than",    short: ">"  },
  { value: "gte",           label: "Greater or equal",short: "≥"  },
  { value: "lt",            label: "Less than",       short: "<"  },
  { value: "lte",           label: "Less or equal",   short: "≤"  },
  { value: "eq",            label: "Equal to",        short: "="  },
  { value: "crosses_above", label: "Crosses above",   short: "↗"  },
  { value: "crosses_below", label: "Crosses below",   short: "↘"  },
];

// Quick-add condition templates
const TEMPLATES = [
  { label: "RSI Oversold",       conditions: [{ left: { type:"indicator", indicator:"RSI", period:14 }, operator:"lt", right: { type:"number", value:35 } }] },
  { label: "RSI Overbought",     conditions: [{ left: { type:"indicator", indicator:"RSI", period:14 }, operator:"gt", right: { type:"number", value:70 } }] },
  { label: "Above EMA 50",       conditions: [{ left: { type:"indicator", indicator:"CLOSE" }, operator:"gt", right: { type:"indicator", indicator:"EMA", period:50 } }] },
  { label: "EMA Cross 20/50",    conditions: [{ left: { type:"indicator", indicator:"EMA", period:20 }, operator:"crosses_above", right: { type:"indicator", indicator:"EMA", period:50 } }] },
  { label: "MACD Bullish",       conditions: [{ left: { type:"indicator", indicator:"MACD" }, operator:"crosses_above", right: { type:"indicator", indicator:"MACD_SIGNAL" } }] },
  { label: "Volume Spike 2×",    conditions: [{ left: { type:"indicator", indicator:"VOLUME_RATIO" }, operator:"gte", right: { type:"number", value:200 } }] },
  { label: "Near 52W High",      conditions: [{ left: { type:"indicator", indicator:"PCT_52W_HIGH" }, operator:"gte", right: { type:"number", value:-5 } }] },
  { label: "BB Lower Bounce",    conditions: [{ left: { type:"indicator", indicator:"CLOSE" }, operator:"lte", right: { type:"indicator", indicator:"BB_LOWER", period:20 } }] },
];

// ─── Types ───────────────────────────────────────────────────────────────────

/** Local draft type for the builder form — mirrors ScannerCreateInput + required description */
type ScannerDraft = ScannerCreateInput & { description: string };

// ─── Helpers ─────────────────────────────────────────────────────────────────

const uid = () => Math.random().toString(36).slice(2, 9);

function indInfo(name?: string): IndicatorItem | undefined {
  return ALL_INDICATORS.find(i => i.value === name);
}

function defaultSide(indicator = "CLOSE"): ConditionSide {
  const info = indInfo(indicator);
  if (info?.isNumber) return { type: "number", indicator, value: 0 };
  return { type: "indicator", indicator, period: info?.hasPeriod ? (info.defaultPeriod ?? 20) : undefined };
}

function blankCondition(): Condition {
  return { id: uid(), left: defaultSide("CLOSE"), operator: "gt", right: defaultSide("EMA") };
}

function blankDraft(): ScannerDraft {
  return { name: "", description: "", universe: ["NIFTY100"], logic: "AND", conditions: [blankCondition()] };
}

function condSummary(c: Condition): string {
  function side(s: ConditionSide) {
    if (!s) return "?";
    if (s.type === "number") return `${s.value ?? 0}`;
    const info = indInfo(s.indicator);
    return s.period ? `${info?.label ?? s.indicator}(${s.period})` : (info?.label ?? s.indicator ?? "?");
  }
  const op = OPERATORS.find(o => o.value === c.operator);
  return `${side(c.left)} ${op?.short ?? c.operator} ${side(c.right)}`;
}

// ─── Indicator Picker Component ───────────────────────────────────────────────

function IndicatorPicker({ side, onChange, label }: {
  side: ConditionSide;
  onChange: (s: ConditionSide) => void;
  label: string;
}) {
  const info  = indInfo(side.indicator);
  const color = info ? CAT_COLORS[info.color ?? "gray"] : CAT_COLORS.gray;

  function handleChange(v: string) {
    const newInfo = indInfo(v);
    if (newInfo?.isNumber) return onChange({ type: "number", indicator: v, value: 0 });
    onChange({ type: "indicator", indicator: v, period: newInfo?.hasPeriod ? (newInfo.defaultPeriod ?? 20) : undefined });
  }

  return (
    <div className="flex-1 min-w-0">
      <p className="text-xs font-medium text-gray-400 mb-1">{label}</p>
      <div className={`flex items-center gap-2 rounded-lg border-2 px-3 py-2 ${color.border} ${color.bg}`}>
        {/* Category dot */}
        <div className={`w-2 h-2 rounded-full flex-shrink-0 ${color.text.replace("text-", "bg-").replace("-700", "-500")}`} />

        <select
          value={side.indicator ?? "CLOSE"}
          onChange={e => handleChange(e.target.value)}
          className={`flex-1 min-w-0 bg-transparent text-sm font-medium ${color.text} focus:outline-none cursor-pointer`}
        >
          {INDICATOR_GROUPS.map(g => (
            <optgroup key={g.label} label={g.label}>
              {g.items.map(i => <option key={i.value} value={i.value}>{i.label}</option>)}
            </optgroup>
          ))}
        </select>

        {/* Period */}
        {info?.hasPeriod && side.type === "indicator" && (
          <input
            type="number" min={1} max={500}
            value={side.period ?? info?.defaultPeriod ?? 20}
            onChange={e => onChange({ ...side, period: Math.max(1, parseInt(e.target.value) || 1) })}
            className={`w-12 text-center bg-white border ${color.border} rounded text-xs font-mono font-bold ${color.text} focus:outline-none focus:ring-1`}
            title="Period"
          />
        )}

        {/* Number value */}
        {info?.isNumber && (
          <input
            type="number" step="any"
            value={side.value ?? 0}
            onChange={e => onChange({ ...side, value: parseFloat(e.target.value) || 0 })}
            className="w-20 text-center bg-white border border-gray-200 rounded text-xs font-mono font-bold text-gray-700 focus:outline-none focus:ring-1 focus:ring-indigo-400"
            placeholder="Value"
          />
        )}
      </div>

      {/* Show current value label */}
      <p className={`text-xs mt-0.5 ${color.text} opacity-70`}>
        {info?.group ?? "Value"}
        {side.period ? ` · period ${side.period}` : ""}
      </p>
    </div>
  );
}

// ─── Single Condition Row ─────────────────────────────────────────────────────

function ConditionRow({ condition, index, logic, onChange, onDelete, total }: {
  condition: Condition; index: number; logic: "AND"|"OR";
  onChange: (c: Condition) => void; onDelete: () => void; total: number;
}) {
  const op = OPERATORS.find(o => o.value === condition.operator);

  return (
    <div className="relative bg-white border border-gray-200 rounded-xl p-4 shadow-sm">
      {/* Logic badge */}
      <div className="absolute -left-3 top-1/2 -translate-y-1/2">
        {index === 0 ? (
          <span className="text-xs font-bold text-gray-500 bg-gray-100 border border-gray-200 rounded-full px-2 py-0.5">IF</span>
        ) : (
          <span className={`text-xs font-bold rounded-full px-2 py-0.5 ${
            logic === "AND"
              ? "bg-indigo-100 text-indigo-700 border border-indigo-200"
              : "bg-amber-100 text-amber-700 border border-amber-200"
          }`}>{logic}</span>
        )}
      </div>

      <div className="flex items-start gap-3 pl-2">
        {/* Left indicator */}
        <IndicatorPicker side={condition.left} label="Indicator" onChange={left => onChange({ ...condition, left })} />

        {/* Operator */}
        <div className="flex-shrink-0 pt-1">
          <p className="text-xs font-medium text-gray-400 mb-1 text-center">Condition</p>
          <select
            value={condition.operator}
            onChange={e => onChange({ ...condition, operator: e.target.value })}
            className="block w-full text-center text-sm font-bold text-purple-700 bg-purple-50 border-2 border-purple-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-purple-300 cursor-pointer"
          >
            {OPERATORS.map(o => <option key={o.value} value={o.value}>{o.short} {o.label}</option>)}
          </select>
          <p className="text-xs mt-0.5 text-purple-500 text-center opacity-70">{op?.short} {op?.label}</p>
        </div>

        {/* Right indicator */}
        <IndicatorPicker side={condition.right} label="Compare to" onChange={right => onChange({ ...condition, right })} />

        {/* Delete */}
        <button
          onClick={onDelete}
          disabled={total <= 1}
          className="mt-6 p-1.5 rounded-lg text-gray-300 hover:text-red-400 hover:bg-red-50 disabled:opacity-20 transition flex-shrink-0"
          title="Remove condition"
        >
          <X className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}

// ─── Scanner Card (left panel) ────────────────────────────────────────────────

function ScannerCard({ scanner, isRunning, isSelected, onRun, onEdit, onDuplicate, onDelete, onSelect }: {
  scanner: Scanner; isRunning: boolean; isSelected: boolean;
  onRun: () => void; onEdit: () => void; onDuplicate: () => void; onDelete: () => void; onSelect: () => void;
}) {
  return (
    <div
      onClick={onSelect}
      className={`group cursor-pointer rounded-xl border-2 p-4 transition-all ${
        isSelected ? "border-indigo-400 bg-indigo-50 shadow-md" : "border-gray-200 bg-white hover:border-gray-300 hover:shadow-sm"
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="font-semibold text-gray-900 text-sm truncate">{scanner.name}</h3>
            <span className={`text-xs px-1.5 py-0.5 rounded-md font-bold ${
              scanner.logic === "AND" ? "bg-indigo-100 text-indigo-600" : "bg-amber-100 text-amber-600"
            }`}>{scanner.logic}</span>
          </div>
          {scanner.description && <p className="text-xs text-gray-500 mt-0.5 truncate">{scanner.description}</p>}

          {/* Universe badges */}
          <div className="flex gap-1 mt-1.5 flex-wrap">
            {scanner.universe?.map((u: string) => (
              <span key={u} className="text-xs bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded-md">{u}</span>
            ))}
            <span className="text-xs text-gray-400">{scanner.conditions?.length} condition{scanner.conditions?.length !== 1 ? "s" : ""}</span>
          </div>

          {/* Condition chips */}
          <div className="mt-2 space-y-1">
            {scanner.conditions?.slice(0, 3).map((c: any, i: number) => {
              const info = indInfo(c.left?.indicator);
              const col  = CAT_COLORS[info?.color ?? "gray"];
              return (
                <span key={i} className={`inline-block text-xs px-2 py-0.5 rounded-full font-mono mr-1 ${col.bg} ${col.text} border ${col.border}`}>
                  {condSummary(c)}
                </span>
              );
            })}
            {scanner.conditions?.length > 3 && (
              <span className="text-xs text-gray-400">+{scanner.conditions.length - 3} more</span>
            )}
          </div>

          {scanner.lastRunAt && (
            <p className="text-xs text-gray-400 mt-2">
              Last: {new Date(scanner.lastRunAt).toLocaleDateString("en-IN", { day:"2-digit", month:"short", hour:"2-digit", minute:"2-digit" })}
              {scanner.lastResultCount !== undefined && ` · ${scanner.lastResultCount} matched`}
            </p>
          )}
        </div>
      </div>

      {/* Action buttons */}
      <div className="flex items-center gap-1.5 mt-3">
        <button
          onClick={e => { e.stopPropagation(); onRun(); }}
          disabled={isRunning}
          className="flex items-center gap-1.5 flex-1 justify-center py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-semibold transition disabled:opacity-60"
        >
          {isRunning ? <Loader2 className="w-3 h-3 animate-spin" /> : <Play className="w-3 h-3" />}
          {isRunning ? "Running…" : "Run Scan"}
        </button>
        <button onClick={e => { e.stopPropagation(); onEdit(); }}    title="Edit"      className="p-1.5 rounded-lg text-gray-400 hover:text-indigo-600 hover:bg-indigo-50 border border-gray-200 transition"><Edit2  className="w-3.5 h-3.5" /></button>
        <button onClick={e => { e.stopPropagation(); onDuplicate();}} title="Duplicate" className="p-1.5 rounded-lg text-gray-400 hover:text-amber-600 hover:bg-amber-50  border border-gray-200 transition"><Copy   className="w-3.5 h-3.5" /></button>
        <button onClick={e => { e.stopPropagation(); onDelete(); }}   title="Delete"    className="p-1.5 rounded-lg text-gray-400 hover:text-red-500   hover:bg-red-50    border border-gray-200 transition"><Trash2 className="w-3.5 h-3.5" /></button>
      </div>
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

type RightPanel = "empty" | "builder" | "results";

export default function Scanners() {
  const qc = useQueryClient();

  // State
  const [rightPanel, setRightPanel] = useState<RightPanel>("empty");
  const [draft, setDraft]           = useState<ScannerDraft>(blankDraft());
  const [editingId, setEditingId]   = useState<string | null>(null);
  const [runningId, setRunningId]   = useState<string | null>(null);
  const [result, setResult]         = useState<ScanResult | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const { data: scanners = [], isLoading } = useQuery({
    queryKey: ["scanners"], queryFn: api.scanners, staleTime: 30_000,
  });

  const saveMut = useMutation({
    mutationFn: (d: ScannerDraft & { id?: string }) =>
      d.id ? api.updateScanner(d.id, d) : api.createScanner(d),
    onSuccess: (saved) => {
      qc.invalidateQueries({ queryKey: ["scanners"] });
      setEditingId(null); setDraft(blankDraft());
      setRightPanel("empty");
    },
  });

  const deleteMut = useMutation({
    mutationFn: api.deleteScanner,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["scanners"] });
      setRightPanel("empty"); setSelectedId(null);
    },
  });

  const runMut = useMutation({
    mutationFn: (id: string) => api.runScanner(id),
    onMutate:  (id) => { setRunningId(id); },
    onSuccess: (data) => { setResult(data); setRightPanel("results"); setRunningId(null); },
    onError:   () => setRunningId(null),
  });

  const testMut = useMutation({
    mutationFn: api.runAdHoc,
    onMutate:   () => { setRunningId("adhoc"); },
    onSuccess:  (data) => { setResult(data); setRightPanel("results"); setRunningId(null); },
    onError:    () => setRunningId(null),
  });

  // Condition helpers
  const updateCondition = useCallback((idx: number, c: Condition) =>
    setDraft(d => ({ ...d, conditions: d.conditions.map((x, i) => i === idx ? c : x) })), []);
  const deleteCondition = useCallback((idx: number) =>
    setDraft(d => ({ ...d, conditions: d.conditions.filter((_, i) => i !== idx) })), []);
  const addCondition    = useCallback(() =>
    setDraft(d => ({ ...d, conditions: [...d.conditions, blankCondition()] })), []);

  function addTemplate(tpl: typeof TEMPLATES[0]) {
    const newConds: Condition[] = tpl.conditions.map(c => ({ ...c, id: uid() } as Condition));
    setDraft(d => ({ ...d, conditions: [...d.conditions, ...newConds] }));
  }

  function startNew() {
    setDraft(blankDraft()); setEditingId(null); setRightPanel("builder");
  }

  function startEdit(scanner: any) {
    setDraft({
      name: scanner.name, description: scanner.description ?? "",
      universe: scanner.universe ?? ["NIFTY100"], logic: scanner.logic ?? "AND",
      conditions: scanner.conditions?.map((c: any) => ({ ...c, id: c.id || uid() })) ?? [],
    });
    setEditingId(scanner.id); setSelectedId(scanner.id); setRightPanel("builder");
  }

  function duplicate(scanner: any) {
    setDraft({
      name: `${scanner.name} (copy)`, description: scanner.description ?? "",
      universe: scanner.universe ?? ["NIFTY100"], logic: scanner.logic ?? "AND",
      conditions: scanner.conditions?.map((c: any) => ({ ...c, id: uid() })) ?? [],
    });
    setEditingId(null); setRightPanel("builder");
  }

  const canSave = draft.name.trim().length > 0 && draft.conditions.length > 0 && draft.universe.length > 0;

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <div className="h-full flex flex-col">
      {/* Page Header */}
      <div className="flex items-center justify-between mb-5 flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Stock Scanners</h1>
          <p className="text-sm text-gray-500">Build, save & run custom condition-based scans across any universe</p>
        </div>
        <button onClick={startNew}
          className="flex items-center gap-2 px-4 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-semibold hover:bg-indigo-700 transition shadow-sm">
          <Plus className="w-4 h-4" /> New Scanner
        </button>
      </div>

      {/* Split layout */}
      <div className="flex gap-5 flex-1 min-h-0">

        {/* ── LEFT: Scanner List ────────────────────────────────────────────── */}
        <div className="w-80 flex-shrink-0 flex flex-col gap-3 overflow-y-auto pb-4">
          {isLoading ? (
            [...Array(3)].map((_, i) => <div key={i} className="h-36 bg-gray-100 animate-pulse rounded-xl" />)
          ) : scanners.length === 0 ? (
            <div className="text-center py-12 text-gray-400 border-2 border-dashed border-gray-200 rounded-xl">
              <Filter className="w-8 h-8 mx-auto mb-2 opacity-30" />
              <p className="font-medium text-sm">No scanners yet</p>
              <p className="text-xs mt-1">Click "New Scanner" to start</p>
            </div>
          ) : (
            scanners.map((s: any) => (
              <ScannerCard
                key={s.id} scanner={s}
                isRunning={runningId === s.id}
                isSelected={selectedId === s.id}
                onRun={() => { setSelectedId(s.id); runMut.mutate(s.id); }}
                onEdit={() => startEdit(s)}
                onDuplicate={() => duplicate(s)}
                onDelete={() => { if (confirm(`Delete "${s.name}"?`)) deleteMut.mutate(s.id); }}
                onSelect={() => setSelectedId(s.id)}
              />
            ))
          )}
        </div>

        {/* ── RIGHT: Builder or Results ─────────────────────────────────────── */}
        <div className="flex-1 min-w-0 overflow-y-auto pb-4">

          {/* ── BUILDER ──────────────────────────────────────────────────────── */}
          {rightPanel === "builder" && (
            <div className="space-y-5">
              {/* Name + Description */}
              <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
                <h2 className="text-sm font-bold text-gray-700 uppercase tracking-wide mb-4">Scanner Details</h2>
                <div className="space-y-3">
                  <div>
                    <label className="block text-xs font-semibold text-gray-600 mb-1">Scanner Name *</label>
                    <input
                      value={draft.name}
                      onChange={e => setDraft(d => ({ ...d, name: e.target.value }))}
                      placeholder='e.g. "RSI Oversold + Volume Spike"'
                      className="w-full border-2 border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-indigo-400 transition"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-gray-600 mb-1">Description (optional)</label>
                    <input
                      value={draft.description}
                      onChange={e => setDraft(d => ({ ...d, description: e.target.value }))}
                      placeholder="Describe what this scanner finds…"
                      className="w-full border-2 border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-indigo-400 transition"
                    />
                  </div>
                </div>
              </div>

              {/* Universe + Logic */}
              <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
                <h2 className="text-sm font-bold text-gray-700 uppercase tracking-wide mb-4">Scan Settings</h2>
                <div className="flex flex-wrap gap-6">
                  <div>
                    <p className="text-xs font-semibold text-gray-600 mb-2">Stock Universe *</p>
                    <div className="flex gap-2">
                      {["NIFTY100", "MIDCAP", "SMALLCAP"].map(u => {
                        const active = draft.universe.includes(u);
                        return (
                          <button key={u} onClick={() => setDraft(d => ({
                            ...d,
                            universe: active ? d.universe.filter(x => x !== u) : [...d.universe, u]
                          }))}
                            className={`px-3 py-1.5 rounded-lg text-sm font-semibold border-2 transition ${
                              active
                                ? "bg-indigo-600 text-white border-indigo-600"
                                : "bg-white text-gray-600 border-gray-200 hover:border-indigo-300"
                            }`}
                          >{u}</button>
                        );
                      })}
                    </div>
                  </div>

                  <div>
                    <p className="text-xs font-semibold text-gray-600 mb-2">Condition Logic</p>
                    <div className="flex rounded-xl overflow-hidden border-2 border-gray-200">
                      {(["AND", "OR"] as const).map(l => (
                        <button key={l} onClick={() => setDraft(d => ({ ...d, logic: l }))}
                          className={`px-5 py-1.5 text-sm font-bold transition ${
                            draft.logic === l
                              ? l === "AND" ? "bg-indigo-600 text-white" : "bg-amber-500 text-white"
                              : "bg-white dark:bg-slate-700 text-gray-500 dark:text-slate-300 hover:bg-gray-50 dark:hover:bg-slate-600"
                          }`}>{l}</button>
                      ))}
                    </div>
                    <p className="text-xs text-gray-400 mt-1.5">
                      {draft.logic === "AND" ? "✓ All conditions must pass" : "✓ Any condition can pass"}
                    </p>
                  </div>
                </div>
              </div>

              {/* Conditions */}
              <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
                <div className="flex items-center justify-between mb-3">
                  <div>
                    <h2 className="text-sm font-bold text-gray-700 uppercase tracking-wide">Conditions</h2>
                    <p className="text-xs text-gray-400 mt-0.5">
                      {draft.conditions.length} condition{draft.conditions.length !== 1 ? "s" : ""}
                      {" · "}{draft.logic === "AND" ? "All must pass" : "Any can pass"}
                    </p>
                  </div>
                </div>

                {/* Condition rows */}
                <div className="space-y-3 pl-4">
                  {draft.conditions.map((c, i) => (
                    <ConditionRow
                      key={c.id} condition={c} index={i} logic={draft.logic} total={draft.conditions.length}
                      onChange={nc => updateCondition(i, nc)}
                      onDelete={() => deleteCondition(i)}
                    />
                  ))}
                </div>

                {/* Add condition */}
                <button onClick={addCondition}
                  className="mt-4 w-full flex items-center justify-center gap-2 py-2.5 border-2 border-dashed border-gray-200 rounded-xl text-sm text-gray-500 hover:border-indigo-300 hover:text-indigo-600 hover:bg-indigo-50 transition">
                  <Plus className="w-4 h-4" /> Add Condition
                </button>
              </div>

              {/* Quick templates */}
              <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
                <h2 className="text-sm font-bold text-gray-700 uppercase tracking-wide mb-3">Quick Add from Templates</h2>
                <div className="flex flex-wrap gap-2">
                  {TEMPLATES.map(t => (
                    <button key={t.label} onClick={() => addTemplate(t)}
                      className="flex items-center gap-1.5 text-xs px-3 py-1.5 bg-gray-50 hover:bg-indigo-50 border border-gray-200 hover:border-indigo-300 text-gray-700 hover:text-indigo-700 rounded-full transition">
                      <Plus className="w-3 h-3" /> {t.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Action buttons */}
              <div className="flex items-center gap-3 flex-wrap">
                <button
                  onClick={() => testMut.mutate(draft)}
                  disabled={!canSave || !!runningId}
                  className="flex items-center gap-2 px-5 py-2.5 bg-amber-500 hover:bg-amber-600 text-white rounded-xl text-sm font-semibold transition disabled:opacity-60 shadow-sm"
                >
                  {runningId === "adhoc" ? <Loader2 className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4" />}
                  {runningId === "adhoc" ? "Scanning…" : "Test Run (don't save)"}
                </button>

                <button
                  onClick={() => saveMut.mutate({ ...draft, ...(editingId ? { id: editingId } : {}) })}
                  disabled={!canSave || saveMut.isPending}
                  className="flex items-center gap-2 px-5 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-sm font-semibold transition disabled:opacity-60 shadow-sm"
                >
                  {saveMut.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                  {saveMut.isPending ? "Saving…" : editingId ? "Update Scanner" : "Save Scanner"}
                </button>

                <button onClick={() => { setRightPanel("empty"); setEditingId(null); setDraft(blankDraft()); }}
                  className="px-4 py-2.5 text-sm text-gray-500 hover:text-gray-700 transition">
                  Cancel
                </button>

                {!canSave && draft.name.trim() === "" && (
                  <span className="text-xs text-red-500 flex items-center gap-1">
                    <AlertCircle className="w-3.5 h-3.5" /> Name required
                  </span>
                )}
              </div>
            </div>
          )}

          {/* ── RESULTS ──────────────────────────────────────────────────────── */}
          {rightPanel === "results" && result && (
            <div className="space-y-4">
              {/* Results header */}
              <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <h2 className="font-bold text-gray-900 text-lg">{result.scannerName ?? "Test Results"}</h2>
                    <p className="text-sm text-gray-500 mt-0.5">
                      {new Date(result.runAt).toLocaleString("en-IN", { day:"2-digit", month:"short", hour:"2-digit", minute:"2-digit" })}
                      {" · "}{result.totalScanned} stocks scanned
                    </p>
                  </div>
                  <button onClick={() => setRightPanel("empty")}
                    className="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition">
                    <X className="w-4 h-4" />
                  </button>
                </div>

                {/* Summary stats */}
                <div className="grid grid-cols-3 gap-3 mt-4">
                  <div className="bg-indigo-50 rounded-lg p-3 text-center border border-indigo-100">
                    <p className="text-2xl font-bold text-indigo-600">{result.totalScanned}</p>
                    <p className="text-xs text-indigo-700 font-medium mt-0.5">Scanned</p>
                  </div>
                  <div className={`rounded-lg p-3 text-center border ${result.totalMatched > 0 ? "bg-green-50 border-green-100" : "bg-gray-50 border-gray-200"}`}>
                    <p className={`text-2xl font-bold ${result.totalMatched > 0 ? "text-green-600" : "text-gray-400"}`}>{result.totalMatched}</p>
                    <p className={`text-xs font-medium mt-0.5 ${result.totalMatched > 0 ? "text-green-700" : "text-gray-500"}`}>Matched</p>
                  </div>
                  <div className="bg-gray-50 rounded-lg p-3 text-center border border-gray-200">
                    <p className="text-2xl font-bold text-gray-600">
                      {result.totalScanned ? Math.round((result.totalMatched / result.totalScanned) * 100) : 0}%
                    </p>
                    <p className="text-xs text-gray-500 font-medium mt-0.5">Hit Rate</p>
                  </div>
                </div>
              </div>

              {/* No results */}
              {result.results?.length === 0 && (
                <div className="bg-white rounded-xl border border-gray-200 p-10 text-center shadow-sm">
                  <Target className="w-10 h-10 mx-auto mb-3 text-gray-300" />
                  <p className="font-semibold text-gray-600">No stocks matched</p>
                  <p className="text-sm text-gray-400 mt-1">Try relaxing conditions or expanding the universe</p>
                  <button onClick={() => setRightPanel("builder")}
                    className="mt-4 px-4 py-2 bg-indigo-50 text-indigo-600 rounded-lg text-sm font-medium hover:bg-indigo-100 transition">
                    Edit Conditions
                  </button>
                </div>
              )}

              {/* Result rows */}
              {result.results?.length > 0 && (
                <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
                  <div className="px-5 py-3 bg-gray-50 border-b border-gray-100 flex items-center justify-between">
                    <span className="text-sm font-semibold text-gray-700">{result.results.length} matching stocks</span>
                    <span className="text-xs text-gray-400">Logic: {result.logic}</span>
                  </div>
                  <div className="divide-y divide-gray-50">
                    {result.results.map((r: any, i: number) => (
                      <div key={i} className="px-5 py-4 hover:bg-gray-50 transition">
                        <div className="flex items-center justify-between gap-4">
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-3 flex-wrap">
                              <span className="font-bold text-gray-900 text-base">{r.symbol}</span>
                              <ChartButton symbol={r.symbol} />
                              <span className={`flex items-center gap-1 text-sm font-semibold ${r.pChange >= 0 ? "text-green-600" : "text-red-500"}`}>
                                {r.pChange >= 0 ? <TrendingUp className="w-3.5 h-3.5" /> : <TrendingDown className="w-3.5 h-3.5" />}
                                {r.pChange >= 0 ? "+" : ""}{r.pChange?.toFixed(2)}%
                              </span>
                              <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded-full font-medium">
                                {r.conditionsMatched}/{r.totalConditions} met
                              </span>
                            </div>

                            {/* Matched condition chips */}
                            <div className="flex flex-wrap gap-1 mt-2">
                              {r.matchedConditions?.map((mc: string, j: number) => (
                                <span key={j} className="inline-flex items-center gap-1 text-xs bg-green-50 text-green-700 border border-green-100 px-2 py-0.5 rounded-full">
                                  <CheckCircle2 className="w-3 h-3 flex-shrink-0" /> {mc}
                                </span>
                              ))}
                            </div>
                          </div>

                          <div className="text-right flex-shrink-0">
                            <p className="font-bold text-gray-900 text-lg">₹{r.lastPrice?.toFixed(2)}</p>
                            <div className="mt-1">
                              <div className="w-20 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                                <div className="h-full bg-indigo-500 rounded-full" style={{ width: `${r.score}%` }} />
                              </div>
                              <p className="text-xs text-indigo-600 mt-0.5 font-medium">{r.score}% match</p>
                            </div>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ── EMPTY STATE ────────────────────────────────────────────────── */}
          {rightPanel === "empty" && (
            <div className="h-full flex items-center justify-center min-h-64">
              <div className="text-center text-gray-400 max-w-xs">
                <BarChart2 className="w-14 h-14 mx-auto mb-4 opacity-20" />
                <h3 className="font-semibold text-gray-500 text-base">Select a scanner to run</h3>
                <p className="text-sm mt-1">Click "Run Scan" on any scanner to see results here, or build a new one</p>
                <button onClick={startNew}
                  className="mt-4 flex items-center gap-2 mx-auto px-4 py-2 bg-indigo-50 hover:bg-indigo-100 text-indigo-600 rounded-lg text-sm font-medium transition">
                  <Plus className="w-4 h-4" /> Build a Scanner
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
