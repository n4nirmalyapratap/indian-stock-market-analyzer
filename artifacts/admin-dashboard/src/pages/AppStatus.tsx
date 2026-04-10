import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Activity, Clock, Code2, Zap, MessageCircle, Send, RefreshCw } from "lucide-react";

function StatCard({ icon: Icon, label, value, color = "indigo" }: {
  icon: React.ElementType;
  label: string;
  value: string | number;
  color?: string;
}) {
  const colors: Record<string, string> = {
    indigo: "bg-indigo-50 text-indigo-600",
    green: "bg-green-50 text-green-600",
    blue: "bg-blue-50 text-blue-600",
    amber: "bg-amber-50 text-amber-600",
    purple: "bg-purple-50 text-purple-600",
  };
  return (
    <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-5 flex items-center gap-4">
      <div className={`w-11 h-11 rounded-lg flex items-center justify-center flex-shrink-0 ${colors[color] || colors.indigo}`}>
        <Icon className="w-5 h-5" />
      </div>
      <div>
        <p className="text-xs text-gray-500 font-medium uppercase tracking-wide">{label}</p>
        <p className="text-lg font-bold text-gray-900 mt-0.5">{value}</p>
      </div>
    </div>
  );
}

function formatUptime(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) return `${h}h ${m}m ${s}s`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

export default function AppStatus() {
  const { data, isLoading, isError, refetch, isFetching } = useQuery({
    queryKey: ["admin-status"],
    queryFn: api.adminStatus,
    refetchInterval: 15000,
  });

  const { data: health } = useQuery({
    queryKey: ["health"],
    queryFn: api.health,
    refetchInterval: 10000,
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">App Status</h1>
          <p className="text-sm text-gray-500 mt-0.5">Backend health and runtime metrics</p>
        </div>
        <button
          onClick={() => refetch()}
          disabled={isFetching}
          className="flex items-center gap-2 px-3 py-1.5 text-sm bg-white border border-gray-200 rounded-lg hover:bg-gray-50 transition disabled:opacity-60"
        >
          <RefreshCw className={`w-4 h-4 ${isFetching ? "animate-spin" : ""}`} />
          Refresh
        </button>
      </div>

      {/* API Health pill */}
      <div className="flex items-center gap-3">
        <div className={`flex items-center gap-2 px-4 py-2 rounded-full text-sm font-medium border
          ${health ? "bg-green-50 border-green-200 text-green-700" : "bg-red-50 border-red-200 text-red-600"}`}>
          <span className={`w-2 h-2 rounded-full ${health ? "bg-green-500 animate-pulse" : "bg-red-500"}`} />
          {health ? "API: ONLINE" : "API: OFFLINE"}
        </div>
        {data && (
          <span className="text-xs text-gray-400">
            Started: {new Date(data.started_at).toLocaleString()}
          </span>
        )}
      </div>

      {isLoading && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {[1,2,3,4].map(i => (
            <div key={i} className="bg-gray-100 rounded-xl h-20 animate-pulse" />
          ))}
        </div>
      )}

      {isError && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-sm text-red-700">
          Failed to load status. The <code className="bg-red-100 px-1 rounded">/api/admin/status</code> endpoint may not exist yet.
        </div>
      )}

      {data && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard icon={Clock}    label="Uptime"           value={formatUptime(data.uptime)}  color="green"  />
          <StatCard icon={Code2}    label="Python Version"   value={data.python_version}        color="blue"   />
          <StatCard icon={Zap}      label="API Endpoints"    value={data.endpoints}             color="purple" />
          <StatCard icon={Activity} label="Backend"          value="Running"                    color="indigo" />
        </div>
      )}

      {data && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div className={`bg-white rounded-xl border p-5 flex items-center gap-4
            ${data.telegram_configured ? "border-blue-100" : "border-gray-100"}`}>
            <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${data.telegram_configured ? "bg-blue-50" : "bg-gray-50"}`}>
              <Send className={`w-5 h-5 ${data.telegram_configured ? "text-blue-500" : "text-gray-400"}`} />
            </div>
            <div>
              <p className="text-xs text-gray-500 uppercase tracking-wide font-medium">Telegram Bot</p>
              <p className={`text-sm font-semibold mt-0.5 ${data.telegram_configured ? "text-blue-700" : "text-gray-400"}`}>
                {data.telegram_configured ? "Token Configured" : "Not Configured"}
              </p>
            </div>
          </div>
          <div className={`bg-white rounded-xl border p-5 flex items-center gap-4
            ${data.whatsapp_configured ? "border-green-100" : "border-gray-100"}`}>
            <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${data.whatsapp_configured ? "bg-green-50" : "bg-gray-50"}`}>
              <MessageCircle className={`w-5 h-5 ${data.whatsapp_configured ? "text-green-500" : "text-gray-400"}`} />
            </div>
            <div>
              <p className="text-xs text-gray-500 uppercase tracking-wide font-medium">WhatsApp Bot</p>
              <p className={`text-sm font-semibold mt-0.5 ${data.whatsapp_configured ? "text-green-700" : "text-gray-400"}`}>
                {data.whatsapp_configured ? "Configured" : "Not Configured"}
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
