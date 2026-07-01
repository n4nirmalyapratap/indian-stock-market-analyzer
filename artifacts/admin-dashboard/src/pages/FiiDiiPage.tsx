import { useState, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchAdmin, getAdminToken } from "@/lib/api";
import {
  Upload, Download, Plus, RefreshCw, CheckCircle2,
  AlertTriangle, TrendingUp, TrendingDown,
} from "lucide-react";

type SegmentStatus = {
  segment: string;
  rows: number;
  firstDate: string | null;
  lastDate: string | null;
  lastUpdatedMs: number | null;
};

type StatusResp = {
  segments: SegmentStatus[];
  missing: string[];
};

type UpsertResp = { written: number; segment: string };
type UploadResp = { written: number; skipped: number; errors: string[] };

const SEGMENTS = [
  { key: "equity",        label: "Equity",       type: "cash" },
  { key: "index_future",  label: "Index Future",  type: "fo"   },
  { key: "index_option",  label: "Index Option",  type: "fo"   },
  { key: "stock_future",  label: "Stock Future",  type: "fo"   },
  { key: "stock_option",  label: "Stock Option",  type: "fo"   },
] as const;

type SegKey = (typeof SEGMENTS)[number]["key"];

function segType(seg: SegKey) {
  return SEGMENTS.find(s => s.key === seg)?.type ?? "cash";
}

function fmtDate(ms: number | null) {
  if (!ms) return "—";
  return new Date(ms).toLocaleString("en-IN", { timeZone: "Asia/Kolkata" });
}

function StatusCard({ seg }: { seg: SegmentStatus }) {
  const label = SEGMENTS.find(s => s.key === seg.segment)?.label ?? seg.segment;
  const fresh = seg.lastDate && new Date(seg.lastDate) >= new Date(Date.now() - 2 * 86_400_000);
  return (
    <div className="bg-white rounded-xl border border-gray-100 p-4 flex flex-col gap-1.5">
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold text-gray-700">{label}</span>
        <span className={`text-xs px-1.5 py-0.5 rounded-full font-medium ${fresh ? "bg-green-50 text-green-700" : "bg-amber-50 text-amber-700"}`}>
          {fresh ? "Fresh" : "Stale"}
        </span>
      </div>
      <div className="text-xs text-gray-400 space-y-0.5">
        <div><span className="text-gray-500 font-medium">{seg.rows.toLocaleString()}</span> rows</div>
        <div>From <span className="text-gray-600">{seg.firstDate ?? "—"}</span> to <span className="text-gray-600">{seg.lastDate ?? "—"}</span></div>
        <div>Updated {fmtDate(seg.lastUpdatedMs)}</div>
      </div>
    </div>
  );
}

