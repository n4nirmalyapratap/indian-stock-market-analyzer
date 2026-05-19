export async function friendlyError(r: Response): Promise<string> {
  let raw = "";
  try { raw = await r.text(); } catch { /* ignore */ }
  let detail = "";
  try {
    const j = JSON.parse(raw);
    detail = String(j?.detail || j?.error || j?.message || "").trim();
  } catch { detail = raw.trim(); }
  if (r.status === 401 || r.status === 403)
    return "You're signed out. Please sign in again.";
  if (r.status === 404)
    return "We couldn't find that — it may have been deleted or re-run.";
  if (r.status === 429)
    return "You've hit today's limit. Please try again later.";
  if (r.status >= 500)
    return "Our server hit a snag. Please try again in a moment.";
  if (detail && !/^not found$/i.test(detail)) return detail;
  return `Something went wrong (HTTP ${r.status}). Please try again.`;
}

export function friendlyMessage(e: any): string {
  const m = String(e?.message || e || "").trim();
  if (!m) return "Something went wrong. Please try again.";
  if (/failed to fetch|network|load failed/i.test(m))
    return "Can't reach the server right now. Check your connection and try again.";
  if (m.startsWith("{") || m.startsWith("[")) {
    try {
      const j = JSON.parse(m);
      const d = String(j?.detail || j?.error || j?.message || "").trim();
      if (d && !/^not found$/i.test(d)) return d;
    } catch { /* fall through */ }
    return "Something went wrong. Please try again.";
  }
  return m;
}

const TICKER_RX = /^[A-Z0-9][A-Z0-9.\-]{0,19}$/;

export function sanitizeTickers(raw: string | string[], cap = 50): string[] {
  const list = Array.isArray(raw) ? raw : String(raw || "").split(",");
  const out: string[] = [];
  const seen = new Set<string>();
  for (const t of list) {
    const u = String(t || "").trim().toUpperCase();
    if (!u || !TICKER_RX.test(u)) continue;
    if (seen.has(u)) continue;
    seen.add(u);
    out.push(u);
    if (out.length >= cap) break;
  }
  return out;
}

export function sanitizeTicker(raw: string): string {
  const u = String(raw || "").trim().toUpperCase();
  return TICKER_RX.test(u) ? u : "";
}
