import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useCustomAuth } from "@/context/CustomAuthContext";
import { useTheme } from "@/context/ThemeContext";
import WhatsAppBot from "@/pages/WhatsAppBot";
import TelegramBot from "@/pages/TelegramBot";
import {
  User, Mail, Shield, LogOut, Sun, Moon, ChevronDown,
  MessageCircle, Send, Wifi, WifiOff, CheckCircle, XCircle,
  KeyRound,
} from "lucide-react";

function Avatar({ name }: { name: string }) {
  const initials = name.trim().split(" ").map(n => n[0]).join("").toUpperCase().slice(0, 2) || "?";
  return (
    <div className="w-20 h-20 text-2xl rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-white font-bold flex-shrink-0 ring-4 ring-white dark:ring-gray-900">
      {initials}
    </div>
  );
}

function WhatsAppStatus() {
  const { data } = useQuery({ queryKey: ["whatsapp-status"], queryFn: api.whatsappStatus, refetchInterval: 30000 });
  return data?.enabled
    ? <span className="flex items-center gap-1.5 text-xs text-green-600 dark:text-green-400 font-medium"><Wifi className="w-3 h-3" /> Connected</span>
    : <span className="flex items-center gap-1.5 text-xs text-gray-400"><WifiOff className="w-3 h-3" /> Disabled</span>;
}

function TelegramStatus() {
  const { data } = useQuery({ queryKey: ["telegram-status"], queryFn: () => api.telegramStatus(), refetchInterval: 15000 });
  const ok = (data as any)?.configured;
  return ok
    ? <span className="flex items-center gap-1.5 text-xs text-green-600 dark:text-green-400 font-medium"><CheckCircle className="w-3 h-3" /> Configured</span>
    : <span className="flex items-center gap-1.5 text-xs text-gray-400"><XCircle className="w-3 h-3" /> Not configured</span>;
}

