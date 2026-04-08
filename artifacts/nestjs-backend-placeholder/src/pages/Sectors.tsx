import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { TrendingUp, TrendingDown } from "lucide-react";

const CATEGORY_COLORS: Record<string, string> = {
  "Banking & Finance": "bg-blue-100 text-blue-700",
  "Technology": "bg-purple-100 text-purple-700",
  "Automobile": "bg-yellow-100 text-yellow-700",
  "Pharmaceuticals": "bg-teal-100 text-teal-700",
  "FMCG": "bg-orange-100 text-orange-700",
  "Metals & Mining": "bg-gray-100 text-gray-700",
  "Real Estate": "bg-pink-100 text-pink-700",
  "Energy & Oil": "bg-red-100 text-red-700",
  "Broad Market": "bg-indigo-100 text-indigo-700",
};

export default function Sectors() {
  const { data: sectors, isLoading } = useQuery({
    queryKey: ["sectors"],
    queryFn: api.sectors,
    staleTime: 5 * 60 * 1000,
  });
  const { data: rotation, isLoading: rotLoading } = useQuery({
    queryKey: ["rotation"],
    queryFn: api.sectorRotation,
    staleTime: 5 * 60 * 1000,
  });

  const sorted = sectors ? [...sectors].sort((a, b) => (b.pChange || 0) - (a.pChange || 0)) : [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Sector Analysis</h1>
        <p className="text-sm text-gray-500">NSE sector indices performance and rotation</p>
      </div>

      {rotation && (
        <div className="bg-indigo-600 rounded-xl text-white p-5">
          <h2 className="font-semibold text-lg">{rotation.rotationPhase}</h2>
          <p className="text-indigo-200 text-sm mt-1">{rotation.recommendation}</p>
          <div className="mt-3 flex gap-6">
            <div>
              <span className="text-2xl font-bold text-green-300">{rotation.marketBreadth?.advancing}</span>
              <span className="text-xs text-indigo-200 ml-1">Advancing</span>
            </div>
            <div>
              <span className="text-2xl font-bold text-red-300">{rotation.marketBreadth?.declining}</span>
              <span className="text-xs text-indigo-200 ml-1">Declining</span>
            </div>
            <div>
              <span className="text-2xl font-bold">{rotation.marketBreadth?.advanceDeclineRatio}</span>
              <span className="text-xs text-indigo-200 ml-1">A/D Ratio</span>
            </div>
          </div>
        </div>
      )}

      {isLoading ? (
        <div className="grid md:grid-cols-2 gap-3">
          {[...Array(8)].map((_, i) => (
            <div key={i} className="h-20 bg-gray-100 animate-pulse rounded-xl" />
          ))}
        </div>
      ) : (
        <div className="grid md:grid-cols-2 gap-3">
          {sorted.map((sector, i) => (
            <div key={i} className={`bg-white rounded-xl border shadow-sm p-4 ${sector.pChange > 0 ? "border-green-100" : sector.pChange < 0 ? "border-red-100" : "border-gray-100"}`}>
              <div className="flex items-start justify-between">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <h3 className="font-semibold text-gray-900 text-sm">{sector.name}</h3>
                    <span className={`text-xs px-2 py-0.5 rounded-full ${CATEGORY_COLORS[sector.category ?? ""] || "bg-gray-100 text-gray-600"}`}>
                      {sector.category}
                    </span>
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${sector.focus === "BUY" ? "bg-green-100 text-green-700" : sector.focus === "AVOID" ? "bg-red-100 text-red-700" : "bg-gray-100 text-gray-600"}`}>
                      {sector.focus}
                    </span>
                  </div>
                  <p className="text-xs text-gray-500 mt-0.5">{sector.symbol}</p>
                </div>
                <div className="text-right ml-2">
                  <p className="font-bold text-gray-900">{sector.lastPrice ? sector.lastPrice.toLocaleString("en-IN") : "—"}</p>
                  <p className={`text-sm font-medium flex items-center gap-0.5 justify-end ${sector.pChange >= 0 ? "text-green-600" : "text-red-500"}`}>
                    {sector.pChange >= 0 ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
                    {sector.pChange >= 0 ? "+" : ""}{sector.pChange?.toFixed(2) || "0"}%
                  </p>
                </div>
              </div>
              <div className="mt-2 flex gap-3 text-xs text-gray-500">
                {sector.advances && <span>↑ {sector.advances}</span>}
                {sector.declines && <span>↓ {sector.declines}</span>}
                {sector.source && <span className="ml-auto text-gray-400">via {sector.source}</span>}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
