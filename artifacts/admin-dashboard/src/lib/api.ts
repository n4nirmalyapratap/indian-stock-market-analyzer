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

  adminUsers: () =>
    fetchAdmin<{
      users: Array<{
        id: string;
        email: string | null;
        first_name: string | null;
        last_name: string | null;
        image_url: string | null;
        created_at: number;
        last_sign_in_at: number | null;
      }>;
      total: number;
    }>("/admin/users"),

  adminLogs: (lines?: number) =>
    fetchAdmin<{ logs: string[]; total: number }>(`/admin/logs${lines ? `?lines=${lines}` : ""}`),

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
