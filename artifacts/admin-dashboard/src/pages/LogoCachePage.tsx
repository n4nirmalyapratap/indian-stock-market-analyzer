import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchAdmin } from "@/lib/api";
import {
  RefreshCw, Trash2, Search, ImageOff, CheckCircle2, XCircle, Plus,
} from "lucide-react";

type LogoRow = {
  symbol: string;
  fetch_symbol: string;
  content_type: string;
  bytes_size: number | null;
  fetch_ok: boolean;
  updated_by: string;
  fetched_at_ms: number;
  updated_at_ms: number;
};

type ListResp = { logos: LogoRow[]; total: number };

function fmtBytes(n: number | null | undefined): string {
  if (!n) return "—";
  if (n < 1024) return `${n} B`;
  return `${(n / 1024).toFixed(1)} KB`;
}

function fmtDate(ms: number): string {
  if (!ms) return "—";
  return new Date(ms).toLocaleString();
}

function LogoPreview({ symbol }: { symbol: string }) {
  const [err, setErr] = useState(false);
  if (err) return <ImageOff className="w-7 h-7 text-gray-300" />;
  return (
    <img
      src={`/api/logos/${symbol}?t=${Date.now()}`}
      alt={symbol}
      className="w-8 h-8 rounded object-contain bg-white border border-gray-200 p-0.5"
      onError={() => setErr(true)}
    />
  );
}

function RefreshModal({
  symbol,
  fetchSymbol,
  onClose,
  onDone,
}: {
  symbol: string;
  fetchSymbol: string;
  onClose: () => void;
  onDone: () => void;
}) {
  const [fetchAs, setFetchAs] = useState(fetchSymbol);
  const [result, setResult] = useState<{ ok: boolean; bytes_size: number } | null>(null);

  const refresh = useMutation({
    mutationFn: () =>
      fetchAdmin<{ ok: boolean; bytes_size: number; symbol: string }>(
        `/admin/logos/${symbol}/refresh`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ fetchAs: fetchAs !== symbol ? fetchAs : undefined }),
        },
      ),
    onSuccess: (data) => {
      setResult(data);
      onDone();
    },
  });

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-sm p-6">
        <h3 className="font-semibold text-gray-900 mb-1">Refresh logo — {symbol}</h3>
        <p className="text-xs text-gray-500 mb-4">
          The backend will fetch the logo from Dhan CDN using the symbol below and update the cache.
        </p>
        <label className="block text-xs font-medium text-gray-700 mb-1">
          Dhan fetch key
        </label>
        <input
          className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm mb-4 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          value={fetchAs}
          onChange={e => setFetchAs(e.target.value.toUpperCase())}
          placeholder="e.g. RELIANCE"
        />
        <p className="text-xs text-gray-400 mb-4">
          Change this only if Dhan uses a different ticker (e.g. LTIM → LTIMindtree).
          Leave as-is for most stocks.
        </p>

        {result && (
          <div className={`flex items-center gap-2 text-sm mb-4 ${result.ok ? "text-green-700" : "text-red-600"}`}>
            {result.ok
              ? <><CheckCircle2 className="w-4 h-4" /> Logo saved ({fmtBytes(result.bytes_size)})</>
              : <><XCircle className="w-4 h-4" /> Dhan had no logo for this key</>}
          </div>
        )}

        <div className="flex gap-2 justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm rounded-lg border border-gray-200 text-gray-600 hover:bg-gray-50"
          >
            Close
          </button>
          <button
            onClick={() => refresh.mutate()}
            disabled={refresh.isPending || !fetchAs}
            className="px-4 py-2 text-sm rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50 flex items-center gap-2"
          >
            {refresh.isPending && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
            Fetch & Save
          </button>
        </div>
      </div>
    </div>
  );
}

function AddLogoForm({ onDone }: { onDone: () => void }) {
  const [symbol, setSymbol] = useState("");
  const [fetchAs, setFetchAs] = useState("");
  const [result, setResult] = useState<{ ok: boolean; bytes_size: number } | null>(null);

  const add = useMutation({
    mutationFn: () =>
      fetchAdmin<{ ok: boolean; bytes_size: number }>(
        `/admin/logos/${symbol.trim().toUpperCase()}/refresh`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ fetchAs: fetchAs.trim() || undefined }),
        },
      ),
    onSuccess: (data) => {
      setResult(data);
      if (data.ok) {
        setSymbol("");
        setFetchAs("");
        onDone();
      }
    },
  });

  return (
    <div className="bg-indigo-50 border border-indigo-100 rounded-xl p-4 mb-6">
      <h3 className="text-sm font-semibold text-indigo-800 mb-3 flex items-center gap-2">
        <Plus className="w-4 h-4" /> Add / Override Logo
      </h3>
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="flex-1">
          <label className="block text-xs font-medium text-gray-600 mb-1">Symbol (your ticker)</label>
          <input
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            placeholder="e.g. LTIM"
            value={symbol}
            onChange={e => setSymbol(e.target.value.toUpperCase())}
          />
        </div>
        <div className="flex-1">
          <label className="block text-xs font-medium text-gray-600 mb-1">
            Dhan fetch key <span className="text-gray-400">(leave blank = same as symbol)</span>
          </label>
          <input
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            placeholder="e.g. LTIMindtree"
            value={fetchAs}
            onChange={e => setFetchAs(e.target.value)}
          />
        </div>
        <div className="flex items-end">
          <button
            onClick={() => add.mutate()}
            disabled={add.isPending || !symbol.trim()}
            className="px-4 py-2 text-sm rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50 flex items-center gap-2 whitespace-nowrap"
          >
            {add.isPending && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
            Fetch & Cache
          </button>
        </div>
      </div>
      {result && (
        <p className={`mt-2 text-xs ${result.ok ? "text-green-700" : "text-red-600"}`}>
          {result.ok
            ? `✓ Cached (${fmtBytes(result.bytes_size)})`
            : "✗ Dhan had no logo for that key. Try a different fetch key."}
        </p>
      )}
    </div>
  );
}

