"""
options_chatbot.py
Zero-cost, rule-based options education chatbot for Indian markets.

No external API calls. No per-token charges.
Answers common options questions using keyword matching and injects
live strategy context (spot, Greeks, P&L, legs) into every response.
"""

import re
import math
from typing import Optional

# ── Helper ─────────────────────────────────────────────────────────────────────

def _fmt(n, decimals=2):
    if n is None:
        return "—"
    return f"₹{abs(n):,.{decimals}f}"

def _pct(n):
    return f"{n * 100:.1f}%" if n is not None else "—"

def _contains(text: str, *keywords) -> bool:
    t = text.lower()
    return any(kw in t for kw in keywords)

# ── Context summary builder ────────────────────────────────────────────────────

def _context_block(ctx: dict) -> str:
    """Render the user's current strategy into a readable summary string."""
    if not ctx:
        return ""
    parts = []
    sym   = ctx.get("symbol", "")
    spot  = ctx.get("spot")
    hv    = ctx.get("hv30_pct")
    dte   = round(ctx.get("T", 0) * 365) if ctx.get("T") else None
    legs  = ctx.get("legs") or []
    analysis = ctx.get("analysis") or {}
    payoff   = analysis.get("payoff") or {}
    greeks   = analysis.get("greeks") or {}

    if sym and spot:
        parts.append(f"**{sym}** — spot ₹{spot:,.2f}" + (f" | HV30: {hv:.1f}%" if hv else ""))
    if dte:
        parts.append(f"DTE: {dte} days")
    if legs:
        parts.append("**Legs:**")
        for i, leg in enumerate(legs, 1):
            action = leg.get("action", "?").upper()
            otype  = leg.get("option_type", "?").upper()
            strike = leg.get("strike", "?")
            prem   = leg.get("premium", 0)
            lots   = leg.get("lots", 1)
            iv_pct = leg.get("iv", 0) * 100
            parts.append(
                f"  {i}. {action} {otype} K={strike} | ₹{prem:.2f}/unit | {lots} lot(s) | IV {iv_pct:.1f}%"
            )
    if payoff:
        np = payoff.get("net_premium")
        mp = payoff.get("max_profit")
        ml = payoff.get("max_loss")
        be = payoff.get("breakevens") or []
        if np is not None:
            label = "CREDIT" if np >= 0 else "DEBIT"
            parts.append(f"Net premium: ₹{abs(np):,.0f} ({label})")
        if mp is not None:
            parts.append(f"Max profit: ₹{mp:,.0f}")
        if ml is not None:
            parts.append(f"Max loss: ₹{ml:,.0f}")
        if be:
            parts.append("Breakevens: " + " / ".join(f"₹{b:,.0f}" for b in be))
    if greeks:
        parts.append(
            f"Greeks — Δ {greeks.get('delta', 0):.3f} | "
            f"Θ {greeks.get('theta', 0):.2f}/day | "
            f"ν {greeks.get('vega', 0):.2f}/1%IV | "
            f"Γ {greeks.get('gamma', 0):.5f}"
        )
    return "\n".join(parts)


# ── Response generators ────────────────────────────────────────────────────────

def _reply_net_premium(ctx: dict) -> str:
    payoff = (ctx.get("analysis") or {}).get("payoff") or {}
    np = payoff.get("net_premium")
    legs = ctx.get("legs") or []

    buys  = [l for l in legs if l.get("action") == "buy"]
    sells = [l for l in legs if l.get("action") == "sell"]

    if np is None:
        return (
            "**Net Premium** is the total cash flow when you open a strategy:\n\n"
            "- **Positive (CREDIT)** → you collected more premium than you paid. You receive cash upfront.\n"
            "- **Negative (DEBIT)** → you paid more than you collected. It's an upfront cost.\n\n"
            "**Examples:**\n"
            "- Iron Condor, Short Straddle → CREDIT (you sell more than you buy)\n"
            "- Long Straddle, Long Call → DEBIT (you only buy)\n\n"
            "Fetch a spot price and build a strategy, then click **Analyse Strategy** to see your exact numbers."
        )

    label = "**CREDIT** (you receive cash upfront)" if np >= 0 else "**DEBIT** (you pay cash upfront)"
    reply = f"**Your net premium: ₹{abs(np):,.0f} — {label}**\n\n"

    if np < 0:
        reply += (
            f"You have {len(buys)} buy leg(s) and {len(sells)} sell leg(s). "
            f"Buying options always costs a premium, so debit strategies have negative net premium by definition. "
            f"This is **correct** — it means your maximum loss is ₹{abs(np):,.0f} if all legs expire worthless.\n\n"
            f"**Tips for debit strategies:**\n"
            f"- You profit only if the move happens — theta (time decay) works against you\n"
            f"- Max loss = what you paid (the debit)\n"
            f"- Break-even requires the underlying to move enough to cover your cost"
        )
    else:
        reply += (
            f"You collected ₹{np:,.0f} upfront. This is the **maximum profit** "
            f"if the underlying stays between your short strikes at expiry.\n\n"
            f"**Risks for credit strategies:**\n"
            f"- You keep the credit only if the underlying stays in range\n"
            f"- Time decay (Theta) works **in your favour**\n"
            f"- Sharp moves beyond your breakevens cause losses"
        )
    return reply