export default function SettingsPage() {
  const { user, logout } = useCustomAuth();
  const { theme, toggleWithRipple } = useTheme();
  const [botsExpanded, setBotsExpanded] = useState(false);
  const [activeBot, setActiveBot] = useState<"whatsapp" | "telegram">("whatsapp");

  const isDark = theme === "dark";
  const displayName = user?.name || "User";
  const email = user?.email || "";

  return (
    <div className="max-w-2xl space-y-6">

      {/* ── Profile card ──────────────────────────────────────────────────── */}
      <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-100 dark:border-white/[0.06] overflow-hidden">
        <div className="h-20 bg-gradient-to-r from-indigo-500 via-purple-500 to-indigo-600" />

        <div className="px-6 pb-6">
          <div className="-mt-10 mb-4">
            <Avatar name={displayName} />
          </div>

          <div className="flex items-start justify-between gap-4">
            <div className="space-y-1 min-w-0">
              <h2 className="text-xl font-bold text-gray-900 dark:text-white truncate">{displayName}</h2>
              <div className="flex items-center gap-1.5 text-sm text-gray-500 dark:text-gray-400">
                <Mail className="w-3.5 h-3.5 flex-shrink-0" />
                <span className="truncate">{email}</span>
              </div>
            </div>

            <span className="flex-shrink-0 inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold border bg-indigo-50 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-400 border-indigo-200 dark:border-indigo-700">
              <KeyRound className="w-3 h-3" />
              Email + Password
            </span>
          </div>
        </div>
      </div>

      {/* ── Account details ────────────────────────────────────────────────── */}
      <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-100 dark:border-white/[0.06] divide-y divide-gray-100 dark:divide-white/[0.04]">

        <div className="px-5 py-4 flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-gray-100 dark:bg-gray-800 flex items-center justify-center flex-shrink-0">
            <User className="w-4 h-4 text-gray-500 dark:text-gray-400" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-xs font-medium text-gray-400 dark:text-gray-500 uppercase tracking-wide">Full Name</p>
            <p className="text-sm font-medium text-gray-900 dark:text-white truncate mt-0.5">{displayName}</p>
          </div>
        </div>

        <div className="px-5 py-4 flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-gray-100 dark:bg-gray-800 flex items-center justify-center flex-shrink-0">
            <Mail className="w-4 h-4 text-gray-500 dark:text-gray-400" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-xs font-medium text-gray-400 dark:text-gray-500 uppercase tracking-wide">Email Address</p>
            <p className="text-sm font-medium text-gray-900 dark:text-white truncate mt-0.5">{email}</p>
          </div>
        </div>

        <div className="px-5 py-4 flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-gray-100 dark:bg-gray-800 flex items-center justify-center flex-shrink-0">
            <Shield className="w-4 h-4 text-gray-500 dark:text-gray-400" />
          </div>
          <div className="flex-1">
            <p className="text-xs font-medium text-gray-400 dark:text-gray-500 uppercase tracking-wide">Sign-in Method</p>
            <p className="text-sm font-medium text-gray-900 dark:text-white mt-0.5">Email & Password</p>
          </div>
        </div>
      </div>

      {/* ── Preferences ───────────────────────────────────────────────────── */}
      <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-100 dark:border-white/[0.06]">
        <div className="px-5 py-3 border-b border-gray-100 dark:border-white/[0.04]">
          <p className="text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wide">Preferences</p>
        </div>
        <div className="px-5 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-gray-100 dark:bg-gray-800 flex items-center justify-center">
              {isDark ? <Moon className="w-4 h-4 text-indigo-400" /> : <Sun className="w-4 h-4 text-amber-500" />}
            </div>
            <div>
              <p className="text-sm font-medium text-gray-900 dark:text-white">Appearance</p>
              <p className="text-xs text-gray-400 dark:text-gray-500">{isDark ? "Dark mode is on" : "Light mode is on"}</p>
            </div>
          </div>
          <button
            onClick={(e) => toggleWithRipple(e.clientX, e.clientY)}
            className={`relative w-11 h-6 rounded-full transition-colors duration-200 focus:outline-none ${
              isDark ? "bg-indigo-600" : "bg-gray-200"
            }`}
          >
            <span className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform duration-200 ${
              isDark ? "translate-x-5" : "translate-x-0"
            }`} />
          </button>
        </div>
      </div>

      {/* ── Bot Integrations (collapsed) ──────────────────────────────────── */}
      <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-100 dark:border-white/[0.06] overflow-hidden">
        <button
          onClick={() => setBotsExpanded(s => !s)}
          className="w-full px-5 py-4 flex items-center justify-between hover:bg-gray-50 dark:hover:bg-white/[0.02] transition"
        >
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-gray-100 dark:bg-gray-800 flex items-center justify-center">
              <MessageCircle className="w-4 h-4 text-gray-500 dark:text-gray-400" />
            </div>
            <div className="text-left">
              <p className="text-sm font-medium text-gray-900 dark:text-white">Bot Integrations</p>
              <p className="text-xs text-gray-400 dark:text-gray-500">WhatsApp & Telegram market bots</p>
            </div>
          </div>
          <ChevronDown className={`w-4 h-4 text-gray-400 transition-transform duration-200 ${botsExpanded ? "rotate-180" : ""}`} />
        </button>

        {botsExpanded && (
          <div className="border-t border-gray-100 dark:border-white/[0.04]">
            <div className="flex gap-1 p-3 bg-gray-50 dark:bg-gray-800/50">
              {([
                { id: "whatsapp" as const, label: "WhatsApp", icon: MessageCircle },
                { id: "telegram" as const, label: "Telegram",  icon: Send },
              ]).map(({ id, label, icon: Icon }) => (
                <button
                  key={id}
                  onClick={() => setActiveBot(id)}
                  className={`flex-1 flex items-center justify-center gap-2 py-2 rounded-lg text-sm font-medium transition ${
                    activeBot === id
                      ? "bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm"
                      : "text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
                  }`}
                >
                  <Icon className="w-3.5 h-3.5" />
                  {label}
                  <span className="ml-1">
                    {id === "whatsapp" ? <WhatsAppStatus /> : <TelegramStatus />}
                  </span>
                </button>
              ))}
            </div>
            <div className="p-4">
              {activeBot === "whatsapp" && <WhatsAppBot embedded />}
              {activeBot === "telegram" && <TelegramBot embedded />}
            </div>
          </div>
        )}
      </div>

      {/* ── Sign out ──────────────────────────────────────────────────────── */}
      <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-100 dark:border-white/[0.06]">
        <button
          onClick={logout}
          className="w-full px-5 py-4 flex items-center gap-3 text-left hover:bg-red-50 dark:hover:bg-red-900/10 group transition rounded-2xl"
        >
          <div className="w-8 h-8 rounded-lg bg-red-50 dark:bg-red-900/20 flex items-center justify-center flex-shrink-0">
            <LogOut className="w-4 h-4 text-red-500" />
          </div>
          <div>
            <p className="text-sm font-medium text-red-600 dark:text-red-400 group-hover:text-red-700 dark:group-hover:text-red-300">Sign out</p>
            <p className="text-xs text-gray-400 dark:text-gray-500">{email}</p>
          </div>
        </button>
      </div>

    </div>
  );
}
