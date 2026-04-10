import { useCustomAuth } from "@/context/CustomAuthContext";
import { useTheme } from "@/context/ThemeContext";
import {
  User, Mail, Shield, LogOut, Sun, Moon, KeyRound,
} from "lucide-react";

function Avatar({ name }: { name: string }) {
  const initials = name.trim().split(" ").map(n => n[0]).join("").toUpperCase().slice(0, 2) || "?";
  return (
    <div className="w-20 h-20 text-2xl rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-white font-bold flex-shrink-0 ring-4 ring-white dark:ring-gray-900">
      {initials}
    </div>
  );
}

export default function SettingsPage() {
  const { user, logout } = useCustomAuth();
  const { theme, toggleWithRipple } = useTheme();

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
