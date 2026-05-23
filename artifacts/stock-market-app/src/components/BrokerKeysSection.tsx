/**
 * BrokerKeysSection — Settings card for managing per-user broker API
 * keys. Each broker shows as its own row with status (configured / not),
 * an active toggle, last-test result, and an "Add/Update key" button
 * that opens a broker-specific credential form.
 *
 * Security UX
 * -----------
 * The backend deliberately never returns decrypted credentials over
 * HTTP — `GET /user/broker-keys` returns metadata only. So this
 * component doesn't pre-fill the form on edit. To change a key the user
 * re-enters every field (same pattern GitHub / Stripe / OpenAI use).
 *
 * Adding a new broker
 * -------------------
 * Add an entry to BROKER_DEFINITIONS below. The component renders the
 * card and modal automatically from that definition. The matching
 * backend client must then land (Phases 4-8) and register a test
 * function in `app/routes/user_broker_keys.py`.
 */
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Building2, Plus, Pencil, Trash2, RefreshCw, CheckCircle2, XCircle,
  AlertCircle, ExternalLink, Lock, Eye, EyeOff,
} from "lucide-react";
import { api, BrokerKeyMeta } from "@/lib/api";

// ── Broker definitions ────────────────────────────────────────────────────
// Each broker declares the credential fields it needs + cosmetic data.
// Adding a broker = adding one entry here (backend phases land separately).

type FieldType = "text" | "password";

interface BrokerField {
  name:         string;       // key in the JSON payload sent to backend
  label:        string;       // visible label in the form
  type:         FieldType;    // "password" hides the value while typing
  placeholder?: string;
  helpText?:    string;
}

interface BrokerDef {
  slug:        string;        // matches ALLOWED_BROKERS in broker_keys.py
  name:        string;        // display name
  color:       string;        // Tailwind background class for the icon chip
  helpUrl:     string;        // docs URL — "how to get my key"
  fields:      BrokerField[];
  notes?:      string;        // shown below the form (e.g. "token expires daily")
  tier:        "ready" | "coming-soon";  // "coming-soon" disables the card
  // Honest cost framing — Indian broker APIs are NOT all free:
  //   "free"       → both trading + data tiers free with the account
  //   "paid-data"  → trading free, but data endpoints (LTP/OHLC/historical)
  //                  require a separate paid subscription
  //   "paid-base"  → entire API requires a paid subscription
  cost:        "free" | "paid-data" | "paid-base";
}