def _reply_iron_condor(ctx: dict) -> str:
    payoff  = (ctx.get("analysis") or {}).get("payoff") or {}
    np  = payoff.get("net_premium")
    mp  = payoff.get("max_profit")
    ml  = payoff.get("max_loss")
    be  = payoff.get("breakevens") or []
    spot = ctx.get("spot")

    reply = (
        "## Iron Condor\n\n"
        "An Iron Condor is a **neutral credit strategy** — you profit when the underlying stays range-bound.\n\n"
        "**Structure (4 legs):**\n"
        "| Leg | Action | Type | Strike |\n"
        "|-----|--------|------|--------|\n"
        "| 1 | SELL | Call | Near OTM (e.g. ATM + 1%) |\n"
        "| 2 | BUY  | Call | Far OTM (e.g. ATM + 2%) — caps loss |\n"
        "| 3 | SELL | Put  | Near OTM (e.g. ATM − 1%) |\n"
        "| 4 | BUY  | Put  | Far OTM (e.g. ATM − 2%) — caps loss |\n\n"
        "**P&L profile:**\n"
        "- **Max profit** = net credit received (when underlying stays between short strikes)\n"
        "- **Max loss** = wing width − credit (when underlying blows past either wing)\n"
        "- **Two breakevens** — one above and one below the current price\n\n"
    )

    if np is not None and spot:
        reply += f"**Your current Iron Condor:**\n"
        reply += f"- Net premium: ₹{abs(np):,.0f} CREDIT\n"
        if mp is not None:
            reply += f"- Max profit: ₹{mp:,.0f}\n"
        if ml is not None:
            reply += f"- Max loss: ₹{ml:,.0f}\n"
        if be:
            reply += f"- Breakevens: " + " / ".join(f"₹{b:,.0f}" for b in be) + "\n"
        if spot and len(be) == 2:
            width = be[1] - be[0]
            reply += f"- Safe zone: ₹{width:,.0f} wide (±{width/spot/2*100:.1f}% from spot)\n"

    reply += (
        "\n**Best market conditions:** Low volatility, range-bound market (VIX below 15)\n"
        "**Biggest risk:** Sudden large move (election, Fed, earnings surprise)"
    )
    return reply


def _reply_straddle(ctx: dict, short: bool = False) -> str:
    kind   = "Short" if short else "Long"
    action = "sell" if short else "buy"
    opp    = "buy" if short else "sell"

    reply = (
        f"## {kind} Straddle\n\n"
        f"You **{action}** both an ATM Call and an ATM Put at the same strike.\n\n"
        f"**Structure:**\n"
        f"- {action.upper()} Call @ ATM\n"
        f"- {action.upper()} Put @ ATM\n\n"
    )

    if not short:
        reply += (
            "**When to use:** You expect a BIG move but don't know which direction (earnings, RBI policy, budget).\n\n"
            "- **Max loss** = total premium paid (if underlying doesn't move at all)\n"
            "- **Max profit** = unlimited (if underlying moves far enough)\n"
            "- **Breakevens** = ATM strike ± total premium paid\n"
            "- **Theta hurts you** — time decay eats your premium every day\n"
            "- **Vega helps you** — rising IV benefits your position\n"
        )
    else:
        reply += (
            "**When to use:** You expect NO big move — range-bound market, low event risk.\n\n"
            "- **Max profit** = total premium collected (if underlying stays at ATM)\n"
            "- **Max loss** = unlimited (if underlying moves sharply)\n"
            "- **Breakevens** = ATM strike ± total premium collected\n"
            "- **Theta works for you** — time decay adds to your profit every day\n"
            "- **Vega hurts you** — rising IV is dangerous (hedge with OTM wings)\n"
        )

    payoff = (ctx.get("analysis") or {}).get("payoff") or {}
    np = payoff.get("net_premium")
    be = payoff.get("breakevens") or []
    if np is not None:
        reply += f"\n**Your current position:** ₹{abs(np):,.0f} {'credit' if short else 'debit'}"
        if be:
            reply += f" | Breakevens: " + " / ".join(f"₹{b:,.0f}" for b in be)

    return reply


