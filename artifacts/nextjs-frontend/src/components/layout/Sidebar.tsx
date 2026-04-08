'use client';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  LayoutDashboard,
  PieChart,
  TrendingUp,
  Activity,
  Search,
  MessageSquare,
  BarChart2,
  Cpu,
} from 'lucide-react';
import { clsx } from 'clsx';

const navItems = [
  { href: '/', label: 'Dashboard', icon: LayoutDashboard },
  { href: '/sectors', label: 'Sectors', icon: PieChart },
  { href: '/stocks', label: 'Stock Lookup', icon: TrendingUp },
  { href: '/patterns', label: 'Chart Patterns', icon: Activity },
  { href: '/scanners', label: 'Scanners', icon: Search },
  { href: '/bot', label: 'WhatsApp Bot', icon: MessageSquare },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="hidden md:flex flex-col w-60 border-r border-white/[0.06] bg-[#0a0d16]">
      <div className="flex items-center gap-3 px-5 py-5 border-b border-white/[0.06]">
        <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center">
          <BarChart2 className="w-5 h-5 text-white" />
        </div>
        <div>
          <div className="text-sm font-semibold text-white">StockBot India</div>
          <div className="text-xs text-slate-500">NSE Market Analysis</div>
        </div>
      </div>

      <nav className="flex-1 px-3 py-4 space-y-1">
        {navItems.map(({ href, label, icon: Icon }) => {
          const active = pathname === href;
          return (
            <Link
              key={href}
              href={href}
              className={clsx(
                'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-all duration-150',
                active
                  ? 'bg-blue-600/20 text-blue-400 font-medium'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-white/[0.04]'
              )}
            >
              <Icon className="w-4 h-4 flex-shrink-0" />
              {label}
            </Link>
          );
        })}
      </nav>

      <div className="px-4 py-4 border-t border-white/[0.06]">
        <div className="flex items-center gap-2 text-xs text-slate-500">
          <Cpu className="w-3 h-3" />
          <span>End-of-Day Data</span>
          <span className="ml-auto text-slate-600">NSE + Yahoo</span>
        </div>
      </div>
    </aside>
  );
}
