/**
 * Email Digest settings — manage subscriptions that mail a daily portfolio
 * summary at a fixed IST time.
 *
 * Layout:
 *   - SMTP wire-status banner at top (green/amber depending on backend config)
 *   - List of existing subscriptions with edit / delete / send-now controls
 *   - "Add subscription" form
 *
 * The settings page only talks to /api/email-digest/*. The daily send is
 * driven entirely by the backend scheduler — no client-side polling needed.
 */
import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Mail, Send, Trash2, Plus, Loader2, AlertCircle, Check } from "lucide-react";
import { api, EmailDigestSubscription } from "@/lib/api";

const DEFAULT_TIME = "18:00";

function pillColor(enabled: boolean) {
  return enabled
    ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300"
    : "bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400";
}

function ConfigBanner({
  config,
}: { config: ReturnType<typeof useEmailConfig>["data"] | undefined }) {
  if (!config) return null;
  if (config.configured) {
    return (
      <div className="rounded-xl border border-emerald-300 bg-emerald-50 dark:bg-emerald-900/20 dark:border-emerald-700 px-4 py-3 text-sm flex items-start gap-2 text-emerald-800 dark:text-emerald-200">
        <Check className="w-4 h-4 mt-0.5 flex-shrink-0" />
        <div>
          <p className="font-medium">SMTP is configured.</p>
          <p className="text-xs mt-1 opacity-80">
            From <span className="font-mono">{config.fromAddress}</span> via{" "}
            <span className="font-mono">{config.host}:{config.port}</span>{" "}
            (TLS {config.useTls ? "on" : "off"}). Rate-limited to{" "}
            {config.sendsPerMin}/min · {config.sendsPerDay}/day.
          </p>
        </div>
      </div>
    );
  }
  return (
    <div className="rounded-xl border border-amber-300 bg-amber-50 dark:bg-amber-900/20 dark:border-amber-700 px-4 py-3 text-sm flex items-start gap-2 text-amber-800 dark:text-amber-200">
      <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
      <div>
        <p className="font-medium">SMTP is not configured.</p>
        <p className="text-xs mt-1 opacity-80">
          Subscriptions are saved but no emails will be sent until the backend's{" "}
          <code>SMTP_HOST</code>, <code>SMTP_USERNAME</code>, and{" "}
          <code>SMTP_PASSWORD</code> environment variables are set. For Gmail,
          create an App Password and set <code>SMTP_HOST=smtp.gmail.com</code>,{" "}
          <code>SMTP_PORT=587</code>.
        </p>
      </div>
    </div>
  );
}