def _reply_strangle(ctx: dict, short: bool = False) -> str:
    kind = "Short" if short else "Long"
    reply = (
        f"## {kind} Strangle\n\n"
        f"Similar to a {kind} Straddle but uses **OTM** options — cheaper to enter (Long) or wider profit zone (Short).\n\n"
        f"**Structure:**\n"
        + (f"- BUY OTM Call (strike above ATM)\n- BUY OTM Put (strike below ATM)\n" if not short
           else f"- SELL OTM Call (strike above ATM)\n- SELL OTM Put (strike below ATM)\n") +
        "\n**vs Straddle:**\n"
        "| | Straddle | Strangle |\n"
        "|--|--|--|\n"
        "| Strikes | ATM + ATM | OTM Call + OTM Put |\n"
        "| Premium | Higher | Lower |\n"
        "| Break-even range | Narrower | Wider |\n"
    )
    if not short:
        reply += "\n**Needs a bigger move to profit** compared to a straddle, but costs less."
    else:
        reply += "\n**Wider profit zone** than a short straddle — underlying can move more before you lose."
    return reply


def _reply_spreads(ctx: dict) -> str:
    return (
        "## Bull Call Spread / Bear Put Spread\n\n"
        "**Vertical spreads** are defined-risk directional strategies:\n\n"
        "**Bull Call Spread** (bullish view):\n"
        "- BUY lower-strike call\n"
        "- SELL higher-strike call\n"
        "- Net DEBIT | Limited profit | Limited loss\n"
        "- Max profit = (high strike − low strike − net debit) × lot size\n"
        "- Max loss = net debit paid\n\n"
        "**Bear Put Spread** (bearish view):\n"
        "- BUY higher-strike put\n"
        "- SELL lower-strike put\n"
        "- Net DEBIT | Limited profit | Limited loss\n"
        "- Max profit = (high strike − low strike − net debit) × lot size\n"
        "- Max loss = net debit paid\n\n"
        "**Why use spreads?**\n"
        "- Cheaper than buying a naked option\n"
        "- Defined max loss — no unlimited downside\n"
        "- Good when you're directional but not aggressive"
    )


def _reply_butterfly(ctx: dict) -> str:
    return (
        "## Butterfly Spread\n\n"
        "A **low-cost neutral strategy** — profits if the underlying pins near ATM at expiry.\n\n"
        "**Call Butterfly Structure:**\n"
        "- BUY 1 lower call (ATM − wing)\n"
        "- SELL 2 ATM calls\n"
        "- BUY 1 higher call (ATM + wing)\n\n"
        "**P&L:**\n"
        "- Max profit: ATM at expiry (wings cancel out, body is worth maximum)\n"
        "- Max loss: small net debit (or small credit for a short butterfly)\n"
        "- Very low cost, very defined risk\n\n"
        "**vs Iron Condor:**\n"
        "| | Butterfly | Iron Condor |\n"
        "|--|--|--|\n"
        "| Legs | 3 strikes | 4 strikes |\n"
        "| Best if | Stays at ATM | Stays in range |\n"
        "| Cost | Small debit | Credit |\n"
        "| Complexity | Medium | High |"
    )


def _reply_covered_call(ctx: dict) -> str:
    return (
        "## Covered Call\n\n"
        "You **own 100+ shares** of a stock and **sell an OTM call** against them.\n\n"
        "**Purpose:** Generate extra income (the call premium) on a stock you already hold.\n\n"
        "**P&L:**\n"
        "- If stock stays below call strike: you keep the premium as profit\n"
        "- If stock rises above call strike: your stock gets called away (sold at strike) — you miss the upside\n"
        "- Downside still exists: the sold call only partially offsets a stock decline\n\n"
        "**Note:** Our backtester models only the option leg (selling OTM call) — the underlying stock P&L is not included.\n\n"
        "**Best for:** Slightly bullish to neutral outlook; long-term holders wanting to reduce cost basis."
    )


