'use client';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { SectorRotation, Sector } from '@/types';
import { clsx } from 'clsx';
import { TrendingUp, TrendingDown, RefreshCw, Activity } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts';

export default function SectorsPage() {
  const { data: rotation, isLoading, refetch } = useQuery({
    queryKey: ['rotation'],
    queryFn: () => api.sectors.getRotation().then(r => r.data as SectorRotation),
  });

  const sectors = rotation?.sectors || [];
  const sorted = [...sectors].sort((a, b) => (b.pChange || 0) - (a.pChange || 0));

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Sector Rotation</h1>
          <p className="text-slate-500 text-sm mt-1">Which sectors are gaining and where money is flowing</p>
        </div>
        <button
          onClick={() => refetch()}
          className="flex items-center gap-2 px-3 py-2 text-sm text-slate-400 hover:text-white glass rounded-lg transition-colors"
        >
          <RefreshCw className="w-4 h-4" />
          Refresh
        </button>
      </div>

      {/* Rotation Phase */}
      {rotation && (
        <div className="grid md:grid-cols-3 gap-4">
          <div className="md:col-span-2 card border border-indigo-500/20 bg-indigo-500/5">
            <div className="text-xs text-indigo-400 uppercase tracking-wider font-medium mb-1">Market Phase</div>
            <div className="text-xl font-bold text-white mb-2">{rotation.rotationPhase}</div>
            <div className="text-sm text-slate-400">{rotation.recommendation}</div>
          </div>
          <div className="card">
            <div className="text-xs text-slate-500 uppercase tracking-wider mb-3">Market Breadth</div>
            <div className="space-y-2">
              <div className="flex justify-between items-center">
                <span className="text-sm text-green-400">Advancing</span>
                <span className="font-bold text-green-400">{rotation.marketBreadth?.advancing}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-sm text-red-400">Declining</span>
                <span className="font-bold text-red-400">{rotation.marketBreadth?.declining}</span>
              </div>
              <div className="flex justify-between items-center text-xs text-slate-500">
                <span>A/D Ratio</span>
                <span>{rotation.marketBreadth?.advanceDeclineRatio}</span>
              </div>
              <div className="w-full bg-slate-700/50 rounded-full h-1.5 mt-2">
                <div
                  className="bg-green-500 h-1.5 rounded-full transition-all"
                  style={{ width: `${rotation.marketBreadth?.breadthScore}%` }}
                />
              </div>
              <div className="text-xs text-center text-slate-500">{rotation.marketBreadth?.breadthScore}% bullish</div>
            </div>
          </div>
        </div>
      )}

      {/* Bar Chart */}
      {sorted.length > 0 && (
        <div className="card">
          <h2 className="font-semibold text-white mb-4">Sector Performance Today</h2>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={sorted.slice(0, 12)} margin={{ top: 5, right: 5, left: 0, bottom: 40 }}>
              <XAxis
                dataKey="name"
                tick={{ fill: '#64748b', fontSize: 10 }}
                angle={-30}
                textAnchor="end"
                interval={0}
              />
              <YAxis tick={{ fill: '#64748b', fontSize: 11 }} tickFormatter={v => `${v}%`} />
              <Tooltip
                contentStyle={{ background: '#1e2532', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8 }}
                labelStyle={{ color: '#e2e8f0' }}
                formatter={(value: any) => [`${Number(value).toFixed(2)}%`, 'Change']}
              />
              <Bar dataKey="pChange" radius={[4, 4, 0, 0]}>
                {sorted.slice(0, 12).map((entry, index) => (
                  <Cell key={index} fill={entry.pChange >= 0 ? '#22c55e' : '#ef4444'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Sector Table */}
      <div className="card">
        <h2 className="font-semibold text-white mb-4">All Sectors</h2>
        {isLoading ? (
          <div className="space-y-2">
            {[...Array(10)].map((_, i) => (
              <div key={i} className="h-12 rounded bg-white/[0.03] animate-pulse" />
            ))}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-slate-500 uppercase tracking-wider border-b border-white/[0.06]">
                  <th className="pb-3 pr-4">Sector</th>
                  <th className="pb-3 pr-4 text-right">Last Price</th>
                  <th className="pb-3 pr-4 text-right">Change</th>
                  <th className="pb-3 pr-4 text-right">% Change</th>
                  <th className="pb-3 pr-4 text-right">Adv/Dec</th>
                  <th className="pb-3 text-center">Signal</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/[0.04]">
                {sorted.map((sector) => (
                  <tr key={sector.symbol} className="hover:bg-white/[0.02] transition-colors">
                    <td className="py-3 pr-4">
                      <div className="font-medium text-white">{sector.name}</div>
                      <div className="text-xs text-slate-500">{sector.category}</div>
                    </td>
                    <td className="py-3 pr-4 text-right font-mono text-slate-300">
                      {sector.lastPrice ? `₹${sector.lastPrice.toLocaleString('en-IN')}` : '—'}
                    </td>
                    <td className={clsx('py-3 pr-4 text-right font-mono', sector.change >= 0 ? 'text-green-400' : 'text-red-400')}>
                      {sector.change >= 0 ? '+' : ''}{(sector.change || 0).toFixed(2)}
                    </td>
                    <td className="py-3 pr-4 text-right">
                      <span className={clsx(
                        'inline-flex items-center gap-1 font-semibold',
                        sector.pChange >= 0 ? 'text-green-400' : 'text-red-400'
                      )}>
                        {sector.pChange >= 0 ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
                        {sector.pChange >= 0 ? '+' : ''}{(sector.pChange || 0).toFixed(2)}%
                      </span>
                    </td>
                    <td className="py-3 pr-4 text-right text-xs">
                      <span className="text-green-400">{sector.advances || '—'}</span>
                      {' / '}
                      <span className="text-red-400">{sector.declines || '—'}</span>
                    </td>
                    <td className="py-3 text-center">
                      <span className={clsx(
                        'px-2 py-0.5 rounded text-xs font-medium',
                        sector.focus === 'BUY' ? 'bg-green-500/10 text-green-400' :
                        sector.focus === 'AVOID' ? 'bg-red-500/10 text-red-400' :
                        'bg-slate-500/10 text-slate-400'
                      )}>
                        {sector.focus}
                      </span>
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
