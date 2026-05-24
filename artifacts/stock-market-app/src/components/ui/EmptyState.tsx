/**
 * EmptyState.tsx
 * ==============
 * Consistent "no data" placeholder used across the app.
 * Replaces scattered inline text fallbacks.
 */

import { type LucideIcon, AlertCircle } from "lucide-react";

interface EmptyStateProps {
  message?:   string;
  sub?:       string;
  icon?:      LucideIcon;
  className?: string;
}

export function EmptyState({
  message   = "No data available",
  sub,
  icon: Icon = AlertCircle,
  className  = "",
}: EmptyStateProps) {
  return (
    <div className={`flex flex-col items-center justify-center gap-2 py-8 text-center ${className}`}>
      <Icon className="w-8 h-8 text-gray-300 dark:text-gray-600" />
      <p className="text-sm font-medium text-gray-500 dark:text-gray-400">{message}</p>
      {sub && <p className="text-xs text-gray-400 dark:text-gray-500">{sub}</p>}
    </div>
  );
}