def _reply_greeks(ctx: dict, greek: Optional[str] = None) -> str:
    greeks = (ctx.get("analysis") or {}).get("greeks") or {}

    defs = {
        "delta": (
            "## Delta (Δ)\n\n"
            "Delta measures how much the option price changes for a ₹1 move in the underlying.\n\n"
            "| Option Type | Delta Range | When to Use |\n|--|--|--|\n"
            "| Deep ITM Call | +0.7 to +1.0 | Strong bullish — behaves like holding the stock |\n"
            "| ATM Call | ~+0.5 | Balanced bullish exposure |\n"
            "| OTM Call | 0.0 to +0.3 | Speculative / cheap lottery-style bet |\n"
            "| ATM Put | ~−0.5 | Balanced bearish or portfolio hedge |\n"
            "| OTM Put | −0.3 to 0.0 | Low-cost downside protection |\n"
            "| Deep ITM Put | −0.7 to −1.0 | Strong bearish — acts like short-selling |\n\n"
            "**Portfolio Delta** = your total directional exposure:\n"
            "- Positive delta: profits when market goes UP\n"
            "- Negative delta: profits when market goes DOWN\n"
            "- Delta-neutral: hedged against small moves"
        ),
        "gamma": (
            "## Gamma (Γ)\n\n"
            "Gamma is the **rate of change of Delta** — how fast your delta shifts as the underlying moves.\n\n"
            "- High gamma (near ATM, near expiry): delta changes rapidly → position is sensitive to moves\n"
            "- Low gamma (deep ITM/OTM, far from expiry): delta is stable\n\n"
            "**Gamma risk:** Near expiry, ATM options have huge gamma — small moves cause large P&L swings.\n"
            "**Short gamma positions** (sellers) are most at risk on expiry day."
        ),
        "theta": (
            "## Theta (Θ)\n\n"
            "Theta is **time decay** — how much an option loses value each calendar day.\n\n"
            "- Long options: **negative theta** (position loses value every day the underlying doesn't move)\n"
            "- Short options: **positive theta** (position gains value every day — time is your friend)\n\n"
            "**Time decay accelerates** in the last 30 days before expiry.\n\n"
            "**Iron Condor/Short Straddle:** High positive theta is a key attraction of selling strategies."
        ),
        "vega": (
            "## Vega (ν)\n\n"
            "Vega measures sensitivity to **Implied Volatility (IV)**. Shows P&L change per 1% move in IV.\n\n"
            "- Long options: **positive vega** (rising IV benefits you)\n"
            "- Short options: **negative vega** (rising IV hurts you)\n\n"
            "**India Volatility Index (India VIX):** Key benchmark for NIFTY option IV.\n"
            "- High VIX (>20): options are expensive — good time to sell premium\n"
            "- Low VIX (<12): options are cheap — good time to buy premium\n\n"
            "**Vega risk:** If IV collapses after you buy a straddle, you can lose money even if the market moves."
        ),
        "rho": (
            "## Rho (ρ)\n\n"
            "Rho measures sensitivity to the **risk-free interest rate** (1% change in rate).\n\n"
            "- Much smaller effect than Delta/Theta/Vega in practice\n"
            "- Calls have positive rho (benefit from rate rises); puts have negative rho\n"
            "- Matters most for long-dated options (LEAPS) — less critical for monthly NIFTY options\n\n"
            "**India context:** We use 7% (10-year G-Sec) as the risk-free rate."
        ),
    }

    if greek and greek in defs:
        reply = defs[greek]
        if greeks and greek in greeks:
            val = greeks[greek]
            reply += f"\n\n**Your current portfolio {greek.capitalize()}:** `{val:.4f}`"
        return reply

    # General Greeks overview
    reply = "## The Greeks\n\nFive numbers that fully describe your option risk:\n\n"
    for g, text in [
        ("delta", "**Δ Delta** — directional exposure (₹1 move in underlying)"),
        ("gamma", "**Γ Gamma** — how fast delta changes"),
        ("theta", "**Θ Theta** — daily time decay in ₹"),
        ("vega",  "**ν Vega** — sensitivity to 1% change in IV"),
        ("rho",   "**ρ Rho** — sensitivity to 1% change in interest rate"),
    ]:
        val = f" → **{greeks[g]:.4f}**" if g in greeks else ""
        reply += f"- {text}{val}\n"

    if not greeks:
        reply += "\nBuild a strategy and click **Analyse Strategy** to see your live Greeks."

    return reply


def _reply_iv(ctx: dict) -> str:
    hv = ctx.get("hv30_pct")
    reply = (
        "## Implied Volatility (IV)\n\n"
        "IV is the **market's expectation of future volatility** embedded in option prices.\n\n"
        "- Derived by solving Black-Scholes backwards from the market price\n"
        "- High IV → options are expensive (buy less, sell more)\n"
        "- Low IV → options are cheap (buy more, sell less)\n\n"
        "**IV vs Historical Volatility (HV):**\n"
        "| | HV (Realized) | IV (Implied) |\n"
        "|--|--|--|\n"
        "| What | Actual past volatility | Expected future volatility |\n"
        "| Source | Price history | Options market price |\n"
        "| Use | Calibrate models | Gauge option expensiveness |\n\n"
        "**IV Percentile / IV Rank:** Compare current IV to its 52-week range to judge if options are cheap or expensive.\n"
    )
    if hv:
        reply += f"\n**Your {ctx.get('symbol','')} HV30:** {hv:.1f}% (30-day historical volatility, annualised)"
    return reply


