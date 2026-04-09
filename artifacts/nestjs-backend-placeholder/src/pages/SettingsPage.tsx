import WhatsAppBot from "@/pages/WhatsAppBot";
import TelegramBot from "@/pages/TelegramBot";
import { MessageCircle, Send } from "lucide-react";
import { useState } from "react";

const TABS = [
  { id: "whatsapp", label: "WhatsApp Bot", icon: MessageCircle },
  { id: "telegram", label: "Telegram Bot", icon: Send },
];

export default function SettingsPage() {
  const [tab, setTab] = useState("whatsapp");

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Settings</h1>
        <p className="text-sm text-gray-500 mt-1">Manage bot integrations and notifications</p>
      </div>

      <div className="flex gap-1 bg-gray-100 rounded-xl p-1 w-fit">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all
              ${tab === id
                ? "bg-white shadow-sm text-gray-900"
                : "text-gray-500 hover:text-gray-700"
              }`}
          >
            <Icon className="w-4 h-4" />
            {label}
          </button>
        ))}
      </div>

      <div>
        {tab === "whatsapp" && <WhatsAppBot />}
        {tab === "telegram" && <TelegramBot />}
      </div>
    </div>
  );
}
