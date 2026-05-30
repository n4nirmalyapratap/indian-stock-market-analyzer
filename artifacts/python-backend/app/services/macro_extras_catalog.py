"""Catalog of "useful" Indian macro indicators that aren't on the
headline strip but are still worth surfacing.

What this exists to do
----------------------
We don't have a reliable free data source for these (TradingEconomics
blocks our IP; data.gov.in resource IDs we tried returned nothing
useful). So the values are entered by an admin through the existing
manual-override system (PUT /api/admin/macro/overrides/{slug}), and
this catalog just tells the UI what to render.

How it's used
-------------
* `MACRO_EXTRAS` is the source of truth — slug → metadata.
* The public endpoint `/api/insights/macro/extras` joins this catalog
  with whatever the admin has saved in `macro_overrides` and returns
  one row per entry.
* `admin.py` extends its `_ALLOWED_MACRO_INDICATORS` whitelist with
  every slug below so admins can save overrides for them.

Adding a new indicator
----------------------
Append an entry below. No DB migration needed — `macro_overrides` is
keyed by slug and accepts any string. The frontend grid picks the new
tile up automatically on the next refetch.
"""
from __future__ import annotations

from typing import TypedDict


class MacroExtra(TypedDict):
    slug:        str
    label:       str
    unit:        str        # display unit, e.g. "%" or "$B" or ""
    category:    str        # used to group tiles in the UI
    description: str        # one-liner for the tile tooltip / a11y
    sourceHint:  str        # where the admin can look up the value (RBI, MOSPI, etc.)


MACRO_EXTRAS: list[MacroExtra] = [
    # ── Business activity ────────────────────────────────────────────────
    {
        "slug":        "manufacturing_pmi",
        "label":       "Manufacturing PMI",
        "unit":        "",
        "category":    "Business",
        "description": "S&P Global India Manufacturing PMI. >50 = expansion, <50 = contraction.",
        "sourceHint":  "S&P Global / HSBC (monthly press release, ~1st business day).",
    },
    {
        "slug":        "services_pmi",
        "label":       "Services PMI",
        "unit":        "",
        "category":    "Business",
        "description": "S&P Global India Services PMI. Same scale as manufacturing.",
        "sourceHint":  "S&P Global / HSBC (monthly, ~3rd business day).",
    },
    # ── Labour ───────────────────────────────────────────────────────────
    {
        "slug":        "unemployment",
        "label":       "Unemployment Rate",
        "unit":        "%",
        "category":    "Labour",
        "description": "All-India urban+rural unemployment rate as published by CMIE.",
        "sourceHint":  "CMIE 'unemployment-in-india.cmie.com' (monthly).",
    },
    # ── External sector ──────────────────────────────────────────────────
    {
        "slug":        "fx_reserves",
        "label":       "FX Reserves",
        "unit":        "$B",
        "category":    "Trade",
        "description": "RBI total forex reserves (incl. gold and SDRs) in USD billion.",
        "sourceHint":  "RBI weekly statistical supplement (Friday close).",
    },
    {
        "slug":        "trade_balance",
        "label":       "Trade Balance",
        "unit":        "$B",
        "category":    "Trade",
        "description": "Goods trade balance — exports minus imports for the latest month.",
        "sourceHint":  "DGFT / Commerce Ministry monthly release (~mid-month).",
    },
    {
        "slug":        "current_account",
        "label":       "Current Account",
        "unit":        "% GDP",
        "category":    "Trade",
        "description": "Current account balance as a percent of GDP. Negative = deficit.",
        "sourceHint":  "RBI Balance of Payments release (quarterly).",
    },
    # ── Government finances ──────────────────────────────────────────────
    {
        "slug":        "fiscal_deficit",
        "label":       "Fiscal Deficit",
        "unit":        "% GDP",
        "category":    "Government",
        "description": "Central government fiscal deficit, fiscal-year-to-date as % of GDP.",
        "sourceHint":  "CGA Monthly Accounts (~last week of next month).",
    },
    # ── Prices (extras beyond headline CPI/WPI) ──────────────────────────
    {
        "slug":        "core_cpi",
        "label":       "Core CPI",
        "unit":        "%",
        "category":    "Prices",
        "description": "CPI excluding food and fuel — what the RBI watches for sticky inflation.",
        "sourceHint":  "MOSPI CPI release (12th of month at 5:30pm).",
    },
    {
        "slug":        "food_cpi",
        "label":       "Food CPI",
        "unit":        "%",
        "category":    "Prices",
        "description": "Consumer Food Price Index — the volatile component of headline CPI.",
        "sourceHint":  "MOSPI CPI release (alongside headline CPI).",
    },
    # ── Money ────────────────────────────────────────────────────────────
    {
        "slug":        "money_supply_m3",
        "label":       "M3 Money Supply",
        "unit":        "% YoY",
        "category":    "Money",
        "description": "Broad money supply growth YoY. Captures system-wide liquidity.",
        "sourceHint":  "RBI weekly statistical supplement.",
    },
]


# Convenience set the admin route uses for whitelist validation.
MACRO_EXTRAS_SLUGS: set[str] = {x["slug"] for x in MACRO_EXTRAS}


def by_slug(slug: str) -> MacroExtra | None:
    """Return the catalog entry for a slug, or None if unknown."""
    for x in MACRO_EXTRAS:
        if x["slug"] == slug:
            return x
    return None
