"""F&O analytics suite built on top of the existing options chain.

Six derived views are produced from one chain snapshot:

  1. Max Pain        — strike where option writers lose the least
  2. OI Buildup      — Long buildup / Short buildup / Long unwinding /
                       Short covering classification per strike+type
  3. PCR history     — handled by `_pcr_history`; this module exposes
                       the snapshot writer for the scheduler
  4. IV Smile        — implied vol across strikes (calls + puts curves)
  5. Unusual Activity — strikes where today's volume or OI-change is
                       statistically outsized (>=2σ above the chain mean)
  6. Strategy Heatmap — for each strike, the 1-leg / 2-leg strategy with
                       the best risk-reward right now

All functions are pure transformations of the chain dict shape that
`/api/options/chain/{symbol}` already returns:
    {"calls": [{strike, lastPrice, bid, ask, iv, oi, oiChange, volume,
                inTheMoney, change, pChange}, …],
     "puts":  [...same...]}
"""
from __future__ import annotations

import logging
from statistics import mean, pstdev
from typing import Optional

logger = logging.getLogger("options_analytics")


# ── 1. Max Pain ─────────────────────────────────────────────────────────────


def compute_max_pain(calls: list[dict], puts: list[dict]) -> dict:
    """Total dollar "pain" to option writers at each candidate strike.

    Definition: if spot settled exactly at strike K on expiry, every
    in-the-money option pays its intrinsic value × OI to the buyer.
    The "max pain strike" is K* that MINIMIZES this total payout —
    market lore says spot drifts toward K* on expiry day because
    that's where writers (typically banks/MMs) make the most money.

    Returns:
        {
          "maxPainStrike": float,
          "byStrike": [{ strike, callPain, putPain, totalPain }],
        }
    """
    strikes = sorted({c["strike"] for c in calls} | {p["strike"] for p in puts})
    if not strikes:
        return {"maxPainStrike": None, "byStrike": []}

    # Index strike → OI for fast lookup in the inner loop.
    call_oi = {c["strike"]: c.get("oi", 0) or 0 for c in calls}
    put_oi  = {p["strike"]: p.get("oi", 0) or 0 for p in puts}

    by_strike: list[dict] = []
    best_K, best_pain = strikes[0], float("inf")
    for K in strikes:
        # Calls: payout if spot=K is max(K - strike_of_call, 0).
        # Calls struck BELOW K are ITM and pay; calls above K are 0.
        call_pain = sum((K - s) * call_oi.get(s, 0) for s in strikes if s < K)
        # Puts: payout is max(strike_of_put - K, 0); puts ABOVE K pay.
        put_pain  = sum((s - K) * put_oi.get(s, 0)  for s in strikes if s > K)
        total = call_pain + put_pain
        by_strike.append({
            "strike":    K,
            "callPain":  round(call_pain, 2),
            "putPain":   round(put_pain, 2),
            "totalPain": round(total, 2),
        })
        if total < best_pain:
            best_pain = total
            best_K    = K

    return {"maxPainStrike": best_K, "byStrike": by_strike}


# ── 2. OI Buildup classification ────────────────────────────────────────────


def _classify_buildup(price_change: float, oi_change: float) -> str:
    """4-quadrant classification used by F&O traders.

    Conceptually: open interest rising means *new* positions are being
    created. Price up + OI up means new longs are entering — bullish.
    Price down + OI up means new shorts — bearish. Etc.

    The strings match standard NSE / Sensibull / Quantsapp terminology
    so they're instantly readable to anyone who's used a brokerage
    research desk.
    """
    if oi_change > 0 and price_change > 0:
        return "Long Buildup"
    if oi_change > 0 and price_change < 0:
        return "Short Buildup"
    if oi_change < 0 and price_change < 0:
        return "Long Unwinding"
    if oi_change < 0 and price_change > 0:
        return "Short Covering"
    return "Neutral"


def compute_oi_buildup(calls: list[dict], puts: list[dict]) -> dict:
    """Classify every strike+type by buildup pattern.

    Returns:
        {
          "calls": [{ strike, price, priceChange, oi, oiChange,
                      classification }],
          "puts":  [same shape],
        }
    """
    def _rows(side: list[dict]) -> list[dict]:
        out = []
        for r in side:
            price_chg = float(r.get("change") or 0)
            oi_chg    = float(r.get("oiChange") or 0)
            out.append({
                "strike":         r["strike"],
                "price":          r.get("lastPrice", 0),
                "priceChange":    price_chg,
                "oi":             r.get("oi", 0),
                "oiChange":       oi_chg,
                "classification": _classify_buildup(price_chg, oi_chg),
            })
        return out
    return {"calls": _rows(calls), "puts": _rows(puts)}


