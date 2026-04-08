'use client';
import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { PatternsData, ChartPattern } from '@/types';
import { Activity, RefreshCw, TrendingUp, TrendingDown, Loader2 } from 'lucide-react';
import { clsx } from 'clsx';

export default function PatternsPage() {
  const [universe, setUniverse] = useState('');
  const [signal, setSignal] = useState('');
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ['patterns', universe, signal],
    queryFn: () => api.patterns.getAll(universe || undefined, signal || undefined).then(r => r.data as PatternsData),
  });

  const scanMutation = useMutation({
    mutationFn: () => api.patterns.triggerScan(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['patterns'] });
    },
  });

  const patterns = data?.patterns || [];

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Chart Pattern Detection</h1>
          <p className="text-slate-500 text-sm mt-1">Automated detection across Nifty 100, Midcap & Smallcap</p>
        </div>
        <button
          onClick={() => scanMutation.mutate()}
          disabled={scanMutation.isPending}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
        >
          {scanMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
          Run Scan
        </button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-4">
        <div className="card text-center">
          <div className="text-3xl font-bold text-white">{data?.totalPatterns || 0}</div>
          <div className="text-xs text-slate-500 mt-1">Total Patterns</div>
        </div>
        <div className="card text-center">
          <div className="text-3xl font-bold text-green-400">{data?.callSignals || 0}</div>
          <div className="text-xs text-slate-500 mt-1">CALL Signals</div>
        </div>
        <div className="card text-center">
          <div className="text-3xl font-bold text-red-400">{data?.putSignals || 0}</div>
          <div className="text-xs text-slate-500 mt-1">PUT Signals</div>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-500">Universe:</span>
          {['', 'NIFTY100', 'MIDCAP', 'SMALLCAP'].map(u => (
            <button
              key={u}
              onClick={() => setUniverse(u)}
              className={clsx(
                'text-xs px-3 py-1.5 rounded-lg border transition-colors',
                universe === u
                  ? 'bg-blue-600 border-blue-500 text-white'
                  : 'border-white/[0.08] text-slate-400 hover:text-white glass'
              )}
            >
              {u || 'All'}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-500">Signal:</span>
          {['', 'CALL', 'PUT'].map(s => (
            <button
              key={s}
              onClick={() => setSignal(s)}
              className={clsx(
                'text-xs px-3 py-1.5 rounded-lg border transition-colors',
                signal === s
                  ? s === 'CALL' ? 'bg-green-600 border-green-500 text-white' :
                    s === 'PUT' ? 'bg-red-600 border-red-500 text-white' :
                    'bg-blue-600 border-blue-500 text-white'
                  : 'border-white/[0.08] text-slate-400 hover:text-white glass'
              )}
            >
              {s || 'All'}
            </button>
          ))}
        </div>
      </div>

      {data?.lastScanTime && (
        <div className="text-xs text-slate-500">
          Last scan: {new Date(data.lastScanTime).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' })} IST
        </div>
      )}

      {/* Pattern Cards */}
      {isLoading ? (
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[...Array(6)].map((_, i) => (
            <div key={i} className="card h-40 animate-pulse bg-white/[0.03]" />
          ))}
        </div>
      ) : patterns.length === 0 ? (
        <div className="card text-center py-16">
          <Activity className="w-8 h-8 text-slate-600 mx-auto mb-3" />
          <div className="text-slate-400 font-medium">No patterns detected</div>
          <div className="text-slate-500 text-sm mt-1">Click "Run Scan" to detect chart patterns across all stocks</div>
        </div>
      ) : (
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
          {patterns.map((pattern, i) => (
            <PatternCard key={`${pattern.symbol}-${i}`} pattern={pattern} />
          ))}
        </div>
      )}
    </div>
  );
}

function PatternCard({ pattern }: { pattern: ChartPattern }) {
  const isCall = pattern.signal === 'CALL';
  const isPut = pattern.signal === 'PUT';

  return (
    <div className={clsx(
      'card border',
      isCall ? 'border-green-500/20 hover:border-green-500/40' :
      isPut ? 'border-red-500/20 hover:border-red-500/40' :
      'border-white/[0.08]',
      'transition-all'
    )}>
      <div className="flex items-start justify-between mb-3">
        <div>
          <div className="font-bold text-white">{pattern.symbol}</div>
          <div className="text-xs text-slate-500">{pattern.universe}</div>
        </div>
        <span className={clsx(
          'px-2 py-0.5 rounded text-xs font-bold flex items-center gap-1',
          isCall ? 'bg-green-500 text-white' :
          isPut ? 'bg-red-500 text-white' :
          'bg-slate-500 text-white'
        )}>
          {isCall ? <TrendingUp className="w-3 h-3" /> : isPut ? <TrendingDown className="w-3 h-3" /> : null}
          {pattern.signal}
        </span>
      </div>

      <div className="text-sm font-medium text-slate-200 mb-1">{pattern.pattern}</div>
      <div className="text-xs text-slate-500 mb-3 leading-relaxed">{pattern.description}</div>

      <div className="flex items-center justify-between text-xs">
        <span className="text-slate-400">₹{pattern.currentPrice?.toFixed(2)}</span>
        <div className="flex items-center gap-2">
          <span className="text-slate-500">Confidence:</span>
          <div className="w-16 bg-slate-700 rounded-full h-1.5">
            <div
              className={clsx('h-1.5 rounded-full', isCall ? 'bg-green-500' : isPut ? 'bg-red-500' : 'bg-slate-500')}
              style={{ width: `${pattern.confidence}%` }}
            />
          </div>
          <span className={isCall ? 'text-green-400' : isPut ? 'text-red-400' : 'text-slate-400'}>
            {pattern.confidence}%
          </span>
        </div>
      </div>

      {(pattern.targetPrice || pattern.stopLoss) && (
        <div className="flex gap-3 mt-3 pt-3 border-t border-white/[0.06] text-xs">
          {pattern.targetPrice && (
            <div>
              <span className="text-slate-500">Target: </span>
              <span className="text-green-400 font-mono">₹{pattern.targetPrice.toFixed(2)}</span>
            </div>
          )}
          {pattern.stopLoss && (
            <div>
              <span className="text-slate-500">SL: </span>
              <span className="text-red-400 font-mono">₹{pattern.stopLoss.toFixed(2)}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