// Cost reality of each broker's MARKET-DATA (LTP / OHLC / historical) tier.
// Trading endpoints are typically free across all brokers, but the data
// endpoints — which is what this app uses — vary widely:
//   * Upstox / Angel One: data INCLUDED in their free developer plan
//   * Dhan: data is a paid add-on (~₹500/mo) on top of the free trading API
//   * Zerodha: base Kite is ₹2000/mo (covers live LTP); historical is a
//              separate ₹2000/mo add-on
//   * Groww: public API still in beta, pricing TBD
type CostTier = "free" | "paid-data" | "paid-base";
const BROKER_DEFINITIONS: BrokerDef[] = [
  {
    slug: "upstox", name: "Upstox", color: "bg-purple-600",
    helpUrl: "https://upstox.com/developer/api-documentation/",
    tier: "ready",
    fields: [
      { name: "api_key",      label: "API Key",      type: "text" },
      { name: "api_secret",   label: "API Secret",   type: "password" },
      { name: "access_token", label: "Access Token", type: "password",
        helpText: "Upstox tokens expire daily around 3:30 AM IST — regenerate via the login flow." },
    ],
    notes: "Free for Upstox account holders — both trading AND market data are included. Best free choice for this app.",
    cost: "free",
  },
  {
    slug: "angel_one", name: "Angel One (SmartAPI)", color: "bg-orange-500",
    helpUrl: "https://smartapi.angelbroking.com/",
    tier: "ready",
    fields: [
      { name: "api_key",     label: "API Key",     type: "text" },
      { name: "client_id",   label: "Client ID",   type: "text" },
      { name: "pwd",         label: "Password",    type: "password",
        helpText: "Trading password — NOT your Angel One login PIN." },
      { name: "totp_secret", label: "TOTP Secret", type: "password",
        helpText: "From the SmartAPI portal — used to generate 2FA codes server-side." },
    ],
    notes: "Free with an Angel One account — trading + market data + historical all included. We store your TOTP secret to authenticate without manual codes.",
    cost: "free",
  },
  {
    slug: "dhan", name: "Dhan", color: "bg-emerald-500",
    helpUrl: "https://dhanhq.co/docs/v2/authentication/",
    tier: "ready",
    fields: [
      { name: "client_id",    label: "Client ID",    type: "text",
        placeholder: "1100123456",
        helpText: "Your numeric Dhan client ID — visible in your Dhan account profile." },
      { name: "access_token", label: "Access Token", type: "password",
        placeholder: "eyJhbGciOi...",
        helpText: "JWT-style access token from the Dhan API settings. Long-lived." },
    ],
    notes: "Dhan's TRADING API is free, but the DATA API (quotes + historical) requires a separate paid subscription (~₹500/mo). Use this only if you've subscribed to Dhan's Data API plan.",
    cost: "paid-data",
  },
  {
    slug: "zerodha", name: "Zerodha (Kite Connect)", color: "bg-blue-600",
    helpUrl: "https://kite.trade/docs/connect/v3/",
    tier: "ready",
    fields: [
      { name: "api_key",      label: "API Key",      type: "text" },
      { name: "api_secret",   label: "API Secret",   type: "password" },
      { name: "access_token", label: "Access Token", type: "password",
        helpText: "Kite access tokens expire each day around 6 AM IST — regenerate via the daily login flow." },
    ],
    notes: "Kite Connect base is ₹2000/month (includes live LTP and OHLC). Historical data is a separate ₹2000/month add-on. Access token must be refreshed every trading day.",
    cost: "paid-base",
  },
  {
    slug: "groww", name: "Groww", color: "bg-green-600",
    helpUrl: "https://groww.in/p/groww-api",
    tier: "coming-soon",
    fields: [
      { name: "api_key",    label: "API Key",    type: "text" },
      { name: "api_secret", label: "API Secret", type: "password" },
    ],
    notes: "Groww's public API is currently in limited beta — fields and pricing may change once general availability lands.",
    cost: "free",
  },
];


// ── Per-broker card row ───────────────────────────────────────────────────