function ManualEntryTab({ onSuccess }: { onSuccess: () => void }) {
  const [segment, setSegment] = useState<SegKey>("equity");
  const [date, setDate]       = useState(new Date().toISOString().slice(0, 10));
  const [fields, setFields]   = useState<Record<string, string>>({});
  const [result, setResult]   = useState<string | null>(null);

  const isCash = segType(segment) === "cash";
  const cashFields  = ["fii_buy", "fii_sell", "dii_buy", "dii_sell"] as const;
  const foFields    = ["fii_long", "fii_short", "dii_long", "dii_short", "client_long", "client_short", "pro_long", "pro_short"] as const;
  const activeFields = isCash ? cashFields : foFields;

  const mutation = useMutation({
    mutationFn: async () => {
      const row: Record<string, number | string | null> = { date };
      for (const f of activeFields) {
        const v = fields[f];
        row[f] = v !== "" && v !== undefined ? parseFloat(v) : null;
      }
      if (isCash) {
        const fb = Number(fields.fii_buy ?? 0), fs = Number(fields.fii_sell ?? 0);
        const db = Number(fields.dii_buy ?? 0), ds = Number(fields.dii_sell ?? 0);
        row.fii_net = fb - fs;
        row.dii_net = db - ds;
      } else {
        const fl = Number(fields.fii_long ?? 0), fs = Number(fields.fii_short ?? 0);
        const dl = Number(fields.dii_long ?? 0), ds = Number(fields.dii_short ?? 0);
        row.fii_net = fl - fs;
        row.dii_net = dl - ds;
      }
      return fetchAdmin<UpsertResp>("/admin/fii-dii/upsert", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ segment, rows: [row] }),
      });
    },
    onSuccess: (data) => {
      setResult(`✓ ${data.written} row written for ${segment} on ${date}`);
      onSuccess();
    },
    onError: (e: any) => setResult(`✗ ${e.message}`),
  });

  function setF(key: string, val: string) {
    setFields(prev => ({ ...prev, [key]: val }));
  }

  const labelMap: Record<string, string> = {
    fii_buy: "FII Buy (₹Cr)", fii_sell: "FII Sell (₹Cr)",
    dii_buy: "DII Buy (₹Cr)", dii_sell: "DII Sell (₹Cr)",
    fii_long: "FII Long", fii_short: "FII Short",
    dii_long: "DII Long", dii_short: "DII Short",
    client_long: "Client Long", client_short: "Client Short",
    pro_long: "Pro Long", pro_short: "Pro Short",
  };

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="text-xs font-medium text-gray-600 mb-1.5 block">Segment</label>
          <select
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none"
            value={segment}
            onChange={e => { setSegment(e.target.value as SegKey); setFields({}); setResult(null); }}
          >
            {SEGMENTS.map(s => <option key={s.key} value={s.key}>{s.label}</option>)}
          </select>
        </div>
        <div>
          <label className="text-xs font-medium text-gray-600 mb-1.5 block">Date</label>
          <input
            type="date"
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none"
            value={date}
            onChange={e => setDate(e.target.value)}
          />
        </div>
      </div>

      <div>
        <p className="text-xs font-medium text-gray-500 mb-3">
          {isCash ? "Cash Segment — FII/DII buy & sell (₹ Crore). Net = Buy − Sell (calculated automatically)." : "F&O Segment — Long & Short contracts. Net = Long − Short (calculated automatically)."}
        </p>
        <div className="grid grid-cols-2 gap-3">
          {activeFields.map(f => (
            <div key={f}>
              <label className="text-xs font-medium text-gray-600 mb-1 block">{labelMap[f]}</label>
              <input
                type="number"
                step="0.01"
                placeholder="0.00"
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none"
                value={fields[f] ?? ""}
                onChange={e => setF(f, e.target.value)}
              />
            </div>
          ))}
        </div>
      </div>

      {isCash && fields.fii_buy && fields.fii_sell && (
        <div className="flex gap-4 text-xs text-gray-500 bg-gray-50 rounded-lg px-4 py-2">
          <span>FII Net = <strong className={(Number(fields.fii_buy) - Number(fields.fii_sell)) >= 0 ? "text-green-600" : "text-red-500"}>
            ₹{((Number(fields.fii_buy) - Number(fields.fii_sell))).toFixed(2)} Cr
          </strong></span>
          {fields.dii_buy && fields.dii_sell && (
            <span>DII Net = <strong className={(Number(fields.dii_buy) - Number(fields.dii_sell)) >= 0 ? "text-green-600" : "text-red-500"}>
              ₹{((Number(fields.dii_buy) - Number(fields.dii_sell))).toFixed(2)} Cr
            </strong></span>
          )}
        </div>
      )}

      <button
        onClick={() => mutation.mutate()}
        disabled={mutation.isPending || !date}
        className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded-lg transition"
      >
        <Plus className="w-4 h-4" />
        {mutation.isPending ? "Saving…" : "Save Row"}
      </button>

      {result && (
        <div className={`flex items-center gap-2 text-sm px-3 py-2 rounded-lg ${result.startsWith("✓") ? "bg-green-50 text-green-700" : "bg-red-50 text-red-600"}`}>
          {result.startsWith("✓") ? <CheckCircle2 className="w-4 h-4 flex-shrink-0" /> : <AlertTriangle className="w-4 h-4 flex-shrink-0" />}
          {result}
        </div>
      )}
    </div>
  );
}

