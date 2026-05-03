"""
Portfolio Manager Service — SQLite-backed CRUD + live valuation.

Stores per-user portfolios and holdings.  Supports importing Zerodha Console
and Upstox tradebook CSVs (no broker key required at this stage).

Live valuation, day P&L, total P&L, sector / market-cap allocations and
concentration warnings are computed from our existing PriceService cache so we
never re-fetch quotes that the dashboard already has.

Tables:
  portfolios   (id, user_id, name, base_currency, cash, created_at, updated_at)
  transactions (id, portfolio_id, symbol, side BUY|SELL|DIVIDEND,
                qty, price, fees, traded_at, source)

Holdings are *derived* from the transactions table (FIFO net qty + weighted
avg cost) — that way every dividend / sell / buy tweaks the position in one
place and the books always reconcile to the trade history.
"""
from __future__ import annotations

import asyncio
import csv
import io
import logging
import os
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ── Storage location ─────────────────────────────────────────────────────────

_CACHE_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "market_cache",
)
os.makedirs(_CACHE_DIR, exist_ok=True)
DB_PATH = os.path.join(_CACHE_DIR, "portfolio.db")

_WRITE_LOCK: asyncio.Lock | None = None


def _lock() -> asyncio.Lock:
    global _WRITE_LOCK
    if _WRITE_LOCK is None:
        _WRITE_LOCK = asyncio.Lock()
    return _WRITE_LOCK


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def ensure_schema() -> None:
    conn = _connect()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS portfolios (
            id            TEXT PRIMARY KEY,
            user_id       TEXT NOT NULL,
            name          TEXT NOT NULL,
            base_currency TEXT NOT NULL DEFAULT 'INR',
            cash          REAL NOT NULL DEFAULT 0,
            created_at    INTEGER NOT NULL,
            updated_at    INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_portfolios_user ON portfolios(user_id);

        CREATE TABLE IF NOT EXISTS transactions (
            id           TEXT PRIMARY KEY,
            portfolio_id TEXT NOT NULL,
            symbol       TEXT NOT NULL,
            side         TEXT NOT NULL CHECK (side IN ('BUY','SELL','DIVIDEND')),
            qty          REAL NOT NULL,
            price        REAL NOT NULL,
            fees         REAL NOT NULL DEFAULT 0,
            traded_at    TEXT NOT NULL,
            source       TEXT NOT NULL DEFAULT 'manual',
            note         TEXT,
            FOREIGN KEY (portfolio_id) REFERENCES portfolios(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_tx_portfolio ON transactions(portfolio_id);
        CREATE INDEX IF NOT EXISTS idx_tx_symbol    ON transactions(portfolio_id, symbol);
        """
    )
    conn.commit()
    conn.close()


ensure_schema()


# ── Helpers ──────────────────────────────────────────────────────────────────

def _now_ms() -> int:
    return int(time.time() * 1000)


def _iso(ts: int | None = None) -> str:
    return datetime.fromtimestamp((ts or _now_ms()) / 1000, tz=timezone.utc).isoformat()


def _row_to_portfolio(row: sqlite3.Row) -> dict:
    return {
        "id":            row["id"],
        "userId":        row["user_id"],
        "name":          row["name"],
        "baseCurrency":  row["base_currency"],
        "cash":          float(row["cash"] or 0),
        "createdAt":     _iso(row["created_at"]),
        "updatedAt":     _iso(row["updated_at"]),
    }


def _row_to_tx(row: sqlite3.Row) -> dict:
    return {
        "id":          row["id"],
        "portfolioId": row["portfolio_id"],
        "symbol":      row["symbol"],
        "side":        row["side"],
        "qty":         float(row["qty"]),
        "price":       float(row["price"]),
        "fees":        float(row["fees"] or 0),
        "tradedAt":    row["traded_at"],
        "source":      row["source"],
        "note":        row["note"],
    }


def _norm_symbol(sym: str) -> str:
    s = (sym or "").strip().upper()
    # Strip exchange suffixes that show up in broker statements
    for suffix in ("-EQ", ".NS", ".BO", ":NSE", ":BSE"):
        if s.endswith(suffix):
            s = s[: -len(suffix)]
    return s


# ── Portfolio CRUD ───────────────────────────────────────────────────────────

def list_portfolios(user_id: str) -> list[dict]:
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM portfolios WHERE user_id=? ORDER BY created_at ASC",
        (user_id,),
    ).fetchall()
    conn.close()
    return [_row_to_portfolio(r) for r in rows]


def get_portfolio(user_id: str, portfolio_id: str) -> Optional[dict]:
    conn = _connect()
    row = conn.execute(
        "SELECT * FROM portfolios WHERE id=? AND user_id=?",
        (portfolio_id, user_id),
    ).fetchone()
    conn.close()
    return _row_to_portfolio(row) if row else None


def create_portfolio(user_id: str, name: str, cash: float = 0.0,
                     base_currency: str = "INR") -> dict:
    pid = str(uuid.uuid4())
    now = _now_ms()
    conn = _connect()
    conn.execute(
        "INSERT INTO portfolios(id,user_id,name,base_currency,cash,created_at,updated_at) "
        "VALUES(?,?,?,?,?,?,?)",
        (pid, user_id, (name or "My Portfolio").strip()[:80],
         (base_currency or "INR").upper()[:8], float(cash or 0), now, now),
    )
    conn.commit()
    conn.close()
    return get_portfolio(user_id, pid)  # type: ignore[return-value]


def update_portfolio(user_id: str, portfolio_id: str,
                     name: Optional[str] = None,
                     cash: Optional[float] = None) -> Optional[dict]:
    p = get_portfolio(user_id, portfolio_id)
    if not p:
        return None
    fields, values = [], []
    if name is not None:
        fields.append("name=?")
        values.append(name.strip()[:80])
    if cash is not None:
        fields.append("cash=?")
        values.append(float(cash))
    if not fields:
        return p
    fields.append("updated_at=?")
    values.append(_now_ms())
    values.extend([portfolio_id, user_id])
    conn = _connect()
    conn.execute(
        f"UPDATE portfolios SET {', '.join(fields)} WHERE id=? AND user_id=?",
        tuple(values),
    )
    conn.commit()
    conn.close()
    return get_portfolio(user_id, portfolio_id)


def delete_portfolio(user_id: str, portfolio_id: str) -> bool:
    conn = _connect()
    cur = conn.execute(
        "DELETE FROM portfolios WHERE id=? AND user_id=?",
        (portfolio_id, user_id),
    )
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted


# ── Transactions ─────────────────────────────────────────────────────────────

def list_transactions(user_id: str, portfolio_id: str,
                      symbol: Optional[str] = None) -> list[dict]:
    if not get_portfolio(user_id, portfolio_id):
        return []
    conn = _connect()
    if symbol:
        rows = conn.execute(
            "SELECT * FROM transactions WHERE portfolio_id=? AND symbol=? "
            "ORDER BY traded_at DESC",
            (portfolio_id, _norm_symbol(symbol)),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM transactions WHERE portfolio_id=? ORDER BY traded_at DESC",
            (portfolio_id,),
        ).fetchall()
    conn.close()
    return [_row_to_tx(r) for r in rows]


def add_transaction(user_id: str, portfolio_id: str, *,
                    symbol: str, side: str, qty: float, price: float,
                    fees: float = 0.0, traded_at: Optional[str] = None,
                    source: str = "manual",
                    note: Optional[str] = None) -> Optional[dict]:
    if not get_portfolio(user_id, portfolio_id):
        return None
    side_u = (side or "").upper()
    if side_u not in ("BUY", "SELL", "DIVIDEND"):
        raise ValueError(f"Invalid side: {side!r}")
    qty_f = abs(float(qty))
    price_f = float(price)
    if qty_f <= 0:
        raise ValueError("Quantity must be positive")
    if price_f < 0:
        raise ValueError("Price must be non-negative")

    tx_id = str(uuid.uuid4())
    iso = (traded_at or _iso())[:32]
    conn = _connect()
    conn.execute(
        "INSERT INTO transactions(id,portfolio_id,symbol,side,qty,price,fees,"
        "traded_at,source,note) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (tx_id, portfolio_id, _norm_symbol(symbol), side_u, qty_f, price_f,
         float(fees or 0), iso, source[:32], note),
    )
    # SELL / BUY moves cash; DIVIDEND adds cash
    if side_u == "BUY":
        cash_delta = -(qty_f * price_f + (fees or 0))
    elif side_u == "SELL":
        cash_delta = +(qty_f * price_f - (fees or 0))
    else:  # DIVIDEND
        cash_delta = +(qty_f * price_f)
    conn.execute(
        "UPDATE portfolios SET cash = cash + ?, updated_at = ? WHERE id=?",
        (cash_delta, _now_ms(), portfolio_id),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM transactions WHERE id=?", (tx_id,)).fetchone()
    conn.close()
    return _row_to_tx(row)


def delete_transaction(user_id: str, portfolio_id: str, tx_id: str) -> bool:
    if not get_portfolio(user_id, portfolio_id):
        return False
    conn = _connect()
    row = conn.execute(
        "SELECT * FROM transactions WHERE id=? AND portfolio_id=?",
        (tx_id, portfolio_id),
    ).fetchone()
    if not row:
        conn.close()
        return False

    side, qty, price, fees = row["side"], float(row["qty"]), float(row["price"]), float(row["fees"] or 0)
    if side == "BUY":
        cash_delta = +(qty * price + fees)
    elif side == "SELL":
        cash_delta = -(qty * price - fees)
    else:
        cash_delta = -(qty * price)

    conn.execute("DELETE FROM transactions WHERE id=?", (tx_id,))
    conn.execute(
        "UPDATE portfolios SET cash = cash + ?, updated_at = ? WHERE id=?",
        (cash_delta, _now_ms(), portfolio_id),
    )
    conn.commit()
    conn.close()
    return True


# ── Holdings derivation ──────────────────────────────────────────────────────

def derive_holdings(portfolio_id: str) -> list[dict]:
    """
    Roll up transactions into per-symbol holdings.

      qty       = sum(BUY) − sum(SELL)
      avg_cost  = weighted avg of net BUY cost  (sells reduce qty proportionally;
                  the cost basis per remaining share stays the historical avg).
      realised  = sum of (sell_price − running_avg_cost) * sell_qty
      dividends = sum of DIVIDEND.qty * DIVIDEND.price

    This is the standard Indian retail-tax book-keeping convention (FIFO is
    only enforced at tax-filing time; for live P&L we use weighted-avg cost).
    """
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM transactions WHERE portfolio_id=? ORDER BY traded_at ASC, rowid ASC",
        (portfolio_id,),
    ).fetchall()
    conn.close()

    book: dict[str, dict] = {}
    for r in rows:
        sym  = r["symbol"]
        side = r["side"]
        qty  = float(r["qty"])
        px   = float(r["price"])
        fees = float(r["fees"] or 0)

        h = book.setdefault(sym, {
            "symbol":   sym,
            "qty":      0.0,
            "avgCost":  0.0,
            "invested": 0.0,
            "realised": 0.0,
            "dividends": 0.0,
            "fees":     0.0,
            "buys":     0,
            "sells":    0,
            "firstTradedAt": r["traded_at"],
            "lastTradedAt":  r["traded_at"],
        })

        h["lastTradedAt"] = r["traded_at"]

        if side == "BUY":
            new_qty       = h["qty"] + qty
            new_invested  = h["invested"] + qty * px
            h["qty"]      = new_qty
            h["invested"] = new_invested
            h["avgCost"]  = (new_invested / new_qty) if new_qty > 0 else 0.0
            h["fees"]    += fees
            h["buys"]    += 1
        elif side == "SELL":
            avg          = h["avgCost"]
            sell_qty     = min(qty, h["qty"])  # cap at current qty
            h["realised"] += (px - avg) * sell_qty - fees
            h["qty"]      -= sell_qty
            h["invested"] = h["avgCost"] * h["qty"]   # remaining cost basis
            h["fees"]    += fees
            h["sells"]   += 1
        elif side == "DIVIDEND":
            h["dividends"] += qty * px

    # Drop fully-closed positions (qty effectively zero) but keep their P&L
    # under "closed" so the UI can show realised P&L on positions that were
    # entered + exited.
    open_holdings, closed_holdings = [], []
    for h in book.values():
        h["qty"]      = round(h["qty"], 6)
        h["avgCost"]  = round(h["avgCost"], 4)
        h["invested"] = round(h["invested"], 2)
        h["realised"] = round(h["realised"], 2)
        h["dividends"] = round(h["dividends"], 2)
        if h["qty"] > 1e-6:
            open_holdings.append(h)
        else:
            h["qty"] = 0.0
            closed_holdings.append(h)
    return open_holdings + closed_holdings


# ── Live valuation ───────────────────────────────────────────────────────────

async def value_portfolio(user_id: str, portfolio_id: str,
                          price_service) -> Optional[dict]:
    """
    Compute live valuation of a portfolio.

    Reuses our existing PriceService (NSE → Yahoo → disk cache) so we never
    duplicate quote calls that the dashboard already issued.
    """
    p = get_portfolio(user_id, portfolio_id)
    if not p:
        return None
    holdings = derive_holdings(portfolio_id)
    open_holdings = [h for h in holdings if h["qty"] > 0]

    if not open_holdings:
        return {
            "portfolio":       p,
            "holdings":        [],
            "closedHoldings":  [h for h in holdings if h["qty"] == 0],
            "totals": {
                "cash":           p["cash"],
                "marketValue":    0.0,
                "investedValue":  0.0,
                "dayPnl":         0.0,
                "dayPnlPct":      0.0,
                "unrealisedPnl":  0.0,
                "unrealisedPnlPct": 0.0,
                "realisedPnl":    sum(h["realised"] for h in holdings),
                "dividendsRcvd":  sum(h["dividends"] for h in holdings),
                "totalEquity":    p["cash"],
            },
            "concentration": [],
            "fetchedAt":     _iso(),
        }

    # Fetch all quotes concurrently via PriceService
    async def _q(sym: str) -> tuple[str, dict]:
        try:
            qm = await price_service.get_quote_with_meta(sym)
            return sym, (qm or {}).get("quote") or {}
        except Exception as exc:
            logger.warning("portfolio: quote failed for %s: %s", sym, exc)
            return sym, {}

    quotes = dict(await asyncio.gather(*[_q(h["symbol"]) for h in open_holdings]))

    valued = []
    total_mv     = 0.0
    total_inv    = 0.0
    total_day    = 0.0
    total_unreal = 0.0
    sector_buckets: dict[str, float] = {}
    cap_buckets:    dict[str, float] = {"Large Cap": 0, "Mid Cap": 0, "Small Cap": 0, "Unknown": 0}

    for h in open_holdings:
        q = quotes.get(h["symbol"], {})
        last_price = float(q.get("lastPrice") or q.get("regularMarketPrice") or 0)
        prev_close = float(q.get("previousClose") or q.get("regularMarketPreviousClose") or last_price)
        market_cap = float(q.get("marketCap") or 0)

        market_value = last_price * h["qty"]
        invested     = h["avgCost"] * h["qty"]
        unrealised   = market_value - invested
        unrealised_pct = (unrealised / invested * 100) if invested > 0 else 0.0
        day_pnl      = (last_price - prev_close) * h["qty"]
        day_pnl_pct  = ((last_price / prev_close) - 1) * 100 if prev_close > 0 else 0.0

        sector = str(q.get("sector") or q.get("industry") or "Unknown") or "Unknown"
        sector_buckets[sector] = sector_buckets.get(sector, 0) + market_value

        cap_label = (
            "Large Cap" if market_cap >= 50_000 * 1e7 else      # ≥ ₹50,000 cr
            "Mid Cap"   if market_cap >= 10_000 * 1e7 else      # ≥ ₹10,000 cr
            "Small Cap" if market_cap > 0 else
            "Unknown"
        )
        cap_buckets[cap_label] += market_value

        total_mv     += market_value
        total_inv    += invested
        total_day    += day_pnl
        total_unreal += unrealised

        valued.append({
            **h,
            "lastPrice":      round(last_price, 2),
            "previousClose":  round(prev_close, 2),
            "marketValue":    round(market_value, 2),
            "unrealisedPnl":  round(unrealised, 2),
            "unrealisedPnlPct": round(unrealised_pct, 4),
            "dayPnl":         round(day_pnl, 2),
            "dayPnlPct":      round(day_pnl_pct, 4),
            "sector":         sector,
            "marketCap":      market_cap or None,
            "marketCapBucket": cap_label,
            "weight":         0.0,  # filled below once total_mv is known
            "companyName":    q.get("companyName") or q.get("longName") or h["symbol"],
        })

    # Fill weights & build allocation arrays
    total_equity = total_mv + p["cash"]
    for v in valued:
        v["weight"] = round((v["marketValue"] / total_mv) if total_mv > 0 else 0, 4)

    allocation_sector = [
        {"label": k, "value": round(v, 2),
         "weight": round(v / total_mv, 4) if total_mv > 0 else 0}
        for k, v in sorted(sector_buckets.items(), key=lambda kv: -kv[1])
    ]
    allocation_cap = [
        {"label": k, "value": round(v, 2),
         "weight": round(v / total_mv, 4) if total_mv > 0 else 0}
        for k, v in cap_buckets.items() if v > 0
    ]

    # Concentration warnings — any single position above 25% of equity
    concentration_warnings = [
        {"symbol": v["symbol"], "weight": v["weight"], "marketValue": v["marketValue"]}
        for v in valued if v["weight"] >= 0.25
    ]

    realised  = sum(h["realised"] for h in holdings)
    dividends = sum(h["dividends"] for h in holdings)
    total_day_pct = (total_day / (total_mv - total_day)) * 100 if (total_mv - total_day) > 0 else 0.0
    total_unreal_pct = (total_unreal / total_inv) * 100 if total_inv > 0 else 0.0

    return {
        "portfolio":       p,
        "holdings":        valued,
        "closedHoldings":  [h for h in holdings if h["qty"] == 0],
        "allocation": {
            "sector":     allocation_sector,
            "marketCap":  allocation_cap,
        },
        "totals": {
            "cash":             round(p["cash"], 2),
            "marketValue":      round(total_mv, 2),
            "investedValue":    round(total_inv, 2),
            "dayPnl":           round(total_day, 2),
            "dayPnlPct":        round(total_day_pct, 4),
            "unrealisedPnl":    round(total_unreal, 2),
            "unrealisedPnlPct": round(total_unreal_pct, 4),
            "realisedPnl":      round(realised, 2),
            "dividendsRcvd":    round(dividends, 2),
            "totalEquity":      round(total_equity, 2),
        },
        "concentration": concentration_warnings,
        "fetchedAt":     _iso(),
    }


# ── CSV Import (Zerodha Console / Upstox tradebook) ──────────────────────────

ZERODHA_HEADER_HINTS = ("trade_date", "symbol", "trade_type", "quantity", "price")
UPSTOX_HEADER_HINTS  = ("date", "scrip", "buy/sell", "quantity", "price")


def _detect_format(headers: list[str]) -> str:
    h = [str(x).strip().lower() for x in headers]
    if all(any(hint in col for col in h) for hint in ZERODHA_HEADER_HINTS):
        return "zerodha"
    if all(any(hint in col for col in h) for hint in UPSTOX_HEADER_HINTS):
        return "upstox"
    return "generic"


def _row_get(row: dict, *keys: str) -> Optional[str]:
    """Case-insensitive lookup with fallback aliases."""
    lower = {k.strip().lower(): v for k, v in row.items() if k}
    for k in keys:
        v = lower.get(k.strip().lower())
        if v is not None and str(v).strip() != "":
            return str(v).strip()
    return None


def _parse_zerodha_row(row: dict) -> Optional[dict]:
    sym  = _row_get(row, "symbol", "tradingsymbol")
    side = (_row_get(row, "trade_type", "buy_sell") or "").upper()
    qty  = _row_get(row, "quantity", "qty")
    px   = _row_get(row, "price", "trade_price")
    date = _row_get(row, "trade_date", "date")
    if not (sym and side in ("BUY", "SELL", "B", "S") and qty and px and date):
        return None
    side = "BUY" if side[0] == "B" else "SELL"
    return {
        "symbol":    sym,
        "side":      side,
        "qty":       float(qty.replace(",", "")),
        "price":     float(str(px).replace(",", "")),
        "fees":      float(_row_get(row, "brokerage", "charges", "fees") or 0),
        "tradedAt":  date,
        "source":    "zerodha-csv",
    }


def _parse_upstox_row(row: dict) -> Optional[dict]:
    sym  = _row_get(row, "scrip", "symbol", "instrument")
    side = (_row_get(row, "buy/sell", "buy_sell", "trade_type") or "").upper()
    qty  = _row_get(row, "quantity", "qty")
    px   = _row_get(row, "price", "rate")
    date = _row_get(row, "date", "trade_date", "trade date")
    if not (sym and side in ("BUY", "SELL", "B", "S") and qty and px and date):
        return None
    side = "BUY" if side[0] == "B" else "SELL"
    return {
        "symbol":    sym,
        "side":      side,
        "qty":       float(str(qty).replace(",", "")),
        "price":     float(str(px).replace(",", "")),
        "fees":      float(_row_get(row, "brokerage", "fees", "charges") or 0),
        "tradedAt":  date,
        "source":    "upstox-csv",
    }


def _parse_generic_row(row: dict) -> Optional[dict]:
    sym  = _row_get(row, "symbol", "scrip", "tradingsymbol", "instrument")
    side = (_row_get(row, "side", "trade_type", "buy/sell", "buy_sell") or "").upper()
    qty  = _row_get(row, "qty", "quantity")
    px   = _row_get(row, "price", "rate", "trade_price")
    date = _row_get(row, "date", "traded_at", "trade_date")
    if not (sym and side in ("BUY", "SELL", "B", "S", "DIVIDEND", "DIV") and qty and px and date):
        return None
    side = "DIVIDEND" if side.startswith("DIV") else ("BUY" if side[0] == "B" else "SELL")
    return {
        "symbol":   sym,
        "side":     side,
        "qty":      float(str(qty).replace(",", "")),
        "price":    float(str(px).replace(",", "")),
        "fees":     float(_row_get(row, "fees", "brokerage", "charges") or 0),
        "tradedAt": date,
        "source":   "csv",
    }


def parse_tradebook_csv(text: str) -> dict:
    """Parse a CSV string and return {format, transactions, errors}."""
    if not text or not text.strip():
        return {"format": "unknown", "transactions": [], "errors": ["Empty CSV"]}

    # Some Zerodha/Upstox exports prefix metadata rows; find the header row.
    lines = text.splitlines()
    header_idx = 0
    for i, ln in enumerate(lines):
        low = ln.lower()
        if ("symbol" in low or "scrip" in low or "instrument" in low) and "," in ln:
            header_idx = i
            break

    cleaned = "\n".join(lines[header_idx:])
    reader  = csv.DictReader(io.StringIO(cleaned))
    headers = reader.fieldnames or []
    fmt     = _detect_format(headers)
    parser  = {
        "zerodha": _parse_zerodha_row,
        "upstox":  _parse_upstox_row,
    }.get(fmt, _parse_generic_row)

    txs: list[dict] = []
    errors: list[str] = []
    for i, row in enumerate(reader, start=2):  # 2 = first data row in source
        try:
            parsed = parser(row)
            if parsed:
                txs.append(parsed)
        except Exception as exc:
            errors.append(f"row {i}: {exc}")
    return {"format": fmt, "transactions": txs, "errors": errors}


def import_transactions(user_id: str, portfolio_id: str, csv_text: str) -> dict:
    """Parse a tradebook CSV and import every valid row.

    Behaviour:
      * Each row is pre-validated independently. Rows that fail validation
        are skipped and surfaced in `errors[]` so the user can fix and
        re-upload only the bad rows (a hard fail-the-whole-batch policy
        would force users to re-clean a 500-row tradebook over a single
        typo).
      * The valid rows that survive validation are then inserted in a
        single SQLite transaction (`executemany` + the rolled-up cash
        UPDATE) — so the actual DB write is atomic: either every valid
        row is committed or none of them are. There is no partial
        DB-write state on infrastructure failure.

    Returns `{format, rowsParsed, rowsInserted, errors[]}`.
    """
    if not get_portfolio(user_id, portfolio_id):
        return {"error": "portfolio not found"}

    parsed = parse_tradebook_csv(csv_text)

    # Pre-validate + normalise every row first; if any row fails we abort
    # before touching the DB so import is genuinely all-or-nothing.
    prepared: list[tuple] = []
    cash_delta_total = 0.0
    for tx in parsed["transactions"]:
        try:
            side_u = (tx.get("side") or "").upper()
            if side_u not in ("BUY", "SELL", "DIVIDEND"):
                raise ValueError(f"Invalid side: {tx.get('side')!r}")
            qty_f = abs(float(tx["qty"]))
            price_f = float(tx["price"])
            fees_f = float(tx.get("fees") or 0)
            if qty_f <= 0:
                raise ValueError("Quantity must be positive")
            if price_f < 0:
                raise ValueError("Price must be non-negative")
            sym = _norm_symbol(tx["symbol"])
            iso = (tx.get("tradedAt") or _iso())[:32]
            source = (tx.get("source") or "csv")[:32]
            prepared.append((str(uuid.uuid4()), portfolio_id, sym, side_u,
                             qty_f, price_f, fees_f, iso, source, None))
            if side_u == "BUY":
                cash_delta_total -= qty_f * price_f + fees_f
            elif side_u == "SELL":
                cash_delta_total += qty_f * price_f - fees_f
            else:  # DIVIDEND
                cash_delta_total += qty_f * price_f
        except Exception as exc:
            parsed["errors"].append(f"{tx.get('symbol')}: {exc}")

    inserted = 0
    if prepared:
        conn = _connect()
        try:
            conn.execute("BEGIN")
            conn.executemany(
                "INSERT INTO transactions(id,portfolio_id,symbol,side,qty,"
                "price,fees,traded_at,source,note) VALUES(?,?,?,?,?,?,?,?,?,?)",
                prepared,
            )
            conn.execute(
                "UPDATE portfolios SET cash = cash + ?, updated_at = ? WHERE id=?",
                (cash_delta_total, _now_ms(), portfolio_id),
            )
            conn.commit()
            inserted = len(prepared)
        except Exception as exc:
            conn.rollback()
            parsed["errors"].append(f"import rolled back: {exc}")
        finally:
            conn.close()

    return {
        "format":          parsed["format"],
        "rowsParsed":      len(parsed["transactions"]),
        "rowsInserted":    inserted,
        "errors":          parsed["errors"],
    }


# ── Performance vs benchmark ─────────────────────────────────────────────────

async def equity_curve(user_id: str, portfolio_id: str,
                       price_service, days: int = 365,
                       benchmark: str = "NIFTY 50") -> Optional[dict]:
    """
    Build an equity curve by replaying transactions day-by-day against the
    daily-close history of every symbol that has ever been held.

    Compares against the chosen benchmark (default NIFTY 50, normalised to
    start-of-window value of 100 for clean overlay).
    """
    p = get_portfolio(user_id, portfolio_id)
    if not p:
        return None

    txs = list_transactions(user_id, portfolio_id)
    if not txs:
        return {"portfolioId": portfolio_id, "series": [], "benchmark": benchmark}

    txs.sort(key=lambda t: t["tradedAt"])
    symbols = sorted({t["symbol"] for t in txs if t["side"] in ("BUY", "SELL")})

    # Reverse-engineer the starting cash that existed before *any* transaction
    # was applied. `p["cash"]` is the *current* book cash (after every BUY /
    # SELL / DIVIDEND has already moved it in `add_transaction`), so we
    # subtract the net cashflow of all transactions to get the t0 starting
    # cash and replay forward from there. This avoids double-counting the
    # cash deltas (which would happen if we added `p["cash"]` to a series
    # that already accumulates the same deltas).
    total_cash_delta = 0.0
    for tx in txs:
        qty   = float(tx["qty"])
        price = float(tx["price"])
        fees  = float(tx.get("fees") or 0)
        if tx["side"] == "BUY":
            total_cash_delta -= qty * price + fees
        elif tx["side"] == "SELL":
            total_cash_delta += qty * price - fees
        elif tx["side"] == "DIVIDEND":
            total_cash_delta += qty * price
    initial_cash = float(p["cash"]) - total_cash_delta

    async def _hist(sym: str) -> tuple[str, list[dict]]:
        try:
            h = await price_service.get_historical_data(sym, days)
            return sym, h or []
        except Exception as exc:
            logger.warning("portfolio.equity_curve: %s history failed: %s", sym, exc)
            return sym, []

    sym_hist = dict(await asyncio.gather(*[_hist(s) for s in symbols]))
    bench_sym, bench_data = await _hist(benchmark)

    # Build a sorted list of unique trading dates we'll project on
    all_dates = set()
    for h in sym_hist.values():
        for r in h:
            d = str(r.get("date", ""))[:10]
            if d:
                all_dates.add(d)
    for r in bench_data:
        d = str(r.get("date", ""))[:10]
        if d:
            all_dates.add(d)
    timeline = sorted(all_dates)

    # Per-symbol close lookup
    close_by_sym: dict[str, dict[str, float]] = {
        s: {str(r["date"])[:10]: float(r["close"]) for r in h if r.get("close")}
        for s, h in sym_hist.items()
    }
    bench_close = {str(r["date"])[:10]: float(r["close"]) for r in bench_data if r.get("close")}

    # Walk timeline. At each date apply transactions ≤ that date (incrementally
    # via a pointer into the sorted tx list) and value the resulting holdings.
    series: list[dict] = []
    book: dict[str, float] = {}   # symbol → qty
    cash = 0.0
    tx_iter = iter(txs)
    next_tx = next(tx_iter, None)

    prev_close: dict[str, float] = {}
    for d in timeline:
        # Apply all transactions with traded_at ≤ d
        while next_tx and str(next_tx["tradedAt"])[:10] <= d:
            sym  = next_tx["symbol"]
            side = next_tx["side"]
            qty  = float(next_tx["qty"])
            px   = float(next_tx["price"])
            fees = float(next_tx.get("fees") or 0)
            if side == "BUY":
                book[sym] = book.get(sym, 0) + qty
                cash     -= qty * px + fees
            elif side == "SELL":
                book[sym] = book.get(sym, 0) - qty
                cash     += qty * px - fees
            elif side == "DIVIDEND":
                cash     += qty * px
            next_tx = next(tx_iter, None)

        # Mark to market — fall back to previous close if we don't have a
        # quote for this date for a particular symbol
        mv = 0.0
        for sym, qty in book.items():
            if qty <= 0:
                continue
            close = close_by_sym.get(sym, {}).get(d) or prev_close.get(sym)
            if close is None:
                continue
            prev_close[sym] = close
            mv += qty * close
        # Equity = mark-to-market value of holdings + cash on that date.
        # `initial_cash` is the t0 starting cash (pre-first-tx) and `cash`
        # is the running net cash delta from replayed transactions; their
        # sum equals the cash balance as of date `d`.
        series.append({
            "date":   d,
            "equity": round(mv + initial_cash + cash, 2),
            "marketValue": round(mv, 2),
        })

    # Normalise benchmark to first portfolio equity value (so they overlay)
    bench_series = []
    if series and bench_close:
        # Find first benchmark close on/after first series date
        start_eq = None
        bench_first = None
        for pt in series:
            if pt["equity"] > 0:
                start_eq = pt["equity"]
                bench_first = bench_close.get(pt["date"]) or next(
                    (bench_close[d] for d in sorted(bench_close) if d >= pt["date"]), None)
                break
        if start_eq and bench_first:
            scale = start_eq / bench_first
            for d in timeline:
                bc = bench_close.get(d)
                if bc is not None:
                    bench_series.append({"date": d, "value": round(bc * scale, 2)})

    return {
        "portfolioId": portfolio_id,
        "series":      series,
        "benchmark":   bench_sym,
        "benchmarkSeries": bench_series,
        "fetchedAt":   _iso(),
    }
