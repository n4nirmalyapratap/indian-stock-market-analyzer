"""
portfolio_audit_demo.py
End-to-end audit of a sample Indian portfolio.

What it does (one shot, no HTTP — calls services directly so the audit
is reproducible without spinning up auth):
  1. Generates a sample tradebook as an .xlsx workbook
     (artifacts/python-backend/data/sample_portfolio.xlsx).
  2. Creates a fresh portfolio for a synthetic test user (in an isolated
     SQLite DB so the real prod portfolio table is never touched).
  3. Uploads the workbook through the same xlsx_bytes_to_csv +
     import_transactions pipeline that the new POST /import-file
     endpoint uses, so we exercise the real production path.
  4. Runs every audit lens we ship:
        - Live valuation (sector & cap concentration)
        - Risk metrics (95/99% VaR, Sharpe, Sortino, max DD,
          full correlation matrix via portfolio_var)
        - Efficient-frontier optimiser + concrete rebalance trades
        - Concentration alerts (>25% single-name, >40% sector,
          >50% cash drag)
  5. Writes the full audit JSON + a human-readable Markdown report to
     .local/audit/.
"""
from __future__ import annotations

import asyncio, json, os, sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from openpyxl import Workbook

# Point the portfolio service at an isolated SQLite file so the demo
# never collides with real data.  This must happen BEFORE importing
# portfolio_service so its module-level DB_PATH is overridden.
DEMO_DB = ROOT / "data" / "audit_demo.sqlite"
DEMO_DB.parent.mkdir(parents=True, exist_ok=True)
if DEMO_DB.exists():
    DEMO_DB.unlink()

from app.services import portfolio_service as ps          # noqa: E402
ps.DB_PATH = str(DEMO_DB)
# ensure_schema() ran at import time against the prod path; re-run it
# now that DB_PATH points at the isolated demo file.
ps.ensure_schema()

from app.services import portfolio_optimizer_service as opt  # noqa: E402
from app.services.nse_service import NseService           # noqa: E402
from app.services.yahoo_service import YahooService       # noqa: E402
from app.services.price_service import PriceService       # noqa: E402
from app.services import hydra_var_service as hv          # noqa: E402

OUT_DIR = Path(__file__).resolve().parents[3] / ".local" / "audit"
OUT_DIR.mkdir(parents=True, exist_ok=True)
SAMPLE_XLSX = ROOT / "data" / "sample_portfolio.xlsx"
SAMPLE_XLSX.parent.mkdir(parents=True, exist_ok=True)

USER_ID = "audit_demo_user"


# ── 1. Build a realistic Indian sample portfolio Excel ───────────────────────