def _reply_breakeven(ctx: dict) -> str:
    payoff = (ctx.get("analysis") or {}).get("payoff") or {}
    be = payoff.get("breakevens") or []
    spot = ctx.get("spot")

    reply = (
        "## Breakeven Point(s)\n\n"
        "The spot price at expiry where your strategy makes **exactly ₹0**.\n\n"
        "- **Above upper breakeven:** Loss for credit spreads / profit for long calls\n"
        "- **Below lower breakeven:** Loss for credit spreads / profit for long puts\n"
        "- **Between breakevens:** Profit zone for Iron Condors / Short Strangles\n\n"
        "**Formula (ATM Long Call):** Strike + Premium paid\n"
        "**Formula (Short Straddle):** ATM strike ± total premium collected\n"
    )

    if be and spot:
        reply += f"\n**Your breakevens:**\n"
        for b in be:
            dist = abs(b - spot)
            pct  = dist / spot * 100
            direction = "above" if b > spot else "below"
            reply += f"- ₹{b:,.0f} ({pct:.1f}% {direction} current spot ₹{spot:,.0f})\n"
    elif not be:
        reply += "\nRun **Analyse Strategy** to calculate your breakevens."
    return reply


def _reply_var(ctx: dict) -> str:
    return (
        "## Value at Risk (VaR)\n\n"
        "VaR answers: **'What's the worst I could lose with X% confidence over N days?'**\n\n"
        "**How ours works:**\n"
        "1. Simulate 10,000 possible underlying price paths using **Geometric Brownian Motion**\n"
        "2. Reprice all legs at each simulated spot\n"
        "3. Sort the P&L outcomes — the 5th percentile (at 95% confidence) is the **95% VaR**\n\n"
        "**CVaR (Conditional VaR):** Average loss in the worst 5% of scenarios — more conservative than VaR.\n\n"
        "**Key inputs:**\n"
        "- Horizon: how many days forward (default: 5)\n"
        "- Confidence: 95% = worst-case in 1 out of 20 days\n"
        "- Sigma: historical volatility used to simulate price paths\n\n"
        "Go to the **Risk Analysis** tab to run VaR on your current strategy."
    )


def _reply_scenario(ctx: dict) -> str:
    return (
        "## Scenario Analysis\n\n"
        "A 2D grid showing estimated P&L under **different price and volatility shocks**.\n\n"
        "**Rows:** Price shocks (−15% to +15%)\n"
        "**Columns:** IV shocks (−10% to +10%)\n\n"
        "**How to read it:**\n"
        "- **Green cells** = profit under that scenario\n"
        "- **Red cells** = loss under that scenario\n"
        "- Darker colour = larger magnitude\n\n"
        "**Why it matters:**\n"
        "- Lets you stress-test before entering a trade\n"
        "- Shows if your trade is more sensitive to price moves or IV changes\n"
        "- Useful for planning exit points\n\n"
        "Go to the **Risk Analysis** tab to see your strategy's scenario matrix."
    )


def _reply_lot_size(ctx: dict) -> str:
    return (
        "## NSE Lot Sizes\n\n"
        "Each futures/options contract covers a fixed number of shares (1 lot):\n\n"
        "| Underlying | Lot Size |\n"
        "|--|--|\n"
        "| NIFTY 50 | **75** |\n"
        "| BANK NIFTY | **30** |\n"
        "| FINNIFTY | **40** |\n"
        "| MIDCPNIFTY | **75** |\n"
        "| SENSEX | **10** |\n"
        "| BANKEX | **15** |\n\n"
        "**Example:** 1 lot of NIFTY Iron Condor at ₹100 net credit = ₹100 × 75 = ₹7,500 collected\n\n"
        "Lot sizes are set by SEBI/NSE and revised periodically to keep notional value consistent."
    )


def _reply_expiry(ctx: dict) -> str:
    return (
        "## NSE Options Expiry\n\n"
        "**Monthly expiry:** Last Thursday of each calendar month\n"
        "**Weekly expiry:** Available for NIFTY (every Thursday) and BANKNIFTY (every Wednesday)\n\n"
        "**On expiry day:**\n"
        "- European-style contracts settle at the **Final Settlement Price** (spot index closing)\n"
        "- No early exercise possible (unlike American-style stock options in the US)\n"
        "- ITM options are cash-settled — the intrinsic value is credited/debited\n"
        "- OTM options expire worthless\n\n"
        "**Rollover:** Many traders roll positions 3–5 days before expiry to avoid high gamma risk."
    )


