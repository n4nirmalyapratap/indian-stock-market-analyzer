import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchApi } from "@/lib/api";
import { PageHeader, PillTabs, Card, Loading, EmptyState } from "../_shared";
import { Rocket, Calendar, TrendingUp, Users, Building2, Info, TrendingDown, Flame } from "lucide-react";
import DataFreshness from "@/components/DataFreshness";
import { pickMeta, marketDataQueryOptions } from "@/lib/marketData";

type Tab = "open" | "upcoming" | "listed";

interface Subscription { qib: number | null; nii: number | null; retail: number | null; total: number | null; }

interface Gmp {
  premium:     number | null;   // ₹ over issue price
  estListing:  number | null;   // ₹ estimated listing price
  estGainPct:  number | null;   // %
  lastUpdated: string | null;
  matchedName: string | null;
}

interface IpoIssue {
  symbol:       string;
  companyName:  string;
  series:       string;
  isSme:        boolean;
  isReit:       boolean;
  openDate:     string | null;
  closeDate:    string | null;
  priceLow:     number | null;
  priceHigh:    number | null;
  lotSize:      number | null;
  issueSizeCr:  number | null;
  issueShares:  number | null;
  status:       "open" | "upcoming";
  subscription?: Subscription;
  gmp?:         Gmp | null;
  fromGmpOnly?: boolean;   // true for BSE/SME IPOs not on NSE's feed
}

interface ListedIssue {
  symbol:      string;
  companyName: string;
  series:      string;
  isSme:       boolean;
  isReit:      boolean;
  openDate:    string | null;
  closeDate:   string | null;
  priceLow:    number | null;
  priceHigh:   number | null;
  lotSize:     number | null;
  issueSizeCr: number | null;
  source:      string;
  gmp?:        Gmp | null;
}

interface IpoResponse {
  available: boolean;
  message?:  string;
  open:      IpoIssue[];
  upcoming:  IpoIssue[];
  listed:    ListedIssue[];
  fetchedAt?: string;
  gmpSource?: { url: string | null; fetchedAt: string | null; note?: string | null };
}

const fmtDate = (iso: string | null) => {
  if (!iso) return "—";
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString("en-IN", { day: "2-digit", month: "short" });
};

const fmtMoney = (cr: number | null) => {
  if (cr == null) return "—";
  if (cr >= 1000) return `₹${(cr / 1000).toFixed(2)} K Cr`;
  return `₹${cr.toFixed(2)} Cr`;
};

const fmtBand = (lo: number | null, hi: number | null) => {
  if (lo == null && hi == null) return "—";
  if (lo == null) return `₹${hi}`;          // GMP-only rows: cap price only
  if (hi == null || lo === hi) return `₹${lo}`;
  return `₹${lo} – ₹${hi}`;
};

const dayCount = (from: string | null, to: string | null) => {
  if (!from || !to) return null;
  const a = new Date(from + "T00:00:00").getTime();
  const b = new Date(to   + "T00:00:00").getTime();
  return Math.round((b - a) / 86_400_000) + 1;
};

const daysUntil = (iso: string | null) => {
  if (!iso) return null;
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const target = new Date(iso + "T00:00:00");
  return Math.round((target.getTime() - today.getTime()) / 86_400_000);
};

const GmpBlock = ({ gmp }: { gmp: Gmp }) => {
  // GMP can be 0, positive, or negative (rare but happens for cold IPOs).
  const prem = gmp.premium;
  const pct  = gmp.estGainPct;
  const tone =
    prem == null      ? "neutral"
    : prem > 0        ? "up"
    : prem < 0        ? "down"
    :                   "neutral";
  const cls = tone === "up"
    ? "bg-emerald-50 dark:bg-emerald-500/10 border-emerald-200 dark:border-emerald-500/20"
    : tone === "down"
    ? "bg-rose-50 dark:bg-rose-500/10 border-rose-200 dark:border-rose-500/20"
    : "bg-gray-50 dark:bg-gray-700/40 border-gray-200 dark:border-gray-700";
  const Icon = tone === "up" ? TrendingUp : tone === "down" ? TrendingDown : Flame;
  const colorText = tone === "up"
    ? "text-emerald-700 dark:text-emerald-300"
    : tone === "down"
    ? "text-rose-700 dark:text-rose-300"
    : "text-gray-700 dark:text-gray-200";
  return (
    <div className={`rounded-lg border px-2.5 py-2 flex items-center justify-between gap-2 ${cls}`}>
      <div className="flex items-center gap-2 min-w-0">
        <Icon className={`w-3.5 h-3.5 flex-shrink-0 ${colorText}`} />
        <div className="min-w-0">
          <p className="text-[10px] uppercase tracking-wide font-bold text-gray-500 dark:text-gray-400 leading-tight">
            Grey Market Premium
          </p>
          <p className={`text-sm font-bold tabular-nums leading-tight ${colorText}`}>
            {prem == null ? "—" : `${prem >= 0 ? "+" : ""}₹${prem}`}
            {pct != null && pct !== 0 && (
              <span className="ml-1.5 text-[11px] font-semibold opacity-80">
                ({pct >= 0 ? "+" : ""}{pct.toFixed(2)}%)
              </span>
            )}
          </p>
        </div>
      </div>
      {gmp.estListing != null && (
        <div className="text-right">
          <p className="text-[9px] uppercase tracking-wide text-gray-500 dark:text-gray-400 leading-tight">Est. Listing</p>
          <p className="text-xs font-bold text-gray-900 dark:text-white tabular-nums leading-tight">₹{gmp.estListing}</p>
        </div>
      )}
    </div>
  );
};