def build_sample_xlsx() -> Path:
    """Diversified-ish but deliberately concentration-skewed (RELIANCE 30%+)
    so the audit will flag it.  Mix of sectors: Energy, IT, Banking, FMCG,
    NBFC.  Dates inside the last 12 months so equity-curve has data."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Tradebook"
    ws.append(["symbol", "side", "qty", "price", "date", "fees"])
    today = datetime.utcnow().date()
    rows = [
        # Heavy RELIANCE position — should trigger >25% concentration alert
        ("RELIANCE",   "BUY",  60, 2_650.00, today - timedelta(days=300), 18.50),
        ("RELIANCE",   "BUY",  40, 2_810.00, today - timedelta(days=180), 12.20),
        # IT
        ("TCS",        "BUY",  25, 3_750.00, today - timedelta(days=270),  9.40),
        ("INFY",       "BUY",  40, 1_480.00, today - timedelta(days=240),  7.10),
        # Banking
        ("HDFCBANK",   "BUY",  35, 1_510.00, today - timedelta(days=210),  8.20),
        ("ICICIBANK",  "BUY",  50, 1_120.00, today - timedelta(days=150),  9.80),
        # FMCG
        ("ITC",        "BUY", 120,   415.00, today - timedelta(days=120),  6.30),
        # NBFC
        ("BAJFINANCE", "BUY",   8, 7_200.00, today - timedelta(days=90),  10.50),
        # Partial profit-take on TCS
        ("TCS",        "SELL", 10, 4_010.00, today - timedelta(days=30),   5.10),
        # Dividend
        ("RELIANCE",   "DIVIDEND", 100, 10.00, today - timedelta(days=20),  0),
    ]
    for r in rows:
        ws.append(list(r))
    wb.save(SAMPLE_XLSX)
    return SAMPLE_XLSX


# ── 2. Audit pipeline ────────────────────────────────────────────────────────

async def run_audit() -> dict:
    print(f"→ Sample workbook        : {SAMPLE_XLSX}")
    xlsx_path = build_sample_xlsx()
    xlsx_bytes = xlsx_path.read_bytes()
    print(f"  ({xlsx_path.stat().st_size:,} bytes)")

    # Same pipeline as POST /api/portfolio/{pid}/import-file
    csv_text = ps.xlsx_bytes_to_csv(xlsx_bytes)
    print(f"→ XLSX → CSV converter   : {len(csv_text.splitlines())} lines")

    # Create a fresh portfolio
    pf = ps.create_portfolio(USER_ID, name="Audit Demo (XLSX)",
                             cash=2_000_000.0, base_currency="INR")
    pid = pf["id"]
    print(f"→ Portfolio created      : {pid}")

    # Import — this is the real production path
    imp = ps.import_transactions(USER_ID, pid, csv_text)
    print(f"→ Imported               : {imp['rowsInserted']}/{imp['rowsParsed']} "
          f"rows (format={imp['format']}, errors={len(imp['errors'])})")
    if imp["errors"]:
        for e in imp["errors"][:5]:
            print(f"   ! {e}")

    # Live pricing
    price = PriceService(NseService(), YahooService())

    # ── Audit lenses ─────────────────────────────────────────────────────────
    val = await ps.value_portfolio(USER_ID, pid, price)
    totals = val["totals"]
    print(f"→ Valuation              : MV ₹{totals['marketValue']:,.0f} "
          f"P&L ₹{totals['unrealisedPnl']:,.0f} "
          f"({totals['unrealisedPnlPct']:+.2f}%)")

    # Pull histories for risk + optimiser
    symbols = sorted({h["symbol"] for h in val["holdings"]})
    histories: dict[str, list[float]] = {}
    for sym in symbols:
        try:
            rows = await price.get_historical_data(sym, 400)
            closes = [float(b["close"]) for b in (rows or []) if b.get("close")]
            # hydra_var requires ≥30 days; NSE upstream typically caps the
            # daily archive at ~60 trading days so we accept anything ≥30.
            if len(closes) >= 30:
                histories[sym] = closes
            else:
                print(f"   ! {sym}: only {len(closes)} closes — skipping risk")
        except Exception as exc:
            print(f"   ! history failed for {sym}: {exc}")

    print(f"→ Histories loaded       : {len(histories)}/{len(symbols)} symbols")

    # Risk — portfolio_var + per-symbol Sharpe / Sortino / max-DD
    risk_summary: dict = {}
    weights_dict = {h["symbol"]: float(h["weight"]) for h in val["holdings"]
                    if h["weight"] > 0}
    if weights_dict and histories:
        syms = list(weights_dict.keys())
        ws_  = [weights_dict[s] for s in syms]
        try:
            pv95 = hv.portfolio_var(
                symbols=syms, closes_map=histories, weights=ws_,
                confidence=0.95, horizon_days=1,
                portfolio_value=totals["marketValue"],
            )
            pv99 = hv.portfolio_var(
                symbols=syms, closes_map=histories, weights=ws_,
                confidence=0.99, horizon_days=1,
                portfolio_value=totals["marketValue"],
            )
            risk_summary["var95"] = pv95
            risk_summary["var99"] = pv99

            # Per-symbol Sharpe / Sortino / max-DD
            per_sym = {}
            for s in syms:
                per_sym[s] = {
                    "sharpe":     hv.sharpe_ratio(histories[s], 0.07),
                    "sortino":    hv.sortino_ratio(histories[s], 0.07),
                    "maxDrawdown":hv.max_drawdown(histories[s]),
                }
            risk_summary["perSymbol"] = per_sym

            print(f"→ Portfolio VaR (1d 95%) : ₹{pv95.get('portfolioVarAbs', 0):,.0f} "
                  f"({pv95.get('portfolioVarPct', 0):.2f}%)  · "
                  f"99%: ₹{pv99.get('portfolioVarAbs', 0):,.0f}")
            print(f"→ Annualised vol         : {pv95.get('portfolioVolatility', 0):.2f}%")
        except Exception as exc:
            print(f"   ! risk failed: {exc}")
            risk_summary["error"] = str(exc)

    # Optimiser — efficient frontier + concrete rebalance trades
    optimiser: dict = {}
    if len(histories) >= 2:
        try:
            ef = opt.efficient_frontier(
                symbols=list(histories.keys()),
                closes_map=histories,
                points=15, rf_annual=0.07,
            )
            optimiser["efficientFrontier"] = ef
            ms = ef.get("maxSharpe") or {}
            # _portfolio_stats returns weights as an ordered LIST aligned to
            # ef["symbols"]; zip them back into a {symbol: weight} dict so
            # the rebalancer and the markdown report can use them.
            kept = ef.get("symbols") or []
            w_list = ms.get("weights") or []
            tw = {s: float(w) for s, w in zip(kept, w_list) if w > 0}
            if tw:
                # Concrete rebalance trades
                cur_qty = {h["symbol"]: float(h["qty"]) for h in val["holdings"]}
                prices  = {h["symbol"]: float(h["lastPrice"]) for h in val["holdings"]}
                trades = opt.rebalance_trades(
                    target_weights=tw,
                    current_qty=cur_qty,
                    prices=prices,
                    equity=totals["totalEquity"],
                )
                optimiser["targetWeights"] = tw
                optimiser["rebalanceTrades"] = trades
                top = sorted(tw.items(), key=lambda kv: kv[1], reverse=True)[:3]
                top_str = ", ".join(f"{s} {w*100:.1f}%" for s, w in top)
                print(f"→ Optimiser (Markowitz)  : Sharpe* {ms.get('sharpe', 0):.2f}  "
                      f"top {top_str}  ({len(trades)} rebalance trades)")
        except Exception as exc:
            print(f"   ! optimiser failed: {exc}")
            optimiser["error"] = str(exc)

    # Concentration alerts (the "audit" rules)
    alerts = []
    for h in val["holdings"]:
        if h["weight"] > 0.25:
            alerts.append({"severity": "high", "kind": "single_name_concentration",
                           "message": f"{h['symbol']} is {h['weight']*100:.1f}% of MV "
                                      "(>25% single-name limit)"})
    sector_w = {a["label"]: a["weight"] for a in val["allocation"]["sector"]}
    for sec, w in sector_w.items():
        if w > 0.40 and sec != "Unknown":
            alerts.append({"severity": "medium", "kind": "sector_concentration",
                           "message": f"Sector '{sec}' is {w*100:.1f}% (>40% sector limit)"})
    cash_w = (totals["cash"] / totals["totalEquity"]) if totals["totalEquity"] > 0 else 0
    if cash_w > 0.50:
        alerts.append({"severity": "low", "kind": "cash_drag",
                       "message": f"Cash is {cash_w*100:.1f}% of equity — high drag"})
    print(f"→ Audit alerts           : {len(alerts)}")
    for a in alerts:
        print(f"   [{a['severity'].upper():6s}] {a['message']}")

    return {
        "user_id":       USER_ID,
        "portfolio_id":  pid,
        "source_file":   str(xlsx_path),
        "import_result": imp,
        "valuation":     val,
        "risk":          risk_summary,
        "optimiser":     optimiser,
        "alerts":        alerts,
        "sector_weights": sector_w,
        "cash_weight":   cash_w,
        "generated_at":  datetime.utcnow().isoformat() + "Z",
    }


# ── 3. Markdown rendering ────────────────────────────────────────────────────

def render_markdown(audit: dict) -> str:
    val = audit["valuation"]
    totals = val["totals"]
    risk = audit.get("risk") or {}
    optr = audit.get("optimiser") or {}
    lines = [
        "# Portfolio Audit Report",
        "",
        f"_Generated: {audit['generated_at']}_  ",
        f"_Source file: `{Path(audit['source_file']).name}`_  ",
        f"_Portfolio id: `{audit['portfolio_id']}`_",
        "",
        "## 1. Import",
        f"- Format detected: **{audit['import_result']['format']}**",
        f"- Rows parsed: **{audit['import_result']['rowsParsed']}** · "
        f"inserted: **{audit['import_result']['rowsInserted']}**",
        f"- Errors: **{len(audit['import_result']['errors'])}**",
    ]
    if audit["import_result"]["errors"]:
        lines.append("  ```")
        lines += [f"  {e}" for e in audit["import_result"]["errors"][:10]]
        lines.append("  ```")

    lines += [
        "",
        "## 2. Valuation",
        f"- Total equity: **₹{totals['totalEquity']:,.0f}**",
        f"- Market value: ₹{totals['marketValue']:,.0f}",
        f"- Invested   : ₹{totals['investedValue']:,.0f}",
        f"- Unrealised P&L: **₹{totals['unrealisedPnl']:,.0f} "
        f"({totals['unrealisedPnlPct']:+.2f}%)**",
        f"- Realised P&L : ₹{totals['realisedPnl']:,.0f}",
        f"- Dividends    : ₹{totals['dividendsRcvd']:,.0f}",
        f"- Cash: ₹{totals['cash']:,.0f} ({audit['cash_weight']*100:.1f}%)",
        "",
        "### Holdings",
        "| Symbol | Qty | Avg cost | LTP | MV | Weight | P&L % |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for h in sorted(val["holdings"], key=lambda x: -x["marketValue"]):
        lines.append(
            f"| {h['symbol']} | {h['qty']:.2f} | ₹{h['avgCost']:,.2f} | "
            f"₹{h['lastPrice']:,.2f} | ₹{h['marketValue']:,.0f} | "
            f"{h['weight']*100:.1f}% | {h['unrealisedPnlPct']:+.2f}% |"
        )

    lines += ["", "## 3. Sector concentration"]
    for a in val["allocation"]["sector"]:
        lines.append(f"- **{a['label']}**: {a['weight']*100:.1f}% (₹{a['value']:,.0f})")

    lines += ["", "## 4. Market-cap concentration"]
    for a in val["allocation"]["marketCap"]:
        lines.append(f"- **{a['label']}**: {a['weight']*100:.1f}% (₹{a['value']:,.0f})")

    if risk.get("var95"):
        v = risk["var95"]
        v99 = risk.get("var99", {})
        lines += [
            "",
            "## 5. Risk metrics (1-day, historical-simulation)",
            f"- VaR (95%): **₹{v.get('portfolioVarAbs', 0):,.0f}** "
            f"({v.get('portfolioVarPct', 0):.2f}%)",
            f"- CVaR (95%): ₹{v.get('portfolioCvarAbs', 0):,.0f} "
            f"({v.get('portfolioCvarPct', 0):.2f}%)",
            f"- VaR (99%): ₹{v99.get('portfolioVarAbs', 0):,.0f} "
            f"({v99.get('portfolioVarPct', 0):.2f}%)",
            f"- Annualised volatility: {v.get('portfolioVolatility', 0):.2f}%",
            f"- Sample size (days): {v.get('sampleSize', 0)}",
        ]
        # Correlation matrix (small enough to embed)
        corr = v.get("correlationMatrix") or []
        syms = v.get("symbols") or []
        if corr and syms and len(corr) == len(syms):
            lines += ["", "### Correlation matrix",
                      "| | " + " | ".join(syms) + " |",
                      "|---|" + "---|" * len(syms)]
            for i, s in enumerate(syms):
                row_vals = " | ".join(f"{corr[i][j]:.2f}" for j in range(len(syms)))
                lines.append(f"| **{s}** | {row_vals} |")
        # Per-symbol table
        ps_ = risk.get("perSymbol") or {}
        if ps_:
            lines += [
                "",
                "### Per-symbol risk",
                "| Symbol | Sharpe | Sortino | Max DD % |",
                "|---|---:|---:|---:|",
            ]
            for s, m in sorted(ps_.items()):
                sh = m.get("sharpe", {}).get("sharpe")
                so = m.get("sortino", {}).get("sortino")
                dd = m.get("maxDrawdown", {}).get("maxDrawdownPct")
                lines.append(f"| {s} | "
                             f"{sh if sh is not None else 'n/a'} | "
                             f"{so if so is not None else 'n/a'} | "
                             f"{dd if dd is not None else 'n/a'} |")

    if optr.get("targetWeights"):
        ms = (optr.get("efficientFrontier") or {}).get("maxSharpe") or {}
        tw = optr["targetWeights"]
        cur = {h["symbol"]: h["weight"] for h in val["holdings"]}
        lines += [
            "",
            "## 6. Optimiser (Max-Sharpe / Markowitz)",
            f"- Optimised Sharpe: **{ms.get('sharpe', 0):.2f}**",
            f"- Expected return: {ms.get('expectedReturn', 0)*100:.2f}%",
            f"- Expected vol   : {ms.get('volatility', 0)*100:.2f}%",
            "",
            "### Suggested target weights",
            "| Symbol | Current | Target | Δ |",
            "|---|---:|---:|---:|",
        ]
        for s in sorted(set(list(cur) + list(tw)), key=lambda x: -tw.get(x, 0)):
            c, t = cur.get(s, 0), tw.get(s, 0)
            lines.append(f"| {s} | {c*100:.1f}% | {t*100:.1f}% | "
                         f"{(t-c)*100:+.1f} pp |")
        if optr.get("rebalanceTrades"):
            lines += [
                "",
                "### Concrete rebalance trades",
                "| Symbol | Side | Qty | Notional |",
                "|---|---|---:|---:|",
            ]
            for tr in optr["rebalanceTrades"]:
                lines.append(
                    f"| {tr['symbol']} | {tr['side']} | "
                    f"{tr['qty']:.2f} | ₹{tr['notional']:,.0f} |"
                )

    lines += ["", "## 7. Audit alerts"]
    if not audit["alerts"]:
        lines.append("- _No rule violations._")
    for a in audit["alerts"]:
        lines.append(f"- **[{a['severity'].upper()}]** {a['message']}")

    return "\n".join(lines) + "\n"


# ── 4. Entry ─────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 72)
    print("PORTFOLIO AUDIT — XLSX upload + full diagnostics")
    print("=" * 72)
    audit = asyncio.run(run_audit())

    json_path = OUT_DIR / "portfolio_audit.json"
    md_path   = OUT_DIR / "portfolio_audit.md"
    json_path.write_text(json.dumps(audit, indent=2, default=str))
    md_path.write_text(render_markdown(audit))
    print()
    print(f"→ Wrote {json_path}")
    print(f"→ Wrote {md_path}")
    print(f"→ Sample workbook at {SAMPLE_XLSX}")


if __name__ == "__main__":
    main()
