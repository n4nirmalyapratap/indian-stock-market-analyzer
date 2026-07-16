"""
Quarterly financial-results service (SEBI Reg-33 / in-bse-fin XBRL).

What it does
------------
Returns the per-quarter Profit & Loss statement for any NSE-listed Indian
equity — the full income statement that Yahoo collapses into 5 lines:
revenue, the complete expense breakdown (materials / employee / finance /
depreciation / other), exceptional items, the current+deferred tax split,
PAT, basic AND diluted EPS, and segment results — for BOTH the standalone
and consolidated basis the company files.

This is the data Screener.in shows on its P&L tab and that the Yahoo-based
`/financials` endpoint cannot reach. It is the natural companion to the
shareholding XBRL parser (`shareholding_service.py`) — same source family,
same fetch + disk-cache + lxml pattern, different taxonomy.

Source chain
------------
  1. NSE corp-info `/api/corporates-financial-results?index=equities&symbol=X`
     — the index of every result the company has filed, each row carrying
     a direct `xbrl` URL plus the basis/audited/quarter flags. (Verified
     reachable from the container; same endpoint family the shareholding
     parser uses.)
  2. in-bse-fin XBRL — fetch + parse each quarter's filing for the full
     P&L. Disk-cached forever (filings are immutable once published).

Each fetch upserts into PG (`financial_results`, one row per
symbol × period-end × basis). Reads come from PG.

Units
-----
in-bse-fin monetary facts are absolute rupees (unitRef INR). We convert to
₹ Crores (÷ 1e7) to match the existing `/financials` shape. EPS, ratios and
face value are stored as reported.

Period selection
----------------
A Reg-33 filing carries several columns (current quarter, previous quarter,
prior-year quarter, YTD…) in separate contexts that can share identical
period dates. The in-bse-fin taxonomy pins the *current reporting period* to
context id `OneD` (duration) / `OneI` (instant) by convention — that is our
primary anchor, validated against DateOfEndOfReportingPeriod.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import httpx

from ..lib.auth_store import ensure_primary_schema, get_conn, now_ms
from ..lib.symbol_map import canonical_symbol
from .nse_service import NseService

logger = logging.getLogger("financial_results")

# Absolute-rupees → ₹ Crores.
_CR = 1e7

# Refresh policy: the most recent quarter can get a re-fetch on staleness;
# older quarters are immutable. Mirrors the shareholding service.
_CURRENT_REFRESH_S = 24 * 3600
_CURRENT_WINDOW_DAYS = 130            # a quarter + filing lag
_DEFAULT_HISTORY = 12                 # quarters returned by default (3 yrs)
# How many result rows (across both bases + both feeds) to enrich on a cold
# fetch. ~16 quarters × 2 bases — sorted newest-first so the recent
# integrated-filing quarters are always covered.
_MAX_FILINGS = 32

_nse = NseService()

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/xml, text/xml, */*",
}

_XBRL_CACHE_DIR = (
    Path(__file__).resolve().parent.parent.parent / "data" / "results_xbrl_cache"
)


# ── in-bse-fin field map ─────────────────────────────────────────────────────
#
# localname → (output key, kind). kind drives unit handling:
#   "money" → value is absolute rupees, divide by 1e7 → ₹ Cr
#   "asis"  → EPS / ratios / face value, keep as reported
_FININ_MONEY = {
    "RevenueFromOperations":                            "revenueFromOperations",
    "OtherIncome":                                      "otherIncome",
    "Income":                                           "totalIncome",
    "CostOfMaterialsConsumed":                          "costOfMaterials",
    "PurchasesOfStockInTrade":                          "purchasesOfStockInTrade",
    "ChangesInInventoriesOfFinishedGoodsWorkInProgressAndStockInTrade": "changesInInventories",
    "EmployeeBenefitExpense":                           "employeeBenefitExpense",
    "FinanceCosts":                                     "financeCosts",
    "DepreciationDepletionAndAmortisationExpense":      "depreciation",
    "OtherExpenses":                                    "otherExpenses",
    "Expenses":                                         "totalExpenses",
    "ProfitBeforeExceptionalItemsAndTax":               "profitBeforeExceptionalAndTax",
    "ExceptionalItemsBeforeTax":                        "exceptionalItems",
    "ProfitBeforeTax":                                  "profitBeforeTax",
    "CurrentTax":                                       "currentTax",
    "DeferredTax":                                      "deferredTax",
    "TaxExpense":                                       "taxExpense",
    "ProfitLossForPeriodFromContinuingOperations":      "profitFromContinuingOps",
    "ProfitLossForPeriod":                              "netProfit",
    "OtherComprehensiveIncomeNetOfTaxes":               "otherComprehensiveIncome",
    "ComprehensiveIncomeForThePeriod":                  "totalComprehensiveIncome",
    "PaidUpValueOfEquityShareCapital":                  "paidUpEquityCapital",
}
_FININ_ASIS = {
    "BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations":   "basicEps",
    "DilutedEarningsLossPerShareFromContinuingAndDiscontinuedOperations": "dilutedEps",
    "BasicEarningsLossPerShareFromContinuingOperations":                  "basicEpsContinuing",
    "DilutedEarningsLossPerShareFromContinuingOperations":                "dilutedEpsContinuing",
    "FaceValueOfEquityShareCapital":                                      "faceValue",
    "DebtEquityRatio":                                                    "debtEquityRatio",
    "DebtServiceCoverageRatio":                                           "debtServiceCoverageRatio",
    "InterestServiceCoverageRatio":                                       "interestServiceCoverageRatio",
}

# Banks / financial institutions file the Form-B layout (Interest Earned /
# Expended, provisions) under different element names than the standard
# Ind-AS P&L. Element local-names are disjoint from the standard map above,
# so we can iterate the union and let presence decide — only one layout's
# elements exist in any given filing.
_FININ_BANK_MONEY = {
    "InterestEarned":                                  "interestEarned",
    "InterestExpended":                                "interestExpended",
    "OperatingExpenses":                               "operatingExpenses",
    "ExpenditureExcludingProvisionsAndContingencies":  "totalExpenditure",
    "ProvisionsOtherThanTaxAndContingencies":          "provisions",
    "OperatingProfitBeforeProvisionAndContingencies":  "operatingProfit",
    "ProfitLossFromOrdinaryActivitiesBeforeTax":       "profitBeforeTax",
    "ProfitLossForThePeriod":                          "netProfit",
    "ProfitLossAfterTaxesMinorityInterestAndShareOfProfitLossOfAssociates": "netProfitAfterMinority",
}
_FININ_BANK_ASIS = {
    "BasicEarningsPerShareAfterExtraordinaryItems":    "basicEps",
    "DilutedEarningsPerShareAfterExtraordinaryItems":  "dilutedEps",
    "BasicEarningsPerShareBeforeExtraordinaryItems":   "basicEpsBeforeExtra",
    "DilutedEarningsPerShareBeforeExtraordinaryItems": "dilutedEpsBeforeExtra",
}

# Iterated unions — standard ∪ banking. Safe because the two layouts use
# disjoint element names; "OtherIncome"/"Income"/"TaxExpense"/
# "PaidUpValueOfEquityShareCapital"/"FaceValueOfEquityShareCapital" are
# shared and map to the same output key in both.
_MONEY_ALL = {**_FININ_MONEY, **_FININ_BANK_MONEY}
_ASIS_ALL  = {**_FININ_ASIS, **_FININ_BANK_ASIS}


# ── NSE results index ────────────────────────────────────────────────────────


async def _fetch_results_index(symbol: str) -> list[dict]:
    """Merged index of results filings, newest quarter first.

    Two NSE endpoints have to be combined because SEBI's Integrated Filing
    framework moved financial results to a new feed from the quarter ending
    Dec-2024:
      * `corporates-financial-results` — the LEGACY feed. Carries full
        history but is frozen at the Dec-2024 quarter.
      * `integrated-filing-results`    — the CURRENT feed (Dec-2024 onward).
        Returns both governance and financial ("INDAS") filings; only the
        latter carry a P&L. Same in-bse-fin XBRL, so the parser is reused.

    Returns [] on total failure; partial results if only one feed responds.
    """
    from urllib.parse import quote  # noqa: PLC0415
    encoded = quote(symbol, safe="")
    referer = f"https://www.nseindia.com/get-quotes/equity?symbol={encoded}"
    out: list[dict] = []

    # 1. Legacy feed (history through Dec-2024).
    try:
        raw = await _nse.fetch_nse(
            f"/api/corporates-financial-results?index=equities&symbol={encoded}&period=Quarterly",
            f"finresults-nse-{symbol}", ttl=12 * 3600, referer=referer,
        )
        rows = raw if isinstance(raw, list) else (raw.get("data") if isinstance(raw, dict) else None)
        for e in (rows or []):
            if not isinstance(e, dict):
                continue
            url = (e.get("xbrl") or "").strip()
            if url.startswith("http"):
                out.append({"xbrl": url, "toDate": e.get("toDate")})
    except Exception as exc:
        logger.debug("results legacy index %s: %s", symbol, str(exc)[:120])

    # 2. Integrated-filing feed (Dec-2024 onward). Keep only the financial
    # ("INDAS") filings — identified by a Standalone/Consolidated basis tag;
    # governance filings carry consolidated=null and no P&L.
    try:
        integ = await _nse.fetch_nse(
            f"/api/integrated-filing-results?index=equities&symbol={encoded}",
            f"intfiling-nse-{symbol}", ttl=12 * 3600, referer=referer,
        )
        idata = integ.get("data") if isinstance(integ, dict) else (integ if isinstance(integ, list) else None)
        for e in (idata or []):
            if not isinstance(e, dict):
                continue
            if (e.get("consolidated") or "").strip() not in ("Standalone", "Consolidated"):
                continue
            url = (e.get("xbrl") or "").strip()
            if url.startswith("http"):
                out.append({"xbrl": url, "toDate": e.get("qe_Date")})
    except Exception as exc:
        logger.debug("results integrated index %s: %s", symbol, str(exc)[:120])

    # Newest quarter first so the per-refresh cap keeps the recent filings.
    out.sort(key=lambda r: _parse_iso(r.get("toDate")) or date(1900, 1, 1), reverse=True)
    return out


# ── XBRL fetch (disk-cached, immutable) ──────────────────────────────────────


def _cache_path(url: str) -> Path:
    h = hashlib.sha256(url.encode("utf-8")).hexdigest()
    return _XBRL_CACHE_DIR / f"{h}.xml"


async def _fetch_xbrl(url: str) -> Optional[bytes]:
    cp = _cache_path(url)
    if cp.exists():
        try:
            return cp.read_bytes()
        except Exception:
            pass
    try:
        async with httpx.AsyncClient(timeout=20.0, headers=_BROWSER_HEADERS,
                                     follow_redirects=True) as client:
            r = await client.get(url)
            if r.status_code != 200:
                logger.debug("results XBRL %s -> %d", url, r.status_code)
                return None
            content = r.content
    except Exception as exc:
        logger.debug("results XBRL fetch failed %s: %s", url, str(exc)[:120])
        return None
    try:
        _XBRL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cp.write_bytes(content)
    except Exception:
        pass
    return content


# ── Parser ────────────────────────────────────────────────────────────────


def _parse_results_xbrl(xml_bytes: bytes) -> Optional[dict]:
    """Parse one in-bse-fin filing → a structured P&L dict.

    Returns None on parse failure or if the primary period can't be
    resolved. Output shape:
        {
          "basis":        "standalone" | "consolidated",
          "periodEnd":    "2024-12-31",
          "periodStart":  "2024-10-01",
          "audited":      bool | None,
          "relatingTo":   "Third quarter",
          "multiSegment": bool | None,
          "lineItems":    { revenueFromOperations: <Cr>, ... basicEps, ... },
          "segments":     [ {name, revenue, result} ],
        }
    """
    try:
        from lxml import etree  # noqa: PLC0415
    except Exception as exc:
        logger.warning("results parse: lxml unavailable: %s", exc)
        return None
    try:
        root = etree.fromstring(xml_bytes)
    except Exception as exc:
        logger.debug("results parse: lxml failed: %s", str(exc)[:120])
        return None

    def qn(e) -> str:
        return etree.QName(e).localname or ""

    # ctx_id → period + whether it carries any dimension; vals[ctx][ln] = text
    ctx_period: dict[str, tuple[Optional[str], Optional[str], Optional[str], bool]] = {}
    for c in root.iter():
        if qn(c) != "context":
            continue
        cid = c.get("id", "")
        if not cid:
            continue
        st = en = inst = None
        has_dim = False
        for e in c.iter():
            ln = qn(e)
            if ln == "startDate":
                st = (e.text or "").strip()
            elif ln == "endDate":
                en = (e.text or "").strip()
            elif ln == "instant":
                inst = (e.text or "").strip()
            elif ln in ("explicitMember", "typedMember"):
                has_dim = True
        ctx_period[cid] = (st, en, inst, has_dim)

    vals: dict[str, dict[str, str]] = {}
    for el in root.iter():
        cref = el.get("contextRef")
        if not cref:
            continue
        t = (el.text or "").strip()
        if not t:
            continue
        vals.setdefault(cref, {}).setdefault(qn(el), t)

    # Header meta lives in the OneD-family duration context (string fields).
    def _meta(name: str) -> Optional[str]:
        for bag in vals.values():
            if name in bag:
                return bag[name]
        return None

    period_end   = _meta("DateOfEndOfReportingPeriod")
    period_start = _meta("DateOfStartOfReportingPeriod")
    basis_raw    = (_meta("NatureOfReportStandaloneConsolidated") or "").lower()
    basis        = "consolidated" if "consol" in basis_raw else "standalone" if basis_raw else None
    audited_raw  = (_meta("WhetherResultsAreAuditedOrUnaudited") or "").lower()
    audited      = (audited_raw == "audited") if audited_raw else None
    multiseg_raw = (_meta("IsCompanyReportingMultisegmentOrSingleSegment") or "").lower()
    multi_seg    = ("multi" in multiseg_raw) if multiseg_raw else None
    relating_to  = _meta("ReportingQuarter")

    # Primary period = context "OneD" by in-bse-fin convention; fall back to
    # the no-dimension duration context whose end matches the reporting end.
    primary = None
    if "OneD" in vals and not ctx_period.get("OneD", (None, None, None, True))[3]:
        primary = "OneD"
    if primary is None:
        for cid, (st, en, inst, has_dim) in ctx_period.items():
            if has_dim or inst or not en:
                continue
            if period_end and en == period_end and st == period_start:
                primary = cid
                break
    if primary is None or primary not in vals:
        logger.debug("results parse: no primary context (period_end=%s)", period_end)
        return None

    bag = vals[primary]

    line_items: dict[str, float] = {}
    for ln, key in _MONEY_ALL.items():
        v = bag.get(ln)
        if v is not None:
            try:
                line_items[key] = round(float(v) / _CR, 2)
            except (ValueError, TypeError):
                pass
    for ln, key in _ASIS_ALL.items():
        v = bag.get(ln)
        if v is not None:
            try:
                line_items[key] = round(float(v), 2)
            except (ValueError, TypeError):
                pass

    if not any(k in line_items for k in ("revenueFromOperations", "interestEarned", "netProfit")):
        # Nothing recognisable (e.g. an insurer's distinct layout) — skip.
        logger.debug("results parse: no P&L items in primary context %s", primary)
        return None

    # Banking layout when the interest-income line is present.
    report_format = "banking" if "interestEarned" in line_items else "standard"

    # Segments — name + revenue + result, indexed by the segment number
    # embedded in the per-segment context ids (…ReportableSegmentRevenue01D…).
    segs: dict[str, dict] = {}
    for cid, b in vals.items():
        m = re.search(r"ReportableSegment(Revenue|Results)0*(\d+)", cid)
        if not m:
            continue
        seg = segs.setdefault(m.group(2), {})
        if "DescriptionOfReportableSegment" in b:
            seg["name"] = b["DescriptionOfReportableSegment"]
        if m.group(1) == "Revenue" and "SegmentRevenue" in b:
            try:
                seg["revenue"] = round(float(b["SegmentRevenue"]) / _CR, 2)
            except (ValueError, TypeError):
                pass
        if m.group(1) == "Results" and "SegmentProfitLossBeforeTaxAndFinanceCosts" in b:
            try:
                seg["result"] = round(float(b["SegmentProfitLossBeforeTaxAndFinanceCosts"]) / _CR, 2)
            except (ValueError, TypeError):
                pass
    segments = [s for _, s in sorted(segs.items()) if s.get("name")]

    return {
        "basis":        basis,
        "periodEnd":    period_end,
        "periodStart":  period_start,
        "audited":      audited,
        "relatingTo":   relating_to,
        "multiSegment": multi_seg,
        "format":       report_format,
        "lineItems":    line_items,
        "segments":     segments or None,
    }


# ── PG layer ─────────────────────────────────────────────────────────────────


def _parse_iso(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%d-%b-%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _upsert(symbol: str, parsed: dict) -> bool:
    """Upsert one parsed filing. Keyed (symbol, period_end, basis)."""
    pe = _parse_iso(parsed.get("periodEnd"))
    basis = parsed.get("basis")
    if pe is None or not basis:
        return False
    ensure_primary_schema()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO financial_results
                    (symbol, period_end, basis, period_type, audited,
                     relating_to, multi_segment, report_format, line_items,
                     segments, source, fetched_at_ms)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s)
                ON CONFLICT (symbol, period_end, basis) DO UPDATE SET
                    period_type   = EXCLUDED.period_type,
                    audited       = EXCLUDED.audited,
                    relating_to   = EXCLUDED.relating_to,
                    multi_segment = EXCLUDED.multi_segment,
                    report_format = EXCLUDED.report_format,
                    line_items    = EXCLUDED.line_items,
                    segments      = EXCLUDED.segments,
                    source        = EXCLUDED.source,
                    fetched_at_ms = EXCLUDED.fetched_at_ms
                """,
                (
                    symbol, pe, basis, "Quarterly", parsed.get("audited"),
                    parsed.get("relatingTo"), parsed.get("multiSegment"),
                    parsed.get("format"),
                    json.dumps(parsed.get("lineItems") or {}),
                    json.dumps(parsed.get("segments")) if parsed.get("segments") else None,
                    "XBRL", now_ms(),
                ),
            )
        conn.commit()
    return True


