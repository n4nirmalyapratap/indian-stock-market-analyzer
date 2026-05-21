"""
Portfolio routes — `/api/portfolio/*`

  GET    /api/portfolio                                 — list user's portfolios
  POST   /api/portfolio                                 — create a portfolio
  GET    /api/portfolio/{pid}                           — portfolio meta
  PUT    /api/portfolio/{pid}                           — rename / update cash
  DELETE /api/portfolio/{pid}                           — delete a portfolio

  GET    /api/portfolio/{pid}/valuation                 — live MV, P&L, allocation
  GET    /api/portfolio/{pid}/transactions              — list transactions
  POST   /api/portfolio/{pid}/transactions              — add a transaction
  DELETE /api/portfolio/{pid}/transactions/{tx_id}      — delete a transaction
  POST   /api/portfolio/{pid}/import                    — import Zerodha/Upstox CSV

  GET    /api/portfolio/{pid}/risk                      — VaR / CVaR / Sharpe / Sortino / max-DD
  GET    /api/portfolio/{pid}/performance               — equity curve vs benchmark
  POST   /api/portfolio/{pid}/optimize                  — Markowitz / CVaR + rebalance trades
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Request, Body, UploadFile, File
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..services import portfolio_service as ps
from ..services import portfolio_optimizer_service as opt
from ..services import hydra_var_service as hv
from ..services.nse_service import NseService
from ..services.yahoo_service import YahooService
from ..services.price_service import PriceService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/portfolio", tags=["portfolio"])

_nse   = NseService()
_yahoo = YahooService()
_price = PriceService(_nse, _yahoo)


def _user_id(request: Request) -> str:
    """Return the authenticated user_id from middleware, or raise 401.

    Falling back to a literal "anonymous" string would put every unauthed
    caller into the same shared portfolio bucket — a cross-tenant data leak
    if any /api/portfolio/* path ever escapes the auth middleware.
    """
    from fastapi import HTTPException
    uid = getattr(request.state, "user_id", None)
    if not uid:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return uid


# ── Pydantic input schemas ───────────────────────────────────────────────────

class CreatePortfolioReq(BaseModel):
    name:         str
    cash:         float = 0.0
    baseCurrency: str   = "INR"


class UpdatePortfolioReq(BaseModel):
    name: Optional[str]   = None
    cash: Optional[float] = None


class TxReq(BaseModel):
    symbol:   str
    side:     str
    qty:      float
    price:    float
    fees:     float = 0.0
    tradedAt: Optional[str] = None
    note:     Optional[str] = None


class ImportReq(BaseModel):
    # Cap the in-body CSV at ~10 MB so a giant string can't OOM the worker.
    # A human tradebook is well under 1 MB.
    csv: str = Field(..., max_length=10 * 1024 * 1024)


class OptimizeReq(BaseModel):
    method:        str   = "markowitz"  # 'markowitz' | 'cvar' | 'min_vol'
    confidence:    float = 0.95
    riskFreeRate:  float = 0.07
    # Cap to 200 extra symbols — enough for a watchlist, prevents O(n²)
    # covariance from stalling the worker on attacker-controlled lists.
    universe:      Optional[list[str]] = Field(default=None, max_length=200)
    points:        int   = 25
    targetWeights: Optional[dict[str, float]] = None  # if user already chose


class RiskReq(BaseModel):
    confidence:    float = 0.95
    horizonDays:   int   = 1
    riskFreeRate:  float = 0.07
    lookbackDays:  int   = 365


# ── Portfolio CRUD ───────────────────────────────────────────────────────────

@router.get("")
async def list_portfolios(request: Request):
    return {"portfolios": ps.list_portfolios(_user_id(request))}


@router.post("")
async def create_portfolio(req: CreatePortfolioReq, request: Request):
    p = ps.create_portfolio(_user_id(request), req.name, req.cash, req.baseCurrency)
    return p


@router.get("/{pid}")
async def get_portfolio(pid: str, request: Request):
    p = ps.get_portfolio(_user_id(request), pid)
    if not p:
        return JSONResponse(status_code=404, content={"error": "portfolio not found"})
    return p


@router.put("/{pid}")
async def update_portfolio(pid: str, req: UpdatePortfolioReq, request: Request):
    p = ps.update_portfolio(_user_id(request), pid, name=req.name, cash=req.cash)
    if not p:
        return JSONResponse(status_code=404, content={"error": "portfolio not found"})
    return p


@router.delete("/{pid}")
async def delete_portfolio(pid: str, request: Request):
    if not ps.delete_portfolio(_user_id(request), pid):
        return JSONResponse(status_code=404, content={"error": "portfolio not found"})
    return {"success": True, "id": pid}


# ── Transactions ─────────────────────────────────────────────────────────────

@router.get("/{pid}/transactions")
async def list_transactions(pid: str, request: Request, symbol: Optional[str] = None):
    if not ps.get_portfolio(_user_id(request), pid):
        return JSONResponse(status_code=404, content={"error": "portfolio not found"})
    return {"transactions": ps.list_transactions(_user_id(request), pid, symbol)}


@router.post("/{pid}/transactions")
async def add_transaction(pid: str, req: TxReq, request: Request):
    try:
        tx = ps.add_transaction(
            _user_id(request), pid,
            symbol=req.symbol, side=req.side, qty=req.qty, price=req.price,
            fees=req.fees, traded_at=req.tradedAt, note=req.note,
        )
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    if tx is None:
        return JSONResponse(status_code=404, content={"error": "portfolio not found"})
    return tx


@router.delete("/{pid}/transactions/{tx_id}")
async def delete_transaction(pid: str, tx_id: str, request: Request):
    if not ps.delete_transaction(_user_id(request), pid, tx_id):
        return JSONResponse(status_code=404, content={"error": "transaction not found"})
    return {"success": True, "id": tx_id}


class BulkDeleteTxBody(BaseModel):
    """Body for the portfolio transaction bulk-delete endpoint. Capped at
    500 ids — well over any human-scale tradebook clean-up batch."""
    ids: list[str] = Field(..., min_length=1, max_length=500)


@router.post("/{pid}/transactions/bulk-delete")
async def delete_transactions_bulk(pid: str, body: BulkDeleteTxBody, request: Request):
    """Delete many transactions in one shot and roll back their cash
    impact atomically. Useful for undoing a bad CSV import. We POST (not
    DELETE) because DELETE-with-body has shaky proxy support."""
    res = ps.delete_transactions_bulk(_user_id(request), pid, body.ids)
    if res.get("error"):
        return JSONResponse(status_code=404, content=res)
    return {"requested": len(body.ids), **res}


# ── Capital-gains tax report ─────────────────────────────────────────────────

@router.get("/{pid}/tax-report")
async def get_tax_report(
    pid: str,
    request: Request,
    fy: str = "",
):
    """Build the FIFO-matched capital-gains report for a financial year.

    Query params:
        fy — Indian FY string like "2024-25". If omitted, defaults to the
             FY that's currently in progress in IST (April-to-March).

    Response: see tax_report_service.compute_report.
    """
    from ..services import tax_report_service as trs  # noqa: PLC0415
    uid = _user_id(request)
    if not fy:
        # Default to the in-progress FY (April-to-March in IST).
        import datetime as _dt
        from datetime import timezone as _tz, timedelta as _td
        now_ist = _dt.datetime.now(tz=_tz(_td(hours=5, minutes=30)))
        start_year = now_ist.year if now_ist.month >= 4 else now_ist.year - 1
        fy = f"{start_year}-{str(start_year + 1)[-2:]}"
    try:
        return trs.compute_report(uid, pid, fy)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{pid}/tax-report/fys")
async def list_tax_fys(pid: str, request: Request):
    """List every FY that has at least one transaction in this portfolio,
    newest first. Powers the FY selector on the frontend."""
    from ..services import tax_report_service as trs  # noqa: PLC0415
    return {"fys": trs.list_available_fys(_user_id(request), pid)}


@router.get("/{pid}/tax-report.csv")
async def get_tax_report_csv(
    pid: str,
    request: Request,
    fy: str = "",
):
    """Download the report as CSV. Filename includes the FY so the user
    can save multiple years without overwriting."""
    from fastapi.responses import PlainTextResponse  # noqa: PLC0415
    from ..services import tax_report_service as trs  # noqa: PLC0415
    uid = _user_id(request)
    if not fy:
        import datetime as _dt
        from datetime import timezone as _tz, timedelta as _td
        now_ist = _dt.datetime.now(tz=_tz(_td(hours=5, minutes=30)))
        start_year = now_ist.year if now_ist.month >= 4 else now_ist.year - 1
        fy = f"{start_year}-{str(start_year + 1)[-2:]}"
    try:
        report = trs.compute_report(uid, pid, fy)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if "error" in report:
        raise HTTPException(status_code=404, detail=report["error"])
    csv_text = trs.to_csv(report)
    safe_fy = fy.replace("/", "-")
    return PlainTextResponse(
        content=csv_text,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="tax-report-{safe_fy}.csv"',
        },
    )


@router.post("/{pid}/import")
async def import_csv(pid: str, req: ImportReq, request: Request):
    res = ps.import_transactions(_user_id(request), pid, req.csv)
    if res.get("error"):
        return JSONResponse(status_code=404, content=res)
    return res


@router.post("/{pid}/import-file")
async def import_file(pid: str, request: Request, file: UploadFile = File(...)):
    """Upload a tradebook as a file — accepts .csv or .xlsx.
    Excel workbooks are flattened to CSV (first sheet only) before parsing
    so the same column conventions apply (Zerodha / Upstox / generic
    symbol,side,qty,price,date)."""
    # Cap the upload at 10 MB to prevent memory-exhaustion DoS. A real
    # tradebook for a human is well under 1 MB even after years of trading.
    _MAX_UPLOAD_BYTES = 10 * 1024 * 1024
    raw = await file.read(_MAX_UPLOAD_BYTES + 1)
    if not raw:
        return JSONResponse(status_code=400, content={"error": "Empty file"})
    if len(raw) > _MAX_UPLOAD_BYTES:
        return JSONResponse(
            status_code=413,
            content={"error": f"File too large (>{_MAX_UPLOAD_BYTES // (1024 * 1024)} MB)."},
        )
    name = (file.filename or "").lower()
    try:
        if name.endswith(".xlsx") or name.endswith(".xlsm"):
            csv_text = ps.xlsx_bytes_to_csv(raw)
        elif name.endswith(".csv") or name.endswith(".txt") or not name:
            csv_text = raw.decode("utf-8", errors="replace")
        else:
            return JSONResponse(status_code=400,
                content={"error": f"Unsupported file type: {file.filename!r}. "
                                  "Upload a .csv or .xlsx tradebook."})
    except Exception as exc:
        return JSONResponse(status_code=400,
            content={"error": f"Could not read file: {exc}"})
    res = ps.import_transactions(_user_id(request), pid, csv_text)
    if res.get("error"):
        return JSONResponse(status_code=404, content=res)
    res["source_filename"] = file.filename
    return res


# ── Vision-LLM import (broker screenshot) ────────────────────────────────────
# Two-step flow so the user can review/edit before any row hits the DB:
#   POST /{pid}/extract-from-image    — Vision model parses screenshot → preview
#   POST /{pid}/apply-extracted       — user-confirmed rows → real transactions

class ExtractedHolding(BaseModel):
    """A single row pulled out of a broker screenshot. Confidence is the
    model's own self-reported confidence in this row (0-1)."""
    symbol:     str   = Field(..., max_length=24)
    qty:        float = Field(..., gt=0)
    avgPrice:   float = Field(..., ge=0)
    confidence: float = Field(..., ge=0, le=1)
    rawName:    Optional[str] = Field(default=None, max_length=80)


class ApplyExtractedReq(BaseModel):
    """User-confirmed rows to commit as BUY transactions. Frontend only
    sends rows the user kept (un-checked rows are dropped)."""
    holdings: list[ExtractedHolding] = Field(..., min_length=1, max_length=200)
    tradedAt: Optional[str] = Field(default=None, max_length=32)
    source:   str = Field(default="screenshot", max_length=32)


@router.post("/{pid}/extract-from-image")
async def extract_from_image(
    pid: str,
    request: Request,
    file: UploadFile = File(...),
):
    """Extract holdings from an uploaded broker portfolio screenshot.

    Does NOT touch the database. Returns extracted rows + per-row confidence
    so the frontend can show a preview-and-confirm panel; the user picks
    which rows to keep and then POSTs them back to ``apply-extracted``.
    """
    # Verify portfolio belongs to caller before spending an AI call.
    uid = _user_id(request)
    if not ps.get_portfolio(uid, pid):
        return JSONResponse(status_code=404, content={"error": "portfolio not found"})

    # Cap at 5 MB — typical screenshots are under 500 KB; anything 5 MB+ is
    # either a screen recording dropped in by mistake or an attack.
    _MAX_IMAGE_BYTES = 5 * 1024 * 1024
    raw = await file.read(_MAX_IMAGE_BYTES + 1)
    if not raw:
        return JSONResponse(status_code=400, content={"error": "Empty file"})
    if len(raw) > _MAX_IMAGE_BYTES:
        return JSONResponse(
            status_code=413,
            content={"error": f"Image too large (>{_MAX_IMAGE_BYTES // (1024 * 1024)} MB)."},
        )

    # Detect MIME from filename + magic bytes. We only accept jpg/png/webp;
    # GIF / SVG / TIFF are rejected so we don't pass exotic formats to the
    # Vision API only to get back an empty response.
    name = (file.filename or "").lower()
    mime: Optional[str] = None
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        mime = "image/png"
    elif raw[:3] == b"\xff\xd8\xff" or name.endswith((".jpg", ".jpeg")):
        mime = "image/jpeg"
    elif raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        mime = "image/webp"
    elif name.endswith(".png"):
        mime = "image/png"
    elif name.endswith(".webp"):
        mime = "image/webp"
    if mime is None:
        return JSONResponse(
            status_code=400,
            content={"error": "Unsupported image format. Use JPG, PNG, or WebP."},
        )

    import base64 as _b64
    from ..services import ai_client  # noqa: PLC0415

    img_b64 = _b64.b64encode(raw).decode("ascii")
    prompt = _EXTRACT_PROMPT
    try:
        raw_response = await ai_client.ask_vision(
            prompt,
            image_b64=img_b64,
            image_mime=mime,
            system=_EXTRACT_SYSTEM,
            max_tokens=2048,
            temperature=0.1,
        )
    except Exception:
        logger.exception("extract_from_image: vision call failed")
        return JSONResponse(
            status_code=503,
            content={"error": "Vision model is temporarily unavailable; please retry."},
        )

    holdings = _parse_vision_response(raw_response)
    return {
        "filename":  file.filename,
        "rowsFound": len(holdings),
        "holdings":  holdings,
    }


@router.post("/{pid}/apply-extracted")
async def apply_extracted(pid: str, req: ApplyExtractedReq, request: Request):
    """Persist user-confirmed extracted rows as BUY transactions.

    Each row becomes a single BUY at the supplied avgPrice/qty. We don't
    invent a side/fees — broker screenshots show net holdings only. If the
    user wants the cash side to balance they can edit the portfolio cash
    afterwards.
    """
    uid = _user_id(request)
    if not ps.get_portfolio(uid, pid):
        return JSONResponse(status_code=404, content={"error": "portfolio not found"})

    inserted = 0
    errors: list[str] = []
    for h in req.holdings:
        try:
            ps.add_transaction(
                uid, pid,
                symbol   = h.symbol,
                side     = "BUY",
                qty      = h.qty,
                price    = h.avgPrice,
                fees     = 0.0,
                traded_at= req.tradedAt,
                source   = req.source,
                note     = f"from screenshot (confidence {h.confidence:.2f})",
            )
            inserted += 1
        except Exception as exc:
            errors.append(f"{h.symbol}: {exc}")

    return {
        "rowsApplied": inserted,
        "rowsRejected": len(req.holdings) - inserted,
        "errors": errors,
    }


# ── Vision prompt + response parser ──────────────────────────────────────────

_EXTRACT_SYSTEM = (
    "You are a careful data-extraction assistant. The user will upload a "
    "screenshot of their stock-broker holdings page (Zerodha Kite, Groww, "
    "Upstox, ICICI Direct, HDFC Securities, or any other Indian retail "
    "broker). Extract the holdings table as JSON. Be precise; do not "
    "invent rows. If a value is ambiguous lower the confidence."
)

_EXTRACT_PROMPT = (
    "Extract every holding row visible in this screenshot. For each row "
    "return:\n"
    "  - symbol     : NSE-style ticker (e.g. RELIANCE, TCS, HDFCBANK). Strip "
    "exchange suffixes like .NS / .BO / -EQ. If only a company name is shown, "
    "map it to the NSE ticker if obvious.\n"
    "  - qty        : positive number\n"
    "  - avgPrice   : the average buy price per share, in INR. Do NOT use the "
    "current market price.\n"
    "  - confidence : 0-1 self-reported confidence in this row. Penalise "
    "rows where the ticker mapping was guessed, the OCR was blurry, or the "
    "broker UI made columns ambiguous.\n"
    "  - rawName    : the exact company name as shown on screen (helpful for "
    "the user to verify)\n\n"
    "Respond with ONLY a JSON object of the form:\n"
    '  {"holdings": [{"symbol": "...", "qty": ..., "avgPrice": ..., '
    '"confidence": ..., "rawName": "..."}]}\n'
    "No prose, no markdown fences, no commentary. If the screenshot has no "
    "holdings table return {\"holdings\": []}."
)


def _parse_vision_response(text: str) -> list[dict]:
    """Best-effort parse of the vision model's response.

    Strips markdown fences, finds the first JSON object, and validates each
    row through the Pydantic schema. Bad rows are dropped silently — the
    frontend will surface the count rather than blowing up the whole call.
    """
    import json as _json
    import re as _re

    if not text:
        return []

    # Strip ```json ... ``` fences a model might still emit despite the prompt.
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = _re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = _re.sub(r"\s*```\s*$", "", cleaned)

    try:
        payload = _json.loads(cleaned)
    except Exception:
        # As a last resort, look for the outermost {...} block.
        match = _re.search(r"\{.*\}", cleaned, _re.DOTALL)
        if not match:
            return []
        try:
            payload = _json.loads(match.group(0))
        except Exception:
            return []

    rows = payload.get("holdings") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return []

    out: list[dict] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        try:
            validated = ExtractedHolding(
                symbol     = str(r.get("symbol") or "").strip().upper(),
                qty        = float(r.get("qty") or 0),
                avgPrice   = float(r.get("avgPrice") or 0),
                confidence = max(0.0, min(1.0, float(r.get("confidence") or 0))),
                rawName    = (str(r.get("rawName")).strip() if r.get("rawName") else None),
            )
        except Exception:
            continue
        out.append(validated.model_dump())
    return out


# ── Live valuation ───────────────────────────────────────────────────────────

@router.get("/{pid}/valuation")
async def get_valuation(pid: str, request: Request):
    val = await ps.value_portfolio(_user_id(request), pid, _price)
    if val is None:
        return JSONResponse(status_code=404, content={"error": "portfolio not found"})
    return val


# ── Risk metrics (VaR / CVaR / Sharpe / Sortino / max-DD) ────────────────────

@router.get("/{pid}/risk")
async def compute_risk_get(
    pid: str,
    request: Request,
    confidence: float = 0.95,
    horizonDays: int = 1,
    riskFreeRate: float = 0.07,
    lookbackDays: int = 365,
):
    """GET alias for /risk so consumers expecting REST-style GET semantics
    (per the original Phase-2 spec) can use query parameters instead of a
    POST body. Both endpoints return identical payloads."""
    return await compute_risk(pid, RiskReq(
        confidence=confidence, horizonDays=horizonDays,
        riskFreeRate=riskFreeRate, lookbackDays=lookbackDays,
    ), request)


@router.post("/{pid}/risk")
async def compute_risk(pid: str, req: RiskReq, request: Request):
    user_id = _user_id(request)
    val = await ps.value_portfolio(user_id, pid, _price)
    if val is None:
        return JSONResponse(status_code=404, content={"error": "portfolio not found"})
    holdings = val["holdings"]
    if not holdings:
        return {"error": "no open holdings"}

    # Pull daily history for every symbol
    import asyncio  # noqa: PLC0415
    syms = [h["symbol"] for h in holdings]
    weights = [h["weight"] for h in holdings]

    async def _hist(sym: str) -> tuple[str, list[float]]:
        try:
            data = await _price.get_historical_data(sym, req.lookbackDays)
            return sym, [float(d["close"]) for d in (data or []) if d.get("close")]
        except Exception as exc:
            logger.warning("portfolio.risk: %s history failed: %s", sym, exc)
            return sym, []

    results = dict(await asyncio.gather(*[_hist(s) for s in syms]))

    portfolio_value = float(val["totals"]["marketValue"]) or 1.0
    var = hv.portfolio_var(
        symbols=syms,
        closes_map=results,
        weights=weights,
        confidence=req.confidence,
        horizon_days=req.horizonDays,
        portfolio_value=portfolio_value,
    )

    # Per-position Sharpe / Sortino / max-DD
    per_position = []
    for h in holdings:
        closes = results.get(h["symbol"], [])
        sortino = hv.sortino_ratio(closes, risk_free_rate_annual=req.riskFreeRate)
        sharpe  = hv.sharpe_ratio(closes,  risk_free_rate_annual=req.riskFreeRate)
        dd      = hv.max_drawdown(closes)
        per_position.append({
            "symbol":   h["symbol"],
            "weight":   h["weight"],
            "sharpe":   sharpe.get("sharpe"),
            "sortino":  sortino.get("sortino"),
            "annualReturn":     sharpe.get("annualReturn"),
            "annualVolatility": sharpe.get("annualVolatility"),
            "maxDrawdownPct":   dd.get("maxDrawdownPct"),
        })

    # Portfolio-level Sortino + Sharpe + max-DD via the equity curve
    perf = await ps.equity_curve(user_id, pid, _price, days=req.lookbackDays)
    # Guard against equity=None on a gap day — `dict.get(k, 0)` returns the value
    # even when it's None, which would TypeError on `> 0`.
    equity_closes = [pt["equity"] for pt in (perf or {}).get("series", []) if (pt.get("equity") or 0) > 0] if perf else []
    pf_sharpe  = hv.sharpe_ratio(equity_closes,  risk_free_rate_annual=req.riskFreeRate) if equity_closes else {}
    pf_sortino = hv.sortino_ratio(equity_closes, risk_free_rate_annual=req.riskFreeRate) if equity_closes else {}
    pf_dd      = hv.max_drawdown(equity_closes) if equity_closes else {}

    return {
        "portfolioId":   pid,
        "totals":        val["totals"],
        "var":           var,
        "perPosition":   per_position,
        "portfolio": {
            "sharpe":         pf_sharpe.get("sharpe"),
            "sortino":        pf_sortino.get("sortino"),
            "annualReturn":   pf_sharpe.get("annualReturn"),
            "annualVolatility": pf_sharpe.get("annualVolatility"),
            "maxDrawdownPct": pf_dd.get("maxDrawdownPct"),
        },
        "fetchedAt":     val["fetchedAt"],
    }


# ── Performance vs benchmark ─────────────────────────────────────────────────

@router.get("/{pid}/performance")
async def performance(pid: str, request: Request, benchmark: str = "NIFTY 50",
                      days: int = 365):
    perf = await ps.equity_curve(_user_id(request), pid, _price,
                                 days=days, benchmark=benchmark)
    if perf is None:
        return JSONResponse(status_code=404, content={"error": "portfolio not found"})
    return perf


# ── Optimizer (Markowitz frontier + CVaR + rebalance trades) ─────────────────

@router.post("/{pid}/optimize")
async def optimize(pid: str, req: OptimizeReq, request: Request):
    user_id = _user_id(request)
    val = await ps.value_portfolio(user_id, pid, _price)
    if val is None:
        return JSONResponse(status_code=404, content={"error": "portfolio not found"})

    held_syms = [h["symbol"] for h in val["holdings"]]
    extra_syms = [s.upper().strip() for s in (req.universe or []) if s and s.strip()]
    universe   = sorted(set(held_syms + extra_syms))
    if len(universe) < 2:
        return JSONResponse(status_code=400, content={
            "error": "Need at least 2 symbols (current holdings + optional universe). "
                     "Add more positions or pass `universe` with extra tickers."})

    import asyncio  # noqa: PLC0415

    async def _hist(sym: str) -> tuple[str, list[float]]:
        try:
            data = await _price.get_historical_data(sym, 400)
            return sym, [float(d["close"]) for d in (data or []) if d.get("close")]
        except Exception as exc:
            logger.warning("portfolio.optimize: %s history failed: %s", sym, exc)
            return sym, []

    closes_map = dict(await asyncio.gather(*[_hist(s) for s in universe]))

    method = (req.method or "markowitz").lower()
    if method == "cvar":
        result = opt.cvar_optimal(universe, closes_map,
                                  confidence=req.confidence,
                                  rf_annual=req.riskFreeRate)
        # Bail out early on optimiser failure (insufficient history, solver
        # divergence, etc.) — otherwise an empty target-weights dict would
        # cause `rebalance_trades` to suggest selling every existing
        # position, which is an unsafe failure mode.
        if not req.targetWeights and (result.get("error") or not result.get("weights")):
            return JSONResponse(status_code=400, content=result)
        target_weights = (
            req.targetWeights
            if req.targetWeights else
            dict(zip(result["symbols"], result["weights"]))
        )
        frontier = None
    else:
        frontier = opt.efficient_frontier(universe, closes_map,
                                          points=req.points,
                                          rf_annual=req.riskFreeRate)
        if frontier.get("error"):
            return JSONResponse(status_code=400, content=frontier)
        # Use max-Sharpe by default; min-vol if method == 'min_vol'.
        chosen = frontier["minVol"] if method == "min_vol" else frontier["maxSharpe"]
        if not chosen:
            return JSONResponse(status_code=500,
                                content={"error": "Optimisation failed to converge"})
        target_weights = (
            req.targetWeights
            if req.targetWeights else
            dict(zip(frontier["symbols"], chosen["weights"]))
        )
        result = chosen

    # Build rebalance trades
    current_qty: dict[str, float] = {h["symbol"]: float(h["qty"]) for h in val["holdings"]}
    prices: dict[str, float] = {h["symbol"]: float(h.get("lastPrice") or 0) for h in val["holdings"]}
    # Add prices for symbols in target set that we don't currently hold
    for sym in target_weights.keys():
        if sym not in prices:
            closes = closes_map.get(sym, [])
            prices[sym] = float(closes[-1]) if closes else 0.0
            current_qty.setdefault(sym, 0.0)

    equity = float(val["totals"]["totalEquity"])
    trades = opt.rebalance_trades(
        target_weights=target_weights,
        current_qty=current_qty,
        prices=prices,
        equity=equity,
    )

    return {
        "portfolioId":   pid,
        "method":        method,
        "result":        result,
        "frontier":      frontier,
        "currentWeights": {h["symbol"]: h["weight"] for h in val["holdings"]},
        "targetWeights": {k: round(float(v), 4) for k, v in target_weights.items()},
        "trades":        trades,
        "equity":        equity,
        "universe":      universe,
        "fetchedAt":     val["fetchedAt"],
    }