# ── 4. IV Smile / Skew ──────────────────────────────────────────────────────


def compute_iv_smile(calls: list[dict], puts: list[dict], spot: float) -> list[dict]:
    """One row per strike with call IV, put IV, and an ATM flag.

    The smile shape (curve of IV vs strike) tells you what the market
    is *implying* about future volatility — flat = boring, smiling =
    tail-risk-priced-in, skewed = directional bias (puts dearer means
    crash protection in demand).

    Returns oldest→newest sorted by strike, ready to feed recharts.
    """
    by_strike: dict[float, dict] = {}
    for c in calls:
        by_strike.setdefault(c["strike"], {"strike": c["strike"]})
        by_strike[c["strike"]]["callIV"] = float(c.get("iv") or 0) * 100
    for p in puts:
        by_strike.setdefault(p["strike"], {"strike": p["strike"]})
        by_strike[p["strike"]]["putIV"]  = float(p.get("iv") or 0) * 100

    strikes = sorted(by_strike)
    if not strikes:
        return []

    # Flag the closest strike to spot as ATM (only one true ATM).
    atm = min(strikes, key=lambda s: abs(s - spot)) if spot else None
    out = []
    for s in strikes:
        row = by_strike[s]
        out.append({
            "strike": s,
            "callIV": round(row.get("callIV", 0), 2) if row.get("callIV") else None,
            "putIV":  round(row.get("putIV",  0), 2) if row.get("putIV")  else None,
            "isATM":  s == atm,
        })
    return out


# ── 5. Unusual Activity scanner ─────────────────────────────────────────────


def _zscore(values: list[float], target: float) -> float:
    if not values or len(values) < 3:
        return 0.0
    mu = mean(values)
    sd = pstdev(values)
    if sd == 0:
        return 0.0
    return (target - mu) / sd


def compute_unusual_activity(
    calls: list[dict], puts: list[dict],
    volume_z_threshold: float = 2.0,
    oi_z_threshold:     float = 2.0,
) -> list[dict]:
    """Flag strikes where today's volume or OI-change is statistically
    outsized vs the rest of the chain.

    Without historical per-strike volume baselines we use a cross-
    sectional z-score: how many standard deviations is this strike's
    volume above the chain-wide mean? It's a crude proxy — a strike
    that's *always* heavily traded (e.g. weekly-ATM) gets flagged
    every day — but it's a useful "look here first" signal and it
    needs zero historical data.

    Returns a list sorted by descending volume z-score; each row has
    enough context to render a one-line "unusual activity" alert.
    """
    flagged: list[dict] = []

    for side_name, side in (("CE", calls), ("PE", puts)):
        volumes = [float(r.get("volume") or 0) for r in side]
        oi_chgs = [abs(float(r.get("oiChange") or 0)) for r in side]
        for r in side:
            vol = float(r.get("volume") or 0)
            oic = abs(float(r.get("oiChange") or 0))
            vz  = _zscore(volumes, vol)
            oz  = _zscore(oi_chgs, oic)
            if vz >= volume_z_threshold or oz >= oi_z_threshold:
                flagged.append({
                    "strike":      r["strike"],
                    "type":        side_name,
                    "volume":      int(vol),
                    "volumeZ":     round(vz, 2),
                    "oiChange":    int(r.get("oiChange") or 0),
                    "oiChangeZ":   round(oz, 2),
                    "lastPrice":   r.get("lastPrice"),
                    "iv":          round(float(r.get("iv") or 0) * 100, 2),
                    "reason":
                        "Volume" if vz >= volume_z_threshold and vz >= oz
                        else "OI change",
                })

    flagged.sort(key=lambda x: max(x["volumeZ"], x["oiChangeZ"]), reverse=True)
    return flagged[:20]  # top 20 most unusual — UI doesn't need a long tail


# ── 6. Strategy heatmap (per strike, best 1- or 2-leg setup) ────────────────
#
# We score four canonical strategies per strike. For each we compute
# (max_profit, max_loss) at expiry and pick the one with the best
# reward-to-risk ratio. The "best" is then displayed on a heatmap.
#
# Strategy formulas (per lot, ignoring premium-adjusted breakevens
# since the UI only needs a comparative score, not P&L curves):
#
#   Long Call            : max_profit = ∞ (cap at 5× premium for ranking)
#                          max_loss   = call_premium
#   Long Put             : max_profit = strike − put_premium  (cap)
#                          max_loss   = put_premium
#   Bull Call Spread     : pair this strike (long) with next-OTM (short)
#                          max_profit = (K2 − K1) − net_debit
#                          max_loss   = net_debit
#   Bear Put Spread      : pair this strike (long put) with next-OTM put (short)
#                          max_profit = (K1 − K2) − net_debit
#                          max_loss   = net_debit


