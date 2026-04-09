import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import WhatsAppBot from "@/pages/WhatsAppBot";
import TelegramBot from "@/pages/TelegramBot";
import {
  MessageCircle, Send, Settings, Wifi, WifiOff,
  CheckCircle, XCircle, ChevronRight
} from "lucide-react";

type Tab = "whatsapp" | "telegram";

const INTEGRATIONS: { id: Tab; label: string; icon: React.ElementType; color: string; bg: string; description: string }[] = [
  {
    id: "whatsapp",
    label: "WhatsApp Bot",
    icon: MessageCircle,
    color: "text-green-700",
    bg: "bg-green-50 border-green-200",
    description: "Test and preview WhatsApp bot commands",
  },
  {
    id: "telegram",
    label: "Telegram Bot",
    icon: Send,
    color: "text-blue-700",
    bg: "bg-blue-50 border-blue-200",
    description: "Real-time NSE data via Telegram with NLP",
  },
];

function WhatsAppStatusDot() {
  const { data } = useQuery({ queryKey: ["whatsapp-status"], queryFn: api.whatsappStatus, refetchInterval: 30000 });
  return data?.enabled
    ? <span className="flex items-center gap-1 text-xs text-green-600 font-medium"><Wifi className="w-3 h-3" /> Connected</span>
    : <span className="flex items-center gap-1 text-xs text-gray-400"><WifiOff className="w-3 h-3" /> Disabled</span>;
}

function TelegramStatusDot() {
  const { data } = useQuery({ queryKey: ["telegram-status"], queryFn: () => api.telegramStatus(), refetchInterval: 15000 });
  const ok = (data as any)?.configured;
  return ok
    ? <span className="flex items-center gap-1 text-xs text-green-600 font-medium"><CheckCircle className="w-3 h-3" /> Configured</span>
    : <span className="flex items-center gap-1 text-xs text-gray-400"><XCircle className="w-3 h-3" /> Not configured</span>;
}

export default function SettingsPage() {
  const [tab, setTab] = useState<Tab>("whatsapp");

  return (
    <div className="space-y-6 max-w-5xl">

      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-indigo-50 flex items-center justify-center">
          <Settings className="w-5 h-5 text-indigo-600" />
        </div>
        <div>
          <h1 className="text-xl font-bold text-gray-900">Settings</h1>
          <p className="text-sm text-gray-500">Manage bot integrations and notifications</p>
        </div>
      </div>

      {/* Integration selector cards */}
      <div>
        <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-3">Integrations</p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {INTEGRATIONS.map(({ id, label, icon: Icon, color, bg, description }) => {
            const active = tab === id;
            return (
              <button
                key={id}
                onClick={() => setTab(id)}
                className={`relative text-left rounded-xl border p-4 transition-all
                  ${active
                    ? `${bg} shadow-sm ring-2 ring-offset-1 ${id === "whatsapp" ? "ring-green-300" : "ring-blue-300"}`
                    : "bg-white border-gray-200 hover:border-gray-300 hover:shadow-sm"
                  }`}
              >
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <div className={`w-9 h-9 rounded-lg flex items-center justify-center ${active ? "bg-white shadow-sm" : "bg-gray-50"}`}>
                      <Icon className={`w-4 h-4 ${active ? color : "text-gray-400"}`} />
                    </div>
                    <div>
                      <p className={`text-sm font-semibold ${active ? color : "text-gray-700"}`}>{label}</p>
                      <p className="text-xs text-gray-400 mt-0.5">{description}</p>
                    </div>
                  </div>
                  <ChevronRight className={`w-4 h-4 mt-1 transition-transform ${active ? `${color} rotate-90` : "text-gray-300"}`} />
                </div>
                <div className="mt-3 pt-3 border-t border-gray-100">
                  {id === "whatsapp" ? <WhatsAppStatusDot /> : <TelegramStatusDot />}
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* Divider */}
      <div className="border-t border-gray-100" />

      {/* Bot console */}
      <div>
        <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-4">
          {tab === "whatsapp" ? "WhatsApp" : "Telegram"} Console
        </p>
        {tab === "whatsapp" && <WhatsAppBot embedded />}
        {tab === "telegram" && <TelegramBot embedded />}
      </div>
    </div>
  );
}