function SubscriptionCard({
  sub, onChanged,
}: { sub: EmailDigestSubscription; onChanged: () => void }) {
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft]     = useState<EmailDigestSubscription>(sub);

  const upsert = useMutation({
    mutationFn: () => api.emailDigestUpsert({
      groupName:      draft.groupName,
      recipientEmail: draft.recipientEmail,
      symbols:        draft.symbols,
      sendTimeIst:    draft.sendTimeIst,
      enabled:        draft.enabled,
    }),
    onSuccess: () => { setEditing(false); onChanged(); qc.invalidateQueries({ queryKey: ["emailDigestList"] }); },
  });
  const remove = useMutation({
    mutationFn: () => api.emailDigestDelete(sub.id),
    onSuccess: () => { onChanged(); qc.invalidateQueries({ queryKey: ["emailDigestList"] }); },
  });
  const sendNow = useMutation({
    mutationFn: () => api.emailDigestSendNow(sub.id),
  });

  // Reset draft when not editing so it always reflects server state.
  useEffect(() => { if (!editing) setDraft(sub); }, [sub, editing]);

  return (
    <div className="rounded-xl border border-gray-200 dark:border-white/10 bg-white dark:bg-gray-900 p-4 space-y-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <code className="font-mono text-sm font-semibold">{sub.groupName}</code>
            <span className={`text-[10px] uppercase tracking-wide px-2 py-0.5 rounded ${pillColor(sub.enabled)}`}>
              {sub.enabled ? "Active" : "Paused"}
            </span>
            <span className="text-xs text-gray-400">→ {sub.recipientEmail}</span>
          </div>
          <p className="text-xs text-gray-500 mt-1">
            Sends at <span className="font-mono">{sub.sendTimeIst}</span> IST ·{" "}
            {sub.symbols.length === 0
              ? <em>all portfolio holdings</em>
              : `${sub.symbols.length} symbols: ${sub.symbols.slice(0, 5).join(", ")}${sub.symbols.length > 5 ? "…" : ""}`}
            {sub.lastSentDateIst && (
              <> · Last sent <span className="font-mono">{sub.lastSentDateIst}</span></>
            )}
          </p>
        </div>
        <div className="flex gap-1 flex-shrink-0">
          <button
            onClick={() => sendNow.mutate()}
            disabled={sendNow.isPending}
            className="px-2 py-1 text-xs border border-indigo-200 dark:border-indigo-800 text-indigo-600 dark:text-indigo-300 rounded hover:bg-indigo-50 dark:hover:bg-indigo-900/20 disabled:opacity-50"
            title="Send a digest right now (still respects daily cap)"
          >
            {sendNow.isPending ? <Loader2 className="w-3 h-3 animate-spin" /> : <Send className="w-3 h-3" />}
          </button>
          <button
            onClick={() => setEditing(v => !v)}
            className="px-2 py-1 text-xs border border-gray-200 dark:border-white/10 rounded hover:bg-gray-50 dark:hover:bg-gray-800"
          >
            {editing ? "Cancel" : "Edit"}
          </button>
          <button
            onClick={() => { if (confirm(`Delete "${sub.groupName}"?`)) remove.mutate(); }}
            disabled={remove.isPending}
            className="px-2 py-1 text-xs border border-rose-200 dark:border-rose-800 text-rose-600 dark:text-rose-300 rounded hover:bg-rose-50 dark:hover:bg-rose-900/20 disabled:opacity-50"
          >
            <Trash2 className="w-3 h-3" />
          </button>
        </div>
      </div>

      {sendNow.isSuccess && (
        <p className="text-xs text-emerald-600 dark:text-emerald-400 flex items-center gap-1">
          <Check className="w-3 h-3" /> Queued: {sendNow.data?.subject}
        </p>
      )}
      {sendNow.isError && (
        <p className="text-xs text-rose-600 dark:text-rose-400">
          Send failed: {(sendNow.error as Error).message}
        </p>
      )}

      {editing && (
        <div className="grid sm:grid-cols-2 gap-2 pt-2 border-t border-gray-100 dark:border-white/5">
          <label className="text-xs flex flex-col gap-1">
            Recipient
            <input
              type="email"
              value={draft.recipientEmail}
              onChange={(e) => setDraft({ ...draft, recipientEmail: e.target.value })}
              className="px-2 py-1.5 text-sm bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-white/10 rounded"
            />
          </label>
          <label className="text-xs flex flex-col gap-1">
            Send time (IST, HH:MM)
            <input
              type="time"
              value={draft.sendTimeIst}
              onChange={(e) => setDraft({ ...draft, sendTimeIst: e.target.value })}
              className="px-2 py-1.5 text-sm bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-white/10 rounded"
            />
          </label>
          <label className="text-xs flex flex-col gap-1 sm:col-span-2">
            Symbols (comma-separated; leave blank to use all portfolio holdings)
            <input
              type="text"
              value={draft.symbols.join(",")}
              placeholder="RELIANCE,TCS,HDFCBANK"
              onChange={(e) => setDraft({
                ...draft,
                symbols: e.target.value.split(",").map(s => s.trim().toUpperCase()).filter(Boolean),
              })}
              className="px-2 py-1.5 text-sm font-mono bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-white/10 rounded"
            />
          </label>
          <label className="text-xs flex items-center gap-2 sm:col-span-2">
            <input
              type="checkbox"
              checked={draft.enabled}
              onChange={(e) => setDraft({ ...draft, enabled: e.target.checked })}
            />
            Enabled (uncheck to pause without deleting)
          </label>
          {upsert.isError && (
            <p className="text-xs text-rose-600 sm:col-span-2">
              {(upsert.error as Error).message}
            </p>
          )}
          <button
            onClick={() => upsert.mutate()}
            disabled={upsert.isPending}
            className="sm:col-span-2 mt-1 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-sm font-medium rounded"
          >
            {upsert.isPending ? "Saving…" : "Save changes"}
          </button>
        </div>
      )}
    </div>
  );
}

