import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Scan, TrendingUp, TrendingDown, Filter, Activity } from "lucide-react";
import ChatButton from "@/components/ChatButton";

const UNIVERSES  = ["ALL", "NIFTY100", "MIDCAP", "SMALLCAP"];
const SIGNALS    = ["ALL", "CALL", "PUT", "WAIT"];
const CATEGORIES = ["ALL", "Candlestick", "Two-Candle", "Three-Candle", "Indicator", "Structure"];

const CAT_COLORS: Record<string, string> = {
  "Candlestick":  "bg-amber-50 text-amber-700 border border-amber-200",
  "Two-Candle":   "bg-orange-50 text-orange-700 border border-orange-200",
  "Three-Candle": "bg-rose-50 text-rose-700 border border-rose-200",
  "Indicator":    "bg-blue-50 text-blue-700 border border-blue-200",
  "Structure":    "bg-purple-50 text-purple-700 border border-purple-200",
};

const SIG_COLORS: Record<string, string> = {
  CALL: "bg-green-100 text-green-700",
  PUT:  "bg-red-100 text-red-700",
  WAIT: "bg-yellow-100 text-yellow-700",
};

const TYPE_COLORS: Record<string, string> = {
  BULLISH: "text-green-600",
  BEARISH: "text-red-500",
  NEUTRAL: "text-yellow-600",
};