def _reply_black_scholes(ctx: dict) -> str:
    return (
        "## Black-Scholes Model\n\n"
        "The mathematical formula used to price European options. Our engine uses it for all NIFTY/BANKNIFTY pricing.\n\n"
        "**Inputs:** Spot (S), Strike (K), Time to expiry (T), Risk-free rate (r), Volatility (σ)\n\n"
        "**Call price:** `C = S·N(d₁) − K·e^(−rT)·N(d₂)`\n\n"
        "**Assumptions:**\n"
        "- Log-normally distributed returns\n"
        "- No dividends\n"
        "- Constant volatility (real markets have a *volatility smile*)\n"
        "- European-style (no early exercise) ✓ — correct for NIFTY/BANKNIFTY\n\n"
        "**Limitations:**\n"
        "- Doesn't capture fat tails (rare large moves)\n"
        "- IV in practice varies by strike (skew) and expiry (term structure)\n"
        "- Works best for near-the-money, near-term options"
    )


def _reply_strategy_comparison(ctx: dict) -> str:
    return (
        "## Strategy Comparison\n\n"
        "| Strategy | View | Risk | Reward | Key driver |\n"
        "|--|--|--|--|--|\n"
        "| Long Call | Strong bullish | Limited | Unlimited | Delta, Vega |\n"
        "| Long Put | Strong bearish | Limited | Limited | Delta, Vega |\n"
        "| Short Call | Neutral/bearish | Unlimited | Limited | Theta |\n"
        "| Short Put | Neutral/bullish | Large | Limited | Theta |\n"
        "| Long Straddle | Big move (any dir) | Limited | Unlimited | Vega, Delta |\n"
        "| Short Straddle | No move | Unlimited | Limited | Theta, Delta |\n"
        "| Long Strangle | Big move (any dir) | Limited | Unlimited | Vega, Delta |\n"
        "| Short Strangle | Range-bound | Large | Limited | Theta |\n"
        "| Bull Call Spread | Moderately bullish | Limited | Limited | Delta |\n"
        "| Bear Put Spread | Moderately bearish | Limited | Limited | Delta |\n"
        "| Iron Condor | Range-bound | Limited | Limited | Theta, Vega |\n"
        "| Butterfly | Stays at ATM | Limited | Limited | Theta |\n"
        "| Covered Call | Neutral/slightly up | Downside of stock | Limited | Theta |"
    )


def _reply_risk_management(ctx: dict) -> str:
    spot = ctx.get("spot")
    payoff = (ctx.get("analysis") or {}).get("payoff") or {}
    ml = payoff.get("max_loss")

    reply = (
        "## Risk Management for Options\n\n"
        "**1. Define your maximum loss before entering**\n"
        "Never trade strategies with undefined max loss (naked short calls/puts) without a stop-loss.\n\n"
        "**2. Position sizing**\n"
        "- Never risk more than 2–5% of your capital on a single trade\n"
        "- Adjust number of lots to keep max loss within tolerance\n\n"
        "**3. Breakeven awareness**\n"
        "Know exactly where the underlying needs to be at expiry for you to lose money.\n\n"
        "**4. Stop-loss rules**\n"
        "- Credit strategies: exit if the position loses 2× the premium collected\n"
        "- Debit strategies: exit if 50% of premium paid is lost\n\n"
        "**5. Avoid holding through high-IV events**\n"
        "Budget, RBI policy, elections, earnings — IV spikes can cause large losses even without a big price move.\n"
    )
    if ml:
        reply += f"\n**Your current max loss: ₹{abs(ml):,.0f}** — ensure this fits your risk budget."
    return reply


def _reply_backtest(ctx: dict) -> str:
    return (
        "## Backtesting Options Strategies\n\n"
        "The **Backtest tab** runs an event-driven simulation on historical price data.\n\n"
        "**How it works:**\n"
        "1. For each monthly expiry in your date range, it enters the strategy ~30 DTE\n"
        "2. Prices legs using Black-Scholes with the historical 30-day HV as IV proxy\n"
        "3. Exits at expiry (or earlier if you set Roll DTE > 0)\n"
        "4. Calculates P&L after slippage (0.3% of premium) and commission (₹20/lot)\n\n"
        "**Metrics explained:**\n"
        "- **Win Rate:** % of months the trade was profitable\n"
        "- **Profit Factor:** Total wins ÷ total losses (>1.5 is good)\n"
        "- **Sharpe Ratio:** Risk-adjusted return (monthly, annualised ×√12)\n"
        "- **Sortino Ratio:** Like Sharpe but only penalises downside volatility\n"
        "- **Max Drawdown:** Largest peak-to-trough drop in cumulative P&L\n\n"
        "**Limitations:**\n"
        "- Uses HV30 as IV proxy (real option prices may differ due to IV skew)\n"
        "- Monthly contracts only (no weekly data)\n"
        "- No early assignment risk (European-style settlement assumed)"
    )