def _strike_above(strikes: list[float], K: float) -> Optional[float]:
    """Smallest strike strictly greater than K, or None."""
    bigger = [s for s in strikes if s > K]
    return bigger[0] if bigger else None


def _strike_below(strikes: list[float], K: float) -> Optional[float]:
    bigger = [s for s in strikes if s < K]
    return bigger[-1] if bigger else None


def _rr(profit: float, loss: float) -> float:
    """Reward/risk. Higher is better. Cap at 99 so naked longs with
    tiny premium don't dominate the heatmap visually."""
    if loss <= 0:
        return 0.0
    return min(99.0, profit / loss)


def compute_strategy_heatmap(
    calls: list[dict], puts: list[dict], spot: float,
) -> list[dict]:
    """For each strike, score the four canonical strategies and surface
    the one with the best risk-reward ratio. Returns ready-to-render
    rows for the heatmap.
    """
    call_by_strike = {c["strike"]: c for c in calls}
    put_by_strike  = {p["strike"]: p for p in puts}
    strikes        = sorted(set(call_by_strike) | set(put_by_strike))
    if not strikes:
        return []

    out: list[dict] = []
    for K in strikes:
        cp = call_by_strike.get(K, {})
        pp = put_by_strike.get(K, {})
        call_prem = float(cp.get("lastPrice") or 0)
        put_prem  = float(pp.get("lastPrice") or 0)

        scores: list[tuple[str, float, float, float]] = []
        # (label, max_profit, max_loss, rr)

        # 1. Long Call — cap profit at 5× premium for fair ranking.
        if call_prem > 0:
            mp = call_prem * 5
            scores.append(("Long Call", mp, call_prem, _rr(mp, call_prem)))

        # 2. Long Put
        if put_prem > 0:
            mp = put_prem * 5
            scores.append(("Long Put", mp, put_prem, _rr(mp, put_prem)))

        # 3. Bull Call Spread — long this strike, short next-higher.
        K_up = _strike_above(strikes, K)
        if K_up is not None:
            short_prem = float(call_by_strike.get(K_up, {}).get("lastPrice") or 0)
            if call_prem > 0 and short_prem > 0:
                debit = call_prem - short_prem
                if debit > 0:
                    width = K_up - K
                    mp = max(0.0, width - debit)
                    scores.append(("Bull Call Spread", mp, debit, _rr(mp, debit)))

        # 4. Bear Put Spread — long this strike (put), short next-lower (put).
        K_dn = _strike_below(strikes, K)
        if K_dn is not None:
            short_prem = float(put_by_strike.get(K_dn, {}).get("lastPrice") or 0)
            if put_prem > 0 and short_prem > 0:
                debit = put_prem - short_prem
                if debit > 0:
                    width = K - K_dn
                    mp = max(0.0, width - debit)
                    scores.append(("Bear Put Spread", mp, debit, _rr(mp, debit)))

        if not scores:
            out.append({
                "strike":    K,
                "best":      None,
                "rr":        0.0,
                "maxProfit": None,
                "maxLoss":   None,
                "moneyness": "ITM" if (spot and K < spot) else "OTM" if (spot and K > spot) else "ATM",
            })
            continue

        # Pick the strategy with highest rr score.
        scores.sort(key=lambda x: x[3], reverse=True)
        label, mp, ml, rr = scores[0]
        out.append({
            "strike":    K,
            "best":      label,
            "rr":        round(rr, 2),
            "maxProfit": round(mp, 2),
            "maxLoss":   round(ml, 2),
            "moneyness": "ATM" if spot and abs(K - spot) / spot < 0.005
                         else "ITM" if (spot and K < spot)
                         else "OTM",
        })
    return out


# ── Top-level aggregator ────────────────────────────────────────────────────


def compute_analytics(
    calls: list[dict], puts: list[dict], spot: float,
) -> dict:
    """Run every analytics pass on a single chain snapshot.

    The chain HTTP call (NSE / Yahoo / Dhan-BS) is the only expensive
    work; computing all six analyses below is microseconds. The route
    handler should call this once and return the full dict in a single
    response.
    """
    return {
        "maxPain":   compute_max_pain(calls, puts),
        "oiBuildup": compute_oi_buildup(calls, puts),
        "smile":     compute_iv_smile(calls, puts, spot),
        "unusual":   compute_unusual_activity(calls, puts),
        "strategy":  compute_strategy_heatmap(calls, puts, spot),
    }
