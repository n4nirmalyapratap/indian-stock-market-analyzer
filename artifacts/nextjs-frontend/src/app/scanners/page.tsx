'use client';
import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { Scanner, ScannerRunResult } from '@/types';
import { Plus, Play, Trash2, Edit2, Search, Loader2, ChevronDown, ChevronUp } from 'lucide-react';
import { clsx } from 'clsx';

const INDICATORS = ['RSI', 'EMA', 'MACD', 'BOLLINGER', 'PRICE', 'VOLUME'];
const OPERATORS = ['ABOVE', 'BELOW', 'CROSSES_ABOVE', 'CROSSES_BELOW', 'BETWEEN'];
const UNIVERSES = ['NIFTY100', 'MIDCAP', 'SMALLCAP'];

const defaultCondition = { indicator: 'RSI', period: 14, operator: 'BELOW', value: 35 };

export default function ScannersPage() {
  const [showCreate, setShowCreate] = useState(false);
  const [runResults, setRunResults] = useState<Record<string, ScannerRunResult>>({});
  const [runningId, setRunningId] = useState<string | null>(null);
  const [expandedResult, setExpandedResult] = useState<string | null>(null);
  const [form, setForm] = useState({
    name: '',
    description: '',
    universe: ['NIFTY100'] as string[],
    conditions: [{ ...defaultCondition }],
  });
  const queryClient = useQueryClient();

  const { data: scanners = [], isLoading } = useQuery({
    queryKey: ['scanners'],
    queryFn: () => api.scanners.getAll().then(r => r.data as Scanner[]),
  });

  const createMutation = useMutation({
    mutationFn: (data: any) => api.scanners.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['scanners'] });
      setShowCreate(false);
      setForm({ name: '', description: '', universe: ['NIFTY100'], conditions: [{ ...defaultCondition }] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.scanners.delete(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['scanners'] }),
  });

  const runScanner = async (id: string) => {
    setRunningId(id);
    setExpandedResult(id);
    try {
      const result = await api.scanners.run(id);
      setRunResults(prev => ({ ...prev, [id]: result.data as ScannerRunResult }));
    } catch (err) {
      console.error(err);
    } finally {
      setRunningId(null);
    }
  };

  const toggleUniverse = (u: string) => {
    setForm(f => ({
      ...f,
      universe: f.universe.includes(u) ? f.universe.filter(x => x !== u) : [...f.universe, u],
    }));
  };

  const addCondition = () => {
    setForm(f => ({ ...f, conditions: [...f.conditions, { ...defaultCondition }] }));
  };

  const removeCondition = (idx: number) => {
    setForm(f => ({ ...f, conditions: f.conditions.filter((_, i) => i !== idx) }));
  };

  const updateCondition = (idx: number, key: string, value: any) => {
    setForm(f => {
      const conds = [...f.conditions];
      conds[idx] = { ...conds[idx], [key]: value };
      return { ...f, conditions: conds };
    });
  };

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Custom Scanners</h1>
          <p className="text-slate-500 text-sm mt-1">Build, save and run your own stock scanners with EMA, RSI and more</p>
        </div>
        <button
          onClick={() => setShowCreate(s => !s)}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors"
        >
          <Plus className="w-4 h-4" />
          Create Scanner
        </button>
      </div>

      {/* Create Scanner Form */}
      {showCreate && (
        <div className="card border border-blue-500/20">
          <h2 className="font-semibold text-white mb-4">New Scanner</h2>
          <div className="space-y-4">
            <div className="grid md:grid-cols-2 gap-4">
              <input
                type="text"
                placeholder="Scanner name"
                value={form.name}
                onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                className="px-3 py-2 bg-white/[0.04] border border-white/[0.08] rounded-lg text-white placeholder-slate-500 text-sm focus:outline-none focus:border-blue-500/50"
              />
              <input
                type="text"
                placeholder="Description (optional)"
                value={form.description}
                onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
                className="px-3 py-2 bg-white/[0.04] border border-white/[0.08] rounded-lg text-white placeholder-slate-500 text-sm focus:outline-none focus:border-blue-500/50"
              />
            </div>

            <div>
              <div className="text-xs text-slate-500 mb-2">Universe (stocks to scan):</div>
              <div className="flex gap-2">
                {UNIVERSES.map(u => (
                  <button
                    key={u}
                    onClick={() => toggleUniverse(u)}
                    className={clsx(
                      'px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors',
                      form.universe.includes(u)
                        ? 'bg-blue-600 border-blue-500 text-white'
                        : 'border-white/[0.08] text-slate-400 hover:text-white glass'
                    )}
                  >
                    {u}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <div className="text-xs text-slate-500 mb-2">Conditions (ALL must match):</div>
              <div className="space-y-2">
                {form.conditions.map((cond, idx) => (
                  <div key={idx} className="flex flex-wrap gap-2 p-3 rounded-lg bg-white/[0.02] border border-white/[0.06]">
                    <select
                      value={cond.indicator}
                      onChange={e => updateCondition(idx, 'indicator', e.target.value)}
                      className="px-2 py-1 bg-slate-800 border border-white/[0.08] rounded text-white text-xs focus:outline-none"
                    >
                      {INDICATORS.map(i => <option key={i}>{i}</option>)}
                    </select>
                    {['EMA', 'RSI'].includes(cond.indicator) && (
                      <input
                        type="number"
                        placeholder="Period"
                        value={cond.period || ''}
                        onChange={e => updateCondition(idx, 'period', parseInt(e.target.value))}
                        className="w-20 px-2 py-1 bg-slate-800 border border-white/[0.08] rounded text-white text-xs focus:outline-none"
                      />
                    )}
                    <select
                      value={cond.operator}
                      onChange={e => updateCondition(idx, 'operator', e.target.value)}
                      className="px-2 py-1 bg-slate-800 border border-white/[0.08] rounded text-white text-xs focus:outline-none"
                    >
                      {OPERATORS.map(o => <option key={o}>{o}</option>)}
                    </select>
                    <input
                      type="number"
                      placeholder="Value"
                      value={cond.value || ''}
                      onChange={e => updateCondition(idx, 'value', parseFloat(e.target.value))}
                      className="w-20 px-2 py-1 bg-slate-800 border border-white/[0.08] rounded text-white text-xs focus:outline-none"
                    />
                    {cond.operator === 'BETWEEN' && (
                      <input
                        type="number"
                        placeholder="Value 2"
                        value={(cond as any).value2 || ''}
                        onChange={e => updateCondition(idx, 'value2', parseFloat(e.target.value))}
                        className="w-20 px-2 py-1 bg-slate-800 border border-white/[0.08] rounded text-white text-xs focus:outline-none"
                      />
                    )}
                    {cond.operator === 'CROSSES_ABOVE' || cond.operator === 'CROSSES_BELOW' ? (
                      <input
                        type="number"
                        placeholder="Period 2"
                        value={(cond as any).period2 || ''}
                        onChange={e => updateCondition(idx, 'period2', parseInt(e.target.value))}
                        className="w-20 px-2 py-1 bg-slate-800 border border-white/[0.08] rounded text-white text-xs focus:outline-none"
                      />
                    ) : null}
                    {form.conditions.length > 1 && (
                      <button onClick={() => removeCondition(idx)} className="text-red-400 hover:text-red-300 text-xs ml-auto">
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    )}
                  </div>
                ))}
                <button onClick={addCondition} className="text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1">
                  <Plus className="w-3 h-3" /> Add Condition
                </button>
              </div>
            </div>

            <div className="flex gap-3 pt-2">
              <button
                onClick={() => createMutation.mutate(form)}
                disabled={!form.name || createMutation.isPending}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
              >
                {createMutation.isPending ? 'Saving...' : 'Save Scanner'}
              </button>
              <button
                onClick={() => setShowCreate(false)}
                className="px-4 py-2 glass text-slate-400 hover:text-white rounded-lg text-sm transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Scanner List */}
      {isLoading ? (
        <div className="space-y-3">
          {[1,2,3].map(i => <div key={i} className="card h-24 animate-pulse bg-white/[0.03]" />)}
        </div>
      ) : (
        <div className="space-y-4">
          {scanners.map(scanner => (
            <div key={scanner.id} className="card">
              <div className="flex items-center justify-between">
                <div className="flex-1">
                  <div className="font-semibold text-white">{scanner.name}</div>
                  {scanner.description && (
                    <div className="text-sm text-slate-500 mt-0.5">{scanner.description}</div>
                  )}
                  <div className="flex flex-wrap gap-2 mt-2">
                    {scanner.universe.map(u => (
                      <span key={u} className="text-xs px-2 py-0.5 rounded bg-blue-500/10 text-blue-400 border border-blue-500/20">{u}</span>
                    ))}
                    <span className="text-xs text-slate-500">{scanner.conditions.length} condition(s)</span>
                  </div>
                </div>
                <div className="flex items-center gap-2 ml-4">
                  <button
                    onClick={() => runScanner(scanner.id)}
                    disabled={runningId === scanner.id}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-green-600/20 hover:bg-green-600/30 text-green-400 rounded-lg text-xs font-medium transition-colors disabled:opacity-50"
                  >
                    {runningId === scanner.id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
                    {runningId === scanner.id ? 'Scanning...' : 'Run'}
                  </button>
                  <button
                    onClick={() => deleteMutation.mutate(scanner.id)}
                    className="p-1.5 text-slate-500 hover:text-red-400 transition-colors"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>

              {/* Conditions Preview */}
              <div className="mt-3 pt-3 border-t border-white/[0.04]">
                <div className="flex flex-wrap gap-2">
                  {scanner.conditions.map((c, i) => (
                    <span key={i} className="text-xs px-2 py-0.5 rounded bg-white/[0.04] text-slate-400 border border-white/[0.06]">
                      {c.indicator}{c.period ? `(${c.period})` : ''} {c.operator.replace(/_/g, ' ')} {c.value}{c.value2 ? `-${c.value2}` : ''}
                    </span>
                  ))}
                </div>
              </div>

              {/* Run Results */}
              {runResults[scanner.id] && (
                <div className="mt-3">
                  <button
                    onClick={() => setExpandedResult(expandedResult === scanner.id ? null : scanner.id)}
                    className="flex items-center gap-2 text-xs text-slate-400 hover:text-white transition-colors"
                  >
                    {expandedResult === scanner.id ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                    Results: {runResults[scanner.id].totalMatched} / {runResults[scanner.id].totalScanned} matched
                  </button>
                  {expandedResult === scanner.id && (
                    <div className="mt-2 space-y-2 max-h-60 overflow-y-auto">
                      {runResults[scanner.id].results.length === 0 ? (
                        <div className="text-xs text-slate-500 py-2">No stocks matched this scanner today.</div>
                      ) : (
                        runResults[scanner.id].results.map((r, i) => (
                          <div key={i} className="flex items-center gap-3 p-2 rounded bg-white/[0.03] border border-white/[0.04]">
                            <span className="font-bold text-sm text-white w-24">{r.symbol}</span>
                            <span className={clsx('text-xs', r.pChange >= 0 ? 'text-green-400' : 'text-red-400')}>
                              {r.pChange >= 0 ? '+' : ''}{r.pChange?.toFixed(2)}%
                            </span>
                            <div className="flex flex-wrap gap-1 flex-1">
                              {r.matchedConditions.map((c, j) => (
                                <span key={j} className="text-xs text-green-400">✓ {c}</span>
                              ))}
                            </div>
                            <span className="text-xs font-mono text-slate-400">₹{r.lastPrice?.toFixed(2)}</span>
                          </div>
                        ))
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
