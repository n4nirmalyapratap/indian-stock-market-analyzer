"""
strategy_builder_service.py
Smart Strategy Builder — reads market state and invents / scores strategies.

The key differentiator vs every other platform:
  • Scores ALL 12 pre-defined strategies against *current* market data.
  • Invents 5 non-standard (custom) strategies with actual strikes derived from ATM.
  • Ranks everything together so the best fit floats to the top.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Dict, Optional


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class MarketState:
    vol_regime: str      # "low" | "moderate" | "high" | "very_high"
    vol_bias:   str      # "expanding" | "contracting" | "stable"
    hv_pct:     float    # 0-100
    hv:         float    # annualised HV (decimal, e.g. 0.18)
    spot:       float
    atm:        int
    step:       int      # inferred strike step
    lot_size:   int


@dataclass
class StrategyLeg:
    action:      str     # "buy" | "sell"
    option_type: str     # "call" | "put"
    strike:      int
    lots:        int = 1


@dataclass
class StrategyRecommendation:
    name:        str
    description: str
    category:    str     # "sell_vol" | "buy_vol" | "buy_dir" | "sell_dir" | "spread" | "custom"
    outlook:     str     # "bullish" | "bearish" | "neutral" | "volatile"
    legs:        List[StrategyLeg]
    fit_score:   int     # 0-100
    rationale:   str
    key_risk:    str
    is_custom:   bool = False


# ── Market state detection ────────────────────────────────────────────────────

def detect_market_state(
    spot: float,
    atm:  int,
    hv:   float,
    hv_pct: float,
    lot_size: int,
) -> MarketState:
    """Classify market conditions from spot-info data."""
    vol_regime = (
        "very_high" if hv_pct >= 75 else
        "high"      if hv_pct >= 55 else
        "moderate"  if hv_pct >= 35 else
        "low"
    )

    # Strike step logic (mirrors frontend QUICK_STRATEGIES step logic)
    step = 100 if atm >= 10_000 else 50 if atm >= 2_000 else 10

    vol_bias = (
        "expanding"   if hv_pct >= 65 else
        "contracting" if hv_pct <= 30 else
        "stable"
    )

    return MarketState(
        vol_regime=vol_regime,
        vol_bias=vol_bias,
        hv_pct=hv_pct,
        hv=hv,
        spot=spot,
        atm=atm,
        step=step,
        lot_size=lot_size,
    )


# ── Pre-defined strategy legs ─────────────────────────────────────────────────

def _legs_for_strategy(name: str, ms: MarketState) -> List[StrategyLeg]:
    """Build pre-defined strategy legs with actual strikes centred around ATM."""
    a, s = ms.atm, ms.step
    otm = s * 3   # standard 3-step OTM offset

    PREDEFINED: Dict[str, List[StrategyLeg]] = {
        "Long Call": [
            StrategyLeg("buy",  "call", a),
        ],
        "Short Put": [
            StrategyLeg("sell", "put", a - otm),
        ],
        "Long Put": [
            StrategyLeg("buy",  "put", a),
        ],
        "Short Call": [
            StrategyLeg("sell", "call", a + otm),
        ],
        "Long Straddle": [
            StrategyLeg("buy", "call", a),
            StrategyLeg("buy", "put",  a),
        ],
        "Long Strangle": [
            StrategyLeg("buy", "call", a + otm),
            StrategyLeg("buy", "put",  a - otm),
        ],
        "Short Straddle": [
            StrategyLeg("sell", "call", a),
            StrategyLeg("sell", "put",  a),
        ],
        "Short Strangle": [
            StrategyLeg("sell", "call", a + otm),
            StrategyLeg("sell", "put",  a - otm),
        ],
        "Bull Call Spread": [
            StrategyLeg("buy",  "call", a),
            StrategyLeg("sell", "call", a + otm),
        ],
        "Bear Put Spread": [
            StrategyLeg("buy",  "put", a),
            StrategyLeg("sell", "put", a - otm),
        ],
        "Iron Condor": [
            StrategyLeg("sell", "call", a + otm),
            StrategyLeg("buy",  "call", a + 2 * otm),
            StrategyLeg("sell", "put",  a - otm),
            StrategyLeg("buy",  "put",  a - 2 * otm),
        ],
        "Butterfly": [
            StrategyLeg("buy",  "call", a - s,  1),
            StrategyLeg("sell", "call", a,       2),
            StrategyLeg("buy",  "call", a + s,   1),
        ],
    }
    return PREDEFINED.get(name, [])


# ── Pre-defined strategy scoring ──────────────────────────────────────────────

def _score_predefined(name: str, ms: MarketState) -> int:
    """Score a predefined strategy 0-100 for the current market state."""
    hp = ms.hv_pct
    score = 50

    VOL_BUY  = {"Long Straddle", "Long Strangle"}
    VOL_SELL = {"Short Straddle", "Short Strangle", "Iron Condor"}
    BUY_DIR  = {"Long Call", "Long Put"}
    SELL_DIR = {"Short Call", "Short Put"}
    SPREAD   = {"Bull Call Spread", "Bear Put Spread"}
    PIN      = {"Butterfly"}

    if name in VOL_BUY:
        score += 30 if hp < 35 else 10 if hp < 50 else -10 if hp < 65 else -30
    elif name in VOL_SELL:
        score += 30 if hp > 65 else 10 if hp > 50 else -10 if hp > 40 else -30
    elif name in BUY_DIR:
        score += 25 if hp < 40 else 10 if hp < 55 else -10 if hp < 65 else -25
    elif name in SELL_DIR:
        score += 25 if hp > 60 else 5 if hp > 45 else -15 if hp > 35 else -25
    elif name in SPREAD:
        score += 15 if 30 < hp < 70 else -10
    elif name in PIN:
        score += 30 if hp < 30 else 10 if hp < 45 else -15 if hp < 60 else -30

    return max(0, min(100, score))


def _predefined_rationale(name: str, ms: MarketState) -> str:
    hp = ms.hv_pct
    VOL_BUY  = {"Long Straddle", "Long Strangle"}
    VOL_SELL = {"Short Straddle", "Short Strangle", "Iron Condor"}
    BUY_DIR  = {"Long Call", "Long Put"}
    SELL_DIR = {"Short Call", "Short Put"}
    PIN      = {"Butterfly"}

    if name in VOL_BUY:
        qual = "cheap — good time to buy" if hp < 40 else "expensive — buying is costly" if hp > 60 else "moderate"
        return (f"HV at {hp:.0f}th pct, vol is {qual}. "
                f"{name} profits from any large move in either direction.")
    elif name in VOL_SELL:
        qual = "rich — good time to sell" if hp > 60 else "thin — selling not ideal" if hp < 40 else "moderate"
        return (f"HV at {hp:.0f}th pct, premium is {qual}. "
                f"{name} collects theta as long as the market stays range-bound.")
    elif name in BUY_DIR:
        dir_word = "upside" if "Call" in name else "downside"
        qual = "cheap entry" if hp < 45 else "expensive entry"
        return (f"HV at {hp:.0f}th pct — {qual}. "
                f"{name} gives unlimited {dir_word} exposure with defined risk.")
    elif name in SELL_DIR:
        qual = "premium rich, selling works" if hp > 60 else "thin premium, not ideal to sell"
        return (f"HV at {hp:.0f}th pct — {qual}. "
                f"{name} collects premium expecting limited market move.")
    elif name == "Bull Call Spread":
        return (f"HV at {hp:.0f}th pct. Defined-risk bullish play. "
                f"Cost-effective vs long call when vol is {'elevated' if hp > 55 else 'moderate'}.")
    elif name == "Bear Put Spread":
        return (f"HV at {hp:.0f}th pct. Defined-risk bearish play. "
                "Lower cost than outright long put.")
    elif name in PIN:
        qual = "calm market — pin play works" if hp < 35 else "too volatile for butterfly"
        return (f"HV at {hp:.0f}th pct — {qual}. "
                "Max profit if market expires at the centre strike.")
    return f"HV at {hp:.0f}th pct."


# ── Custom (invented) strategy builder ───────────────────────────────────────

def _invent_custom_strategies(ms: MarketState) -> List[StrategyRecommendation]:
    """
    Invent 5 non-standard strategies with actual strikes derived from ATM.
    These are strategies NO standard Indian options platform pre-packages.
    """
    a, s = ms.atm, ms.step
    hp   = ms.hv_pct
    results: List[StrategyRecommendation] = []

    # ── 1. Jade Lizard (high IV, neutral-to-bullish) ──────────────────────────
    # Sell OTM put + sell OTM call + buy further OTM call (caps call-side risk).
    # Net credit has no upside breakeven if credit > put spread width.
    jade_score = int(max(0, min(100,
        50 + (hp - 50) * 1.2 if hp > 50 else 50 - (50 - hp) * 1.2
    )))
    results.append(StrategyRecommendation(
        name="Jade Lizard",
        description="Sell OTM put + sell OTM call + buy further OTM call — net credit, no upside BE",
        category="sell_vol",
        outlook="neutral",
        legs=[
            StrategyLeg("sell", "put",  a - s,     1),
            StrategyLeg("sell", "call", a + s,      1),
            StrategyLeg("buy",  "call", a + 3 * s,  1),
        ],
        fit_score=jade_score,
        rationale=(
            f"HV at {hp:.0f}th pct — premium is {'rich' if hp > 60 else 'fair'}. "
            "Jade Lizard collects credit from both sides while capping call-side risk. "
            "No upside breakeven if the net credit received exceeds the put-spread width. "
            "Unique: combines short strangle economics with a defined call ceiling."
        ),
        key_risk="Put-side exposure if market drops sharply past the short put strike.",
        is_custom=True,
    ))

    # ── 2. Broken Wing Butterfly — Call (mildly bullish, moderate-high IV) ────
    # Buy ATM call + sell 2 × (ATM+1s) call + buy (ATM+3s) call.
    # Asymmetric — upper wing is wider than lower wing → net credit.
    bwb_score = int(max(0, min(100,
        50 + (hp - 50) * 0.8 if hp > 50 else 50 - (50 - hp) * 0.5
    )))
    results.append(StrategyRecommendation(
        name="Broken Wing Butterfly (Call)",
        description="Asymmetric call butterfly skewed bullish — wider upper wing gives net credit",
        category="custom",
        outlook="bullish",
        legs=[
            StrategyLeg("buy",  "call", a,         1),
            StrategyLeg("sell", "call", a + s,      2),
            StrategyLeg("buy",  "call", a + 3 * s,  1),
        ],
        fit_score=bwb_score,
        rationale=(
            f"HV at {hp:.0f}th pct. BWB creates a net credit with a large profit zone "
            "above the lower strike. If the market pins near ATM+1 step at expiry, "
            "the position achieves maximum profit. "
            "Beats a standard butterfly by adding positive carry instead of paying a debit."
        ),
        key_risk="Max loss if market falls hard past ATM; small loss if far above upper wing.",
        is_custom=True,
    ))

    # ── 3. Ratio Call Spread (high IV, neutral-to-mildly bullish) ─────────────
    # Buy 1 ATM call + sell 2 OTM calls — net credit, profit if market stays below shorts.
    ratio_score = int(max(0, min(100,
        50 + (hp - 50) * 1.4 if hp > 50 else 50 - (50 - hp) * 1.0
    )))
    results.append(StrategyRecommendation(
        name="Ratio Call Spread",
        description="Buy 1 ATM call, sell 2 OTM calls — net credit when vol is elevated",
        category="sell_vol",
        outlook="bullish",
        legs=[
            StrategyLeg("buy",  "call", a,       1),
            StrategyLeg("sell", "call", a + 2*s, 2),
        ],
        fit_score=ratio_score,
        rationale=(
            f"HV at {hp:.0f}th pct. Selling 2 OTM calls against 1 ATM call generates "
            "a net credit when vol is elevated. The spread profits if the market stays "
            "below or near the short strikes. Unlimited upside risk beyond shorts, "
            "but net credit provides a buffer."
        ),
        key_risk="Unlimited loss if market rallies strongly beyond the short call strikes.",
        is_custom=True,
    ))

    # ── 4. Put Back Spread (low IV, bearish explosive) ────────────────────────
    # Sell 1 ATM put + buy 2 OTM puts — cheap when vol is low, profits on crash.
    put_bs_score = int(max(0, min(100,
        50 + (40 - hp) * 1.2 if hp < 40 else 50 - (hp - 40) * 0.8
    )))
    results.append(StrategyRecommendation(
        name="Put Back Spread",
        description="Sell 1 ATM put, buy 2 OTM puts — explosive profits from sharp selloff",
        category="buy_vol",
        outlook="bearish",
        legs=[
            StrategyLeg("sell", "put", a,       1),
            StrategyLeg("buy",  "put", a - 2*s, 2),
        ],
        fit_score=put_bs_score,
        rationale=(
            f"HV at {hp:.0f}th pct — options are {'cheap, ideal time to buy back-spreads' if hp < 40 else 'moderate'}. "
            "Selling 1 ATM put funds buying 2 OTM puts. "
            "If the market stays above ATM, the loss is small. "
            "If it crashes, the 2× OTM puts generate outsized gains — "
            "profit accelerates beyond the OTM strikes."
        ),
        key_risk="Loses if market ends between short put and OTM puts at expiry (dead zone).",
        is_custom=True,
    ))

    # ── 5. Call Back Spread (low IV, bullish explosive) ───────────────────────
    # Sell 1 ATM call + buy 2 OTM calls — cheap when vol is low, profits on rally.
    call_bs_score = int(max(0, min(100,
        50 + (40 - hp) * 1.2 if hp < 40 else 50 - (hp - 40) * 0.8
    )))
    results.append(StrategyRecommendation(
        name="Call Back Spread",
        description="Sell 1 ATM call, buy 2 OTM calls — explosive profits from strong rally",
        category="buy_vol",
        outlook="bullish",
        legs=[
            StrategyLeg("sell", "call", a,       1),
            StrategyLeg("buy",  "call", a + 2*s, 2),
        ],
        fit_score=call_bs_score,
        rationale=(
            f"HV at {hp:.0f}th pct — {'cheap vol, good time to buy back-spreads' if hp < 40 else 'moderate vol'}. "
            "Selling 1 ATM call finances buying 2 OTM calls at a small net debit. "
            "Profits accelerate if the market rallies strongly beyond the OTM call strikes."
        ),
        key_risk="Loses if market ends between short call and OTM calls at expiry (dead zone).",
        is_custom=True,
    ))

    return results


# ── Public entry point ────────────────────────────────────────────────────────

def build_smart_suggestions(
    spot:     float,
    atm:      int,
    hv:       float,
    hv_pct:   float,
    lot_size: int,
    top_n:    int = 5,
) -> dict:
    """
    Build ranked strategy suggestions (predefined + custom) for the current market.

    Returns:
        {
            "market_state":      { vol_regime, vol_bias, hv_pct, hv, spot, atm, step, lot_size },
            "recommendations":   [ { name, description, category, outlook, fit_score,
                                     rationale, key_risk, is_custom, legs } ]  ← top_n items
        }
    """
    ms = detect_market_state(spot=spot, atm=atm, hv=hv, hv_pct=hv_pct, lot_size=lot_size)

    # ── Score all pre-defined strategies ─────────────────────────────────────
    predefined_names = [
        "Long Call", "Short Put", "Long Put", "Short Call",
        "Long Straddle", "Long Strangle", "Short Straddle", "Short Strangle",
        "Bull Call Spread", "Bear Put Spread", "Iron Condor", "Butterfly",
    ]
    predefined_recs: List[StrategyRecommendation] = []
    for name in predefined_names:
        predefined_recs.append(StrategyRecommendation(
            name=name,
            description=f"Standard {name} strategy",
            category="predefined",
            outlook="neutral",
            legs=_legs_for_strategy(name, ms),
            fit_score=_score_predefined(name, ms),
            rationale=_predefined_rationale(name, ms),
            key_risk="Depends on market direction and magnitude of move.",
            is_custom=False,
        ))

    # ── Invent custom strategies ──────────────────────────────────────────────
    custom_recs = _invent_custom_strategies(ms)

    # ── Combine, rank, return top N ───────────────────────────────────────────
    all_recs = predefined_recs + custom_recs
    all_recs.sort(key=lambda r: r.fit_score, reverse=True)
    top = all_recs[:top_n]

    return {
        "market_state": {
            "vol_regime": ms.vol_regime,
            "vol_bias":   ms.vol_bias,
            "hv_pct":     ms.hv_pct,
            "hv":         round(ms.hv * 100, 2),
            "spot":       ms.spot,
            "atm":        ms.atm,
            "step":       ms.step,
            "lot_size":   ms.lot_size,
        },
        "recommendations": [
            {
                "name":        r.name,
                "description": r.description,
                "category":    r.category,
                "outlook":     r.outlook,
                "fit_score":   r.fit_score,
                "rationale":   r.rationale,
                "key_risk":    r.key_risk,
                "is_custom":   r.is_custom,
                "legs": [
                    {
                        "action":      l.action,
                        "option_type": l.option_type,
                        "strike":      l.strike,
                        "lots":        l.lots,
                    }
                    for l in r.legs
                ],
            }
            for r in top
        ],
    }
