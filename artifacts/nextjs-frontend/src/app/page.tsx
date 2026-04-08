'use client';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { TrendingUp, TrendingDown, Activity, Search, MessageSquare, BarChart2, ArrowRight } from 'lucide-react';
import Link from 'next/link';
import { clsx } from 'clsx';
import { SectorRotation, PatternsData, WhatsAppStatus } from '@/types';

export default function Dashboard() {
  const { data: rotation, isLoading: loadingRotation } = useQuery({
    queryKey: ['rotation'],
    queryFn: () => api.sectors.getRotation().then(r => r.data as SectorRotation),
  });

  const { data: patterns } = useQuery({
    queryKey: ['patterns'],
    queryFn: () => api.patterns.getAll().then(r => r.data as PatternsData),
  });

  const { data: botStatus } = useQuery({
    queryKey: ['bot-status'],
    queryFn: () => api.whatsapp.getStatus().then(r => r.data as WhatsAppStatus),
  });

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      <div>
        <h1 className="text-2xl font-bold text-white">Market Dashboard</h1>
        <p className="text-slate-500 text-sm mt-1">Indian stock market analysis — NSE sector rotation, patterns & bot</p>
      </div>

      {/* Stats Row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard
          label="Sectors Tracked"
          value={rotation?.sectors?.length?.toString() || '15'}
          icon={<BarChart2 className="w-5 h-5" />}
          color="blue"
          href="/sectors"
        />
        <StatCard
          label="Patterns Detected"
          value={patterns?.totalPatterns?.toString() || '0'}
          icon={<Activity className="w-5 h-5" />}
          color="purple"
          href="/patterns"
        />
        <StatCard
          label="CALL Signals"
          value={patterns?.callSignals?.toString() || '0'}
          icon={<TrendingUp className="w-5 h-5" />}
          color="green"
          href="/patterns?signal=CALL"
        />
        <StatCard
          label="PUT Signals"
          value={patterns?.putSignals?.toString() || '0'}
          icon={<TrendingDown className="w-5 h-5" />}
          color="red"
          href="/patterns?signal=PUT"
        />
      </div>

      {/* Rotation Phase Banner */}
      {rotation && (
        <div className="card border border-blue-500/20 bg-blue-500/5">
          <div className="flex items-start justify-between">
            <div>
              <div className="text-xs text-blue-400 font-medium uppercase tracking-wider mb-1">Rotation Phase</div>
              <div className="text-lg font-semibold text-white">{rotation.rotationPhase}</div>
              <div className="text-sm text-slate-400 mt-1">{rotation.recommendation}</div>
            </div>
            <div className="text-right">
              <div className="text-xs text-slate-500">Market Breadth</div>
              <div className="text-sm mt-1">
                <span className="text-green-400">{rotation.marketBreadth?.advancing} up</span>
                {' / '}
                <span className="text-red-400">{rotation.marketBreadth?.declining} down</span>
              </div>
              <div className="text-xs text-slate-500 mt-0.5">
                A/D: {rotation.marketBreadth?.advanceDeclineRatio}
              </div>
            </div>
          </div>
        </div>
      )}

      <div className="grid md:grid-cols-2 gap-6">
        {/* Top Sectors */}
        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-semibold text-white">Top Sectors Today</h2>
            <Link href="/sectors" className="text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1">
              View All <ArrowRight className="w-3 h-3" />
            </Link>
          </div>
          {loadingRotation ? (
            <div className="space-y-3">
              {[1,2,3,4,5].map(i => (
                <div key={i} className="h-10 rounded bg-white/[0.03] animate-pulse" />
              ))}
            </div>
          ) : (
            <div className="space-y-2">
              {rotation?.topPerformers?.slice(0, 6).map((sector) => (
                <div key={sector.symbol} className="flex items-center justify-between py-2 border-b border-white/[0.04] last:border-0">
                  <div>
                    <div className="text-sm text-white font-medium">{sector.name}</div>
                    <div className="text-xs text-slate-500">{sector.category}</div>
                  </div>
                  <div className="text-right">
                    <div className={clsx(
                      'text-sm font-semibold',
                      sector.pChange >= 0 ? 'text-green-400' : 'text-red-400'
                    )}>
                      {sector.pChange >= 0 ? '+' : ''}{(sector.pChange || 0).toFixed(2)}%
                    </div>
                    <div className={clsx(
                      'text-xs px-1.5 py-0.5 rounded',
                      sector.focus === 'BUY' ? 'text-green-400 bg-green-500/10' :
                      sector.focus === 'AVOID' ? 'text-red-400 bg-red-500/10' :
                      'text-slate-400 bg-slate-500/10'
                    )}>
                      {sector.focus}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Where to Focus Now */}
        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-semibold text-white">Where to Focus Now</h2>
            <Link href="/sectors" className="text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1">
              Full Analysis <ArrowRight className="w-3 h-3" />
            </Link>
          </div>
          <div className="space-y-3">
            {rotation?.whereToBuyNow?.slice(0, 5).map((sector, i) => (
              <div key={sector.symbol} className="flex items-center gap-3 p-3 rounded-lg bg-green-500/5 border border-green-500/10">
                <div className="w-6 h-6 rounded-full bg-green-500/20 flex items-center justify-center text-xs font-bold text-green-400">
                  {i + 1}
                </div>
                <div className="flex-1">
                  <div className="text-sm text-white font-medium">{sector.name}</div>
                  <div className="text-xs text-slate-500">{sector.category}</div>
                </div>
                <div className="text-green-400 text-sm font-semibold">
                  +{(sector.pChange || 0).toFixed(2)}%
                </div>
              </div>
            ))}
            {(!rotation?.whereToBuyNow || rotation.whereToBuyNow.length === 0) && (
              <div className="text-center py-8 text-slate-500 text-sm">
                No strong buy signals today. Market in consolidation.
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Quick Actions */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { href: '/patterns', label: 'View Pattern Alerts', desc: 'CALL & PUT signals', icon: Activity, color: 'text-purple-400' },
          { href: '/stocks', label: 'Lookup a Stock', desc: 'Full technical analysis', icon: Search, color: 'text-blue-400' },
          { href: '/scanners', label: 'Run a Scanner', desc: 'Custom stock filters', icon: TrendingUp, color: 'text-green-400' },
          { href: '/bot', label: 'Configure Bot', desc: 'WhatsApp integration', icon: MessageSquare, color: 'text-yellow-400' },
        ].map(({ href, label, desc, icon: Icon, color }) => (
          <Link key={href} href={href} className="card hover:bg-white/[0.06] transition-colors cursor-pointer group">
            <Icon className={clsx('w-5 h-5 mb-2', color)} />
            <div className="text-sm font-medium text-white group-hover:text-blue-300 transition-colors">{label}</div>
            <div className="text-xs text-slate-500 mt-0.5">{desc}</div>
          </Link>
        ))}
      </div>
    </div>
  );
}

function StatCard({ label, value, icon, color, href }: {
  label: string; value: string; icon: React.ReactNode;
  color: 'blue' | 'green' | 'red' | 'purple'; href: string;
}) {
  const colors = {
    blue: 'text-blue-400 bg-blue-500/10',
    green: 'text-green-400 bg-green-500/10',
    red: 'text-red-400 bg-red-500/10',
    purple: 'text-purple-400 bg-purple-500/10',
  };
  return (
    <Link href={href} className="card hover:bg-white/[0.06] transition-colors">
      <div className={clsx('w-8 h-8 rounded-lg flex items-center justify-center mb-2', colors[color])}>
        {icon}
      </div>
      <div className="text-2xl font-bold text-white">{value}</div>
      <div className="text-xs text-slate-500 mt-0.5">{label}</div>
    </Link>
  );
}
