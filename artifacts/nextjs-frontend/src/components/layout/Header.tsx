'use client';
import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Search, Bell, RefreshCw } from 'lucide-react';

export function Header() {
  const [searchInput, setSearchInput] = useState('');
  const router = useRouter();

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    const symbol = searchInput.trim().toUpperCase();
    if (symbol) {
      router.push(`/stocks?symbol=${symbol}`);
      setSearchInput('');
    }
  };

  return (
    <header className="flex items-center gap-4 px-5 py-3.5 border-b border-white/[0.06] bg-[#0a0d16]">
      <form onSubmit={handleSearch} className="flex-1 max-w-md">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
          <input
            type="text"
            value={searchInput}
            onChange={e => setSearchInput(e.target.value)}
            placeholder="Search NSE symbol... (e.g. RELIANCE, TCS)"
            className="w-full pl-9 pr-4 py-2 text-sm bg-white/[0.04] border border-white/[0.08] rounded-lg text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500/50 focus:bg-white/[0.06] transition-all"
          />
        </div>
      </form>

      <div className="flex items-center gap-2 ml-auto">
        <div className="flex items-center gap-1.5 text-xs text-slate-500 px-3 py-1.5 rounded-lg bg-white/[0.03] border border-white/[0.06]">
          <div className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse"></div>
          <span>NSE Data Live</span>
        </div>
        <button className="p-2 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-white/[0.04] transition-colors">
          <Bell className="w-4 h-4" />
        </button>
      </div>
    </header>
  );
}