def _read(symbol: str) -> list[dict]:
    ensure_primary_schema()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT period_end, basis, period_type, audited, relating_to,
                       multi_segment, report_format, line_items, segments,
                       fetched_at_ms
                  FROM financial_results
                 WHERE symbol = %s
              ORDER BY period_end DESC
                """,
                (symbol,),
            )
            return [dict(r) for r in (cur.fetchall() or [])]


def _needs_refresh(rows: list[dict]) -> bool:
    if not rows:
        return True
    latest = rows[0]["period_end"]
    if isinstance(latest, datetime):
        latest = latest.date()
    if (date.today() - latest).days > _CURRENT_WINDOW_DAYS:
        return True
    age_s = (now_ms() - (rows[0].get("fetched_at_ms") or 0)) / 1000.0
    return age_s > _CURRENT_REFRESH_S


# ── Refresh ──────────────────────────────────────────────────────────────────


async def _enrich(symbol: str, url: str) -> Optional[dict]:
    xml = await _fetch_xbrl(url)
    if not xml:
        return None
    return _parse_results_xbrl(xml)


# ── Yahoo Finance fallback ────────────────────────────────────────────────────
# When NSE is Akamai-blocked we have no XBRL URLs and the primary path
# returns nothing. yfinance `quarterly_income_stmt` gives a quarterly P&L
# (Total Revenue, Net Income, Operating Income, EPS, etc.) that covers the
# most important line items — enough to populate the Financials tab until
# the NSE feed is reachable again.

_YF_MONEY: dict[str, str] = {
    "Total Revenue":                    "revenueFromOperations",
    "Operating Revenue":                "revenueFromOperations",
    "Net Income":                       "netProfit",
    "Net Income Common Stockholders":   "netProfit",
    "Operating Income":                 "profitBeforeExceptionalAndTax",
    "EBIT":                             "profitBeforeExceptionalAndTax",
    "Total Expenses":                   "totalExpenses",
    "Cost Of Revenue":                  "totalExpenses",
    "Tax Provision":                    "taxExpense",
    "Interest Expense":                 "financeCosts",
    "Reconciled Depreciation":          "depreciation",
    "Gross Profit":                     "grossProfit",
}
_YF_ASIS: dict[str, str] = {
    "Basic EPS":   "basicEps",
    "Diluted EPS": "dilutedEps",
}


async def _fetch_yahoo_results(symbol: str) -> list[dict]:
    """Fallback quarterly P&L from yfinance when NSE XBRL is unavailable.

    Values in the yfinance DataFrame are absolute local-currency rupees;
    money items are converted to ₹ Crores (÷ 1e7) to match the XBRL path.
    EPS is kept as-is (already per-share).
    """
    try:
        import yfinance as yf                              # noqa: PLC0415
        from ..lib.symbol_map import to_yahoo_ticker       # noqa: PLC0415
    except Exception:
        return []

    ticker_sym = to_yahoo_ticker(symbol)

    def _grab():
        try:
            return yf.Ticker(ticker_sym).quarterly_income_stmt
        except Exception as exc:
            logger.debug("yfinance quarterly_income_stmt %s: %s",
                         symbol, str(exc)[:120])
            return None

    df = await asyncio.to_thread(_grab)
    if df is None or getattr(df, "empty", True):
        logger.info("results YAHOO %s: no quarterly_income_stmt", symbol)
        return []

    out: list[dict] = []
    for col in df.columns:
        try:
            period_end = col.date().isoformat()
        except Exception:
            continue

        line_items: dict[str, float] = {}

        for yf_key, our_key in _YF_MONEY.items():
            if yf_key not in df.index or our_key in line_items:
                continue
            try:
                fval = float(df.loc[yf_key, col])
                import math                                # noqa: PLC0415
                if not math.isnan(fval):
                    line_items[our_key] = round(fval / _CR, 2)
            except (TypeError, ValueError):
                pass

        for yf_key, our_key in _YF_ASIS.items():
            if yf_key not in df.index:
                continue
            try:
                fval = float(df.loc[yf_key, col])
                import math                                # noqa: PLC0415
                if not math.isnan(fval):
                    line_items[our_key] = round(fval, 2)
            except (TypeError, ValueError):
                pass

        if not any(k in line_items for k in ("revenueFromOperations", "netProfit")):
            continue

        out.append({
            "basis":        "standalone",
            "periodEnd":    period_end,
            "periodStart":  None,
            "audited":      None,
            "relatingTo":   None,
            "multiSegment": None,
            "format":       "standard",
            "lineItems":    line_items,
            "segments":     None,
        })

    logger.info("results YAHOO %s: %d quarters parsed", symbol, len(out))
    return out


async def _refresh(symbol: str) -> None:
    """Fetch the NSE index, then fan-out parse the most recent filings.
    Falls back to yfinance when NSE is blocked and returns no XBRL URLs."""
    index: list[dict] = []
    try:
        index = await _fetch_results_index(symbol)
    except Exception as exc:
        logger.warning("results index %s failed: %s", symbol, str(exc)[:160])

    if index:
        candidates = index[:_MAX_FILINGS]
        parsed = await asyncio.gather(
            *[_enrich(symbol, c["xbrl"]) for c in candidates],
            return_exceptions=True,
        )
        written = 0
        for p in parsed:
            if isinstance(p, dict):
                try:
                    if _upsert(symbol, p):
                        written += 1
                except Exception as exc:
                    logger.debug("results upsert %s failed: %s", symbol, str(exc)[:120])
        logger.info("results %s: %d filings stored (of %d tried)", symbol, written, len(candidates))
    else:
        logger.info("results %s: NSE index empty — trying yfinance fallback", symbol)

    # Fallback: if we still have no rows after the XBRL path, use yfinance.
    # Also triggered if NSE was blocked (index=[]).
    existing = _read(symbol)
    if not existing:
        try:
            yf_rows = await _fetch_yahoo_results(symbol)
            yf_written = 0
            for row in yf_rows:
                try:
                    if _upsert(symbol, row):
                        yf_written += 1
                except Exception as exc:
                    logger.debug("results yfinance upsert %s failed: %s", symbol, str(exc)[:120])
            if yf_written:
                logger.info("results YAHOO fallback %s: %d quarters stored", symbol, yf_written)
            else:
                logger.info("results YAHOO fallback %s: 0 stored (yfinance returned nothing)", symbol)
        except Exception as exc:
            logger.warning("results YAHOO fallback %s failed: %s", symbol, str(exc)[:160])


# ── Public API ───────────────────────────────────────────────────────────────


def _to_api(row: dict) -> dict:
    pe = row["period_end"]
    li = row.get("line_items")
    if isinstance(li, str):
        try:
            li = json.loads(li)
        except (ValueError, TypeError):
            li = {}
    seg = row.get("segments")
    if isinstance(seg, str):
        try:
            seg = json.loads(seg)
        except (ValueError, TypeError):
            seg = None
    return {
        "periodEnd":    pe.isoformat() if hasattr(pe, "isoformat") else str(pe),
        "basis":        row.get("basis"),
        "audited":      row.get("audited"),
        "relatingTo":   row.get("relating_to"),
        "multiSegment": row.get("multi_segment"),
        "format":       row.get("report_format"),
        "lineItems":    li or {},
        "segments":     seg,
    }


async def get_financial_results(
    symbol: str, *, basis: str = "consolidated", quarters: int = _DEFAULT_HISTORY,
    force: bool = False,
) -> dict:
    """Quarterly Reg-33 P&L history for `symbol`.

    Returns rows for the requested basis (falling back to the other basis
    when the requested one isn't filed — many companies file only
    standalone). Newest quarter first.
    """
    canon = canonical_symbol(symbol)
    if not canon:
        return {"symbol": symbol, "basis": basis, "available": [], "rows": []}

    cached = _read(canon)
    if force or _needs_refresh(cached):
        await _refresh(canon)
        cached = _read(canon)

    available = sorted({r["basis"] for r in cached if r.get("basis")})
    want = basis if basis in available else (available[0] if available else basis)
    rows = [r for r in cached if r.get("basis") == want][:max(1, quarters)]
    return {
        "symbol":    canon,
        "basis":     want,
        "available": available,
        "rows":      [_to_api(r) for r in rows],
    }
