export class ApiError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

let _getToken: ((opts?: Record<string, unknown>) => Promise<string | null>) | null = null;

export function setTokenGetter(fn: (opts?: Record<string, unknown>) => Promise<string | null>) {
  _getToken = fn;
}

const BASE = "/api";

export async function fetchApi<T>(path: string, options?: RequestInit): Promise<T> {
  const authHeaders: Record<string, string> = {};
  if (_getToken) {
    try {
      const token = await _getToken();
      if (token) authHeaders["Authorization"] = `Bearer ${token}`;
    } catch {
      // not signed in yet
    }
  }
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
  health: () => fetchApi<{ status: string }>("/healthz"),

  adminStatus: () =>
    fetchApi<{
      uptime: number;
      started_at: string;
      python_version: string;
      endpoints: number;
      telegram_configured: boolean;
      whatsapp_configured: boolean;
    }>("/admin/status"),

  adminUsers: () =>
    fetchApi<{
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
    fetchApi<{ logs: string[]; total: number }>(`/admin/logs${lines ? `?lines=${lines}` : ""}`),

  whatsappStatus: () =>
    fetchApi<{
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
    fetchApi<Array<{ from: string; text: string; timestamp: string; response: string }>>("/whatsapp/messages"),

  whatsappMessage: (from: string, message: string) =>
    fetchApi<{ from: string; text: string; timestamp: string; response: string }>("/whatsapp/message", {
      method: "POST",
      headers: J,
      body: JSON.stringify({ from, message }),
    }),

  telegramStatus: () =>
    fetchApi<Record<string, unknown>>("/telegram/status"),

  telegramMessages: () =>
    fetchApi<Array<{ from: string; text: string; timestamp: string; response: string }>>("/telegram/messages"),

  telegramTest: (text: string) =>
    fetchApi<{ text: string; response: string; timestamp: string }>("/telegram/test", {
      method: "POST",
      headers: J,
      body: JSON.stringify({ text }),
    }),
};