export default function Patterns() {
  const [universe, setUniverse]   = useState("ALL");
  const [signal, setSignal]       = useState("ALL");
  const [category, setCategory]   = useState("ALL");
  const qc = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ["patterns", universe, signal, category],
    queryFn: () => api.patterns({
      universe: universe !== "ALL" ? universe : undefined,
      signal:   signal   !== "ALL" ? signal   : undefined,
      category: category !== "ALL" ? category : undefined,
    }),
    staleTime: 10 * 60 * 1000,
  });

  const scanMut = useMutation({
    mutationFn: api.triggerScan,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["patterns"] }),
  });

  const patterns: any[] = data?.patterns ?? [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Chart Patterns</h1>
          <p className="text-sm text-gray-500">
            50+ pattern types — candlestick, indicator & structural — across Nifty 100, Midcap & Smallcap
          </p>
        </div>
        <button
          onClick={() => scanMut.mutate()}
          disabled={scanMut.isPending}
          className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 disabled:opacity-60 transition"
        >
          <Scan className="w-4 h-4" />
          {scanMut.isPending ? "Scanning… (~2 min)" : "Run Scan Now"}
        </button>
      </div>

      {/* Stats */}
      {data && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div className="bg-green-50 border border-green-100 rounded-xl p-4 text-center">
            <p className="text-3xl font-bold text-green-600">{data.callSignals}</p>
            <p className="text-xs text-green-700 font-medium mt-1">CALL Signals</p>
          </div>
          <div className="bg-red-50 border border-red-100 rounded-xl p-4 text-center">
            <p className="text-3xl font-bold text-red-600">{data.putSignals}</p>
            <p className="text-xs text-red-700 font-medium mt-1">PUT Signals</p>
          </div>
          <div className="bg-blue-50 border border-blue-100 rounded-xl p-4 text-center">
            <p className="text-3xl font-bold text-blue-600">{data.totalPatterns}</p>
            <p className="text-xs text-blue-700 font-medium mt-1">Total Detected</p>
          </div>
          <div className="bg-indigo-50 border border-indigo-100 rounded-xl p-4 text-center">
            <p className="text-3xl font-bold text-indigo-600">{(data.categories ?? []).length}</p>
            <p className="text-xs text-indigo-700 font-medium mt-1">Pattern Categories</p>
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="bg-white border rounded-xl p-4 space-y-3">
        <div className="flex items-center gap-2 text-xs font-semibold text-gray-500 uppercase tracking-wide">
          <Filter className="w-3.5 h-3.5" /> Filters
        </div>

        <div className="flex flex-wrap gap-3">
          {/* Universe */}
          <div className="flex flex-wrap gap-1 items-center">
            <span className="text-xs text-gray-400 mr-1">Universe:</span>
            {UNIVERSES.map(u => (
              <button key={u} onClick={() => setUniverse(u)}
                className={`text-xs px-3 py-1.5 rounded-full transition ${universe === u ? "bg-indigo-600 text-white" : "bg-gray-100 text-gray-600 hover:bg-gray-200"}`}>
                {u}
              </button>
            ))}
          </div>

          {/* Signal */}
          <div className="flex flex-wrap gap-1 items-center">
            <span className="text-xs text-gray-400 mr-1">Signal:</span>
            {SIGNALS.map(s => (
              <button key={s} onClick={() => setSignal(s)}
                className={`text-xs px-3 py-1.5 rounded-full transition ${signal === s
                  ? s === "CALL" ? "bg-green-600 text-white"
                  : s === "PUT"  ? "bg-red-600 text-white"
                  : s === "WAIT" ? "bg-yellow-500 text-white"
                  : "bg-indigo-600 text-white"
                  : "bg-gray-100 text-gray-600 hover:bg-gray-200"}`}>
                {s}
              </button>
            ))}
          </div>
        </div>

        {/* Category */}
        <div className="flex flex-wrap gap-1 items-center">
          <span className="text-xs text-gray-400 mr-1">Category:</span>
          {CATEGORIES.map(c => (
            <button key={c} onClick={() => setCategory(c)}
              className={`text-xs px-3 py-1.5 rounded-full transition ${category === c ? "bg-indigo-600 text-white" : "bg-gray-100 text-gray-600 hover:bg-gray-200"}`}>
              {c}
            </button>
          ))}
        </div>

        {data?.lastScanTime && (
          <p className="text-xs text-gray-400">
            Last scan: {new Date(data.lastScanTime).toLocaleString("en-IN")}
            {" · "}{patterns.length} results shown
          </p>
        )}
      </div>

      {/* Pattern Cards */}
      {isLoading ? (
        <div className="space-y-3">
          {[...Array(8)].map((_, i) => (
            <div key={i} className="h-24 bg-gray-100 animate-pulse rounded-xl" />
          ))}
        </div>
      ) : patterns.length > 0 ? (
        <div className="space-y-2">
          {patterns.map((p: any, i: number) => (
            <div key={i} className={`bg-white rounded-xl border shadow-sm p-4 ${
              p.signal === "CALL" ? "border-green-100" :
              p.signal === "PUT"  ? "border-red-100"   :
              "border-yellow-100"
            }`}>
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span className="font-bold text-gray-900">{p.symbol}</span>
                    <ChatButton symbol={p.symbol} />
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${SIG_COLORS[p.signal] ?? "bg-gray-100 text-gray-600"}`}>
                      {p.signal}
                    </span>
                    <span className={`text-xs px-2 py-0.5 rounded-full ${CAT_COLORS[p.category] ?? "bg-gray-100 text-gray-600"}`}>
                      {p.category}
                    </span>
                    <span className="text-xs bg-gray-100 text-gray-700 px-2 py-0.5 rounded-full font-medium">
                      {p.pattern}
                    </span>
                    <span className="text-xs text-gray-400">{p.universe}</span>
                  </div>
                  <p className="text-xs text-gray-500 mt-1.5 leading-relaxed">{p.description}</p>
                  {(p.targetPrice || p.stopLoss) && (
                    <div className="mt-2 flex gap-4 text-xs items-center">
                      {p.signal === "CALL"
                        ? <TrendingUp  className="w-3 h-3 text-green-500 flex-shrink-0" />
                        : <TrendingDown className="w-3 h-3 text-red-500  flex-shrink-0" />
                      }
                      {p.targetPrice && (
                        <span className="text-green-600 font-medium">Target: ₹{p.targetPrice?.toFixed(2)}</span>
                      )}
                      {p.stopLoss && (
                        <span className="text-red-500 font-medium">SL: ₹{p.stopLoss?.toFixed(2)}</span>
                      )}
                    </div>
                  )}
                </div>
                <div className="text-right flex-shrink-0">
                  <p className="font-semibold text-gray-900">₹{p.currentPrice?.toFixed(2)}</p>
                  <p className={`text-xs font-medium mt-0.5 ${TYPE_COLORS[p.patternType] ?? "text-gray-500"}`}>
                    {p.confidence}% confidence
                  </p>
                  <p className="text-xs text-gray-400 mt-0.5">{p.patternType}</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="text-center py-16 text-gray-500">
          <Activity className="w-10 h-10 mx-auto mb-3 opacity-20" />
          <p className="font-medium">No patterns detected yet</p>
          <p className="text-sm mt-1">Click "Run Scan Now" to begin detection across 28 stocks</p>
          <p className="text-xs mt-1 text-gray-400">First scan takes ~2 minutes to fetch and analyze all data</p>
        </div>
      )}
    </div>
  );
}
