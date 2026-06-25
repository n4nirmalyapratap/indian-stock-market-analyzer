import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchAdmin } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/hooks/use-toast";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Rocket, Plus, Trash2, CheckCircle, RefreshCw, Database } from "lucide-react";

interface IpoRecord {
  symbol:      string;
  companyName: string;
  series:      string;
  isSme:       boolean;
  isReit:      boolean;
  openDate:    string | null;
  closeDate:   string | null;
  listingDate: string | null;
  priceLow:    number | null;
  priceHigh:   number | null;
  lotSize:     number | null;
  issueSizeCr: number | null;
  source:      string;
  isListed:    boolean;
  updatedAt:   string | null;
}

interface ListResponse {
  ipos:   IpoRecord[];
  counts: { active: number; listed: number; total: number };
}

const fmtDate = (iso: string | null) => {
  if (!iso) return "—";
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
};

const fmtBand = (lo: number | null, hi: number | null) => {
  if (!lo && !hi) return "—";
  if (!lo) return `₹${hi}`;
  if (!hi || lo === hi) return `₹${lo}`;
  return `₹${lo}–${hi}`;
};

function AddIpoDialog({ onAdded }: { onAdded: () => void }) {
  const [open, setOpen] = useState(false);
  const { toast } = useToast();
  const [form, setForm] = useState({
    companyName: "", symbol: "", series: "EQ",
    openDate: "", closeDate: "", listingDate: "",
    priceLow: "", priceHigh: "", lotSize: "", issueSizeCr: "",
  });

  const mutation = useMutation({
    mutationFn: () =>
      fetchAdmin<{ ok: boolean; record: IpoRecord }>("/admin/ipos", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          companyName: form.companyName.trim(),
          symbol:      form.symbol.trim().toUpperCase() || undefined,
          series:      form.series,
          isSme:       form.series === "SME",
          isReit:      form.series === "REIT",
          openDate:    form.openDate   || null,
          closeDate:   form.closeDate  || null,
          listingDate: form.listingDate || null,
          priceLow:    form.priceLow   ? parseFloat(form.priceLow)   : null,
          priceHigh:   form.priceHigh  ? parseFloat(form.priceHigh)  : null,
          lotSize:     form.lotSize    ? parseInt(form.lotSize)       : null,
          issueSizeCr: form.issueSizeCr ? parseFloat(form.issueSizeCr) : null,
        }),
      }),
    onSuccess: (data) => {
      toast({ title: "IPO saved", description: `${data.record.companyName} (${data.record.symbol})` });
      setOpen(false);
      setForm({ companyName: "", symbol: "", series: "EQ", openDate: "", closeDate: "", listingDate: "", priceLow: "", priceHigh: "", lotSize: "", issueSizeCr: "" });
      onAdded();
    },
    onError: (e: any) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const f = (k: string) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm(prev => ({ ...prev, [k]: e.target.value }));

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm" className="gap-1.5">
          <Plus className="w-4 h-4" /> Add IPO
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Add / Update IPO</DialogTitle>
        </DialogHeader>
        <div className="space-y-3 mt-2">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>Company Name *</Label>
              <Input value={form.companyName} onChange={f("companyName")} placeholder="Acme Industries Ltd" />
            </div>
            <div>
              <Label>Symbol (auto-generated if blank)</Label>
              <Input value={form.symbol} onChange={f("symbol")} placeholder="ACMEIN" />
            </div>
          </div>

          <div>
            <Label>Type</Label>
            <Select value={form.series} onValueChange={(v) => setForm(p => ({ ...p, series: v }))}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="EQ">Mainboard (EQ)</SelectItem>
                <SelectItem value="SME">SME</SelectItem>
                <SelectItem value="REIT">REIT / InvIT</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div>
              <Label>Open Date</Label>
              <Input type="date" value={form.openDate} onChange={f("openDate")} />
            </div>
            <div>
              <Label>Close Date</Label>
              <Input type="date" value={form.closeDate} onChange={f("closeDate")} />
            </div>
            <div>
              <Label>Listing Date</Label>
              <Input type="date" value={form.listingDate} onChange={f("listingDate")} />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>Price Low (₹)</Label>
              <Input type="number" value={form.priceLow} onChange={f("priceLow")} placeholder="150" />
            </div>
            <div>
              <Label>Price High (₹)</Label>
              <Input type="number" value={form.priceHigh} onChange={f("priceHigh")} placeholder="160" />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>Lot Size</Label>
              <Input type="number" value={form.lotSize} onChange={f("lotSize")} placeholder="90" />
            </div>
            <div>
              <Label>Issue Size (₹ Cr)</Label>
              <Input type="number" value={form.issueSizeCr} onChange={f("issueSizeCr")} placeholder="500" />
            </div>
          </div>

          <Button
            className="w-full"
            disabled={!form.companyName.trim() || mutation.isPending}
            onClick={() => mutation.mutate()}
          >
            {mutation.isPending ? "Saving…" : "Save IPO"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function IpoRow({ ipo, onAction }: { ipo: IpoRecord; onAction: () => void }) {
  const { toast } = useToast();

  const markListed = useMutation({
    mutationFn: () => fetchAdmin(`/admin/ipos/${ipo.symbol}/mark-listed`, { method: "PATCH" }),
    onSuccess: () => { toast({ title: "Marked as listed", description: ipo.companyName }); onAction(); },
    onError: (e: any) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const del = useMutation({
    mutationFn: () => fetchAdmin(`/admin/ipos/${ipo.symbol}`, { method: "DELETE" }),
    onSuccess: () => { toast({ title: "Deleted", description: ipo.symbol }); onAction(); },
    onError: (e: any) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const seriesColor = ipo.isSme
    ? "bg-amber-100 text-amber-700"
    : ipo.isReit
    ? "bg-cyan-100 text-cyan-700"
    : "bg-indigo-100 text-indigo-700";

  const sourceColor = ipo.source === "manual"
    ? "bg-violet-100 text-violet-700"
    : ipo.source === "gmp"
    ? "bg-orange-100 text-orange-700"
    : "bg-gray-100 text-gray-600";

  return (
    <tr className="border-b border-gray-100 hover:bg-gray-50 text-sm">
      <td className="py-2.5 px-3">
        <p className="font-semibold text-gray-900">{ipo.companyName}</p>
        <p className="text-xs text-gray-400 font-mono">{ipo.symbol}</p>
      </td>
      <td className="py-2.5 px-3">
        <span className={`text-[10px] font-bold uppercase px-1.5 py-0.5 rounded ${seriesColor}`}>
          {ipo.isSme ? "SME" : ipo.isReit ? "REIT" : "Mainboard"}
        </span>
      </td>
      <td className="py-2.5 px-3 text-gray-600 tabular-nums">
        {fmtDate(ipo.openDate)} – {fmtDate(ipo.closeDate)}
      </td>
      <td className="py-2.5 px-3 text-gray-600 tabular-nums">{fmtBand(ipo.priceLow, ipo.priceHigh)}</td>
      <td className="py-2.5 px-3">
        <span className={`text-[10px] font-bold uppercase px-1.5 py-0.5 rounded ${sourceColor}`}>
          {ipo.source}
        </span>
      </td>
      <td className="py-2.5 px-3">
        {ipo.isListed
          ? <span className="text-xs text-gray-400">Listed</span>
          : <span className="text-xs font-semibold text-emerald-600">Active</span>
        }
      </td>
      <td className="py-2.5 px-3">
        <div className="flex items-center gap-1.5">
          {!ipo.isListed && (
            <button
              onClick={() => markListed.mutate()}
              disabled={markListed.isPending}
              className="p-1 rounded text-gray-400 hover:text-emerald-600 hover:bg-emerald-50 transition"
              title="Mark as listed"
            >
              <CheckCircle className="w-3.5 h-3.5" />
            </button>
          )}
          <button
            onClick={() => {
              if (confirm(`Delete ${ipo.companyName}?`)) del.mutate();
            }}
            disabled={del.isPending}
            className="p-1 rounded text-gray-400 hover:text-rose-600 hover:bg-rose-50 transition"
            title="Delete"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </td>
    </tr>
  );
}

export default function IpoManagerPage() {
  const qc = useQueryClient();
  const [filter, setFilter] = useState<"all" | "active" | "listed">("all");

  const { data, isLoading, refetch } = useQuery<ListResponse>({
    queryKey: ["admin-ipos"],
    queryFn: () => fetchAdmin("/admin/ipos"),
    refetchOnWindowFocus: false,
  });

  const reload = () => qc.invalidateQueries({ queryKey: ["admin-ipos"] });

  const all    = data?.ipos ?? [];
  const counts = data?.counts ?? { active: 0, listed: 0, total: 0 };
  const shown  =
    filter === "active" ? all.filter(r => !r.isListed) :
    filter === "listed" ? all.filter(r =>  r.isListed) :
    all;

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <Rocket className="w-5 h-5 text-indigo-600" />
          <h1 className="text-xl font-bold text-gray-900">IPO Manager</h1>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => refetch()}
            className="p-2 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition"
            title="Refresh"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
          <AddIpoDialog onAdded={reload} />
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3">
        {[
          { label: "Active", value: counts.active, color: "text-emerald-600" },
          { label: "Listed", value: counts.listed, color: "text-gray-500"    },
          { label: "Total",  value: counts.total,  color: "text-indigo-600"  },
        ].map(s => (
          <div key={s.label} className="bg-white rounded-xl border border-gray-100 p-4">
            <p className="text-xs text-gray-400 uppercase tracking-wide font-semibold">{s.label}</p>
            <p className={`text-2xl font-bold mt-1 ${s.color}`}>{s.value}</p>
          </div>
        ))}
      </div>

      <div className="flex items-center gap-1.5">
        <Database className="w-3.5 h-3.5 text-gray-400" />
        <p className="text-xs text-gray-500">
          Persisted in <code className="bg-gray-100 px-1 rounded text-[10px]">market_cache/ipo_store.db</code>.
          IPOs auto-promote to Listed 7 days after their close date.
          GMP is always live from ipowatch.in — not stored here.
        </p>
      </div>

      <div className="bg-white rounded-xl border border-gray-100 overflow-hidden">
        <div className="flex items-center gap-1 p-3 border-b border-gray-100">
          {(["all", "active", "listed"] as const).map(f => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition capitalize ${
                filter === f
                  ? "bg-indigo-50 text-indigo-700"
                  : "text-gray-500 hover:bg-gray-50"
              }`}
            >
              {f} {f === "active" ? `(${counts.active})` : f === "listed" ? `(${counts.listed})` : `(${counts.total})`}
            </button>
          ))}
        </div>

        {isLoading ? (
          <div className="p-8 text-center text-gray-400 text-sm">Loading…</div>
        ) : shown.length === 0 ? (
          <div className="p-8 text-center text-gray-400 text-sm">
            No IPOs yet. Add one manually or wait for the next NSE fetch.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="text-left text-[11px] uppercase tracking-wide text-gray-400 border-b border-gray-100">
                  <th className="py-2 px-3">Company</th>
                  <th className="py-2 px-3">Type</th>
                  <th className="py-2 px-3">Window</th>
                  <th className="py-2 px-3">Price</th>
                  <th className="py-2 px-3">Source</th>
                  <th className="py-2 px-3">Status</th>
                  <th className="py-2 px-3">Actions</th>
                </tr>
              </thead>
              <tbody>
                {shown.map(ipo => (
                  <IpoRow key={ipo.symbol} ipo={ipo} onAction={reload} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
