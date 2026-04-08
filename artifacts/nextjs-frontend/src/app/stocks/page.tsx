'use client';
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { StockData } from '@/types';
import { Search, TrendingUp, TrendingDown, Shield, Target, AlertTriangle } from 'lucide-react';
import { clsx } from 'clsx';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts';

export default function StocksPage() {
  const [symbol, setSymbol] = useState('');
  const [activeSymbol, setActiveSymbol] = useState('');

  const { data: stock, isLoading, error } = useQuery({
    queryKey: ['stock', activeSymbol],
    queryFn: () => api.stocks.getDetail(activeSymbol).then(r => r.data as StockData),
    enabled: !!activeSymbol,
  });

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    const s = symbol.trim().toUpperCase();
    if (s) setActiveSymbol(s);
  };

  const popularStocks = ['RELIANCE', 'TCS', 'HDFCBANK', 'INFY', 'ICICIBANK', 'SUNPHARMA', 'TATAMOTORS', 'ITC'];

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      <div>
        <h1 className="text-2xl font-bold text-white">Stock Lookup</h1>
        <p className="text-slate-500 text-sm mt-1">Enter any NSE symbol for technical analysis and entry/exit insights</p>
      </div>

      {/* Search */}
      <div className="card">
        <form onSubmit={handleSearch} className="flex gap-3">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
            <input
              type="text"
              value={symbol}
              onChange={e => setSymbol(e.target.value.toUpperCase())}
              placeholder="Enter NSE symbol (e.g. RELIANCE, TCS, INFY)"
              className="w-full pl-9 pr-4 py-3 bg-white/[0.04] border border-white/[0.08] rounded-lg text-white placeholder-slate-500 focus:outline-none focus:border-blue-500/50 transition-all text-sm"
            />
          </div>
          <button
            type="submit"
            className="px-6 py-3 bg-blue-600 hover:bg-blue-500 text-white rounded-lg font-medium transition-colors text-sm"
          >
            Analyze
          </button>
        </form>

        <div className="flex flex-wrap gap-2 mt-4">
          <span className="text-xs text-slate-500">Quick:</span>
          {popularStocks.map(s => (
            <button
              key={s}
              onClick={() => { setSymbol(s); setActiveSymbol(s); }}
              className="text-xs px-2.5 py-1 rounded bg-white/[0.04] text-slate-400 hover:text-white hover:bg-white/[0.08] transition-colors border border-white/[0.06]"
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      {isLoading && (
        <div className="grid md:grid-cols-2 gap-4">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="card h-40 animate-pulse bg-white/[0.03]" />
          ))}
        </div>
      )}

      {stock && !stock.error && (
        <div className="space-y-4">
          {/* Price Card */}
          <div className="card">
            <div className="flex items-start justify-between">
              <div>
                <h2 className="text-xl font-bold text-white">{stock.companyName || activeSymbol}</h2>
                <div className="flex items-center gap-2 mt-1">
                  <span className="text-xs text-slate-500">{activeSymbol}</span>
                  {stock.sector && <span className="text-xs text-slate-500">• {stock.sector}</span>}
                  {stock.industry && <span className="text-xs text-slate-500">• {stock.industry}</span>}
                </div>
              </div>
              <div className="text-right">
                <div className="text-2xl font-bold text-white font-mono">
                  ₹{(stock.lastPrice || stock.technicalAnalysis?.currentPrice || 0).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </div>
                <div className={clsx(
                  'flex items-center gap-1 justify-end mt-1',
                  (stock.pChange || 0) >= 0 ? 'text-green-400' : 'text-red-400'
                )}>
                  {(stock.pChange || 0) >= 0 ? <TrendingUp className="w-4 h-4" /> : <TrendingDown className="w-4 h-4" />}
                  <span className="font-semibold">{(stock.pChange || 0) >= 0 ? '+' : ''}{(stock.pChange || 0).toFixed(2)}%</span>
                  <span className="text-sm">({(stock.change || 0) >= 0 ? '+' : ''}₹{(stock.change || 0).toFixed(2)})</span>
                </div>
              </div>
            </div>
          </div>

          {/* Entry Recommendation */}
          {stock.entryRecommendation && (
            <div className={clsx(
              'card border',
              stock.entryRecommendation.entryCall === 'ENTRY_CALL' ? 'border-green-500/30 bg-green-500/5' :
              stock.entryRecommendation.entryCall === 'ENTRY_PUT' ? 'border-red-500/30 bg-red-500/5' :
              'border-yellow-500/30 bg-yellow-500/5'
            )}>
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <AlertTriangle className={clsx(
                    'w-5 h-5',
                    stock.entryRecommendation.entryCall === 'ENTRY_CALL' ? 'text-green-400' :
                    stock.entryRecommendation.entryCall === 'ENTRY_PUT' ? 'text-red-400' : 'text-yellow-400'
                  )} />
                  <span className="font-semibold text-white">Entry Recommendation</span>
                </div>
                <span className={clsx(
                  'px-3 py-1 rounded-full text-sm font-bold',
                  stock.entryRecommendation.entryCall === 'ENTRY_CALL' ? 'bg-green-500 text-white' :
                  stock.entryRecommendation.entryCall === 'ENTRY_PUT' ? 'bg-red-500 text-white' :
                  'bg-yellow-500 text-black'
                )}>
                  {stock.entryRecommendation.entryCall.replace('_', ' ')}
                </span>
              </div>
              <p className="text-slate-300 text-sm mb-3">{stock.entryRecommendation.summary}</p>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {stock.entryRecommendation.targetPrice && (
                  <div className="flex items-center gap-2">
                    <Target className="w-4 h-4 text-green-400" />
                    <div>
                      <div className="text-xs text-slate-500">Target</div>
                      <div className="text-sm font-semibold text-white">₹{stock.entryRecommendation.targetPrice.toFixed(2)}</div>
                    </div>
                  </div>
                )}
                {stock.entryRecommendation.stopLoss && (
                  <div className="flex items-center gap-2">
                    <Shield className="w-4 h-4 text-red-400" />
                    <div>
                      <div className="text-xs text-slate-500">Stop Loss</div>
                      <div className="text-sm font-semibold text-white">₹{stock.entryRecommendation.stopLoss.toFixed(2)}</div>
                    </div>
                  </div>
                )}
                <div>
                  <div className="text-xs text-slate-500">Confidence</div>
                  <div className="text-sm font-semibold text-white">{stock.entryRecommendation.confidence}</div>
                </div>
                {stock.entryRecommendation.riskReward && (
                  <div>
                    <div className="text-xs text-slate-500">Risk:Reward</div>
                    <div className="text-sm font-semibold text-white">1:{stock.entryRecommendation.riskReward}</div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Technical Indicators */}
          {stock.technicalAnalysis && (
            <div className="grid md:grid-cols-2 gap-4">
              <div className="card">
                <h3 className="text-sm font-semibold text-slate-300 mb-3">EMAs</h3>
                <div className="space-y-2">
                  {Object.entries(stock.technicalAnalysis.ema || {}).map(([key, val]) => (
                    <div key={key} className="flex justify-between items-center">
                      <span className="text-xs text-slate-500 uppercase">{key}</span>
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-mono text-white">₹{(val as number)?.toFixed(2) || '—'}</span>
                        <span className={clsx(
                          'text-xs',
                          stock.technicalAnalysis!.currentPrice > (val as number) ? 'text-green-400' : 'text-red-400'
                        )}>
                          {stock.technicalAnalysis!.currentPrice > (val as number) ? 'Above' : 'Below'}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
              <div className="card">
                <h3 className="text-sm font-semibold text-slate-300 mb-3">Momentum Indicators</h3>
                <div className="space-y-3">
                  <div className="flex justify-between items-center">
                    <span className="text-xs text-slate-500">RSI (14)</span>
                    <div className="flex items-center gap-2">
                      <div className="w-20 bg-slate-700 rounded-full h-1.5">
                        <div
                          className={clsx('h-1.5 rounded-full', stock.technicalAnalysis.rsiZone === 'OVERBOUGHT' ? 'bg-red-500' : stock.technicalAnalysis.rsiZone === 'OVERSOLD' ? 'bg-green-500' : 'bg-blue-500')}
                          style={{ width: `${Math.min(stock.technicalAnalysis.rsi || 0, 100)}%` }}
                        />
                      </div>
                      <span className="text-sm font-mono text-white">{stock.technicalAnalysis.rsi?.toFixed(1)}</span>
                      <span className={clsx(
                        'text-xs',
                        stock.technicalAnalysis.rsiZone === 'OVERBOUGHT' ? 'text-red-400' :
                        stock.technicalAnalysis.rsiZone === 'OVERSOLD' ? 'text-green-400' : 'text-slate-400'
                      )}>
                        {stock.technicalAnalysis.rsiZone}
                      </span>
                    </div>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs text-slate-500">MACD</span>
                    <span className={clsx(
                      'text-sm font-medium',
                      stock.technicalAnalysis.macd?.crossover === 'BULLISH' ? 'text-green-400' : 'text-red-400'
                    )}>
                      {stock.technicalAnalysis.macd?.crossover}
                    </span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs text-slate-500">Trend</span>
                    <span className={clsx(
                      'text-sm font-medium',
                      stock.technicalAnalysis.trend?.includes('BULL') ? 'text-green-400' :
                      stock.technicalAnalysis.trend?.includes('BEAR') ? 'text-red-400' : 'text-slate-400'
                    )}>
                      {stock.technicalAnalysis.trend?.replace(/_/g, ' ')}
                    </span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs text-slate-500">BB Position</span>
                    <span className="text-sm text-slate-300">{stock.technicalAnalysis.bollingerBands?.position?.replace(/_/g, ' ')}</span>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Price Chart */}
          {stock.historicalData && stock.historicalData.length > 0 && (
            <div className="card">
              <h3 className="text-sm font-semibold text-slate-300 mb-4">30-Day Price History</h3>
              <ResponsiveContainer width="100%" height={200}>
                <LineChart data={stock.historicalData}>
                  <XAxis dataKey="date" tick={{ fill: '#64748b', fontSize: 10 }} tickFormatter={d => d.slice(5)} interval="preserveStartEnd" />
                  <YAxis tick={{ fill: '#64748b', fontSize: 11 }} tickFormatter={v => `₹${v.toLocaleString('en-IN')}`} domain={['auto', 'auto']} />
                  <Tooltip
                    contentStyle={{ background: '#1e2532', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, fontSize: 12 }}
                    formatter={(v: any) => [`₹${Number(v).toFixed(2)}`, 'Close']}
                  />
                  <Line type="monotone" dataKey="close" stroke="#3b82f6" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Insight */}
          {stock.insight && (
            <div className="card border border-blue-500/20 bg-blue-500/5">
              <h3 className="text-sm font-semibold text-blue-400 mb-2">Analysis Insight</h3>
              <p className="text-sm text-slate-300 leading-relaxed">{stock.insight}</p>
            </div>
          )}
        </div>
      )}

      {stock?.error && (
        <div className="card border border-red-500/20 bg-red-500/5 text-center py-8">
          <div className="text-red-400 font-medium">{stock.error}</div>
          <div className="text-slate-500 text-sm mt-1">Make sure the NSE symbol is correct</div>
        </div>
      )}
    </div>
  );
}
