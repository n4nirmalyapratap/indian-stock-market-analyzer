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
  Calendar, KeyRound,
} from "lucide-react";

export interface ClerkUserInfo {
  name: string;
  email: string;
  imageUrl?: string;
  joinedAt?: number;
}

function Avatar({ name, imageUrl, size = "lg" }: { name: string; imageUrl?: string; size?: "lg" | "xl" }) {
  const initials = name.trim().split(" ").map(n => n[0]).join("").toUpperCase().slice(0, 2) || "?";
  const cls = size === "xl"
    ? "w-20 h-20 text-2xl"
    : "w-12 h-12 text-base";

  if (imageUrl) {
    return <img src={imageUrl} alt={name} className={`${cls} rounded-full object-cover flex-shrink-0 ring-4 ring-white dark:ring-gray-900`} />;
  }
  return (
    <div className={`${cls} rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-white font-bold flex-shrink-0 ring-4 ring-white dark:ring-gray-900`}>
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

export default function SettingsPage({
  clerkUser,
  onSignOut,
}: {
  clerkUser?: ClerkUserInfo;
  onSignOut?: () => void;
}) {
  const { user: customUser, logout: customLogout } = useCustomAuth();
  const { theme, toggleWithRipple } = useTheme();
  const [botsExpanded, setBotsExpanded] = useState(false);
  const [activeBot, setActiveBot] = useState<"whatsapp" | "telegram">("whatsapp");

  const isDark = theme === "dark";

  const isGoogle  = !!clerkUser;
  const isCustom  = !isGoogle && !!customUser;

  const displayName = isGoogle ? clerkUser!.name  : customUser?.name  || "User";
  const email       = isGoogle ? clerkUser!.email : customUser?.email || "";
  const imageUrl    = isGoogle ? clerkUser!.imageUrl : undefined;
  const joinedAt    = isGoogle ? clerkUser!.joinedAt : undefined;

  const handleSignOut = () => {
    if (onSignOut) { onSignOut(); return; }
    if (isCustom) customLogout();
  };

  return (
    <div className="max-w-2xl space-y-6">

      {/* ── Profile card ──────────────────────────────────────────────────── */}
      <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-100 dark:border-white/[0.06] overflow-hidden">
        {/* Top banner */}
        <div className="h-20 bg-gradient-to-r from-indigo-500 via-purple-500 to-indigo-600" />

        <div className="px-6 pb-6">
          {/* Avatar overlapping banner */}
          <div className="-mt-10 mb-4">
            <Avatar name={displayName} imageUrl={imageUrl} size="xl" />
          </div>

          <div className="flex items-start justify-between gap-4">
            <div className="space-y-1 min-w-0">
              <h2 className="text-xl font-bold text-gray-900 dark:text-white truncate">{displayName}</h2>
              <div className="flex items-center gap-1.5 text-sm text-gray-500 dark:text-gray-400">
                <Mail className="w-3.5 h-3.5 flex-shrink-0" />
                <span className="truncate">{email}</span>
              </div>
              {joinedAt && (
                <div className="flex items-center gap-1.5 text-xs text-gray-400">
                  <Calendar className="w-3.5 h-3.5" />
                  Joined {new Date(joinedAt).toLocaleDateString(undefined, { month: "long", year: "numeric" })}
                </div>
              )}
            </div>

            {/* Auth badge */}
            <span className={`flex-shrink-0 inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold border ${
              isGoogle
                ? "bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400 border-blue-200 dark:border-blue-700"
                : "bg-indigo-50 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-400 border-indigo-200 dark:border-indigo-700"
            }`}>
              {isGoogle ? (
                <>
                  <svg className="w-3 h-3" viewBox="0 0 24 24">
                    <path fill="currentColor" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                    <path fill="currentColor" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                    <path fill="currentColor" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
                    <path fill="currentColor" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
                  </svg>
                  Google Account
                </>
              ) : (
                <>
                  <KeyRound className="w-3 h-3" />
                  Email + Password
                </>
              )}
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
            <p className="text-sm font-medium text-gray-900 dark:text-white mt-0.5">
              {isGoogle ? "Google OAuth (Sign in with Google)" : "Email & Password"}
            </p>
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
            {/* Tab switcher */}
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
          onClick={handleSignOut}
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