function CsvUploadTab({ onSuccess }: { onSuccess: () => void }) {
  const [file, setFile]       = useState<File | null>(null);
  const [result, setResult]   = useState<UploadResp | null>(null);
  const [errMsg, setErrMsg]   = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const TEMPLATE_HEADER = "segment,date,fii_buy,fii_sell,fii_net,dii_buy,dii_sell,dii_net,fii_long,fii_short,dii_long,dii_short,client_long,client_short,pro_long,pro_short";
  const TEMPLATE_ROWS = [
    "equity,2024-01-15,5000.50,3000.25,2000.25,2000.00,1500.00,500.00,,,,,,,,",
    "equity,2024-01-16,4800.00,3200.00,1600.00,2100.00,1400.00,700.00,,,,,,,,",
    "index_future,2024-01-15,,,,,,,100000,80000,50000,40000,60000,55000,20000,18000",
  ].join("\n");

  function downloadTemplate() {
    const csv = TEMPLATE_HEADER + "\n" + TEMPLATE_ROWS;
    const blob = new Blob([csv], { type: "text/csv" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "fii_dii_template.csv";
    a.click();
  }

  async function upload() {
    if (!file) return;
    setUploading(true);
    setResult(null);
    setErrMsg(null);
    try {
      const token = getAdminToken();
      const fd = new FormData();
      fd.append("file", file);
      const resp = await fetch("/admin/fii-dii/upload-csv", {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: fd,
      });
      if (!resp.ok) {
        const t = await resp.text();
        throw new Error(t || `HTTP ${resp.status}`);
      }
      const data: UploadResp = await resp.json();
      setResult(data);
      onSuccess();
    } catch (e: any) {
      setErrMsg(e.message || "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="space-y-5">
      <div className="bg-gray-50 rounded-xl border border-gray-200 p-4 space-y-2">
        <p className="text-sm font-semibold text-gray-700">CSV Format</p>
        <p className="text-xs text-gray-500">
          One row per segment+date. Leave columns empty if not applicable (e.g. equity rows don't need F&O columns).
          <br/><strong>Equity:</strong> fii_buy, fii_sell, dii_buy, dii_sell — fii_net/dii_net auto-calculated if blank.
          <br/><strong>F&O:</strong> fii_long, fii_short, dii_long, dii_short, client_long, client_short, pro_long, pro_short.
        </p>
        <div className="bg-white border border-gray-200 rounded-lg px-3 py-2 font-mono text-xs text-gray-500 overflow-x-auto whitespace-nowrap">
          {TEMPLATE_HEADER}
        </div>
        <button
          onClick={downloadTemplate}
          className="flex items-center gap-1.5 text-xs text-indigo-600 hover:text-indigo-800 font-medium transition"
        >
          <Download className="w-3.5 h-3.5" /> Download Template CSV
        </button>
      </div>

      <div>
        <label className="text-xs font-medium text-gray-600 mb-2 block">Select CSV file</label>
        <div
          onClick={() => fileRef.current?.click()}
          className="border-2 border-dashed border-gray-200 rounded-xl p-6 text-center cursor-pointer hover:border-indigo-300 hover:bg-indigo-50/30 transition"
        >
          <Upload className="w-6 h-6 text-gray-300 mx-auto mb-2" />
          {file
            ? <p className="text-sm font-medium text-indigo-600">{file.name} ({(file.size / 1024).toFixed(1)} KB)</p>
            : <p className="text-sm text-gray-400">Click to select a .csv file</p>
          }
          <input
            ref={fileRef}
            type="file"
            accept=".csv,text/csv"
            className="hidden"
            onChange={e => { setFile(e.target.files?.[0] ?? null); setResult(null); setErrMsg(null); }}
          />
        </div>
      </div>

      <button
        onClick={upload}
        disabled={!file || uploading}
        className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded-lg transition"
      >
        <Upload className="w-4 h-4" />
        {uploading ? "Uploading…" : "Upload & Ingest"}
      </button>

      {result && (
        <div className="bg-green-50 border border-green-200 rounded-xl p-4 space-y-2">
          <div className="flex items-center gap-2 text-green-700 font-semibold text-sm">
            <CheckCircle2 className="w-4 h-4" />
            Upload complete
          </div>
          <div className="text-sm text-green-700">
            <span className="font-bold">{result.written}</span> rows written &nbsp;·&nbsp;
            <span className="font-bold">{result.skipped}</span> skipped (already up-to-date or invalid)
          </div>
          {result.errors.length > 0 && (
            <div className="text-xs text-amber-700 bg-amber-50 rounded-lg px-3 py-2 space-y-1">
              <p className="font-semibold">Parse warnings ({result.errors.length}):</p>
              {result.errors.slice(0, 10).map((e, i) => <p key={i}>{e}</p>)}
              {result.errors.length > 10 && <p>…and {result.errors.length - 10} more</p>}
            </div>
          )}
        </div>
      )}

      {errMsg && (
        <div className="flex items-center gap-2 text-sm text-red-600 bg-red-50 px-3 py-2 rounded-lg">
          <AlertTriangle className="w-4 h-4 flex-shrink-0" />
          {errMsg}
        </div>
      )}
    </div>
  );
}

export default function FiiDiiPage() {
  const qc = useQueryClient();
  const [tab, setTab] = useState<"manual" | "csv">("manual");

  const { data: status, isLoading, refetch } = useQuery<StatusResp>({
    queryKey: ["admin", "fii-dii", "status"],
    queryFn: () => fetchAdmin<StatusResp>("/admin/fii-dii/status"),
    refetchInterval: 30_000,
  });

  function invalidate() {
    qc.invalidateQueries({ queryKey: ["admin", "fii-dii", "status"] });
  }

  const TABS = [
    { key: "manual", label: "Manual Entry", icon: Plus },
    { key: "csv",    label: "CSV Upload",   icon: Upload },
  ] as const;

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-900 flex items-center gap-2">
            <TrendingUp className="w-5 h-5 text-indigo-600" />
            FII / DII Data Manager
          </h1>
          <p className="text-sm text-gray-500 mt-0.5">Manually insert or backfill missing FII/DII flow data across all 5 segments.</p>
        </div>
        <button
          onClick={() => refetch()}
          className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-indigo-600 transition"
        >
          <RefreshCw className="w-4 h-4" /> Refresh
        </button>
      </div>

      <div>
        <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-3">Current Coverage</p>
        {isLoading ? (
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            {[...Array(5)].map((_, i) => (
              <div key={i} className="bg-gray-100 rounded-xl h-24 animate-pulse" />
            ))}
          </div>
        ) : (
          <>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
              {status?.segments.map(s => <StatusCard key={s.segment} seg={s} />)}
            </div>
            {(status?.missing ?? []).length > 0 && (
              <div className="mt-3 flex items-center gap-2 text-sm text-amber-700 bg-amber-50 px-3 py-2 rounded-lg">
                <AlertTriangle className="w-4 h-4 flex-shrink-0" />
                Missing segments (no data yet): <strong>{status!.missing.join(", ")}</strong>
              </div>
            )}
          </>
        )}
      </div>

      <div className="bg-white rounded-xl border border-gray-100 overflow-hidden">
        <div className="flex border-b border-gray-100">
          {TABS.map(t => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`flex items-center gap-2 px-5 py-3 text-sm font-medium transition border-b-2
                ${tab === t.key
                  ? "border-indigo-500 text-indigo-700 bg-indigo-50/50"
                  : "border-transparent text-gray-500 hover:text-gray-700"
                }`}
            >
              <t.icon className="w-4 h-4" />
              {t.label}
            </button>
          ))}
        </div>
        <div className="p-5">
          {tab === "manual"
            ? <ManualEntryTab onSuccess={invalidate} />
            : <CsvUploadTab onSuccess={invalidate} />
          }
        </div>
      </div>

      <div className="bg-blue-50 border border-blue-100 rounded-xl px-4 py-3 text-xs text-blue-700 space-y-1">
        <p className="font-semibold">When to use this tool</p>
        <p>• NSE archives were blocked for a day — backfill by uploading the CSV you downloaded from <strong>nsearchives.nseindia.com</strong></p>
        <p>• A specific date is missing — use Manual Entry with the segment and correct values</p>
        <p>• All rows use <strong>ON CONFLICT UPDATE</strong> — safe to re-upload; duplicates overwrite with the latest values</p>
      </div>
    </div>
  );
}