function BrokerCard({
  def, meta, onEdit,
}: {
  def:    BrokerDef;
  meta:   BrokerKeyMeta | undefined;
  onEdit: (def: BrokerDef) => void;
}) {
  const qc = useQueryClient();
  const isReady    = def.tier === "ready";
  const configured = !!meta?.configured;
  const active     = meta?.active ?? false;

  const testMut = useMutation({
    mutationFn: () => api.testBrokerKey(def.slug),
    onSuccess:   () => qc.invalidateQueries({ queryKey: ["user-broker-keys"] }),
  });
  const removeMut = useMutation({
    mutationFn: () => api.deleteBrokerKey(def.slug),
    onSuccess:   () => qc.invalidateQueries({ queryKey: ["user-broker-keys"] }),
  });
  const toggleActiveMut = useMutation({
    // The backend treats `active` as opt-in (we re-send every cred field
    // on update). To pause without re-typing, the user removes and re-adds.
    // For now, this is a no-op placeholder so the toggle reads as disabled
    // when the row exists; full pause-without-re-entry is a Phase 9 follow-up.
    mutationFn: () => Promise.resolve(),
  });

  // Format the last-test pill compactly. "Tested 3 min ago" reads cleaner
  // than a full timestamp and matches the dashboard's data-freshness style.
  const testPill = (() => {
    if (!configured) return null;
    if (!meta?.lastTestStatus) {
      return <Pill tone="neutral" icon={<AlertCircle className="w-3 h-3" />} text="Untested" />;
    }
    const ms   = meta.lastTestAtMs ?? 0;
    const ago  = ms ? humanAgo(Date.now() - ms) : "";
    if (meta.lastTestStatus === "ok") {
      return <Pill tone="ok"   icon={<CheckCircle2 className="w-3 h-3" />}
                   text={`Tested ${ago}`}
                   title={meta.lastTestError || undefined} />;
    }
    return <Pill tone="bad" icon={<XCircle className="w-3 h-3" />}
                 text={`Failed ${ago}`}
                 title={meta.lastTestError || undefined} />;
  })();

  return (
    <div className={`px-5 py-4 flex items-start gap-3 ${!isReady ? "opacity-60" : ""}`}>
      {/* Logo chip */}
      <div className={`w-10 h-10 rounded-xl ${def.color} flex items-center justify-center flex-shrink-0`}>
        <Building2 className="w-5 h-5 text-white" />
      </div>

      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between gap-2 flex-wrap mb-1">
          <div className="flex items-center gap-2">
            <h3 className="font-semibold text-gray-900 dark:text-white">{def.name}</h3>
            <CostPill cost={def.cost} />
            {def.tier === "coming-soon" && (
              <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400">
                Coming soon
              </span>
            )}
            {configured && <Pill tone="info" icon={<Lock className="w-3 h-3" />} text="Configured" />}
            {testPill}
          </div>
        </div>

        <p className="text-xs text-gray-500 dark:text-gray-400">
          {def.fields.map(f => f.label).join(" + ")}
          <span className="mx-1">·</span>
          <a href={def.helpUrl} target="_blank" rel="noreferrer"
             className="text-indigo-600 dark:text-indigo-400 hover:underline inline-flex items-center gap-0.5">
            How to get this key <ExternalLink className="w-2.5 h-2.5" />
          </a>
          {def.notes && (
            <span className="block mt-1 italic text-gray-400 dark:text-gray-500">{def.notes}</span>
          )}
        </p>

        {/* Action row */}
        {isReady && (
          <div className="flex items-center gap-2 mt-3 flex-wrap">
            <button
              onClick={() => onEdit(def)}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border border-indigo-200 dark:border-indigo-500/40 text-indigo-600 dark:text-indigo-400 rounded-md hover:bg-indigo-50 dark:hover:bg-indigo-500/10 transition"
            >
              {configured ? <><Pencil className="w-3 h-3" /> Update key</>
                          : <><Plus  className="w-3 h-3" /> Add key</>}
            </button>

            {configured && (
              <>
                <button
                  onClick={() => testMut.mutate()}
                  disabled={testMut.isPending}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 rounded-md hover:bg-gray-50 dark:hover:bg-gray-800 transition disabled:opacity-50"
                >
                  {testMut.isPending ? <RefreshCw className="w-3 h-3 animate-spin" />
                                     : <RefreshCw className="w-3 h-3" />}
                  Test
                </button>
                <button
                  onClick={() => {
                    if (confirm(`Remove your ${def.name} credentials?`)) removeMut.mutate();
                  }}
                  disabled={removeMut.isPending}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border border-red-200 dark:border-red-500/40 text-red-600 dark:text-red-400 rounded-md hover:bg-red-50 dark:hover:bg-red-500/10 transition disabled:opacity-50"
                >
                  <Trash2 className="w-3 h-3" /> Remove
                </button>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}


// ── Add / Update modal ────────────────────────────────────────────────────

function CredentialModal({
  def, onClose,
}: {
  def:     BrokerDef;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [values, setValues] = useState<Record<string, string>>(
    Object.fromEntries(def.fields.map(f => [f.name, ""])),
  );
  const [reveal, setReveal] = useState<Record<string, boolean>>({});

  const saveMut = useMutation({
    mutationFn: () => api.upsertBrokerKey(def.slug, values, true),
    onSuccess:  () => {
      qc.invalidateQueries({ queryKey: ["user-broker-keys"] });
      onClose();
    },
  });

  const valid = def.fields.every(f => values[f.name].trim().length > 0);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
         onClick={onClose}>
      <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-white/[0.08] shadow-2xl max-w-md w-full"
           onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="px-5 py-4 border-b border-gray-100 dark:border-white/[0.04] flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className={`w-8 h-8 rounded-lg ${def.color} flex items-center justify-center`}>
              <Building2 className="w-4 h-4 text-white" />
            </div>
            <div>
              <h2 className="font-bold text-gray-900 dark:text-white">{def.name}</h2>
              <p className="text-xs text-gray-500 dark:text-gray-400">Enter your API credentials</p>
            </div>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-700 dark:hover:text-gray-200">
            ✕
          </button>
        </div>

        {/* Form */}
        <div className="px-5 py-4 space-y-3">
          {def.fields.map(f => {
            const isPwd = f.type === "password";
            const shown = !isPwd || reveal[f.name];
            return (
              <div key={f.name}>
                <label className="block text-xs font-semibold text-gray-700 dark:text-gray-300 mb-1">
                  {f.label} <span className="text-red-500">*</span>
                </label>
                <div className="relative">
                  <input
                    type={shown ? "text" : "password"}
                    value={values[f.name]}
                    onChange={e => setValues(v => ({ ...v, [f.name]: e.target.value }))}
                    placeholder={f.placeholder || ""}
                    autoComplete="off"
                    spellCheck={false}
                    className="w-full px-3 py-2 pr-9 text-sm font-mono bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-white/[0.08] rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500 text-gray-900 dark:text-white"
                  />
                  {isPwd && (
                    <button type="button"
                      onClick={() => setReveal(r => ({ ...r, [f.name]: !r[f.name] }))}
                      className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-700 dark:hover:text-gray-200">
                      {shown ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  )}
                </div>
                {f.helpText && (
                  <p className="text-[11px] text-gray-500 dark:text-gray-400 mt-1">{f.helpText}</p>
                )}
              </div>
            );
          })}

          {/* Encryption-at-rest reassurance */}
          <div className="flex items-start gap-2 text-[11px] text-gray-500 dark:text-gray-400 bg-indigo-50/50 dark:bg-indigo-500/5 border border-indigo-100 dark:border-indigo-500/20 rounded-md px-3 py-2">
            <Lock className="w-3.5 h-3.5 mt-0.5 text-indigo-500 flex-shrink-0" />
            <span>
              Stored encrypted with AES-128 (Fernet) at rest. The decryption key
              is derived from this deployment's session secret. We never share
              your credentials with third parties.
            </span>
          </div>

          {saveMut.error && (
            <p className="text-xs text-red-600 dark:text-red-400">
              {(saveMut.error as Error).message || "Save failed"}
            </p>
          )}
        </div>

        {/* Footer */}
        <div className="px-5 py-3 border-t border-gray-100 dark:border-white/[0.04] flex items-center justify-end gap-2">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium border border-gray-200 dark:border-white/[0.08] text-gray-700 dark:text-gray-300 rounded-md hover:bg-gray-50 dark:hover:bg-gray-800"
          >
            Cancel
          </button>
          <button
            onClick={() => saveMut.mutate()}
            disabled={!valid || saveMut.isPending}
            className="px-4 py-2 text-sm font-medium bg-indigo-600 hover:bg-indigo-700 text-white rounded-md disabled:opacity-50 flex items-center gap-1.5"
          >
            {saveMut.isPending ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : null}
            Save credentials
          </button>
        </div>
      </div>
    </div>
  );
}


// ── Helpers ────────────────────────────────────────────────────────────────

function Pill({
  tone, icon, text, title,
}: {
  tone: "ok" | "bad" | "neutral" | "info";
  icon: React.ReactNode;
  text: string;
  title?: string;
}) {
  const cls = {
    ok:      "bg-emerald-50 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border-emerald-200 dark:border-emerald-500/20",
    bad:     "bg-rose-50 dark:bg-rose-500/10 text-rose-700 dark:text-rose-400 border-rose-200 dark:border-rose-500/20",
    neutral: "bg-amber-50 dark:bg-amber-500/10 text-amber-700 dark:text-amber-400 border-amber-200 dark:border-amber-500/20",
    info:    "bg-indigo-50 dark:bg-indigo-500/10 text-indigo-700 dark:text-indigo-400 border-indigo-200 dark:border-indigo-500/20",
  }[tone];
  return (
    <span title={title}
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold border ${cls}`}>
      {icon}{text}
    </span>
  );
}

/** Small pill that tells the user, at a glance, whether the broker's
 *  market-data API is free, partially paid, or fully paid. Avoids the
 *  user discovering after onboarding that Dhan needs a separate paid
 *  Data API subscription (which previously the UI didn't surface). */
function CostPill({ cost }: { cost: BrokerDef["cost"] }) {
  if (cost === "free") {
    return <Pill tone="ok" icon={<span className="text-[9px]">₹0</span>} text="Free" />;
  }
  if (cost === "paid-data") {
    return (
      <Pill tone="neutral" icon={<span className="text-[9px]">₹</span>}
            text="Paid data plan"
            title="Trading API is free, but the data endpoints (LTP / OHLC / historical) require a separate paid subscription." />
    );
  }
  return (
    <Pill tone="neutral" icon={<span className="text-[9px]">₹</span>}
          text="Paid subscription"
          title="The entire API requires a paid subscription." />
  );
}

function humanAgo(deltaMs: number): string {
  if (deltaMs < 60_000)        return "just now";
  if (deltaMs < 3_600_000)     return `${Math.floor(deltaMs / 60_000)}m ago`;
  if (deltaMs < 86_400_000)    return `${Math.floor(deltaMs / 3_600_000)}h ago`;
  return `${Math.floor(deltaMs / 86_400_000)}d ago`;
}


// ── Top-level section ─────────────────────────────────────────────────────

export default function BrokerKeysSection() {
  const [editing, setEditing] = useState<BrokerDef | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["user-broker-keys"],
    queryFn:  api.listBrokerKeys,
    staleTime: 30_000,
  });

  const metaBySlug = new Map<string, BrokerKeyMeta>();
  for (const m of data?.keys ?? []) metaBySlug.set(m.broker, m);

  return (
    <>
      <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-100 dark:border-white/[0.06]">
        <div className="px-5 py-3 border-b border-gray-100 dark:border-white/[0.04]">
          <p className="text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wide">
            Broker integrations
          </p>
          <p className="text-[11px] text-gray-500 dark:text-gray-400 mt-0.5">
            Connect your broker account to use real-time data from your own subscription.
            Keys are encrypted at rest and never leave this server.
          </p>
          {/* Honest cost-tier guidance — Indian broker data APIs aren't
              uniformly free, and a user who picks Dhan expecting free
              data will be surprised when their requests get rejected. */}
          <div className="mt-2 flex items-start gap-2 text-[11px] text-amber-700 dark:text-amber-400 bg-amber-50 dark:bg-amber-500/5 border border-amber-200 dark:border-amber-500/20 rounded-md px-3 py-2">
            <AlertCircle className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
            <span>
              Not all broker APIs are free for market data.
              <strong className="font-semibold"> Upstox</strong> and
              <strong className="font-semibold"> Angel One</strong> include
              live + historical data on their free developer plans.
              <strong className="font-semibold"> Dhan</strong> requires a separate
              paid Data API subscription (~₹500/mo), and
              <strong className="font-semibold"> Zerodha Kite</strong> is
              ₹2000+/month. Check the pill on each card before subscribing.
            </span>
          </div>
        </div>

        {isLoading ? (
          <div className="px-5 py-8 flex items-center justify-center gap-2 text-sm text-gray-500">
            <RefreshCw className="w-4 h-4 animate-spin" />
            Loading…
          </div>
        ) : (
          <div className="divide-y divide-gray-100 dark:divide-white/[0.04]">
            {BROKER_DEFINITIONS.map(def => (
              <BrokerCard
                key={def.slug}
                def={def}
                meta={metaBySlug.get(def.slug)}
                onEdit={setEditing}
              />
            ))}
          </div>
        )}
      </div>

      {editing && (
        <CredentialModal def={editing} onClose={() => setEditing(null)} />
      )}
    </>
  );
}
