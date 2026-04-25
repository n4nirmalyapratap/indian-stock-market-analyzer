export class ApiError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

const SESSION_KEY = "admin_token";

export function getAdminToken(): string | null {
  return sessionStorage.getItem(SESSION_KEY);
}

export function setAdminToken(token: string) {
  sessionStorage.setItem(SESSION_KEY, token);
}

export function clearAdminToken() {
  sessionStorage.removeItem(SESSION_KEY);
}

const BASE = "/api";

export async function fetchAdmin<T>(path: string, options?: RequestInit): Promise<T> {
  const token = getAdminToken();
  const authHeaders: Record<string, string> = token ? { "X-Admin-Token": token } : {};
  const existing = (options?.headers as Record<string, string>) ?? {};
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: { ...existing, ...authHeaders },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ error: res.statusText }));
    throw new ApiError(res.status, body.error || `API error ${res.status}`);
  }
  return res.json() as Promise<T>;
}

const J = { "Content-Type": "application/json" };

export type AppUser = {
  id: string;
  email: string;
  name: string;
  created_at: number;
};

export type LogRecord = {
  ts: number;
  level: string;
  logger: string;
  msg: string;
};

export const api = {
  login: (username: string, password: string) =>
    fetchAdmin<{ token: string; expires_in: number }>("/admin/login", {
      method: "POST",
      headers: J,
      body: JSON.stringify({ username, password }),
    }),

  health: () =>
    fetch(`${BASE}/healthz`).then(r => r.json() as Promise<{ status: string }>),

  adminStatus: () =>
    fetchAdmin<{
      uptime: number;
      started_at: string;
      python_version: string;
      endpoints: number;
      telegram_configured: boolean;
      whatsapp_configured: boolean;
    }>("/admin/status"),

  // Custom auth (email+password) users
  adminAppUsers: () =>
    fetchAdmin<{ users: AppUser[]; total: number }>("/admin/users/app"),

  adminCreateUser: (email: string, password: string, name: string) =>
    fetchAdmin<{ id: string; email: string; name: string }>("/admin/users/create", {
      method: "POST",
      headers: J,
      body: JSON.stringify({ email, password, name }),
    }),

  adminDeleteAppUser: (userId: string) =>
    fetchAdmin<{ deleted: string }>(`/admin/users/app/${userId}`, { method: "DELETE" }),

  // Structured logs from in-memory ring buffer
  adminLogs: (lines = 200, level = "", search = "") => {
    const params = new URLSearchParams();
    params.set("lines", String(lines));
    if (level) params.set("level", level);
    if (search) params.set("search", search);
    return fetchAdmin<{ logs: LogRecord[]; total: number; structured: boolean }>(
      `/admin/logs?${params.toString()}`
    );
  },

  whatsappStatus: () =>
    fetchAdmin<{
      status: string;
      enabled: boolean;
      qrCode: string | null;
      sessionActive: boolean;
      lastActive: string | null;
      totalMessages: number;
      capabilities: string[];
      commands: string[];
    }>("/whatsapp/status"),

  whatsappMessages: () =>
    fetchAdmin<Array<{ from: string; text: string; timestamp: string; response: string }>>("/whatsapp/messages"),

  whatsappMessage: (from: string, message: string) =>
    fetchAdmin<{ from: string; text: string; timestamp: string; response: string }>("/whatsapp/message", {
      method: "POST",
      headers: J,
      body: JSON.stringify({ from, message }),
    }),

  telegramStatus: () =>
    fetchAdmin<Record<string, unknown>>("/telegram/status"),

  telegramMessages: () =>
    fetchAdmin<Array<{ from: string; text: string; timestamp: string; response: string }>>("/telegram/messages"),

  telegramTest: (text: string) =>
    fetchAdmin<{ text: string; response: string; timestamp: string }>("/telegram/test", {
      method: "POST",
      headers: J,
      body: JSON.stringify({ text }),
    }),
};
