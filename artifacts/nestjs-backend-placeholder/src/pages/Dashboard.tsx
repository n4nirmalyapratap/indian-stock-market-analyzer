import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { TrendingUp, TrendingDown, Activity, AlertCircle, RefreshCw } from "lucide-react";

function StatCard({ title, value, sub, trend }: any) {
  const isUp = trend === "up";
  const isDown = trend === "down";
  return (
    <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-5">
      <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">{title}</p>
      <p className="mt-1 text-2xl font-bold text-gray-900">{value}</p>
      {sub && (
        <p className={`mt-1 text-sm flex items-center gap-1 ${isUp ? "text-green-600" : isDown ? "text-red-500" : "text-gray-500"}`}>
          {isUp && <TrendingUp className="w-3 h-3" />}
          {isDown && <TrendingDown className="w-3 h-3" />}
          {sub}
        </p>
      )}
    </div>
  );
}

export default function Dashboard() {
  const { data: rotation, isLoading: rotLoading, error: rotErr, refetch } = useQuery({
    queryKey: ["rotation"],
    queryFn: api.sectorRotation,
    staleTime: 5 * 60 * 1000,
  });
  const { data: patterns, isLoading: patLoading } = useQuery({
    queryKey: ["patterns-overview"],
    queryFn: () => api.patterns(),
    staleTime: 10 * 60 * 1000,
  });

  const breadth = rotation?.marketBreadth;
  const adRatio = breadth ? (breadth.advancing / (breadth.declining || 1)).toFixed(2) : "-";

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Market Dashboard</h1>
          <p className="text-sm text-gray-500">Indian Stock Market Analysis Platform</p>
        </div>
        <button
          onClick={() => refetch()}
          className="flex items-center gap-2 text-sm text-indigo-600 hover:text-indigo-800 border border-indigo-200 rounded-lg px-3 py-1.5 hover:bg-indigo-50 transition"
        >
          <RefreshCw className="w-4 h-4" /> Refresh
        </button>
      </div>

      {rotErr && (
        <div className="flex items-center gap-2 text-red-600 bg-red-50 border border-red-200 rounded-lg p-3 text-sm">
          <AlertCircle className="w-4 h-4" /> Unable to connect to API server. Make sure it's running.
        </div>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard title="Market Phase" value={rotLoading ? "…" : (rotation?.rotationPhase?.split(" -")[0] || "N/A")} sub={rotation?.rotationPhase?.split(" - ")[1]} />
        <StatCard title="Advancing" value={rotLoading ? "…" : breadth?.advancing ?? "-"} trend="up" sub="sectors gaining" />
        <StatCard title="Declining" value={rotLoading ? "…" : breadth?.declining ?? "-"} trend="down" sub="sectors falling" />
        <StatCard title="A/D Ratio" value={rotLoading ? "…" : adRatio} sub={`Breadth: ${breadth?.breadthScore || "-"}%`} />
      </div>

      <div className="grid md:grid-cols-2 gap-6">
        <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-5">
          <h2 className="font-semibold text-gray-800 mb-4 flex items-center gap-2">
            <TrendingUp className="w-4 h-4 text-green-500" /> Where to Buy Now
          </h2>
          {rotLoading ? (
            <div className="space-y-2">
              {[1,2,3].map(i => <div key={i} className="h-8 bg-gray-100 animate-pulse rounded" />)}
            </div>
          ) : (rotation?.whereToBuyNow?.length ?? 0) > 0 ? (
            <div className="space-y-2">
              {rotation?.whereToBuyNow?.slice(0, 5).map((s: { name: string; pChange?: number }, i: number) => (
                <div key={i} className="flex items-center justify-between p-2 rounded-lg bg-green-50">
                  <span className="text-sm font-medium text-gray-800">{s.name}</span>
                  <span className={`text-sm font-semibold ${(s.pChange ?? 0) >= 0 ? "text-green-600" : "text-red-500"}`}>
                    {(s.pChange ?? 0) >= 0 ? "+" : ""}{s.pChange?.toFixed(2) ?? "0"}%
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-gray-500">No data available</p>
          )}
        </div>

        <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-5">
          <h2 className="font-semibold text-gray-800 mb-4 flex items-center gap-2">
            <Activity className="w-4 h-4 text-indigo-500" /> Pattern Signals
          </h2>
          {patLoading ? (
            <div className="space-y-2">
              {[1,2,3].map(i => <div key={i} className="h-8 bg-gray-100 animate-pulse rounded" />)}
            </div>
          ) : patterns ? (
            <div className="space-y-3">
              <div className="flex gap-4">
                <div className="flex-1 bg-green-50 rounded-lg p-3 text-center">
                  <p className="text-2xl font-bold text-green-600">{patterns.callSignals}</p>
                  <p className="text-xs text-green-700 font-medium">CALL Signals</p>
                </div>
                <div className="flex-1 bg-red-50 rounded-lg p-3 text-center">
                  <p className="text-2xl font-bold text-red-600">{patterns.putSignals}</p>
                  <p className="text-xs text-red-700 font-medium">PUT Signals</p>
                </div>
                <div className="flex-1 bg-blue-50 rounded-lg p-3 text-center">
                  <p className="text-2xl font-bold text-blue-600">{patterns.totalPatterns}</p>
                  <p className="text-xs text-blue-700 font-medium">Total</p>
                </div>
              </div>
              <div className="space-y-1.5">
                {patterns.topCalls?.slice(0, 3).map((p: any, i: number) => (
                  <div key={i} className="flex justify-between text-sm">
                    <span className="text-gray-700">{p.symbol} — <span className="text-gray-500">{p.pattern}</span></span>
                    <span className="text-green-600 font-medium">{p.confidence}%</span>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <p className="text-sm text-gray-500">Run a pattern scan to see signals</p>
          )}
        </div>
      </div>

      <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-5">
        <h2 className="font-semibold text-gray-800 mb-3">Sector Rotation Analysis</h2>
        {rotLoading ? (
          <div className="h-16 bg-gray-100 animate-pulse rounded-lg" />
        ) : rotation ? (
          <div>
            <div className="mb-3 p-3 bg-indigo-50 rounded-lg">
              <p className="text-sm font-medium text-indigo-800">{rotation.rotationPhase}</p>
              <p className="text-xs text-indigo-600 mt-1">{rotation.recommendation}</p>
            </div>
            <div className="overflow-x-auto">
              <div className="flex gap-2 pb-2">
                {rotation.sectors?.slice(0, 8).map((s: any, i: number) => (
                  <div key={i} className={`flex-shrink-0 w-32 rounded-lg p-2.5 text-center ${s.pChange >= 0 ? "bg-green-50 border border-green-100" : "bg-red-50 border border-red-100"}`}>
                    <p className="text-xs font-medium text-gray-700 truncate">{s.name.replace("Nifty ", "")}</p>
                    <p className={`text-sm font-bold ${s.pChange >= 0 ? "text-green-600" : "text-red-500"}`}>
                      {s.pChange >= 0 ? "+" : ""}{s.pChange?.toFixed(2) || "0"}%
                    </p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        ) : (
          <p className="text-sm text-gray-500">No rotation data</p>
        )}
      </div>
    </div>
  );
}