function NewSubscriptionForm({ onCreated }: { onCreated: () => void }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({
    groupName:      "",
    recipientEmail: "",
    symbols:        "",
    sendTimeIst:    DEFAULT_TIME,
  });
  const create = useMutation({
    mutationFn: () => api.emailDigestUpsert({
      groupName:      form.groupName.trim() || "default",
      recipientEmail: form.recipientEmail.trim(),
      symbols:        form.symbols.split(",").map(s => s.trim().toUpperCase()).filter(Boolean),
      sendTimeIst:    form.sendTimeIst || DEFAULT_TIME,
      enabled:        true,
    }),
    onSuccess: () => {
      setOpen(false);
      setForm({ groupName: "", recipientEmail: "", symbols: "", sendTimeIst: DEFAULT_TIME });
      onCreated();
      qc.invalidateQueries({ queryKey: ["emailDigestList"] });
    },
  });

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="w-full px-3 py-2.5 text-sm bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg inline-flex items-center justify-center gap-1"
      >
        <Plus className="w-3.5 h-3.5" /> Add subscription
      </button>
    );
  }
  return (
    <div className="rounded-xl border border-indigo-200 dark:border-indigo-800 bg-indigo-50/40 dark:bg-indigo-500/5 p-4 space-y-2">
      <h3 className="text-sm font-medium text-gray-800 dark:text-gray-200">New subscription</h3>
      <div className="grid sm:grid-cols-2 gap-2">
        <label className="text-xs flex flex-col gap-1">
          Group name
          <input
            type="text"
            placeholder="default, advisor, family…"
            value={form.groupName}
            onChange={(e) => setForm({ ...form, groupName: e.target.value })}
            className="px-2 py-1.5 text-sm bg-white dark:bg-gray-900 border border-gray-200 dark:border-white/10 rounded"
          />
        </label>
        <label className="text-xs flex flex-col gap-1">
          Recipient email
          <input
            type="email"
            placeholder="you@example.com"
            value={form.recipientEmail}
            onChange={(e) => setForm({ ...form, recipientEmail: e.target.value })}
            className="px-2 py-1.5 text-sm bg-white dark:bg-gray-900 border border-gray-200 dark:border-white/10 rounded"
          />
        </label>
        <label className="text-xs flex flex-col gap-1">
          Send time (IST)
          <input
            type="time"
            value={form.sendTimeIst}
            onChange={(e) => setForm({ ...form, sendTimeIst: e.target.value })}
            className="px-2 py-1.5 text-sm bg-white dark:bg-gray-900 border border-gray-200 dark:border-white/10 rounded"
          />
        </label>
        <label className="text-xs flex flex-col gap-1">
          Symbols (optional)
          <input
            type="text"
            placeholder="leave blank for all portfolio holdings"
            value={form.symbols}
            onChange={(e) => setForm({ ...form, symbols: e.target.value })}
            className="px-2 py-1.5 text-sm font-mono bg-white dark:bg-gray-900 border border-gray-200 dark:border-white/10 rounded"
          />
        </label>
      </div>
      {create.isError && (
        <p className="text-xs text-rose-600">{(create.error as Error).message}</p>
      )}
      <div className="flex gap-2 pt-1">
        <button
          onClick={() => create.mutate()}
          disabled={!form.recipientEmail || create.isPending}
          className="flex-1 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-sm font-medium rounded"
        >
          {create.isPending ? "Creating…" : "Create"}
        </button>
        <button
          onClick={() => setOpen(false)}
          className="px-3 py-2 text-sm border border-gray-200 dark:border-white/10 rounded"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}


// Small typed hook so the banner stays tidy.
function useEmailConfig() {
  return useQuery({
    queryKey: ["emailDigestConfig"],
    queryFn:  api.emailDigestConfig,
    staleTime: 60_000,
  });
}


export default function EmailDigestSettings() {
  const qc = useQueryClient();
  const config = useEmailConfig();
  const subs = useQuery({
    queryKey: ["emailDigestList"],
    queryFn:  api.emailDigestList,
  });

  const onChanged = () => qc.invalidateQueries({ queryKey: ["emailDigestList"] });

  return (
    <div className="max-w-3xl mx-auto p-4 lg:p-6 space-y-5">
      <header>
        <h1 className="text-2xl font-semibold flex items-center gap-2">
          <Mail className="w-6 h-6 text-indigo-500" />
          Email Digest Settings
        </h1>
        <p className="text-xs text-gray-500 mt-1">
          A daily mail with your portfolio's prices and an at-a-glance sector
          rotation snippet. Each subscription is one (recipient, time, symbol
          list) combo — useful for routing different watchlists to different
          inboxes (you, an advisor, a family member).
        </p>
      </header>

      <ConfigBanner config={config.data} />

      {subs.isLoading && (
        <div className="flex items-center gap-2 text-sm text-gray-400 py-8 justify-center">
          <Loader2 className="w-4 h-4 animate-spin" /> Loading subscriptions…
        </div>
      )}
      {subs.isError && (
        <div className="rounded-xl border border-rose-300 dark:border-rose-700 bg-rose-50 dark:bg-rose-900/20 px-4 py-3 text-sm flex items-start gap-2 text-rose-700 dark:text-rose-200">
          <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
          <div className="flex-1">
            {/* 404 specifically means the route isn't registered — the
                most common cause is "backend container was not rebuilt
                after the feature shipped". A friendlier hint helps. */}
            {(subs.error as Error & { status?: number })?.status === 404
              ? (
                <>
                  <p className="font-medium">Email-digest endpoint not found (404).</p>
                  <p className="text-xs mt-1 opacity-80">
                    Rebuild and restart the backend so the new routes get
                    picked up: <code>docker compose up --build -d backend</code>.
                  </p>
                </>
              ) : (
                <>
                  <p className="font-medium">Couldn't load subscriptions.</p>
                  <p className="text-xs mt-1 opacity-80">{(subs.error as Error).message}</p>
                </>
              )}
            <button
              onClick={() => subs.refetch()}
              className="mt-2 text-xs underline opacity-90 hover:opacity-100"
            >
              Retry
            </button>
          </div>
        </div>
      )}

      {subs.data?.subscriptions?.length === 0 && (
        <div className="rounded-xl border border-dashed border-gray-200 dark:border-white/10 p-6 text-center text-sm text-gray-500">
          No subscriptions yet. Add one below to start receiving the daily digest.
        </div>
      )}

      {subs.data?.subscriptions?.map(s => (
        <SubscriptionCard key={s.id} sub={s} onChanged={onChanged} />
      ))}

      <NewSubscriptionForm onCreated={onChanged} />
    </div>
  );
}
