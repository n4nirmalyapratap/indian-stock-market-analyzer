"""
strategy_builder_service.py
Smart Strategy Builder — reads market state and scores/invents strategies.

Key design:
  • Scores ALL 12 pre-defined strategies against *current* market data.
  • Invents 5 UNIQUE strategies tailored to the CURRENT vol regime —
    different market conditions produce entirely different AI suggestions.
  • Returns all 17 strategies split into predefined (12) + ai_suggested (5).
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
    category:    str
    outlook:     str     # "bullish" | "bearish" | "neutral" | "volatile"
    legs:        List[StrategyLeg]
    fit_score:   int     # 0-100
    rationale:   str
    key_risk:    str
    is_custom:   bool = False


# ── Market state detection ────────────────────────────────────────────────────

def detect_market_state(
    spot: float, atm: int, hv: float, hv_pct: float, lot_size: int,
) -> MarketState:
    vol_regime = (
        "very_high" if hv_pct >= 75 else
        "high"      if hv_pct >= 55 else
        "moderate"  if hv_pct >= 35 else
        "low"
    )
    step = 100 if atm >= 10_000 else 50 if atm >= 2_000 else 10
    vol_bias = (
        "expanding"   if hv_pct >= 65 else
        "contracting" if hv_pct <= 30 else
        "stable"
    )
    return MarketState(
        vol_regime=vol_regime, vol_bias=vol_bias, hv_pct=hv_pct,
        hv=hv, spot=spot, atm=atm, step=step, lot_size=lot_size,
    )


# ── Pre-defined strategy legs ─────────────────────────────────────────────────

def _legs_for_strategy(name: str, ms: MarketState) -> List[StrategyLeg]:
    a, s = ms.atm, ms.step
    otm = s * 3

    PREDEFINED: Dict[str, List[StrategyLeg]] = {
        "Long Call":        [StrategyLeg("buy",  "call", a)],
        "Short Put":        [StrategyLeg("sell", "put",  a - otm)],
        "Long Put":         [StrategyLeg("buy",  "put",  a)],
        "Short Call":       [StrategyLeg("sell", "call", a + otm)],
        "Long Straddle":    [StrategyLeg("buy",  "call", a), StrategyLeg("buy",  "put",  a)],
        "Long Strangle":    [StrategyLeg("buy",  "call", a + otm), StrategyLeg("buy",  "put",  a - otm)],
        "Short Straddle":   [StrategyLeg("sell", "call", a), StrategyLeg("sell", "put",  a)],
        "Short Strangle":   [StrategyLeg("sell", "call", a + otm), StrategyLeg("sell", "put",  a - otm)],
        "Bull Call Spread": [StrategyLeg("buy",  "call", a), StrategyLeg("sell", "call", a + otm)],
        "Bear Put Spread":  [StrategyLeg("buy",  "put",  a), StrategyLeg("sell", "put",  a - otm)],
        "Iron Condor": [
            StrategyLeg("sell", "call", a + otm),
            StrategyLeg("buy",  "call", a + 2 * otm),
            StrategyLeg("sell", "put",  a - otm),
            StrategyLeg("buy",  "put",  a - 2 * otm),
        ],
        "Butterfly": [
            StrategyLeg("buy",  "call", a - s, 1),
            StrategyLeg("sell", "call", a,     2),
            StrategyLeg("buy",  "call", a + s, 1),
        ],
    }
    return PREDEFINED.get(name, [])


def _score_predefined(name: str, ms: MarketState) -> int:
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
    regime_word = (
        "very cheap — ideal time to buy premium" if hp < 35 else
        "moderate" if hp < 55 else
        "elevated — premium is rich" if hp < 75 else
        "extreme — premium is very expensive"
    )

    VOL_BUY  = {"Long Straddle", "Long Strangle"}
    VOL_SELL = {"Short Straddle", "Short Strangle", "Iron Condor"}
    BUY_DIR  = {"Long Call", "Long Put"}
    SELL_DIR = {"Short Call", "Short Put"}
    PIN      = {"Butterfly"}

    if name in VOL_BUY:
        return (f"HV at {hp:.0f}th pct — vol is {regime_word}. "
                f"{name} profits from any large move in either direction. "
                f"{'Good entry when vol is cheap.' if hp < 40 else 'Costly entry at current premium levels.'}")
    elif name in VOL_SELL:
        return (f"HV at {hp:.0f}th pct — vol is {regime_word}. "
                f"{name} collects theta as long as the market stays range-bound.")
    elif name in BUY_DIR:
        direction = "upside" if "Call" in name else "downside"
        return (f"HV at {hp:.0f}th pct — {regime_word}. "
                f"{name} gives unlimited {direction} exposure with defined risk.")
    elif name in SELL_DIR:
        return (f"HV at {hp:.0f}th pct — {regime_word}. "
                f"{name} collects premium expecting limited market move.")
    elif name == "Bull Call Spread":
        return (f"HV at {hp:.0f}th pct. Defined-risk bullish spread. "
                f"Cost-effective vs long call when vol is {'elevated' if hp > 55 else 'moderate'}.")
    elif name == "Bear Put Spread":
        return (f"HV at {hp:.0f}th pct. Defined-risk bearish spread. Lower cost than outright long put.")
    elif name in PIN:
        return (f"HV at {hp:.0f}th pct — {'calm market, pin play ideal' if hp < 35 else 'high vol reduces pin accuracy'}. "
                "Max profit if market expires at the centre strike.")
    return f"HV at {hp:.0f}th pct."


# ── AI-Invented strategies — REGIME-AWARE ────────────────────────────────────
#
# Each vol regime produces 5 DIFFERENT unique strategies.
# Low vol  → strategies that benefit from cheap options / vol expansion.
# Moderate → balanced strategies with defined-risk and net credit.
# High     → premium-selling strategies capitalising on rich IV.
# Very High → extreme premium-selling / crash-protection combos.

def _invent_custom_strategies(ms: MarketState) -> List[StrategyRecommendation]:
    regime = ms.vol_regime
    if regime == "low":
        return _ai_low_vol(ms)
    elif regime == "moderate":
        return _ai_moderate_vol(ms)
    elif regime == "high":
        return _ai_high_vol(ms)
    else:
        return _ai_very_high_vol(ms)


# ── LOW VOL (hv_pct < 35) — buy time value, explosive payoffs ────────────────

def _ai_low_vol(ms: MarketState) -> List[StrategyRecommendation]:
    a, s, hp = ms.atm, ms.step, ms.hv_pct
    base_score = int(80 - hp)  # higher score the lower the vol

    strategies = [
        StrategyRecommendation(
            name="Calendar Spread (ATM)",
            description="Sell near-term ATM call, buy far-term ATM call — exploits term-structure cheapness",
            category="custom", outlook="neutral",
            legs=[
                StrategyLeg("sell", "call", a, 1),  # near-term (conceptually)
                StrategyLeg("buy",  "call", a, 1),  # far-term
            ],
            fit_score=min(95, base_score + 20),
            rationale=(
                f"HV is in the {hp:.0f}th percentile — options are historically cheap. "
                "Calendar spreads profit from the steeper time decay of near-term options. "
                "The long far-term leg retains value while the short near-term leg decays faster. "
                "Unique: ideal when vol is cheap and you expect it to mean-revert upward."
            ),
            key_risk="Both legs suffer if there is a large sudden move before near-term expiry.",
            is_custom=True,
        ),
        StrategyRecommendation(
            name="Call Back Spread",
            description="Sell 1 ATM call, buy 2 OTM calls — explosive profits from strong rally",
            category="custom", outlook="bullish",
            legs=[
                StrategyLeg("sell", "call", a,       1),
                StrategyLeg("buy",  "call", a + 2*s, 2),
            ],
            fit_score=min(95, base_score + 15),
            rationale=(
                f"HV at {hp:.0f}th pct — cheap vol makes back-spreads ideal. "
                "Selling 1 ATM call finances buying 2 OTM calls at a minimal net cost. "
                "Profits accelerate sharply if the market rallies beyond the OTM strikes. "
                "AI picks this when vol is low because the back-spread becomes expensive in high vol."
            ),
            key_risk="Loses if market ends between short call and OTM calls at expiry (the dead zone).",
            is_custom=True,
        ),
        StrategyRecommendation(
            name="Put Back Spread",
            description="Sell 1 ATM put, buy 2 OTM puts — tail-risk protection when options are cheap",
            category="custom", outlook="bearish",
            legs=[
                StrategyLeg("sell", "put", a,       1),
                StrategyLeg("buy",  "put", a - 2*s, 2),
            ],
            fit_score=min(90, base_score + 10),
            rationale=(
                f"HV at {hp:.0f}th pct — low vol makes buying protection cheap. "
                "Sell 1 ATM put to finance 2 OTM puts. If the market crashes, the 2 OTM puts "
                "generate outsized returns. Ideal tail-risk hedge when complacency is high."
            ),
            key_risk="Max loss between short put and OTM puts (dead zone); small loss if market stays flat.",
            is_custom=True,
        ),
        StrategyRecommendation(
            name="Long Call Ladder",
            description="Buy ATM call, sell OTM+1 call, sell OTM+3 call — profits from slow grind up",
            category="custom", outlook="bullish",
            legs=[
                StrategyLeg("buy",  "call", a,        1),
                StrategyLeg("sell", "call", a + s,    1),
                StrategyLeg("sell", "call", a + 3*s,  1),
            ],
            fit_score=min(85, base_score + 5),
            rationale=(
                f"HV at {hp:.0f}th pct. Long Call Ladder is cost-effective in low vol — "
                "buying the ATM call is cheap, and selling two OTM calls brings in enough credit "
                "to offset cost. Profits in a slow bullish grind up to OTM+3, but losses mount "
                "sharply if the market rips past the short strikes."
            ),
            key_risk="Unlimited loss if market rallies strongly past the highest short call strike.",
            is_custom=True,
        ),
        StrategyRecommendation(
            name="Synthetic Long Forward",
            description="Buy ATM call, sell ATM put — leveraged bullish position at near-zero cost",
            category="custom", outlook="bullish",
            legs=[
                StrategyLeg("buy",  "call", a, 1),
                StrategyLeg("sell", "put",  a, 1),
            ],
            fit_score=min(80, base_score),
            rationale=(
                f"HV at {hp:.0f}th pct — low vol reduces premium on both sides. "
                "A synthetic forward mimics a futures position using options: "
                "buy the call for upside, sell the put to offset the cost. "
                "Net cost is near zero (put-call parity). AI recommends this when the "
                "directional bias is bullish but paying full call premium is unattractive."
            ),
            key_risk="Full downside exposure if market falls — similar to being long futures.",
            is_custom=True,
        ),
    ]
    return strategies


# ── MODERATE VOL (35–55) — balanced, net-credit, defined-risk ────────────────

def _ai_moderate_vol(ms: MarketState) -> List[StrategyRecommendation]:
    a, s, hp = ms.atm, ms.step, ms.hv_pct
    base_score = 65  # moderate vol is best for balanced strategies

    strategies = [
        StrategyRecommendation(
            name="Jade Lizard",
            description="Sell OTM put + sell OTM call + buy further OTM call — net credit, no upside breakeven",
            category="custom", outlook="neutral",
            legs=[
                StrategyLeg("sell", "put",  a - s,    1),
                StrategyLeg("sell", "call", a + s,    1),
                StrategyLeg("buy",  "call", a + 3*s,  1),
            ],
            fit_score=min(90, base_score + 15),
            rationale=(
                f"HV at {hp:.0f}th pct — moderate vol provides fair premium. "
                "Jade Lizard collects credit from both sides while capping call-side risk. "
                "No upside breakeven if the total credit received exceeds the put strike spread. "
                "AI picks this in moderate vol as it outperforms plain short strangle with defined call risk."
            ),
            key_risk="Put-side exposure if market drops sharply past the short put strike.",
            is_custom=True,
        ),
        StrategyRecommendation(
            name="Broken Wing Butterfly (Call)",
            description="Asymmetric call butterfly skewed bullish — wider upper wing creates a net credit",
            category="custom", outlook="bullish",
            legs=[
                StrategyLeg("buy",  "call", a,        1),
                StrategyLeg("sell", "call", a + s,    2),
                StrategyLeg("buy",  "call", a + 3*s,  1),
            ],
            fit_score=min(88, base_score + 13),
            rationale=(
                f"HV at {hp:.0f}th pct. Broken Wing Butterfly uses an uneven wing spread to "
                "generate a net credit rather than a debit. Large profit zone above the ATM. "
                "Max profit if the market pins at ATM+1 step. "
                "AI chooses this in moderate vol for its risk-efficient structure."
            ),
            key_risk="Uncapped loss below ATM and a small loss if far above the upper wing.",
            is_custom=True,
        ),
        StrategyRecommendation(
            name="Skip Strike Butterfly",
            description="Buy ATM call, skip a strike, sell 2× at OTM+2, buy at OTM+3 — precision pin play",
            category="custom", outlook="neutral",
            legs=[
                StrategyLeg("buy",  "call", a,        1),
                StrategyLeg("sell", "call", a + 2*s,  2),
                StrategyLeg("buy",  "call", a + 3*s,  1),
            ],
            fit_score=min(82, base_score + 7),
            rationale=(
                f"HV at {hp:.0f}th pct. The Skip Strike variant shifts the profit zone "
                "OTM compared to a standard butterfly. Cheaper to enter (wider inner gap) "
                "and profits if market settles between ATM+1 and ATM+3 by expiry. "
                "Better risk-adjusted entry in moderate vol vs standard butterfly."
            ),
            key_risk="Max loss at ATM and at the upper wing; profit zone is narrow.",
            is_custom=True,
        ),
        StrategyRecommendation(
            name="Poor Man's Covered Call",
            description="Buy deep ITM long-dated call, sell OTM short-dated call — low-cost income play",
            category="custom", outlook="neutral",
            legs=[
                StrategyLeg("buy",  "call", a - 3*s,  1),  # deep ITM = LEAPS proxy
                StrategyLeg("sell", "call", a + 2*s,  1),  # OTM short-dated
            ],
            fit_score=min(78, base_score + 3),
            rationale=(
                f"HV at {hp:.0f}th pct. Poor Man's Covered Call mimics a covered call "
                "without owning the underlying. Buy a deep ITM call as a stock substitute "
                "(high delta, low time value), then sell an OTM call to generate monthly income. "
                "AI selects this in moderate vol for steady theta collection with defined risk."
            ),
            key_risk="Deep ITM call loses value if the stock falls sharply; OTM call limits upside.",
            is_custom=True,
        ),
        StrategyRecommendation(
            name="Collar Spread",
            description="Buy OTM protective put + sell OTM covered call — hedge with income",
            category="custom", outlook="neutral",
            legs=[
                StrategyLeg("buy",  "put",  a - 2*s,  1),
                StrategyLeg("sell", "call", a + 2*s,  1),
            ],
            fit_score=min(74, base_score - 1),
            rationale=(
                f"HV at {hp:.0f}th pct. A Collar provides two-sided protection: "
                "the put hedges downside while the short call funds that hedge. "
                "Net cost near zero in moderate vol (put and call premiums are balanced). "
                "AI recommends this when traders want a market position with risk capped on both sides."
            ),
            key_risk="Upside is capped at the short call strike; put expires worthless if market stays flat.",
            is_custom=True,
        ),
    ]
    return strategies


# ── HIGH VOL (55–75) — premium is rich, sell intelligently ───────────────────

def _ai_high_vol(ms: MarketState) -> List[StrategyRecommendation]:
    a, s, hp = ms.atm, ms.step, ms.hv_pct
    base_score = int(50 + (hp - 55) * 1.2)

    strategies = [
        StrategyRecommendation(
            name="Iron Butterfly",
            description="Sell ATM straddle + buy OTM wings — tighter than Iron Condor, higher max profit",
            category="custom", outlook="neutral",
            legs=[
                StrategyLeg("sell", "call", a,        1),
                StrategyLeg("sell", "put",  a,        1),
                StrategyLeg("buy",  "call", a + 2*s,  1),
                StrategyLeg("buy",  "put",  a - 2*s,  1),
            ],
            fit_score=min(93, base_score + 20),
            rationale=(
                f"HV at {hp:.0f}th pct — premium is rich. Iron Butterfly sells the ATM straddle "
                "(highest premium) and buys OTM wings for protection. "
                "Generates more credit than a standard Iron Condor at the same wing strikes. "
                "AI picks this when vol is high and expecting IV to contract toward expiry."
            ),
            key_risk="Narrow profit zone — market must stay near ATM. Large move in either direction loses.",
            is_custom=True,
        ),
        StrategyRecommendation(
            name="Ratio Call Spread",
            description="Buy 1 ATM call, sell 2 OTM calls — net credit when IV is elevated",
            category="custom", outlook="bullish",
            legs=[
                StrategyLeg("buy",  "call", a,       1),
                StrategyLeg("sell", "call", a + 2*s, 2),
            ],
            fit_score=min(88, base_score + 15),
            rationale=(
                f"HV at {hp:.0f}th pct — selling 2 OTM calls against 1 ATM call generates "
                "a meaningful net credit when IV is elevated. Profits if market stays below shorts. "
                "AI flags this in high vol as the credit buffer provides a safety margin."
            ),
            key_risk="Unlimited loss above the short call strikes — must manage if market rallies hard.",
            is_custom=True,
        ),
        StrategyRecommendation(
            name="Ratio Put Spread",
            description="Buy 1 ATM put, sell 2 OTM puts — net credit, profits if market stays above OTM",
            category="custom", outlook="bearish",
            legs=[
                StrategyLeg("buy",  "put", a,       1),
                StrategyLeg("sell", "put", a - 2*s, 2),
            ],
            fit_score=min(84, base_score + 11),
            rationale=(
                f"HV at {hp:.0f}th pct. High IV makes selling 2 OTM puts very lucrative. "
                "The long ATM put acts as a partial hedge. Net credit if premium is sufficient. "
                "Profits if the market stays above the OTM short puts by expiry."
            ),
            key_risk="Accelerating loss if market crashes below both short put strikes.",
            is_custom=True,
        ),
        StrategyRecommendation(
            name="Bear Call Ladder",
            description="Sell ATM call, buy OTM+1 call, buy OTM+3 call — profit from sharp rally or flat market",
            category="custom", outlook="volatile",
            legs=[
                StrategyLeg("sell", "call", a,        1),
                StrategyLeg("buy",  "call", a + s,    1),
                StrategyLeg("buy",  "call", a + 3*s,  1),
            ],
            fit_score=min(79, base_score + 6),
            rationale=(
                f"HV at {hp:.0f}th pct. Bear Call Ladder collects premium selling ATM "
                "and hedges upside with two long calls at different OTM levels. "
                "Profits if market stays flat OR if it rallies very strongly past OTM+3. "
                "AI selects this in high vol for the net credit and dual-scenario profit."
            ),
            key_risk="Max loss between ATM and OTM+3 — the middle zone is the worst outcome.",
            is_custom=True,
        ),
        StrategyRecommendation(
            name="Wide OTM Strangle Sell",
            description="Sell far OTM call + far OTM put — high probability, lower premium than ATM strangle",
            category="custom", outlook="neutral",
            legs=[
                StrategyLeg("sell", "call", a + 4*s,  1),
                StrategyLeg("sell", "put",  a - 4*s,  1),
            ],
            fit_score=min(75, base_score + 2),
            rationale=(
                f"HV at {hp:.0f}th pct — even far-OTM options carry meaningful premium. "
                "Wide strangle sell gives a very high probability of profit (both options expire "
                "worthless unless there is an extreme market move). "
                "Compared to ATM Short Strangle: lower premium but higher win rate."
            ),
            key_risk="Unlimited loss on both sides if a large spike occurs — must set stop-losses.",
            is_custom=True,
        ),
    ]
    return strategies


# ── VERY HIGH VOL (hv_pct ≥ 75) — extreme premium, crisis conditions ─────────

def _ai_very_high_vol(ms: MarketState) -> List[StrategyRecommendation]:
    a, s, hp = ms.atm, ms.step, ms.hv_pct
    base_score = int(55 + (hp - 75) * 0.8)

    strategies = [
        StrategyRecommendation(
            name="Wide Iron Condor",
            description="Extra-wide strikes Iron Condor — high premium, generous buffer in extreme vol",
            category="custom", outlook="neutral",
            legs=[
                StrategyLeg("sell", "call", a + 3*s,   1),
                StrategyLeg("buy",  "call", a + 5*s,   1),
                StrategyLeg("sell", "put",  a - 3*s,   1),
                StrategyLeg("buy",  "put",  a - 5*s,   1),
            ],
            fit_score=min(93, base_score + 25),
            rationale=(
                f"HV at extreme {hp:.0f}th pct. In very high vol, standard condor strikes are "
                "too tight. Wide Iron Condor pushes short strikes 3 steps OTM to build a generous "
                "buffer zone. The inflated IV provides exceptional credit collection even at these "
                "wider strikes. AI prioritises this in extreme vol as the single best risk-adjusted play."
            ),
            key_risk="Extreme market moves (>5 steps in one direction) still cause losses; size conservatively.",
            is_custom=True,
        ),
        StrategyRecommendation(
            name="Iron Butterfly",
            description="Sell ATM straddle + buy OTM wings — maximum premium collection at the money",
            category="custom", outlook="neutral",
            legs=[
                StrategyLeg("sell", "call", a,        1),
                StrategyLeg("sell", "put",  a,        1),
                StrategyLeg("buy",  "call", a + 3*s,  1),
                StrategyLeg("buy",  "put",  a - 3*s,  1),
            ],
            fit_score=min(89, base_score + 21),
            rationale=(
                f"HV at {hp:.0f}th pct — ATM options are extraordinarily expensive. "
                "Iron Butterfly captures peak ATM premium (the straddle) and buys wings "
                "for risk management. In very high vol this generates 2–3× more credit than normal. "
                "AI selects this for maximum credit when market fear is at its highest."
            ),
            key_risk="Requires near-perfect market pinning — any large move reduces profit significantly.",
            is_custom=True,
        ),
        StrategyRecommendation(
            name="Broken Wing Butterfly (Put)",
            description="Asymmetric put butterfly skewed bearish — wider lower wing, net credit even in crashes",
            category="custom", outlook="bearish",
            legs=[
                StrategyLeg("buy",  "put", a,         1),
                StrategyLeg("sell", "put", a - s,     2),
                StrategyLeg("buy",  "put", a - 3*s,   1),
            ],
            fit_score=min(83, base_score + 15),
            rationale=(
                f"HV at {hp:.0f}th pct. Put BWB is a bear-biased structure that generates a "
                "net credit in high vol. The wider lower wing means profit if market drops "
                "moderately. Maximum gain if market pins at ATM−1 step. "
                "AI recommends this for bearish bias during extreme vol — better than plain long put."
            ),
            key_risk="Loss if market crashes below the lower wing or stays flat above ATM.",
            is_custom=True,
        ),
        StrategyRecommendation(
            name="Short Ratio Put Spread",
            description="Sell 2 OTM puts, buy 1 ATM put — aggressive premium collection with crash buffer",
            category="custom", outlook="neutral",
            legs=[
                StrategyLeg("buy",  "put", a,       1),
                StrategyLeg("sell", "put", a - 2*s, 2),
            ],
            fit_score=min(78, base_score + 10),
            rationale=(
                f"HV at {hp:.0f}th pct — OTM puts are extremely expensive due to skew. "
                "Selling 2 OTM puts against 1 ATM put generates a large net credit. "
                "The long ATM put provides partial hedge. Profits if market stays above OTM puts. "
                "AI recommends in extreme vol because the OTM put skew makes this unusually lucrative."
            ),
            key_risk="Accelerating loss below the OTM short puts; position requires active management.",
            is_custom=True,
        ),
        StrategyRecommendation(
            name="Calendar Strangle (Synthetic Vega Spread)",
            description="Sell near-term OTM strangle, buy far-term OTM strangle — capture vol term-structure",
            category="custom", outlook="volatile",
            legs=[
                StrategyLeg("sell", "call", a + 2*s,  1),  # near term
                StrategyLeg("sell", "put",  a - 2*s,  1),  # near term
                StrategyLeg("buy",  "call", a + 3*s,  1),  # far term
                StrategyLeg("buy",  "put",  a - 3*s,  1),  # far term
            ],
            fit_score=min(73, base_score + 5),
            rationale=(
                f"HV at {hp:.0f}th pct — front-month vol is spiked vs back-month. "
                "Calendar Strangle sells the expensive near-term OTM options while buying "
                "cheaper far-term equivalents. Profits from vol normalisation (mean reversion). "
                "AI selects this during extreme vol spikes expecting vol to calm in the following weeks."
            ),
            key_risk="Near-term short options may spike further if crisis deepens before near expiry.",
            is_custom=True,
        ),
    ]
    return strategies


# ── Public entry point ────────────────────────────────────────────────────────

def build_smart_suggestions(
    spot: float, atm: int, hv: float, hv_pct: float, lot_size: int,
) -> dict:
    """
    Build all 17 strategy suggestions (12 predefined + 5 AI-invented).

    Returns:
        {
            "market_state":       { vol_regime, vol_bias, hv_pct, hv, spot, atm, step, lot_size },
            "recommendations":    [ ... all 12 predefined sorted by fit_score ... ],
            "ai_suggestions":     [ ... 5 regime-specific AI strategies sorted by fit_score ... ],
        }
    """
    ms = detect_market_state(spot=spot, atm=atm, hv=hv, hv_pct=hv_pct, lot_size=lot_size)

    # ── Score all pre-defined strategies ─────────────────────────────────────
    PREDEFINED_NAMES = [
        "Long Call", "Short Put", "Long Put", "Short Call",
        "Long Straddle", "Long Strangle", "Short Straddle", "Short Strangle",
        "Bull Call Spread", "Bear Put Spread", "Iron Condor", "Butterfly",
    ]
    predefined_recs = []
    for name in PREDEFINED_NAMES:
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
    predefined_recs.sort(key=lambda r: r.fit_score, reverse=True)

    # ── Generate regime-specific AI strategies ────────────────────────────────
    ai_recs = _invent_custom_strategies(ms)
    ai_recs.sort(key=lambda r: r.fit_score, reverse=True)

    def rec_to_dict(r: StrategyRecommendation) -> dict:
        return {
            "name":        r.name,
            "description": r.description,
            "category":    r.category,
            "outlook":     r.outlook,
            "fit_score":   r.fit_score,
            "rationale":   r.rationale,
            "key_risk":    r.key_risk,
            "is_custom":   r.is_custom,
            "legs": [
                {"action": l.action, "option_type": l.option_type,
                 "strike": l.strike, "lots": l.lots}
                for l in r.legs
            ],
        }

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
        "recommendations": [rec_to_dict(r) for r in predefined_recs],
        "ai_suggestions":  [rec_to_dict(r) for r in ai_recs],
    }