const SeriesBadge = ({ issue }: { issue: IpoIssue }) => {
  const label = issue.isSme ? "SME" : issue.isReit ? "REIT" : "Mainboard";
  const cls = issue.isSme
    ? "bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300"
    : issue.isReit
    ? "bg-cyan-100 text-cyan-700 dark:bg-cyan-500/15 dark:text-cyan-300"
    : "bg-indigo-100 text-indigo-700 dark:bg-indigo-500/15 dark:text-indigo-300";
  return (
    <span className={`text-[10px] font-bold uppercase tracking-wide px-2 py-0.5 rounded ${cls}`}>{label}</span>
  );
};

const SubBar = ({ label, value }: { label: string; value: number | null }) => {
  // Log scale so a 1× and a 50× IPO both read meaningfully on the same bar.
  // log10(1+x) maps 0→0, 1×→0.30, 5×→0.78, 10×→1.04, 50×→1.71, 100×→2.00.
  // We anchor 100% fill at 100×, which is roughly the upper band of "hot" IPOs.
  const pct = value == null ? 0 : Math.min(100, (Math.log10(1 + value) / 2) * 100);
  const color =
    value == null      ? "bg-gray-300 dark:bg-gray-600"
    : value >= 10      ? "bg-violet-500"
    : value >= 1       ? "bg-emerald-500"
    : value >= 0.5     ? "bg-amber-500"
    :                    "bg-rose-400";
  return (
    <div>
      <div className="flex items-center justify-between text-[11px] mb-1">
        <span className="text-gray-500 dark:text-gray-400 font-medium">{label}</span>
        <span className="tabular-nums font-bold text-gray-900 dark:text-white">
          {value == null ? "—" : `${value.toFixed(2)}×`}
        </span>
      </div>
      <div className="h-1.5 rounded-full bg-gray-100 dark:bg-gray-700 overflow-hidden">
        <div className={`h-full ${color} transition-all`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
};

const OpenIssueCard = ({ issue }: { issue: IpoIssue }) => {
  const totalDays = dayCount(issue.openDate, issue.closeDate);
  const closesIn  = daysUntil(issue.closeDate);
  const sub = issue.subscription;
  return (
    <Card className="p-4 flex flex-col gap-3">
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 mb-1">
            <SeriesBadge issue={issue}/>
            {closesIn != null && closesIn >= 0 && (
              <span className={`text-[10px] font-semibold px-2 py-0.5 rounded ${
                closesIn === 0 ? "bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300"
                : closesIn <= 1 ? "bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300"
                : "bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300"
              }`}>
                {closesIn === 0 ? "Closes today" : closesIn === 1 ? "Closes tomorrow" : `${closesIn}d left`}
              </span>
            )}
          </div>
          <h3 className="text-sm font-bold text-gray-900 dark:text-white truncate" title={issue.companyName}>
            {issue.companyName}
          </h3>
          <p className="text-[11px] text-gray-500 dark:text-gray-400 truncate">{issue.symbol}</p>
        </div>
      </div>

      {/* Quick facts */}
      <div className="grid grid-cols-3 gap-2 text-center">
        <div>
          <p className="text-[10px] uppercase tracking-wide text-gray-500 dark:text-gray-400 font-semibold">Price</p>
          <p className="text-xs font-bold text-gray-900 dark:text-white tabular-nums">{fmtBand(issue.priceLow, issue.priceHigh)}</p>
        </div>
        <div>
          <p className="text-[10px] uppercase tracking-wide text-gray-500 dark:text-gray-400 font-semibold">Issue Size</p>
          <p className="text-xs font-bold text-gray-900 dark:text-white tabular-nums">{fmtMoney(issue.issueSizeCr)}</p>
        </div>
        <div>
          <p className="text-[10px] uppercase tracking-wide text-gray-500 dark:text-gray-400 font-semibold">Window</p>
          <p className="text-xs font-bold text-gray-900 dark:text-white tabular-nums">
            {fmtDate(issue.openDate)} – {fmtDate(issue.closeDate)}
          </p>
          {totalDays && <p className="text-[10px] text-gray-400">{totalDays} days</p>}
        </div>
      </div>

      {/* GMP */}
      {issue.gmp && <GmpBlock gmp={issue.gmp} />}

      {/* Subscription — only for NSE-tracked issues; GMP-only SME rows have no NSE sub data */}
      {sub && !issue.fromGmpOnly && (
        <div className="space-y-2 pt-2 border-t border-gray-100 dark:border-gray-700">
          <div className="flex items-center justify-between mb-1">
            <p className="text-[11px] font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">Subscription</p>
            {sub.total != null && (
              <span className={`text-xs font-bold tabular-nums ${
                sub.total >= 1 ? "text-emerald-600 dark:text-emerald-400" : "text-gray-700 dark:text-gray-200"
              }`}>
                {sub.total.toFixed(2)}× total
              </span>
            )}
          </div>
          <SubBar label="Retail" value={sub.retail}/>
          <SubBar label="NII"    value={sub.nii}/>
          <SubBar label="QIB"    value={sub.qib}/>
        </div>
      )}
      {issue.fromGmpOnly && (
        <p className="text-[10px] text-gray-400 dark:text-gray-500 pt-1">
          BSE/NSE SME — subscription data not available via public feed
        </p>
      )}
    </Card>
  );
};

const UpcomingIssueCard = ({ issue }: { issue: IpoIssue }) => {
  const opensIn = daysUntil(issue.openDate);
  return (
    <Card className="p-4 flex flex-col gap-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 mb-1">
            <SeriesBadge issue={issue}/>
            {opensIn != null && opensIn > 0 && (
              <span className="text-[10px] font-semibold px-2 py-0.5 rounded bg-violet-100 text-violet-700 dark:bg-violet-500/15 dark:text-violet-300">
                Opens in {opensIn}d
              </span>
            )}
          </div>
          <h3 className="text-sm font-bold text-gray-900 dark:text-white truncate" title={issue.companyName}>
            {issue.companyName}
          </h3>
          <p className="text-[11px] text-gray-500 dark:text-gray-400 truncate">{issue.symbol}</p>
        </div>
      </div>
      <div className="grid grid-cols-3 gap-2 text-center">
        <div>
          <p className="text-[10px] uppercase tracking-wide text-gray-500 dark:text-gray-400 font-semibold">Price</p>
          <p className="text-xs font-bold text-gray-900 dark:text-white tabular-nums">{fmtBand(issue.priceLow, issue.priceHigh)}</p>
        </div>
        <div>
          <p className="text-[10px] uppercase tracking-wide text-gray-500 dark:text-gray-400 font-semibold">Issue Size</p>
          <p className="text-xs font-bold text-gray-900 dark:text-white tabular-nums">{fmtMoney(issue.issueSizeCr)}</p>
        </div>
        <div>
          <p className="text-[10px] uppercase tracking-wide text-gray-500 dark:text-gray-400 font-semibold">Window</p>
          <p className="text-xs font-bold text-gray-900 dark:text-white tabular-nums">
            {fmtDate(issue.openDate)} – {fmtDate(issue.closeDate)}
          </p>
        </div>
      </div>
      {issue.gmp && <GmpBlock gmp={issue.gmp} />}
    </Card>
  );
};

const ListedIssueCard = ({ issue }: { issue: ListedIssue }) => (
  <Card className="p-4 flex flex-col gap-3">
    <div className="flex items-start justify-between gap-2">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 mb-1">
          <SeriesBadge issue={issue as any} />
          <span className="text-[10px] font-semibold px-2 py-0.5 rounded bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400">
            Listed
          </span>
        </div>
        <h3 className="text-sm font-bold text-gray-900 dark:text-white truncate" title={issue.companyName}>
          {issue.companyName}
        </h3>
        <p className="text-[11px] text-gray-500 dark:text-gray-400 truncate">{issue.symbol}</p>
      </div>
    </div>
    <div className="grid grid-cols-3 gap-2 text-center">
      <div>
        <p className="text-[10px] uppercase tracking-wide text-gray-500 dark:text-gray-400 font-semibold">Price Band</p>
        <p className="text-xs font-bold text-gray-900 dark:text-white tabular-nums">{fmtBand(issue.priceLow, issue.priceHigh)}</p>
      </div>
      <div>
        <p className="text-[10px] uppercase tracking-wide text-gray-500 dark:text-gray-400 font-semibold">Issue Size</p>
        <p className="text-xs font-bold text-gray-900 dark:text-white tabular-nums">{fmtMoney(issue.issueSizeCr)}</p>
      </div>
      <div>
        <p className="text-[10px] uppercase tracking-wide text-gray-500 dark:text-gray-400 font-semibold">Closed</p>
        <p className="text-xs font-bold text-gray-900 dark:text-white tabular-nums">{fmtDate(issue.closeDate)}</p>
      </div>
    </div>
    {issue.gmp && <GmpBlock gmp={issue.gmp} />}
  </Card>
);

export default function Ipo() {
  const [tab, setTab] = useState<Tab>("open");

  const { data, isLoading } = useQuery<IpoResponse>(
    marketDataQueryOptions<IpoResponse>(
      ["insights/ipos"],
      () => fetchApi(`/insights/ipos`),
    ),
  );
  const meta = pickMeta(data);

  const counts = useMemo(() => ({
    open:     data?.open?.length     ?? 0,
    upcoming: data?.upcoming?.length ?? 0,
    listed:   data?.listed?.length   ?? 0,
  }), [data]);

  // Derived stats for the small "Top Picks"-style strip above the cards.
  const stats = useMemo(() => {
    const openItems = data?.open ?? [];
    const totalSizeCr = openItems.reduce((s, x) => s + (x.issueSizeCr ?? 0), 0);
    const avgSub = openItems.length
      ? openItems.reduce((s, x) => s + (x.subscription?.total ?? 0), 0) / openItems.length
      : 0;
    const sme  = openItems.filter(x => x.isSme).length;
    const main = openItems.length - sme;
    return { totalSizeCr, avgSub, sme, main, openCount: openItems.length };
  }, [data]);

  const tabOptions: { value: Tab; label: string }[] = [
    { value: "open",     label: `Open Now${counts.open ? ` · ${counts.open}` : ""}` },
    { value: "upcoming", label: `Upcoming${counts.upcoming ? ` · ${counts.upcoming}` : ""}` },
    { value: "listed",   label: "Recently Listed" },
  ];

  const items    = tab === "open" ? data?.open ?? [] : tab === "upcoming" ? data?.upcoming ?? [] : [];
  const listedItems = data?.listed ?? [];

  // GMP is merged from several sources now — attribute whichever one served.
  // Derive href AND host from ONE validated URL so they never disagree: an
  // empty/malformed server URL must fall back to ipowatch for both, not show
  // "ipowatch.in" while linking to "" (which would reload the current page).
  const gmpSource = useMemo(() => {
    const FALLBACK = "https://ipowatch.in/";
    try {
      const u = new URL(data?.gmpSource?.url ?? FALLBACK);
      if (u.protocol !== "http:" && u.protocol !== "https:") throw new Error("non-http");
      return { href: u.href, host: u.hostname.replace(/^www\./, "") };
    } catch {
      return { href: FALLBACK, host: "ipowatch.in" };
    }
  }, [data?.gmpSource?.url]);

  return (
    <div>
      <PageHeader title="IPO Center"
        info="Live mainboard, SME and REIT issues from NSE — price band, lot size, issue size, and live subscription numbers updated every few minutes."/>

      <div className="mb-3">
        <DataFreshness meta={meta} refreshKeys={[["insights/ipos"]]} />
      </div>

      {/* Stats strip — only for OPEN tab where we have rich data */}
      {tab === "open" && stats.openCount > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
          <Card className="p-3">
            <div className="flex items-center gap-2 mb-1">
              <Rocket className="w-3.5 h-3.5 text-pink-500" />
              <p className="text-[10px] uppercase tracking-wide font-bold text-gray-500 dark:text-gray-400">Open Issues</p>
            </div>
            <p className="text-xl font-bold text-gray-900 dark:text-white tabular-nums">{stats.openCount}</p>
            <p className="text-[10px] text-gray-500 dark:text-gray-400">{stats.main} mainboard · {stats.sme} SME</p>
          </Card>
          <Card className="p-3">
            <div className="flex items-center gap-2 mb-1">
              <Building2 className="w-3.5 h-3.5 text-indigo-500" />
              <p className="text-[10px] uppercase tracking-wide font-bold text-gray-500 dark:text-gray-400">Total Size</p>
            </div>
            <p className="text-xl font-bold text-gray-900 dark:text-white tabular-nums">{fmtMoney(stats.totalSizeCr)}</p>
            <p className="text-[10px] text-gray-500 dark:text-gray-400">across all open issues</p>
          </Card>
          <Card className="p-3">
            <div className="flex items-center gap-2 mb-1">
              <Users className="w-3.5 h-3.5 text-emerald-500" />
              <p className="text-[10px] uppercase tracking-wide font-bold text-gray-500 dark:text-gray-400">Avg Subscription</p>
            </div>
            <p className="text-xl font-bold text-gray-900 dark:text-white tabular-nums">{stats.avgSub.toFixed(2)}×</p>
            <p className="text-[10px] text-gray-500 dark:text-gray-400">overall demand</p>
          </Card>
          <Card className="p-3">
            <div className="flex items-center gap-2 mb-1">
              <TrendingUp className="w-3.5 h-3.5 text-violet-500" />
              <p className="text-[10px] uppercase tracking-wide font-bold text-gray-500 dark:text-gray-400">Pipeline</p>
            </div>
            <p className="text-xl font-bold text-gray-900 dark:text-white tabular-nums">{counts.upcoming}</p>
            <p className="text-[10px] text-gray-500 dark:text-gray-400">upcoming issues</p>
          </Card>
        </div>
      )}

      <div className="mb-4">
        <PillTabs value={tab} onChange={(v) => setTab(v as Tab)} options={tabOptions}/>
      </div>

      {isLoading && <Loading label="Fetching IPO calendar…" />}

      {!isLoading && tab === "listed" && listedItems.length === 0 && (
        <EmptyState
          icon={<Calendar className="w-10 h-10" />}
          title="No recently listed IPOs yet"
          message="IPOs automatically move here 7 days after their subscription window closes. Check back after the next listing cycle."
        />
      )}

      {!isLoading && tab === "listed" && listedItems.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
          {listedItems.map(it => <ListedIssueCard key={it.symbol} issue={it} />)}
        </div>
      )}

      {!isLoading && tab !== "listed" && items.length === 0 && (
        <EmptyState
          icon={<Rocket className="w-10 h-10" />}
          title={tab === "open" ? "No IPOs open right now" : "No upcoming IPOs announced"}
          message={tab === "open"
            ? "Check back soon — the next mainboard or SME issue will appear here as soon as bidding opens."
            : "When NSE publishes the next batch of forthcoming issues, they'll show up here."}
        />
      )}

      {!isLoading && items.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
          {items.map(it => tab === "open"
            ? <OpenIssueCard key={it.symbol} issue={it}/>
            : <UpcomingIssueCard key={it.symbol} issue={it}/>
          )}
        </div>
      )}

      {tab !== "listed" && items.length > 0 && (
        <div className="mt-4 space-y-1.5">
          {tab === "open" && (
            <p className="flex items-start gap-1.5 text-[11px] text-gray-500 dark:text-gray-400">
              <Info className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
              <span>Subscription multiples are live from NSE. Bars use a log scale anchored at 100× — a violet bar means oversubscribed beyond 10×.</span>
            </p>
          )}
          <p className="flex items-start gap-1.5 text-[11px] text-gray-500 dark:text-gray-400">
            <Info className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
            <span>
              Grey Market Premium is an unofficial pre-listing indicator sourced from{" "}
              <a href={gmpSource.href} target="_blank" rel="noreferrer"
                 className="text-blue-600 dark:text-blue-400 underline">{gmpSource.host}</a>
              {data?.gmpSource?.fetchedAt && <> · last fetched {data.gmpSource.fetchedAt.replace("T"," ").replace("Z"," UTC")}</>}.
              Estimated listing = issue price + GMP. Treat it as sentiment, not a forecast.
            </span>
          </p>
        </div>
      )}
    </div>
  );
}