def _reply_help(ctx: dict) -> str:
    has_strategy = bool((ctx.get("analysis") or {}).get("payoff"))
    reply = (
        "## Options AI Assistant — What I can help with\n\n"
        "**Strategy explanations:**\n"
        "- \"What is an Iron Condor?\"\n"
        "- \"Explain Long Straddle vs Short Strangle\"\n"
        "- \"When should I use a Bull Call Spread?\"\n\n"
        "**Greeks:**\n"
        "- \"Explain Delta\" / \"What is Theta?\"\n"
        "- \"Explain my strategy Greeks\"\n\n"
        "**Your current position:**\n"
        "- \"Why is my net premium negative?\"\n"
        "- \"Explain my breakevens\"\n"
        "- \"How much can I lose?\"\n\n"
        "**Education:**\n"
        "- \"What is IV?\" / \"Explain Black-Scholes\"\n"
        "- \"How does backtesting work?\"\n"
        "- \"What lot sizes does NSE use?\"\n"
        "- \"Compare all strategies\"\n"
        "- \"Explain risk management\"\n"
    )
    if not has_strategy:
        reply += "\n**Tip:** Fetch NIFTY spot + build a strategy to get context-aware answers about your position."
    return reply


# ── Main router ────────────────────────────────────────────────────────────────

