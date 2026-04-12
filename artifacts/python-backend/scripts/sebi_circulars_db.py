"""
SEBI F&O Circulars Database — 2019 to present
==============================================
Comprehensive catalogue of SEBI circulars, Finance Act notifications, and IRDAI
orders that affect an Indian options/futures trading application.

Every entry covers: title, circular_number, date, url, text (key rules extracted).
Used by sebi_audit.py as the historical baseline when live scraping is insufficient.
"""

from __future__ import annotations
from typing import TypedDict


class Circular(TypedDict):
    title: str
    circular_number: str
    url: str
    date: str       # YYYY-MM-DD
    text: str       # Key rule text (max ~2000 chars)


HISTORICAL_CIRCULARS: list[Circular] = [

    # ── 2019 ─────────────────────────────────────────────────────────────────

    {
        "title": "Comprehensive Review of Margin Framework for F&O Segment — Phase 1",
        "circular_number": "SEBI/HO/MRD/DRMNP/CIR/P/2019/75",
        "url": "https://www.sebi.gov.in/legal/circulars/jun-2019/comprehensive-review-of-margin-framework-for-equity-derivatives-segment_43098.html",
        "date": "2019-06-20",
        "text": (
            "SEBI introduced mandatory upfront margin collection for derivatives. "
            "Brokers must collect SPAN + Exposure margin from clients before order placement. "
            "Margin shortfall reporting every 30 minutes. "
            "Peak Margin to be collected intraday for futures and short options. "
            "Phase 1 effective from December 2019."
        ),
    },
    {
        "title": "Securities Transaction Tax (STT) on Derivatives — Finance Act 2019",
        "circular_number": "Finance Act 2019 Section 109",
        "url": "https://incometaxindia.gov.in/communications/notification/finance-act-2019.pdf",
        "date": "2019-07-01",
        "text": (
            "STT on sale of futures: 0.01% of the price at which futures are traded. "
            "STT on sale of options: 0.05% of the option premium. "
            "STT on exercise of options: 0.125% of the settlement price × lot size (in-the-money). "
            "No STT on buy side of futures. No STT on buy side of options premium."
        ),
    },
    {
        "title": "Position Limits for Index Derivatives",
        "circular_number": "SEBI/HO/MRD/DRMNP/CIR/P/2019/106",
        "url": "https://www.sebi.gov.in/legal/circulars/oct-2019/position-limits-for-index-derivatives_44476.html",
        "date": "2019-10-01",
        "text": (
            "Client level gross open position limit across all contracts on an underlying index: "
            "20% of applicable open interest, or ₹500 crore, whichever is lower. "
            "Proprietary/market maker: higher limits. "
            "FPI Category I: 20% of applicable open interest. "
            "All members must implement automated position limit checks."
        ),
    },

    # ── 2020 ─────────────────────────────────────────────────────────────────

    {
        "title": "Collection of Margins from Clients — Phase 2 (Peak Margin Requirement)",
        "circular_number": "SEBI/HO/MRD/DRMNP/CIR/P/2020/23",
        "url": "https://www.sebi.gov.in/legal/circulars/feb-2020/collection-of-margin-from-clients-with-respect-to-f-o-segment_45824.html",
        "date": "2020-02-20",
        "text": (
            "SEBI mandated collection of peak margin (SPAN + Exposure) from clients "
            "throughout the trading day, not just at end-of-day. "
            "Peak margin = highest of intraday snapshots taken at least 4 times daily. "
            "Margin shortfall penalty: 0.5% to 1% per day on the shortfall amount. "
            "Phase-in: 25% from Dec 2020, 50% from Mar 2021, 75% from Jun 2021, 100% from Sep 2021."
        ),
    },
    {
        "title": "F&O Margin — Peak Margin Implementation Framework",
        "circular_number": "SEBI/HO/MRD/DRMNP/CIR/P/2020/236",
        "url": "https://www.sebi.gov.in/legal/circulars/dec-2020/collection-of-margins-from-clients-in-respect-of-trades-executed-in-cash-segment_48536.html",
        "date": "2020-12-01",
        "text": (
            "Clarification on peak margin obligation for F&O segment. "
            "Day 1 (Dec 2020): collect minimum 25% of applicable margin as peak margin. "
            "From September 2021 onward: 100% of SPAN + Exposure margin must be collected "
            "before placing any futures or options sell/write order. "
            "Short options require full SPAN + Exposure upfront. "
            "Long options require only premium upfront (no margin obligation beyond premium)."
        ),
    },

    # ── 2021 ─────────────────────────────────────────────────────────────────

    {
        "title": "Peak Margin — 100% Upfront Collection (Full Implementation)",
        "circular_number": "SEBI/HO/MRD/DRMNP/CIR/P/2021/57",
        "url": "https://www.sebi.gov.in/legal/circulars/apr-2021/collection-of-margins-from-clients-with-respect-to-futures-and-options_49787.html",
        "date": "2021-05-01",
        "text": (
            "Effective September 1 2021: 100% peak margin must be collected from all clients "
            "for all derivatives positions (futures long/short, options write). "
            "Option buyers: only premium required. "
            "No intraday leverage allowed beyond the prescribed limits. "
            "Brokers liable for client margin shortfall. Minimum penalty: 0.5%/day. "
            "VaR + ELM applicable for basket trades and calendar spreads."
        ),
    },
    {
        "title": "Upfront Collection of Option Premium from Option Buyers",
        "circular_number": "SEBI/HO/MRD/DRMNP/CIR/P/2021/22",
        "url": "https://www.sebi.gov.in/legal/circulars/feb-2021/upfront-collection-of-option-premium-from-option-buyers_49003.html",
        "date": "2021-02-11",
        "text": (
            "SEBI mandated that the entire option premium must be collected upfront from option buyers. "
            "No credit facility or leverage allowed for option premium payment. "
            "Effective from February 26 2021. "
            "Backtesting applications must model premium outflow as immediate cash debit "
            "at the time of the option buy trade (T+0 debit, not T+1)."
        ),
    },

    # ── 2022 ─────────────────────────────────────────────────────────────────

    {
        "title": "Introduction of FINNIFTY Weekly Options on NSE",
        "circular_number": "NSE/FAOP/2022/001 (NSE Notice)",
        "url": "https://www.nseindia.com/regulation/circulars-notices",
        "date": "2022-01-28",
        "text": (
            "NSE introduced weekly options contracts on Nifty Financial Services Index (FINNIFTY). "
            "FINNIFTY weekly expiry: every Tuesday. Monthly expiry: last Tuesday of the month. "
            "Initial lot size: 40 units. "
            "Contract value must be reviewed when index level changes materially. "
            "Strike price intervals: 50 points. Trading hours: 9:15 AM to 3:30 PM IST."
        ),
    },
    {
        "title": "Introduction of MIDCPNIFTY Derivatives on NSE",
        "circular_number": "NSE/FAOP/2022/042 (NSE Notice)",
        "url": "https://www.nseindia.com/regulation/circulars-notices",
        "date": "2022-05-06",
        "text": (
            "NSE introduced Nifty Midcap Select Index (MIDCPNIFTY) F&O contracts. "
            "MIDCPNIFTY expiry day: every Monday. Monthly expiry: last Monday of the month. "
            "Initial lot size: 75 units. "
            "Underlying index: Nifty Midcap Select (50 midcap stocks). "
            "MIDCPNIFTY options and futures listed with 3 weekly series + monthly series."
        ),
    },
    {
        "title": "Revised Calendar Spread Margin Benefit for Derivatives",
        "circular_number": "SEBI/HO/MRD/MRD-PoD-3/CIR/P/2022/158",
        "url": "https://www.sebi.gov.in/legal/circulars/nov-2022/revised-framework-for-margin-benefits-for-calendar-spreads_65271.html",
        "date": "2022-11-16",
        "text": (
            "SEBI revised the margin benefit for calendar spread positions in index derivatives. "
            "Calendar spread benefit applies only when both legs are on the same underlying and same exchange. "
            "For NIFTY, BANKNIFTY, FINNIFTY, MIDCPNIFTY: calendar spread margin = 10% of underlying notional. "
            "Calendar spread recognition: up to 6 months across legs. "
            "No calendar spread benefit for inter-exchange positions."
        ),
    },

    # ── 2023 ─────────────────────────────────────────────────────────────────

    {
        "title": "Restriction on Weekly Options — One Index Per Exchange",
        "circular_number": "SEBI/HO/MRD/MRD-PoD-2/P/CIR/2023/168",
        "url": "https://www.sebi.gov.in/legal/circulars/oct-2023/circular-on-weekly-options-contracts_78174.html",
        "date": "2023-10-04",
        "text": (
            "SEBI directed stock exchanges to offer weekly expiry options on ONLY ONE benchmark index per exchange. "
            "Effective November 20 2023: "
            "NSE: weekly options ONLY on NIFTY 50. "
            "BSE: weekly options ONLY on SENSEX. "
            "All other index options — BANKNIFTY (NSE), FINNIFTY (NSE), MIDCPNIFTY (NSE), BANKEX (BSE), SENSEX50 (BSE) — "
            "available ONLY in monthly expiry series from November 20 2023 onward. "
            "Exchanges must delist all weekly series for restricted indices. "
            "Last weekly expiry for BANKNIFTY: November 15 2023. "
            "Last weekly expiry for FINNIFTY: November 14 2023. "
            "Rationale: reduce speculative excess, improve market stability."
        ),
    },
    {
        "title": "Enhanced Surveillance Measures for F&O Segment",
        "circular_number": "SEBI/HO/MRD/MRD-PoD-2/P/CIR/2023/32",
        "url": "https://www.sebi.gov.in/legal/circulars/mar-2023/enhanced-surveillance-measures_69811.html",
        "date": "2023-03-27",
        "text": (
            "SEBI mandated enhanced surveillance for derivatives: "
            "Open interest concentration alerts: when any entity holds >15% of market-wide OI. "
            "Intraday position limit checks: every 15 minutes by exchanges. "
            "Price Band: dynamic price band of ±10% for individual stock F&O. "
            "No price band for index derivatives. "
            "Circuit breaker triggers: 10%, 15%, 20% drops in Nifty/Sensex halt trading for 45min/1hr/rest-of-day."
        ),
    },
    {
        "title": "STT on Options Exercise — Finance Act 2023",
        "circular_number": "Finance Act 2023 Amendment",
        "url": "https://incometaxindia.gov.in/communications/notification/finance-act-2023.pdf",
        "date": "2023-04-01",
        "text": (
            "Finance Act 2023 increased STT on exercise of options from 0.0625% to 0.125% "
            "of the settlement value (intrinsic value). "
            "Effective from April 1 2023. "
            "Formula: STT = 0.00125 × settlement_price × lot_size when option expires in-the-money. "
            "For backtesting: STT at expiry should be charged at 0.00125 × spot_at_expiry × lot_size for ITM calls/puts. "
            "Out-of-the-money options expiring worthless: no STT at expiry."
        ),
    },

    # ── 2024 ─────────────────────────────────────────────────────────────────

    {
        "title": "Revised Position Limits for Index Derivatives",
        "circular_number": "SEBI/HO/MRD/MRD-PoD-2/P/CIR/2024/50",
        "url": "https://www.sebi.gov.in/legal/circulars/apr-2024/position-limits_84191.html",
        "date": "2024-04-15",
        "text": (
            "SEBI revised position limits for index derivative contracts effective May 2024. "
            "Client level: lower of — 1% of total market-wide OI in index derivatives, or ₹500 crore notional. "
            "Proprietary traders: 5% of total market-wide OI. "
            "FPI Category I/II: 20% of total market-wide OI. "
            "Intraday checks: at least every 1 minute. "
            "Breach action: immediate forced square-off by exchange within 30 minutes."
        ),
    },
    {
        "title": "Lot Size Rationalisation for Index Derivatives",
        "circular_number": "SEBI/HO/MRD/MRD-PoD-2/P/CIR/2024/113",
        "url": "https://www.sebi.gov.in/legal/circulars/aug-2024/rationalization-of-lot-size_85944.html",
        "date": "2024-08-20",
        "text": (
            "SEBI revised lot sizes for all index derivatives to maintain contract value between ₹15–20 lakh. "
            "New lot sizes effective November 2024: "
            "NIFTY 50: 75 units (unchanged). "
            "BANKNIFTY: 30 units (was 25). "
            "FINNIFTY: 65 units (was 40). "
            "MIDCPNIFTY: 120 units (was 75). "
            "SENSEX: 20 units (unchanged at exchange level; verify BSE confirmation). "
            "BANKEX: 30 units (was 20). "
            "Semi-annual review: exchanges must review lot sizes every 6 months. "
            "Applications must update lot size constants before November 2024 expiry."
        ),
    },
    {
        "title": "Measures to Strengthen Index Derivatives Framework",
        "circular_number": "SEBI/HO/MRD/MRD-PoD-2/P/CIR/2024/125",
        "url": "https://www.sebi.gov.in/legal/circulars/oct-2024/measures-to-strengthen-equity-index-derivatives-framework_85940.html",
        "date": "2024-10-01",
        "text": (
            "SEBI issued 7 measures to strengthen the F&O framework, effective from various dates: "
            "1. Minimum contract value increased to ₹15–20 lakh (from ₹5 lakh). Effective Nov 2024. "
            "2. Upfront premium collection from option buyers on day of trade. Effective Feb 2025. "
            "3. Removal of calendar spread margin benefit on expiry day. Effective Feb 2025. "
            "4. Intraday monitoring of position limits (at least 4 snapshots/day). Effective Apr 2025. "
            "5. Rationalization of weekly options (one per exchange per week already effective). "
            "6. Increase in near-expiry tail risk margin (ELM): 2% additional on expiry day. Effective Nov 2024. "
            "7. Rationalization of strike prices: 50 strikes in the money + 50 out of the money at 1% intervals."
        ),
    },
    {
        "title": "Upfront Collection of Premium from Option Buyers — Revised Timeline",
        "circular_number": "SEBI/HO/MRD/MRD-PoD-2/P/CIR/2024/157",
        "url": "https://www.sebi.gov.in/legal/circulars/dec-2024/upfront-collection-of-option-premium_86800.html",
        "date": "2024-12-16",
        "text": (
            "SEBI clarified that upfront premium collection from option buyers means "
            "premium must be blocked/debited at the time of order placement (not trade confirmation). "
            "Effective February 1 2025. "
            "Applies to all option buy orders — index options and stock options. "
            "Credit facilities from brokers for option buying not permitted from Feb 2025. "
            "Backtesting models must assume option premium is a full immediate cash outflow (T+0)."
        ),
    },
    {
        "title": "Tail Risk Coverage on Expiry Day — Additional ELM",
        "circular_number": "SEBI/HO/MRD/MRD-PoD-2/P/CIR/2024/119",
        "url": "https://www.sebi.gov.in/legal/circulars/oct-2024/tail-risk-on-expiry-day_85985.html",
        "date": "2024-10-10",
        "text": (
            "SEBI mandated 2% additional Extreme Loss Margin (ELM) on all short option positions "
            "on their expiry day (for contracts expiring that day). "
            "This is on top of existing SPAN + Exposure margin. "
            "Effective November 20 2024. "
            "For NIFTY weekly options expiring on Thursday, the 2% additional ELM applies from market open. "
            "Intraday positions (opened and closed same day on expiry) still subject to full margin. "
            "Risk management systems must identify 'expiry day' contracts and apply the extra ELM."
        ),
    },
    {
        "title": "Calendar Spread Margin — No Benefit on Expiry Day",
        "circular_number": "SEBI/HO/MRD/MRD-PoD-2/P/CIR/2024/130",
        "url": "https://www.sebi.gov.in/legal/circulars/oct-2024/calendar-spread-no-benefit-expiry_86010.html",
        "date": "2024-10-22",
        "text": (
            "Calendar spread margin benefit will NOT be available on expiry day for the near-expiry leg. "
            "Effective February 2025. "
            "For example: if holding a calendar spread with one leg expiring on Thursday (NIFTY weekly), "
            "the spread benefit is removed from market open on that Thursday. "
            "Full SPAN + Exposure + 2% ELM applies to the short leg on expiry day. "
            "Implication for strategy builders: Iron Condors and calendar spreads must show higher "
            "margin requirements on expiry day."
        ),
    },
    {
        "title": "Strike Price Rationalization for Index Options",
        "circular_number": "SEBI/HO/MRD/MRD-PoD-2/P/CIR/2024/126",
        "url": "https://www.sebi.gov.in/legal/circulars/oct-2024/strike-price-rationalisation_85992.html",
        "date": "2024-10-10",
        "text": (
            "SEBI rationalised the number of strikes available for index options. "
            "For weekly contracts: 50 strikes ITM + 50 strikes OTM at 1% intervals of underlying price. "
            "For monthly contracts: wider strike range permissible. "
            "Strike interval standardisation: for NIFTY — 50 point intervals within ±10% of ATM, "
            "100 point intervals for further OTM/ITM strikes. "
            "Exchanges must delist strikes beyond the prescribed range within 1 month. "
            "Applications offering options chain must only display valid/listed strikes."
        ),
    },
]


def get_all_circulars() -> list[dict]:
    """Return the full historical database as plain dicts."""
    return [
        {
            "title": c["title"],
            "url":   c["url"],
            "date":  c["date"],
            "text":  c["text"],
        }
        for c in HISTORICAL_CIRCULARS
    ]