export default function LogoCachePage() {
  const qc = useQueryClient();
  const [search, setSearch] = useState("");
  const [refreshing, setRefreshing] = useState<string | null>(null);

  const { data, isLoading, error } = useQuery({
    queryKey: ["admin-logos"],
    queryFn: () => fetchAdmin<ListResp>("/admin/logos?limit=500"),
    refetchOnWindowFocus: false,
  });

  const del = useMutation({
    mutationFn: (symbol: string) =>
      fetchAdmin(`/admin/logos/${symbol}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-logos"] }),
  });

  const logos = (data?.logos ?? []).filter(r =>
    !search || r.symbol.includes(search.toUpperCase()) || r.fetch_symbol.includes(search.toUpperCase()),
  );

  return (
    <div className="max-w-5xl mx-auto">
      <div className="mb-6">
        <h1 className="text-xl font-bold text-gray-900">Logo Cache</h1>
        <p className="text-sm text-gray-500 mt-1">
          Stock logos are fetched from Dhan CDN once and stored in PostgreSQL. The backend serves
          them directly — no CDN call ever happens again after the first fetch.
        </p>
      </div>

      <AddLogoForm onDone={() => qc.invalidateQueries({ queryKey: ["admin-logos"] })} />

      <div className="flex items-center gap-3 mb-4">
        <div className="relative flex-1 max-w-xs">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            className="w-full pl-9 pr-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            placeholder="Filter by symbol…"
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
        </div>
        <span className="text-sm text-gray-500">
          {data?.total ?? "…"} cached
          {logos.length !== (data?.total ?? 0) && ` (${logos.length} shown)`}
        </span>
        <button
          onClick={() => qc.invalidateQueries({ queryKey: ["admin-logos"] })}
          className="ml-auto flex items-center gap-1.5 text-xs text-gray-500 hover:text-indigo-600 px-3 py-2 rounded-lg hover:bg-gray-50 border border-gray-200 transition"
        >
          <RefreshCw className="w-3.5 h-3.5" /> Reload
        </button>
      </div>

      {isLoading && (
        <div className="text-center py-12 text-gray-400 text-sm">Loading…</div>
      )}
      {error && (
        <div className="text-center py-12 text-red-500 text-sm">Failed to load logo list.</div>
      )}

      {!isLoading && !error && (
        <div className="bg-white rounded-xl border border-gray-100 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-100">
              <tr>
                <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide w-12">Logo</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Symbol</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Fetch key</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Status</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Size</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Updated</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">By</th>
                <th className="px-4 py-3 w-24"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {logos.length === 0 && (
                <tr>
                  <td colSpan={8} className="text-center py-10 text-gray-400 text-sm">
                    {search ? "No logos match that filter." : "No logos cached yet. Use the form above to add one."}
                  </td>
                </tr>
              )}
              {logos.map(row => (
                <tr key={row.symbol} className="hover:bg-gray-50/60 transition-colors">
                  <td className="px-4 py-2.5">
                    {row.fetch_ok ? (
                      <LogoPreview symbol={row.symbol} />
                    ) : (
                      <div className="w-8 h-8 rounded bg-gray-100 flex items-center justify-center">
                        <ImageOff className="w-4 h-4 text-gray-300" />
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-2.5 font-mono font-semibold text-gray-800">{row.symbol}</td>
                  <td className="px-4 py-2.5">
                    <span className={`font-mono text-xs ${row.fetch_symbol !== row.symbol ? "text-amber-700 bg-amber-50 border border-amber-200 px-1.5 py-0.5 rounded" : "text-gray-500"}`}>
                      {row.fetch_symbol}
                    </span>
                  </td>
                  <td className="px-4 py-2.5">
                    {row.fetch_ok ? (
                      <span className="inline-flex items-center gap-1 text-xs text-green-700 bg-green-50 border border-green-200 px-2 py-0.5 rounded-full">
                        <CheckCircle2 className="w-3 h-3" /> Cached
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-xs text-red-600 bg-red-50 border border-red-200 px-2 py-0.5 rounded-full">
                        <XCircle className="w-3 h-3" /> No logo
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-2.5 text-xs text-gray-500">{fmtBytes(row.bytes_size)}</td>
                  <td className="px-4 py-2.5 text-xs text-gray-400 whitespace-nowrap">{fmtDate(row.updated_at_ms)}</td>
                  <td className="px-4 py-2.5 text-xs text-gray-400 max-w-[120px] truncate">{row.updated_by || "—"}</td>
                  <td className="px-4 py-2.5">
                    <div className="flex items-center gap-1.5 justify-end">
                      <button
                        onClick={() => setRefreshing(row.symbol)}
                        title="Re-fetch from Dhan"
                        className="p-1.5 text-gray-400 hover:text-indigo-600 hover:bg-indigo-50 rounded-lg transition"
                      >
                        <RefreshCw className="w-3.5 h-3.5" />
                      </button>
                      <button
                        onClick={() => {
                          if (confirm(`Remove ${row.symbol} from cache?`)) del.mutate(row.symbol);
                        }}
                        title="Delete from cache"
                        className="p-1.5 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {refreshing && (
        <RefreshModal
          symbol={refreshing}
          fetchSymbol={logos.find(r => r.symbol === refreshing)?.fetch_symbol ?? refreshing}
          onClose={() => setRefreshing(null)}
          onDone={() => {
            setRefreshing(null);
            qc.invalidateQueries({ queryKey: ["admin-logos"] });
          }}
        />
      )}
    </div>
  );
}