def chat_reply(user_message: str, ctx: dict) -> str:
    """
    Route the user's message to the right response generator.
    Returns a markdown-formatted reply string.
    """
    q = user_message.lower().strip()

    # ── Greetings / Help ─────────────────────────────────────────────────────
    if _contains(q, "hello", "hi ", "hey ", "hii", "greet"):
        name = ctx.get("symbol", "")
        intro = f"Hey! I'm your options assistant for {name}. " if name else "Hey! I'm your options strategy assistant. "
        return intro + "Ask me about strategies, Greeks, or your current position. Type **help** to see what I can do."

    if _contains(q, "help", "what can you", "what do you", "commands", "topics"):
        return _reply_help(ctx)

    # ── Net Premium ──────────────────────────────────────────────────────────
    if _contains(q, "net premium", "premium negative", "premium positive", "credit", "debit",
                 "why negative", "why positive", "what is net premium"):
        return _reply_net_premium(ctx)

    # ── Strategy explanations ─────────────────────────────────────────────────
    if _contains(q, "iron condor", "condor"):
        return _reply_iron_condor(ctx)

    if _contains(q, "short straddle"):
        return _reply_straddle(ctx, short=True)

    if _contains(q, "long straddle", "straddle"):
        return _reply_straddle(ctx, short=False)

    if _contains(q, "short strangle"):
        return _reply_strangle(ctx, short=True)

    if _contains(q, "long strangle", "strangle"):
        return _reply_strangle(ctx, short=False)

    if _contains(q, "bull call spread", "bear put spread", "vertical spread", "spread"):
        return _reply_spreads(ctx)

    if _contains(q, "butterfly"):
        return _reply_butterfly(ctx)

    if _contains(q, "covered call"):
        return _reply_covered_call(ctx)

    # ── Greeks ────────────────────────────────────────────────────────────────
    if _contains(q, "delta"):
        return _reply_greeks(ctx, "delta")

    if _contains(q, "gamma"):
        return _reply_greeks(ctx, "gamma")

    if _contains(q, "theta", "time decay", "time value"):
        return _reply_greeks(ctx, "theta")

    if _contains(q, "vega", "volatility sensitivity"):
        return _reply_greeks(ctx, "vega")

    if _contains(q, "rho", "interest rate"):
        return _reply_greeks(ctx, "rho")

    if _contains(q, "greek", "delta gamma theta vega"):
        return _reply_greeks(ctx)

    # ── Volatility ────────────────────────────────────────────────────────────
    if _contains(q, "implied vol", "iv ", " iv", "implied volatility", "historical vol",
                 "hv30", "vix", "volatility"):
        return _reply_iv(ctx)

    # ── Key metrics ───────────────────────────────────────────────────────────
    if _contains(q, "breakeven", "break even", "break-even"):
        return _reply_breakeven(ctx)

    if _contains(q, "var", "value at risk", "cvar", "monte carlo"):
        return _reply_var(ctx)

    if _contains(q, "scenario", "stress test", "what if"):
        return _reply_scenario(ctx)

    if _contains(q, "max profit", "max loss", "maximum profit", "maximum loss", "profit", "loss"):
        payoff = (ctx.get("analysis") or {}).get("payoff") or {}
        mp = payoff.get("max_profit")
        ml = payoff.get("max_loss")
        if mp is not None or ml is not None:
            parts = ["**Your strategy P&L limits:**"]
            if mp is not None:
                parts.append(f"- Max Profit: ₹{mp:,.0f}" + (" (unlimited)" if mp is None else ""))
            if ml is not None:
                parts.append(f"- Max Loss: ₹{abs(ml):,.0f}")
            be = payoff.get("breakevens") or []
            if be:
                parts.append("- Breakevens: " + " / ".join(f"₹{b:,.0f}" for b in be))
            return "\n".join(parts)
        return (
            "Build a strategy and click **Analyse Strategy** to see your max profit and max loss numbers.\n\n"
            "In general:\n"
            "- **Debit strategies** (Long Call, Straddle): max loss = premium paid, profit = unlimited or capped\n"
            "- **Credit strategies** (Iron Condor, Short Straddle): max profit = premium collected, loss = wing width or unlimited"
        )

    # ── Market knowledge ─────────────────────────────────────────────────────
    if _contains(q, "lot size", "lot", "contract size"):
        return _reply_lot_size(ctx)

    if _contains(q, "expiry", "expiration", "settlement", "thursday", "last thursday"):
        return _reply_expiry(ctx)

    if _contains(q, "black-scholes", "black scholes", "bs model", "pricing model", "formula"):
        return _reply_black_scholes(ctx)

    if _contains(q, "compare", "comparison", "which strategy", "best strategy", "all strategies"):
        return _reply_strategy_comparison(ctx)

    if _contains(q, "risk manage", "position size", "stop loss", "stop-loss", "capital"):
        return _reply_risk_management(ctx)

    if _contains(q, "backtest", "back test", "historical", "simulate", "past"):
        return _reply_backtest(ctx)

    # ── Context-aware catch-all ───────────────────────────────────────────────
    ctx_block = _context_block(ctx)
    if _contains(q, "my strategy", "my position", "explain my", "current strategy",
                 "my greeks", "my trade"):
        if ctx_block:
            return f"**Your current strategy:**\n\n{ctx_block}\n\nAsk me anything specific — breakevens, Greeks, max loss, etc."
        return "No strategy loaded yet. Fetch a spot price, add legs, and click **Analyse Strategy** first."

    if _contains(q, "good strategy", "best for", "range bound", "neutral", "bullish", "bearish",
                 "low volatility", "high volatility"):
        if "range" in q or "neutral" in q or "low vol" in q:
            return (
                "**For a range-bound / neutral market:**\n\n"
                "1. **Iron Condor** — sell OTM strangle, buy protection wings. Best reward/risk for range markets.\n"
                "2. **Short Strangle** — higher premium, but naked risk beyond strikes.\n"
                "3. **Butterfly** — profits if underlying pins exactly at ATM.\n\n"
                "All three benefit from **time decay (Theta)**. Enter when IV is elevated so you collect more premium.\n"
                "Try clicking **Iron Condor** in Quick Add Strategy to see a live example."
            )
        if "bullish" in q or "upside" in q:
            return (
                "**For a bullish view:**\n\n"
                "1. **Long Call** — simple, defined risk, unlimited upside\n"
                "2. **Bull Call Spread** — cheaper than long call, capped upside\n"
                "3. **Short Put** — collect premium if you're willing to buy the dip\n\n"
                "Choose based on how strong and how fast your bullish view is."
            )
        if "bearish" in q or "downside" in q:
            return (
                "**For a bearish view:**\n\n"
                "1. **Long Put** — simple, defined risk, large profit if market falls\n"
                "2. **Bear Put Spread** — cheaper, but capped profit\n"
                "3. **Short Call** — collect premium if you're mildly bearish (unlimited risk!)\n\n"
                "Use a Bear Put Spread if you want defined risk on a moderate bearish view."
            )

    # ── AI fallback for unrecognised questions ────────────────────────────────
    return _AI_FALLBACK_REPLY   # sentinel — caller must resolve async


# Sentinel returned when a question needs AI; the route handler upgrades this.
_AI_FALLBACK_REPLY = "__AI_FALLBACK__"
