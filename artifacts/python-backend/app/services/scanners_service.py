import asyncio
import logging
import os
import random
import string
from datetime import datetime
from typing import Any, Optional

from .price_service import PriceService
from . import market_cache_service as _mcs
from .indicators import (
    calculate_ema, calculate_sma, calculate_rsi,
    calculate_macd, calculate_bollinger_bands, calculate_atr,
    calculate_vwap,
)
from ..lib.universe import build_universe

logger = logging.getLogger(__name__)

VALID_OPERATORS = {"gt", "gte", "lt", "lte", "eq", "crosses_above", "crosses_below"}

# ── Tunables (no longer magic — surfaced in /scanners metadata) ───────────────
EQ_TOLERANCE_PCT       = 0.1      # "eq" operator: |a-b| / max(|b|,1) < 0.1%
RATE_LIMIT_DELAY_S     = 0.35     # live-path delay between symbols
# Bounded concurrency for the closed-market fast path. Scanning the full
# ~2,000-symbol "ALL" universe with an unbounded gather would fire 2,000
# simultaneous fetches at any cache-cold symbols and risk a provider ban, so
# cap it. Disk-cached symbols still complete near-instantly. Env-tunable.
SCANNER_SCAN_CONCURRENCY = int(os.environ.get("SCANNER_SCAN_CONCURRENCY", "16"))
WINDOW_52W             = 252      # trading days that constitute "52 weeks"
DEFAULT_FETCH_DAYS     = 90       # baseline bars when no big-period indicator used
BUFFER_MULT            = 3        # indicator seeding buffer multiplier
MAX_FETCH_DAYS         = 500      # hard cap on per-symbol fetch


def _cid() -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=7))


DEFAULT_SCANNERS_DEF = [
    {
        "name": "EMA Golden Cross (20/50)",
        "category": "Trend",
        "description": "EMA20 just crossed above EMA50 — classic medium-term buy signal",
        "universe": ["NIFTY100", "MIDCAP"],
        "logic": "AND",
        "conditions": [
            {"left": {"type": "indicator", "indicator": "EMA", "period": 20}, "operator": "crosses_above", "right": {"type": "indicator", "indicator": "EMA", "period": 50}},
            {"left": {"type": "indicator", "indicator": "RSI", "period": 14}, "operator": "gt",            "right": {"type": "number", "value": 45}},
        ],
    },
    {
        "name": "RSI Oversold + EMA50 Support",
        "category": "Oscillators",
        "description": "RSI below 35 while price is above EMA50 — dip buy setup",
        "universe": ["NIFTY100", "MIDCAP", "SMALLCAP"],
        "logic": "AND",
        "conditions": [
            {"left": {"type": "indicator", "indicator": "RSI", "period": 14}, "operator": "lt",  "right": {"type": "number", "value": 35}},
            {"left": {"type": "indicator", "indicator": "CLOSE"},             "operator": "gt",  "right": {"type": "indicator", "indicator": "EMA", "period": 50}},
        ],
    },
    {
        "name": "Momentum Breakout",
        "category": "Momentum",
        "description": "Price above EMA200, RSI 55-72, volume spike ≥150%",
        "universe": ["NIFTY100"],
        "logic": "AND",
        "conditions": [
            {"left": {"type": "indicator", "indicator": "CLOSE"},             "operator": "gt",  "right": {"type": "indicator", "indicator": "EMA", "period": 200}},
            {"left": {"type": "indicator", "indicator": "RSI", "period": 14}, "operator": "gte", "right": {"type": "number", "value": 55}},
            {"left": {"type": "indicator", "indicator": "RSI", "period": 14}, "operator": "lte", "right": {"type": "number", "value": 72}},
            {"left": {"type": "indicator", "indicator": "VOLUME_RATIO"},      "operator": "gte", "right": {"type": "number", "value": 150}},
        ],
    },
    {
        "name": "Near 52-Week High (within 5%)",
        "category": "Momentum",
        "description": "Price within 5% of true 52-week high — momentum continuation",
        "universe": ["NIFTY100", "MIDCAP"],
        "logic": "AND",
        "conditions": [
            {"left": {"type": "indicator", "indicator": "PCT_52W_HIGH"}, "operator": "gte", "right": {"type": "number", "value": -5}},
            {"left": {"type": "indicator", "indicator": "CLOSE"},        "operator": "gt",  "right": {"type": "indicator", "indicator": "EMA", "period": 50}},
        ],
    },
    {
        "name": "Bollinger Band Lower Bounce",
        "category": "Mean Reversion",
        "description": "Price near/below BB lower, RSI oversold — mean reversion buy",
        "universe": ["NIFTY100", "MIDCAP", "SMALLCAP"],
        "logic": "AND",
        "conditions": [
            {"left": {"type": "indicator", "indicator": "CLOSE"},                "operator": "lte", "right": {"type": "indicator", "indicator": "BB_LOWER", "period": 20}},
            {"left": {"type": "indicator", "indicator": "RSI", "period": 14},    "operator": "lt",  "right": {"type": "number", "value": 40}},
        ],
    },
    {
        "name": "MACD Bullish Crossover",
        "category": "Oscillators",
        "description": "MACD line just crossed above signal line — fresh buy signal",
        "universe": ["NIFTY100", "MIDCAP"],
        "logic": "AND",
        "conditions": [
            {"left": {"type": "indicator", "indicator": "MACD"}, "operator": "crosses_above", "right": {"type": "indicator", "indicator": "MACD_SIGNAL"}},
        ],
    },
    {
        "name": "Superb Momentum (All EMAs aligned)",
        "category": "Trend",
        "description": "Price > EMA9 > EMA20 > EMA50 > EMA200 — textbook bull trend",
        "universe": ["NIFTY100"],
        "logic": "AND",
        "conditions": [
            {"left": {"type": "indicator", "indicator": "CLOSE"},           "operator": "gt", "right": {"type": "indicator", "indicator": "EMA", "period": 9}},
            {"left": {"type": "indicator", "indicator": "EMA", "period": 9}, "operator": "gt", "right": {"type": "indicator", "indicator": "EMA", "period": 20}},
            {"left": {"type": "indicator", "indicator": "EMA", "period": 20},"operator": "gt", "right": {"type": "indicator", "indicator": "EMA", "period": 50}},
            {"left": {"type": "indicator", "indicator": "EMA", "period": 50},"operator": "gt", "right": {"type": "indicator", "indicator": "EMA", "period": 200}},
        ],
    },
    {
        "name": "Volume Spike Breakout",
        "category": "Volume",
        "description": "Volume ≥ 300% of 20-day average on a green candle",
        "universe": ["NIFTY100", "MIDCAP", "SMALLCAP"],
        "logic": "AND",
        "conditions": [
            {"left": {"type": "indicator", "indicator": "VOLUME_RATIO"}, "operator": "gte", "right": {"type": "number", "value": 300}},
            {"left": {"type": "indicator", "indicator": "CHANGE_PCT"},   "operator": "gt",  "right": {"type": "number", "value": 0}},
        ],
    },

    # ── Volume category ──────────────────────────────────────────────
    # Nine new scanners powered by the volume helpers (HIGHEST_VOLUME,
    # VOLUME_ZSCORE, WICK_RATIO, HIGHER_LOWS_COUNT, VOLUME_TREND_UP).
    # All carry category="Volume" so the UI can group them in a tab
    # separate from the indicator/pattern scanners.
    #
    # Three of the original 12 (Opening-Volume Blast, High-Vol Bullish
    # Engulfing, Delivery % Spike) are deferred — they need intraday
    # 15-min bars, a candlestick-pattern indicator framework, and per-
    # symbol delivery data respectively. None of those exist today.

    {
        "name": "RVOL Spike (Bullish)",
        "category": "Volume",
        "description": "Today's volume > 2× 20-day average AND price up — classic intraday CALL signal",
        "universe": ["NIFTY100", "MIDCAP", "SMALLCAP"],
        "logic": "AND",
        "conditions": [
            {"left": {"type": "indicator", "indicator": "VOLUME_RATIO"}, "operator": "gt", "right": {"type": "number", "value": 200}},
            {"left": {"type": "indicator", "indicator": "CHANGE_PCT"},   "operator": "gt", "right": {"type": "number", "value": 0}},
        ],
    },
    {
        "name": "RVOL Spike (Bearish)",
        "category": "Volume",
        "description": "Today's volume > 2× 20-day average AND price down — classic intraday PUT signal",
        "universe": ["NIFTY100", "MIDCAP", "SMALLCAP"],
        "logic": "AND",
        "conditions": [
            {"left": {"type": "indicator", "indicator": "VOLUME_RATIO"}, "operator": "gt", "right": {"type": "number", "value": 200}},
            {"left": {"type": "indicator", "indicator": "CHANGE_PCT"},   "operator": "lt", "right": {"type": "number", "value": 0}},
        ],
    },
    {
        "name": "Volume Breakout Before Price",
        "category": "Volume",
        "description": "Volume > heaviest of last 10 days AND price still below 20-day high — early-warning signal",
        "universe": ["NIFTY100", "MIDCAP", "SMALLCAP"],
        "logic": "AND",
        "conditions": [
            {"left": {"type": "indicator", "indicator": "VOLUME"},
             "operator": "gt",
             "right": {"type": "indicator", "indicator": "HIGHEST_VOLUME", "period": 10}},
            {"left": {"type": "indicator", "indicator": "CLOSE"},
             "operator": "lt",
             "right": {"type": "indicator", "indicator": "HIGHEST_HIGH", "period": 20}},
        ],
    },
    {
        "name": "Accumulation (Quiet Heavy Volume)",
        "category": "Volume",
        "description": "Price barely moves (|Δ| < 2%) but volume > 3× average — institutions absorbing supply",
        "universe": ["NIFTY100", "MIDCAP", "SMALLCAP"],
        "logic": "AND",
        "conditions": [
            {"left": {"type": "indicator", "indicator": "VOLUME_RATIO"}, "operator": "gt",  "right": {"type": "number", "value": 300}},
            {"left": {"type": "indicator", "indicator": "CHANGE_PCT"},   "operator": "lt",  "right": {"type": "number", "value": 2}},
            {"left": {"type": "indicator", "indicator": "CHANGE_PCT"},   "operator": "gt",  "right": {"type": "number", "value": -2}},
        ],
    },
    {
        "name": "Volume Dry-Up",
        "category": "Volume",
        "description": "Today's volume < 50% of 20-day average — often precedes strong breakouts after a correction",
        "universe": ["NIFTY100", "MIDCAP", "SMALLCAP"],
        "logic": "AND",
        "conditions": [
            {"left": {"type": "indicator", "indicator": "VOLUME_RATIO"}, "operator": "lt", "right": {"type": "number", "value": 50}},
        ],
    },
    {
        "name": "Hidden Accumulation (5-bar)",
        "category": "Volume",
        "description": "≥4 of last 5 bars had higher lows AND volume trend is rising — stealth accumulation",
        "universe": ["NIFTY100", "MIDCAP", "SMALLCAP"],
        "logic": "AND",
        "conditions": [
            {"left": {"type": "indicator", "indicator": "HIGHER_LOWS_COUNT", "period": 5},
             "operator": "gte",
             "right": {"type": "number", "value": 4}},
            {"left": {"type": "indicator", "indicator": "VOLUME_TREND_UP", "period": 5},
             "operator": "eq",
             "right": {"type": "number", "value": 1}},
        ],
    },
    {
        "name": "Breakout + Volume Confirmation",
        "category": "Volume",
        "description": "Close above 20-day high AND volume > 150% of average — the most reliable breakout filter",
        "universe": ["NIFTY100", "MIDCAP", "SMALLCAP"],
        "logic": "AND",
        "conditions": [
            {"left": {"type": "indicator", "indicator": "CLOSE"},
             "operator": "gt",
             "right": {"type": "indicator", "indicator": "HIGHEST_HIGH", "period": 20}},
            {"left": {"type": "indicator", "indicator": "VOLUME_RATIO"}, "operator": "gt", "right": {"type": "number", "value": 150}},
        ],
    },
    {
        "name": "VWAP Reclaim + Volume",
        "category": "Volume",
        "description": "Price crossed above VWAP today on volume > 2× average — strong intraday reversal",
        "universe": ["NIFTY100", "MIDCAP"],
        "logic": "AND",
        "conditions": [
            {"left": {"type": "indicator", "indicator": "CLOSE"}, "operator": "crosses_above", "right": {"type": "indicator", "indicator": "VWAP"}},
            {"left": {"type": "indicator", "indicator": "VOLUME_RATIO"}, "operator": "gt", "right": {"type": "number", "value": 200}},
        ],
    },
    {
        "name": "Unusual Volume (Z-Score ≥ 2)",
        "category": "Volume",
        "description": "Volume is ≥ 2 standard deviations above the 20-day mean — statistically abnormal activity",
        "universe": ["NIFTY100", "MIDCAP", "SMALLCAP"],
        "logic": "AND",
        "conditions": [
            {"left": {"type": "indicator", "indicator": "VOLUME_ZSCORE", "period": 20},
             "operator": "gte",
             "right": {"type": "number", "value": 2}},
        ],
    },
    {
        "name": "Volume Climax",
        "category": "Volume",
        "description": "Highest volume in 50 days + long wick (> 50% of range) — possible top/bottom reversal",
        "universe": ["NIFTY100", "MIDCAP", "SMALLCAP"],
        "logic": "AND",
        "conditions": [
            {"left": {"type": "indicator", "indicator": "VOLUME"},
             "operator": "gt",
             "right": {"type": "indicator", "indicator": "HIGHEST_VOLUME", "period": 50}},
            {"left": {"type": "indicator", "indicator": "WICK_RATIO"},
             "operator": "gt",
             "right": {"type": "number", "value": 50}},
        ],
    },

    # ── Pattern + Volume combinations ────────────────────────────────
    # Centralised candle patterns from app/lib/candle_patterns.py are
    # now first-class scanner indicators. These defaults pair the
    # highest-confidence patterns with a volume-confirmation filter —
    # the classic "real signal vs noise" combo most retail screeners
    # bake in. Boolean pattern indicators take values 0.0 / 1.0; we
    # compare with `eq 1` (also `gt 0` works).

    {
        "name": "High-Volume Bullish Engulfing",
        "category": "Pattern + Volume",
        "description": "Bullish Engulfing today AND volume > 150% of 20-day average — the classic confirmed reversal",
        "universe": ["NIFTY100", "MIDCAP", "SMALLCAP"],
        "logic": "AND",
        "conditions": [
            {"left": {"type": "indicator", "indicator": "BULLISH_ENGULFING"},
             "operator": "eq",
             "right": {"type": "number", "value": 1}},
            {"left": {"type": "indicator", "indicator": "VOLUME_RATIO"},
             "operator": "gt",
             "right": {"type": "number", "value": 150}},
        ],
    },
    {
        "name": "High-Volume Bearish Engulfing",
        "category": "Pattern + Volume",
        "description": "Bearish Engulfing today AND volume > 150% — confirmed reversal short setup",
        "universe": ["NIFTY100", "MIDCAP", "SMALLCAP"],
        "logic": "AND",
        "conditions": [
            {"left": {"type": "indicator", "indicator": "BEARISH_ENGULFING"},
             "operator": "eq",
             "right": {"type": "number", "value": 1}},
            {"left": {"type": "indicator", "indicator": "VOLUME_RATIO"},
             "operator": "gt",
             "right": {"type": "number", "value": 150}},
        ],
    },
    {
        "name": "Hammer at Support (Oversold)",
        "category": "Pattern + Volume",
        "description": "Hammer candle AND RSI < 35 AND volume > 120% — reversal at oversold support",
        "universe": ["NIFTY100", "MIDCAP", "SMALLCAP"],
        "logic": "AND",
        "conditions": [
            {"left": {"type": "indicator", "indicator": "HAMMER"},
             "operator": "eq",
             "right": {"type": "number", "value": 1}},
            {"left": {"type": "indicator", "indicator": "RSI", "period": 14},
             "operator": "lt",
             "right": {"type": "number", "value": 35}},
            {"left": {"type": "indicator", "indicator": "VOLUME_RATIO"},
             "operator": "gt",
             "right": {"type": "number", "value": 120}},
        ],
    },
    {
        "name": "Shooting Star at Resistance (Overbought)",
        "category": "Pattern + Volume",
        "description": "Shooting Star AND RSI > 70 AND volume > 120% — exhaustion top",
        "universe": ["NIFTY100", "MIDCAP", "SMALLCAP"],
        "logic": "AND",
        "conditions": [
            {"left": {"type": "indicator", "indicator": "SHOOTING_STAR"},
             "operator": "eq",
             "right": {"type": "number", "value": 1}},
            {"left": {"type": "indicator", "indicator": "RSI", "period": 14},
             "operator": "gt",
             "right": {"type": "number", "value": 70}},
            {"left": {"type": "indicator", "indicator": "VOLUME_RATIO"},
             "operator": "gt",
             "right": {"type": "number", "value": 120}},
        ],
    },
    {
        "name": "Inside Bar Squeeze",
        "category": "Pattern + Volume",
        "description": "Inside Bar (compression) AND today's volume < 70% of average — coiled spring before breakout",
        "universe": ["NIFTY100", "MIDCAP", "SMALLCAP"],
        "logic": "AND",
        "conditions": [
            {"left": {"type": "indicator", "indicator": "INSIDE_BAR"},
             "operator": "eq",
             "right": {"type": "number", "value": 1}},
            {"left": {"type": "indicator", "indicator": "VOLUME_RATIO"},
             "operator": "lt",
             "right": {"type": "number", "value": 70}},
        ],
    },

    # ── Hidden Gems category ────────────────────────────────────────
    # Fundamental-driven screens for undervalued small/mid caps.
    # Each scanner's RESULT rows are also enriched with `hiddenGemScore`
    # (0-100) + `hiddenGemBreakdown` because of the `category` field —
    # see _evaluate() in run_scanner. Note: these scanners trigger a
    # Yahoo `info` prefetch for the entire universe on first run within
    # any 12h window. First run on a fresh deploy is slow (~30-90s for
    # NIFTY100); subsequent runs are instant.

    {
        "name": "Small-Cap Multibagger Setup",
        "category": "Hidden Gems",
        "description": "Small/mid cap (₹500-5000 Cr) + low PE + high ROE + low debt — the classic hidden-gem profile",
        "universe": ["MIDCAP", "SMALLCAP"],
        "logic": "AND",
        "conditions": [
            {"left": {"type": "indicator", "indicator": "MARKET_CAP_CR"}, "operator": "gte", "right": {"type": "number", "value": 500}},
            {"left": {"type": "indicator", "indicator": "MARKET_CAP_CR"}, "operator": "lte", "right": {"type": "number", "value": 5000}},
            {"left": {"type": "indicator", "indicator": "PE_RATIO"},      "operator": "lt",  "right": {"type": "number", "value": 20}},
            {"left": {"type": "indicator", "indicator": "ROE"},           "operator": "gt",  "right": {"type": "number", "value": 15}},
            {"left": {"type": "indicator", "indicator": "DEBT_TO_EQUITY"},"operator": "lt",  "right": {"type": "number", "value": 0.5}},
        ],
    },
    {
        "name": "Quality Compounder",
        "category": "Hidden Gems",
        "description": "High ROE (>18%) + strong margin (>12%) + revenue growth (>15%) + low debt — the buy-and-hold profile",
        "universe": ["NIFTY100", "MIDCAP"],
        "logic": "AND",
        "conditions": [
            {"left": {"type": "indicator", "indicator": "ROE"},               "operator": "gt", "right": {"type": "number", "value": 18}},
            {"left": {"type": "indicator", "indicator": "PROFIT_MARGIN"},     "operator": "gt", "right": {"type": "number", "value": 12}},
            {"left": {"type": "indicator", "indicator": "REVENUE_GROWTH_YOY"},"operator": "gt", "right": {"type": "number", "value": 15}},
            {"left": {"type": "indicator", "indicator": "DEBT_TO_EQUITY"},    "operator": "lt", "right": {"type": "number", "value": 0.4}},
        ],
    },
    {
        "name": "Deep Value + Momentum",
        "category": "Hidden Gems",
        "description": "PE < 12 AND P/B < 2 AND price above 50-DMA AND volume > 120% — cheap stocks that are starting to move",
        "universe": ["NIFTY100", "MIDCAP", "SMALLCAP"],
        "logic": "AND",
        "conditions": [
            {"left": {"type": "indicator", "indicator": "PE_RATIO"},   "operator": "lt", "right": {"type": "number", "value": 12}},
            {"left": {"type": "indicator", "indicator": "PB_RATIO"},   "operator": "lt", "right": {"type": "number", "value": 2}},
            {"left": {"type": "indicator", "indicator": "CLOSE"},      "operator": "gt", "right": {"type": "indicator", "indicator": "EMA", "period": 50}},
            {"left": {"type": "indicator", "indicator": "VOLUME_RATIO"}, "operator": "gt", "right": {"type": "number", "value": 120}},
        ],
    },
    {
        "name": "Conservative Hidden Gem (Debt-Free Compounder)",
        "category": "Hidden Gems",
        "description": "Essentially debt-free (D/E < 0.2) + high ROE + positive FCF yield — capital-light businesses",
        "universe": ["MIDCAP", "SMALLCAP"],
        "logic": "AND",
        "conditions": [
            {"left": {"type": "indicator", "indicator": "DEBT_TO_EQUITY"}, "operator": "lt", "right": {"type": "number", "value": 0.2}},
            {"left": {"type": "indicator", "indicator": "ROE"},            "operator": "gt", "right": {"type": "number", "value": 15}},
            {"left": {"type": "indicator", "indicator": "FCF_YIELD"},      "operator": "gt", "right": {"type": "number", "value": 4}},
            {"left": {"type": "indicator", "indicator": "PE_RATIO"},       "operator": "lt", "right": {"type": "number", "value": 25}},
        ],
    },

    # ── Smart Money Concepts (SMC) category ──────────────────────────
    # Daily-bar structural SMC. Phase 1 = Fair Value Gaps (3-candle
    # imbalances). Detection in app/lib/smc.py is the single source of
    # truth shared with the chart's /smc overlay, so a screener hit is
    # always visible on the chart. NOTE: an FVG is a structural pattern,
    # not a buy/sell signal — these defaults pair it with a trend or
    # volume filter, the same "signal vs noise" combo the Pattern+Volume
    # scanners use.
    {
        "name": "Bullish FVG in Uptrend",
        "category": "Smart Money (SMC)",
        "description": "Fresh bullish Fair Value Gap while price holds above EMA50 — imbalance support inside an uptrend",
        "universe": ["NIFTY100", "MIDCAP"],
        "logic": "AND",
        "conditions": [
            {"left": {"type": "indicator", "indicator": "BULLISH_FVG"}, "operator": "eq", "right": {"type": "number", "value": 1}},
            {"left": {"type": "indicator", "indicator": "CLOSE"},       "operator": "gt", "right": {"type": "indicator", "indicator": "EMA", "period": 50}},
        ],
    },
    {
        "name": "Bearish FVG in Downtrend",
        "category": "Smart Money (SMC)",
        "description": "Fresh bearish Fair Value Gap while price is below EMA50 — imbalance resistance inside a downtrend",
        "universe": ["NIFTY100", "MIDCAP"],
        "logic": "AND",
        "conditions": [
            {"left": {"type": "indicator", "indicator": "BEARISH_FVG"}, "operator": "eq", "right": {"type": "number", "value": 1}},
            {"left": {"type": "indicator", "indicator": "CLOSE"},       "operator": "lt", "right": {"type": "indicator", "indicator": "EMA", "period": 50}},
        ],
    },
    {
        "name": "Bullish FVG + Volume",
        "category": "Smart Money (SMC)",
        "description": "Fresh bullish Fair Value Gap on volume > 150% of average — institutional displacement leaving an imbalance",
        "universe": ["NIFTY100", "MIDCAP", "SMALLCAP"],
        "logic": "AND",
        "conditions": [
            {"left": {"type": "indicator", "indicator": "BULLISH_FVG"},  "operator": "eq", "right": {"type": "number", "value": 1}},
            {"left": {"type": "indicator", "indicator": "VOLUME_RATIO"}, "operator": "gt", "right": {"type": "number", "value": 150}},
        ],
    },
    {
        "name": "Bullish CHoCH (Reversal)",
        "category": "Smart Money (SMC)",
        "description": "Change of Character up — first close back above structure after a downtrend; earliest reversal signal",
        "universe": ["NIFTY100", "MIDCAP"],
        "logic": "AND",
        "conditions": [
            {"left": {"type": "indicator", "indicator": "BULLISH_CHOCH"}, "operator": "eq", "right": {"type": "number", "value": 1}},
        ],
    },
    {
        "name": "Bullish BOS + Volume",
        "category": "Smart Money (SMC)",
        "description": "Break of Structure up confirmed by volume > 130% of average — trend continuation with participation",
        "universe": ["NIFTY100", "MIDCAP", "SMALLCAP"],
        "logic": "AND",
        "conditions": [
            {"left": {"type": "indicator", "indicator": "BULLISH_BOS"},  "operator": "eq", "right": {"type": "number", "value": 1}},
            {"left": {"type": "indicator", "indicator": "VOLUME_RATIO"}, "operator": "gt", "right": {"type": "number", "value": 130}},
        ],
    },
    {
        "name": "Bearish CHoCH (Reversal Warning)",
        "category": "Smart Money (SMC)",
        "description": "Change of Character down — first close below structure after an uptrend; early distribution warning",
        "universe": ["NIFTY100", "MIDCAP"],
        "logic": "AND",
        "conditions": [
            {"left": {"type": "indicator", "indicator": "BEARISH_CHOCH"}, "operator": "eq", "right": {"type": "number", "value": 1}},
        ],
    },
    {
        "name": "Sell-side Sweep (Reversal Long)",
        "category": "Smart Money (SMC)",
        "description": "Today's low pierced a prior swing low but closed back above it — stop-hunt then rejection, a bullish reversal cue",
        "universe": ["NIFTY100", "MIDCAP", "SMALLCAP"],
        "logic": "AND",
        "conditions": [
            {"left": {"type": "indicator", "indicator": "LIQUIDITY_SWEEP_LOW"}, "operator": "eq", "right": {"type": "number", "value": 1}},
        ],
    },
    {
        "name": "Bullish FVG in Discount",
        "category": "Smart Money (SMC)",
        "description": "Fresh bullish Fair Value Gap while price is in the discount half of its dealing range — buy-low imbalance",
        "universe": ["NIFTY100", "MIDCAP", "SMALLCAP"],
        "logic": "AND",
        "conditions": [
            {"left": {"type": "indicator", "indicator": "BULLISH_FVG"}, "operator": "eq", "right": {"type": "number", "value": 1}},
            {"left": {"type": "indicator", "indicator": "IN_DISCOUNT"}, "operator": "eq", "right": {"type": "number", "value": 1}},
        ],
    },
    {
        "name": "Discount + Bullish Order Block",
        "category": "Smart Money (SMC)",
        "description": "Price testing an unmitigated bullish order block while in discount — institutional demand zone in the buy region",
        "universe": ["NIFTY100", "MIDCAP", "SMALLCAP"],
        "logic": "AND",
        "conditions": [
            {"left": {"type": "indicator", "indicator": "AT_BULLISH_OB"}, "operator": "eq", "right": {"type": "number", "value": 1}},
            {"left": {"type": "indicator", "indicator": "IN_DISCOUNT"},   "operator": "eq", "right": {"type": "number", "value": 1}},
        ],
    },
    {
        "name": "Premium + Bearish Order Block",
        "category": "Smart Money (SMC)",
        "description": "Price testing an unmitigated bearish order block while in premium — institutional supply zone in the sell region",
        "universe": ["NIFTY100", "MIDCAP"],
        "logic": "AND",
        "conditions": [
            {"left": {"type": "indicator", "indicator": "AT_BEARISH_OB"}, "operator": "eq", "right": {"type": "number", "value": 1}},
            {"left": {"type": "indicator", "indicator": "IN_PREMIUM"},    "operator": "eq", "right": {"type": "number", "value": 1}},
        ],
    },
]


# ── Indicator categories used to compute the required look-back window ───────
# Period-based indicators: bars needed = period * BUFFER_MULT for stable seeding
_PERIOD_INDS = {
    "EMA", "SMA", "RSI", "BB_UPPER", "BB_MID", "BB_LOWER", "ATR",
    "AVG_VOLUME",
    # Volume-scanner helpers — bars needed = period * BUFFER_MULT for
    # stable rolling-window stats.
    "HIGHEST_VOLUME", "HIGHEST_HIGH", "LOWEST_LOW", "VOLUME_ZSCORE",
    "HIGHER_LOWS_COUNT", "VOLUME_TREND_UP",
}
# Fixed-window indicators: bars needed = WINDOW_52W
_WINDOW_52W_INDS = {"HIGH_52W", "LOW_52W", "PCT_52W_HIGH", "PCT_52W_LOW"}
# MACD: 26 + 9 = 35 bars minimum, * BUFFER_MULT for stable seeding
_MACD_INDS = {"MACD", "MACD_SIGNAL", "MACD_HIST"}

# Fundamental indicators (Yahoo Finance `info` dict, normalised + cached
# by app.services.fundamentals_service). Need no historical bars beyond
# whatever the scanner's technical conditions require, so they don't
# inflate the lookback window. Pre-fetched in run_scanner() via
# fundamentals.prefetch() when any condition uses one of these.
_FUNDAMENTAL_INDS = {
    "PE_RATIO", "PB_RATIO", "PEG_RATIO",
    "ROE", "ROCE", "DEBT_TO_EQUITY",
    "MARKET_CAP_CR", "PROFIT_MARGIN", "REVENUE_GROWTH_YOY",
    "EARNINGS_GROWTH_YOY", "FCF_YIELD",
}

# Candle-pattern indicators (boolean). Defined by name explicitly rather
# than implicitly to avoid accidentally accepting typos. Two-candle
# patterns need ≥ 2 bars of history; the default 90-day fetch is plenty.
_PATTERN_INDS = {
    # Single-candle
    "DOJI", "DRAGONFLY_DOJI", "GRAVESTONE_DOJI",
    "HAMMER", "INVERTED_HAMMER", "SHOOTING_STAR", "HANGING_MAN",
    "BULLISH_MARUBOZU", "BEARISH_MARUBOZU", "SPINNING_TOP",
    # Two-candle
    "BULLISH_ENGULFING", "BEARISH_ENGULFING",
    "BULLISH_HARAMI",    "BEARISH_HARAMI",
    "INSIDE_BAR", "OUTSIDE_BAR",
    "PIERCING_LINE", "DARK_CLOUD_COVER",
    "TWEEZER_BOTTOM", "TWEEZER_TOP",
}

# Smart Money Concepts (SMC) boolean indicators — structural, daily-bar
# detectors centralised in app/lib/smc.py (single source of truth shared
# with the chart's /smc overlay endpoint, so screener and chart agree).
# Like candle patterns they're boolean (1.0/0.0). Phase 1: Fair Value Gaps.
# Need only ~3 bars + a short range window, so DEFAULT_FETCH_DAYS covers
# them — no entry in _PERIOD_INDS / _required_bars_for needed.
_SMC_BOOL_INDS = {"BULLISH_FVG", "BEARISH_FVG"}

# SMC market-structure boolean indicators (Phase 2) — BOS / CHoCH events from
# swing structure. Computed once per symbol and cached on the evaluator (see
# _SymbolEvaluator._smc_events) since several conditions may reference them.
_SMC_STRUCT_INDS = {"BULLISH_BOS", "BEARISH_BOS", "BULLISH_CHOCH", "BEARISH_CHOCH"}

# SMC liquidity / order-block / premium-discount indicators (Phase 3).
# Order blocks + equal-level clusters are computed once per symbol and cached
# on the evaluator; swings are shared with the sweep/dealing-range helpers.
_SMC_LIQ_INDS = {
    "AT_BULLISH_OB", "AT_BEARISH_OB",
    "LIQUIDITY_SWEEP_HIGH", "LIQUIDITY_SWEEP_LOW",
    "IN_PREMIUM", "IN_DISCOUNT",
    "EQUAL_HIGHS", "EQUAL_LOWS",
}


def _required_bars_for(scanner: dict) -> int:
    """Compute the minimum OHLCV history needed to evaluate every condition.

    Honest sizing — under-fetching causes silent indicator drift (seeded EMAs)
    or outright wrong values (52-week high that is actually a 90-day high).
    Always fetch ≥ DEFAULT_FETCH_DAYS so previous-bar lookups have room.
    """
    needed = DEFAULT_FETCH_DAYS
    for cond in scanner.get("conditions") or []:
        for side in (cond.get("left"), cond.get("right")):
            if not side or side.get("type") == "number":
                continue
            ind = side.get("indicator", "")
            period = side.get("period") or 0
            if ind in _PERIOD_INDS and period:
                needed = max(needed, period * BUFFER_MULT)
            elif ind in _WINDOW_52W_INDS:
                needed = max(needed, WINDOW_52W + 30)
            elif ind in _MACD_INDS:
                needed = max(needed, 35 * BUFFER_MULT)
            elif ind == "VWAP":
                needed = max(needed, DEFAULT_FETCH_DAYS)
    return min(needed, MAX_FETCH_DAYS)


def _safe_idx(seq: list, idx: int) -> Optional[float]:
    """Bounds-checked tail indexing. idx must be ≤ -1."""
    if not seq:
        return None
    n = len(seq)
    pos = n + idx  # idx is negative
    if pos < 0 or pos >= n:
        return None
    return seq[pos]


class _SymbolEvaluator:
    """Per-symbol indicator memoization.

    Computing EMA(20) for a 4-condition scanner used to recreate a Pandas
    DataFrame and Series 4× per symbol; for a 100-symbol scan that is
    ~400-1200 redundant computations. This wrapper caches each indicator's
    full series once per symbol so condition eval is O(1) lookups thereafter.

    Crossover semantics: previous-bar values are read from the *same* cached
    series via index `[-2]` rather than re-running the indicator on a
    truncated input list. The earlier truncation approach changed the EMA
    seeding window (29-bar SMA seed vs 30-bar SMA seed), which produced
    phantom crossovers in low-volatility names.
    """

    def __init__(self, ohlcv: list[dict], symbol: Optional[str] = None):
        self.ohlcv  = ohlcv
        self.n      = len(ohlcv)
        # Symbol is optional so existing test-only constructions still
        # work. It's required ONLY when the scanner condition references
        # a fundamental indicator (PE_RATIO etc.) — those look up the
        # symbol's cached fundamentals via fundamentals_service.
        self.symbol = (symbol or "").upper().strip() or None
        # Filter once; downstream indicator helpers expect non-null closes.
        self.closes = [d["close"] for d in ohlcv if d.get("close") is not None]
        self._series_cache: dict = {}
        # SMC market-structure events, computed lazily once per symbol (several
        # BOS/CHoCH conditions can share the one walk).
        self._smc_events: Optional[list] = None
        # Phase-3 SMC caches — swings shared by sweep / dealing-range / equal
        # levels; order blocks and equal-level clusters computed once.
        self._smc_swings: Optional[tuple] = None
        self._smc_obs: Optional[list] = None
        self._smc_equal: Optional[tuple] = None
        # Lazy: fundamentals are only read on demand. `None` means "not
        # looked up yet"; the property does the cache check on first access.
        self._fundamentals: Optional[dict] = None
        self._fundamentals_loaded: bool = False

    def _get_fundamentals(self) -> Optional[dict]:
        """Lazy fetch from the in-process fundamentals cache. Returns
        None when the symbol wasn't prefetched (the run_scanner caller
        warms the cache for any universe that needs them)."""
        if not self._fundamentals_loaded:
            self._fundamentals_loaded = True
            if self.symbol:
                from . import fundamentals_service as _fs  # noqa: PLC0415
                self._fundamentals = _fs.get_cached(self.symbol)
        return self._fundamentals

    # ── Series builders (cached) ────────────────────────────────────────
    def _series(self, ind: str, period: Optional[int]) -> list[float]:
        key = (ind, period)
        cached = self._series_cache.get(key)
        if cached is not None:
            return cached
        c = self.closes
        out: list[float] = []
        if   ind == "EMA":         out = calculate_ema(c, period or 20)
        elif ind == "SMA":         out = calculate_sma(c, period or 20)
        elif ind == "RSI":         out = calculate_rsi(c, period or 14)
        elif ind in _MACD_INDS:
            m = calculate_macd(c)
            self._series_cache[("MACD",        None)] = m.get("macd",      []) or []
            self._series_cache[("MACD_SIGNAL", None)] = m.get("signal",    []) or []
            self._series_cache[("MACD_HIST",   None)] = m.get("histogram", []) or []
            return self._series_cache[(ind, None)]
        elif ind in {"BB_UPPER", "BB_MID", "BB_LOWER"}:
            b = calculate_bollinger_bands(c, period or 20)
            self._series_cache[("BB_UPPER", period)] = b.get("upper",  []) or []
            self._series_cache[("BB_MID",   period)] = b.get("middle", []) or []
            self._series_cache[("BB_LOWER", period)] = b.get("lower",  []) or []
            return self._series_cache[(ind, period)]
        elif ind == "ATR":         out = calculate_atr(self.ohlcv, period or 14)
        elif ind == "VWAP":        out = calculate_vwap(self.ohlcv)
        self._series_cache[key] = out
        return out

    # ── Single value at offset (shift=0 → latest, shift=1 → previous) ───
    def value(self, side: dict, shift: int = 0) -> Optional[float]:
        if side is None:
            return None
        if side.get("type") == "number":
            return side.get("value")
        if self.n < 2:
            return None
        ind = side.get("indicator", "")
        period = side.get("period")
        idx = -1 - shift  # idx ∈ {-1, -2, ...}

        # ── Instant OHLCV reads (always from raw bars, indexed from tail) ──
        if ind == "CLOSE":      return _safe_idx(self.closes, idx) if abs(idx) <= len(self.closes) else None
        if ind == "OPEN":       return _safe_idx([d.get("open")   for d in self.ohlcv], idx)
        if ind == "HIGH":       return _safe_idx([d.get("high")   for d in self.ohlcv], idx)
        if ind == "LOW":        return _safe_idx([d.get("low")    for d in self.ohlcv], idx)
        if ind == "VOLUME":     return _safe_idx([d.get("volume") for d in self.ohlcv], idx)
        if ind == "PREV_CLOSE":
            return _safe_idx(self.closes, idx - 1)
        if ind == "CHANGE_PCT":
            cur = _safe_idx(self.closes, idx)
            prv = _safe_idx(self.closes, idx - 1)
            if cur is None or not prv:
                return None
            return (cur - prv) / prv * 100

        # ── Volume aggregations ────────────────────────────────────────
        if ind == "AVG_VOLUME":
            p = period or 20
            end = self.n + idx + 1
            sl = [d.get("volume") or 0 for d in self.ohlcv[max(0, end - p):end]]
            return sum(sl) / len(sl) if sl else None
        if ind == "VOLUME_RATIO":
            cur_vol = _safe_idx([d.get("volume") for d in self.ohlcv], idx)
            end = self.n + idx + 1
            window = [d.get("volume") or 0 for d in self.ohlcv[max(0, end - 20):end]]
            avg = sum(window) / len(window) if window else 0
            if not avg or cur_vol is None:
                return None
            return cur_vol / avg * 100

        # ── Volume scanners (new — backs the "Volume" scanner category) ─
        # HIGHEST_VOLUME(p): max single-bar volume in the last `p` bars
        # *excluding* the current bar — so the comparison "current volume
        # > HIGHEST_VOLUME(10)" means "today is the heaviest of the last
        # 10 trading days". Without the exclusion the condition would
        # never fire (current volume is always ≤ itself).
        if ind == "HIGHEST_VOLUME":
            p = period or 10
            end = self.n + idx   # excludes the current bar
            window = [d.get("volume") or 0 for d in self.ohlcv[max(0, end - p):end]]
            return max(window) if window else None

        # HIGHEST_HIGH(p) / LOWEST_LOW(p): rolling-window extremes
        # (also excluding the current bar) — used to detect price breakouts.
        if ind == "HIGHEST_HIGH":
            p = period or 20
            end = self.n + idx
            window = [d.get("high") or 0 for d in self.ohlcv[max(0, end - p):end]]
            return max(window) if window else None
        if ind == "LOWEST_LOW":
            p = period or 20
            end = self.n + idx
            window = [d.get("low") or 0 for d in self.ohlcv[max(0, end - p):end]]
            return min(window) if window else None

        # VOLUME_ZSCORE(p): (current_volume - mean) / stdev over the last
        # `p` bars (excluding current). Catches statistical outliers that
        # simple ratio thresholds miss when a stock's normal volume is
        # already volatile. > 2 = "abnormal", > 3 = "extreme".
        if ind == "VOLUME_ZSCORE":
            p = period or 20
            cur_vol = _safe_idx([d.get("volume") for d in self.ohlcv], idx)
            end = self.n + idx
            window = [d.get("volume") or 0 for d in self.ohlcv[max(0, end - p):end]]
            if not window or cur_vol is None or len(window) < 3:
                return None
            mu = sum(window) / len(window)
            var = sum((v - mu) ** 2 for v in window) / len(window)
            sd = var ** 0.5
            if sd == 0:
                return None
            return (cur_vol - mu) / sd

        # WICK_RATIO: combined upper+lower wick length / total range, in
        # percent. 0 = marubozu (no wicks), 100 = doji (all wick).
        # > 60 with high volume often marks reversals / climaxes.
        if ind == "WICK_RATIO":
            o = _safe_idx([d.get("open")  for d in self.ohlcv], idx)
            h = _safe_idx([d.get("high")  for d in self.ohlcv], idx)
            l = _safe_idx([d.get("low")   for d in self.ohlcv], idx)
            c = _safe_idx([d.get("close") for d in self.ohlcv], idx)
            if None in (o, h, l, c):
                return None
            total_range = h - l
            if total_range <= 0:
                return None
            body_top  = max(o, c)
            body_bot  = min(o, c)
            upper     = max(0, h - body_top)
            lower     = max(0, body_bot - l)
            return (upper + lower) / total_range * 100

        # HIGHER_LOWS_COUNT(p): how many of the last `p` consecutive
        # bars have a low strictly greater than the previous bar's low.
        # Used for accumulation patterns ("last 5 candles higher lows").
        # Returns int [0, p].
        if ind == "HIGHER_LOWS_COUNT":
            p = period or 5
            end = self.n + idx + 1
            window = [d.get("low") or 0 for d in self.ohlcv[max(0, end - p - 1):end]]
            if len(window) < 2:
                return None
            return float(sum(
                1 for i in range(1, len(window)) if window[i] > window[i-1]
            ))

        # VOLUME_TREND_UP(p): 1.0 when the second half of the last `p`
        # bars has higher average volume than the first half, else 0.0.
        # Boolean-style — operators "gt 0" / "eq 1" express "volume is
        # rising over the period".
        if ind == "VOLUME_TREND_UP":
            p = period or 5
            end = self.n + idx + 1
            window = [d.get("volume") or 0 for d in self.ohlcv[max(0, end - p):end]]
            if len(window) < 2:
                return None
            half = len(window) // 2
            if half == 0:
                return None
            first_half  = window[:half]
            second_half = window[half:]
            avg_first  = sum(first_half)  / len(first_half)
            avg_second = sum(second_half) / len(second_half)
            return 1.0 if avg_second > avg_first else 0.0

        # ── Fundamentals (Yahoo info dict, cached 12h) ──────────────────
        # Read from in-process cache populated by fundamentals.prefetch()
        # at scan-start. If the symbol's fundamentals aren't available
        # (None — Yahoo had no data, or prefetch was skipped), every
        # fundamental indicator returns None which makes the surrounding
        # condition fail. That's the correct behavior: "data unavailable"
        # MUST exclude the row rather than silently pass.
        if ind in _FUNDAMENTAL_INDS:
            f = self._get_fundamentals()
            if f is None:
                return None
            if ind == "PE_RATIO":            return f.get("pe")
            if ind == "PB_RATIO":            return f.get("pb")
            if ind == "PEG_RATIO":
                # PEG = PE / earnings-growth (in %). yahoo_norm gives
                # earningsGrowth as a percent (e.g. 18.0). PEG only makes
                # sense for positive growth — return None for the rest so
                # conditions like `PEG < 1` exclude unprofitable growers.
                pe = f.get("pe")
                eg = f.get("earningsGrowth")
                if pe and eg and eg > 0:
                    return pe / eg
                return None
            if ind == "ROE":                 return f.get("roe")
            if ind == "ROCE":
                # yfinance doesn't ship ROCE directly. ROA is the closest
                # proxy from Yahoo's free dataset; we expose both names
                # so screener authors familiar with Indian retail
                # terminology can use either.
                return f.get("roa")
            if ind == "DEBT_TO_EQUITY":      return f.get("debtToEquityRatio")
            if ind == "MARKET_CAP_CR":       return f.get("marketCapCr")
            if ind == "PROFIT_MARGIN":       return f.get("netMargin")
            if ind == "REVENUE_GROWTH_YOY":  return f.get("revenueGrowth")
            if ind == "EARNINGS_GROWTH_YOY": return f.get("earningsGrowth")
            if ind == "FCF_YIELD":
                fcf = f.get("freeCashflow")
                mc  = f.get("marketCap")
                if fcf and mc and mc > 0:
                    return (fcf / mc) * 100
                return None

        # ── Candle patterns (centralised in app/lib/candle_patterns) ───
        # Boolean indicators — return 1.0 if today's candle (and the
        # prior candle, for two-bar patterns) matches the shape, else
        # 0.0. Pair with operator `eq 1` in conditions, or `gt 0` —
        # both work. Single source of truth with patterns_service.py.
        if ind.startswith("PATTERN_") or ind in _PATTERN_INDS:
            from ..lib import candle_patterns as _cp  # noqa: PLC0415
            if self.n < 1:
                return None
            c0 = self.ohlcv[idx]
            c1 = self.ohlcv[idx - 1] if abs(idx - 1) <= self.n else None
            try:
                # Single-candle patterns
                if ind == "DOJI":             return 1.0 if _cp.is_doji(c0) else 0.0
                if ind == "DRAGONFLY_DOJI":   return 1.0 if _cp.is_dragonfly_doji(c0) else 0.0
                if ind == "GRAVESTONE_DOJI":  return 1.0 if _cp.is_gravestone_doji(c0) else 0.0
                if ind == "HAMMER":           return 1.0 if _cp.is_hammer(c0) else 0.0
                if ind == "INVERTED_HAMMER":  return 1.0 if _cp.is_inverted_hammer(c0) else 0.0
                if ind == "SHOOTING_STAR":    return 1.0 if _cp.is_shooting_star(c0) else 0.0
                if ind == "HANGING_MAN":      return 1.0 if _cp.is_hanging_man(c0) else 0.0
                if ind == "BULLISH_MARUBOZU": return 1.0 if _cp.is_bullish_marubozu(c0) else 0.0
                if ind == "BEARISH_MARUBOZU": return 1.0 if _cp.is_bearish_marubozu(c0) else 0.0
                if ind == "SPINNING_TOP":     return 1.0 if _cp.is_spinning_top(c0) else 0.0
                # Two-candle patterns — return 0 (not None) if we don't
                # have a prior bar, so AND-chained conditions reject
                # the row instead of erroring out.
                if c1 is None:
                    return 0.0
                if ind == "BULLISH_ENGULFING": return 1.0 if _cp.is_bullish_engulfing(c0, c1) else 0.0
                if ind == "BEARISH_ENGULFING": return 1.0 if _cp.is_bearish_engulfing(c0, c1) else 0.0
                if ind == "BULLISH_HARAMI":    return 1.0 if _cp.is_bullish_harami(c0, c1) else 0.0
                if ind == "BEARISH_HARAMI":    return 1.0 if _cp.is_bearish_harami(c0, c1) else 0.0
                if ind == "INSIDE_BAR":        return 1.0 if _cp.is_inside_bar(c0, c1) else 0.0
                if ind == "OUTSIDE_BAR":       return 1.0 if _cp.is_outside_bar(c0, c1) else 0.0
                if ind == "PIERCING_LINE":     return 1.0 if _cp.is_piercing_line(c0, c1) else 0.0
                if ind == "DARK_CLOUD_COVER":  return 1.0 if _cp.is_dark_cloud_cover(c0, c1) else 0.0
                if ind == "TWEEZER_BOTTOM":    return 1.0 if _cp.is_tweezer_bottom(c0, c1) else 0.0
                if ind == "TWEEZER_TOP":       return 1.0 if _cp.is_tweezer_top(c0, c1) else 0.0
            except (KeyError, TypeError, ZeroDivisionError):
                # Malformed bar (None close, missing high) — treat as
                # "no pattern" rather than crash the whole scan.
                return 0.0
            return None  # Unknown pattern name — let comparison fail loudly

        # ── Smart Money Concepts (centralised in app/lib/smc) ──────────
        # Boolean structural detectors over daily bars. Like candle
        # patterns they return 1.0/0.0 (never None) so AND-chained
        # conditions reject cleanly instead of erroring. `shift` is
        # honoured via idx so previous-bar semantics match every other
        # indicator. Detection is shared verbatim with the /smc chart
        # overlay endpoint, so a screener hit is always drawable.
        if ind in _SMC_BOOL_INDS:
            from ..lib import smc as _smc  # noqa: PLC0415
            pos = self.n + idx  # tail-relative idx (-1-shift) → absolute
            f = _smc.fvg_at(self.ohlcv, pos)
            if ind == "BULLISH_FVG":
                return 1.0 if (f and f["type"] == "bullish") else 0.0
            if ind == "BEARISH_FVG":
                return 1.0 if (f and f["type"] == "bearish") else 0.0
            return 0.0

        if ind in _SMC_STRUCT_INDS:
            from ..lib import smc as _smc  # noqa: PLC0415
            pos = self.n + idx
            if self._smc_events is None:
                self._smc_events = _smc.market_structure(self.ohlcv)
            ev = _smc.structure_at(self.ohlcv, pos, events=self._smc_events)
            if ev is None:
                return 0.0
            t, k = ev["type"], ev["kind"]
            if ind == "BULLISH_BOS":   return 1.0 if (t == "bullish" and k == "BOS")   else 0.0
            if ind == "BEARISH_BOS":   return 1.0 if (t == "bearish" and k == "BOS")   else 0.0
            if ind == "BULLISH_CHOCH": return 1.0 if (t == "bullish" and k == "CHoCH") else 0.0
            if ind == "BEARISH_CHOCH": return 1.0 if (t == "bearish" and k == "CHoCH") else 0.0
            return 0.0

        if ind in _SMC_LIQ_INDS:
            from ..lib import smc as _smc  # noqa: PLC0415
            pos = self.n + idx
            if pos < 0 or pos >= self.n:
                return 0.0
            if self._smc_swings is None:
                self._smc_swings = _smc.swing_points(self.ohlcv)
            sw = self._smc_swings

            if ind in ("AT_BULLISH_OB", "AT_BEARISH_OB"):
                if self._smc_obs is None:
                    if self._smc_events is None:
                        self._smc_events = _smc.market_structure(self.ohlcv)
                    self._smc_obs = _smc.order_blocks(self.ohlcv, events=self._smc_events)
                kind = "bullish" if ind == "AT_BULLISH_OB" else "bearish"
                return 1.0 if _smc.at_order_block(self.ohlcv, pos, kind, obs=self._smc_obs) else 0.0

            if ind == "LIQUIDITY_SWEEP_HIGH":
                return 1.0 if _smc.liquidity_sweep_at(self.ohlcv, pos, swings=sw) == "high" else 0.0
            if ind == "LIQUIDITY_SWEEP_LOW":
                return 1.0 if _smc.liquidity_sweep_at(self.ohlcv, pos, swings=sw) == "low" else 0.0

            if ind == "IN_PREMIUM":
                return 1.0 if _smc.premium_discount_at(self.ohlcv, pos, swings=sw) == "premium" else 0.0
            if ind == "IN_DISCOUNT":
                return 1.0 if _smc.premium_discount_at(self.ohlcv, pos, swings=sw) == "discount" else 0.0

            if ind in ("EQUAL_HIGHS", "EQUAL_LOWS"):
                if self._smc_equal is None:
                    self._smc_equal = _smc.equal_levels(self.ohlcv, swings=sw)
                eq_highs, eq_lows = self._smc_equal
                c = self.ohlcv[pos].get("close")
                if c is None:
                    return 0.0
                if ind == "EQUAL_HIGHS":
                    return 1.0 if any(cl["price"] > c for cl in eq_highs) else 0.0
                return 1.0 if any(cl["price"] < c for cl in eq_lows) else 0.0
            return 0.0

        # ── 52-week aggregations (true 252-day window) ─────────────────
        if ind in _WINDOW_52W_INDS:
            end = self.n + idx + 1
            window = self.closes[max(0, end - WINDOW_52W):end]
            if not window:
                return None
            hi = max(window)
            lo = min(window)
            cur = _safe_idx(self.closes, idx)
            if ind == "HIGH_52W":     return hi
            if ind == "LOW_52W":      return lo
            if cur is None:           return None
            if ind == "PCT_52W_HIGH": return (cur - hi) / hi * 100 if hi else None
            if ind == "PCT_52W_LOW":  return (cur - lo) / lo * 100 if lo else None

        # ── Series-based indicators (cached, indexed from tail) ────────
        s = self._series(ind, period)
        if not s:
            return None
        if abs(idx) > len(s):
            return None
        return s[idx]


def _compare(lv: float, op: str, rv: float) -> bool:
    if op == "gt":  return lv > rv
    if op == "gte": return lv >= rv
    if op == "lt":  return lv < rv
    if op == "lte": return lv <= rv
    if op == "eq":
        # Documented relative tolerance — see EQ_TOLERANCE_PCT at top of file.
        return abs(lv - rv) / max(abs(rv), 1.0) < (EQ_TOLERANCE_PCT / 100.0)
    return False


def _margin(lv: float, op: str, rv: float) -> float:
    """Positive number describing how strongly `lv op rv` was satisfied.

    Used as the per-condition strength input to the scanner score so AND
    scanners no longer always report 100. Margin is normalised to a percent
    of `rv` (so RSI passing 35 by 5 ≈ 14% margin).
    """
    if rv == 0:
        return 0.0
    if op in ("gt", "gte"):
        return max(0.0, (lv - rv) / abs(rv) * 100)
    if op in ("lt", "lte"):
        return max(0.0, (rv - lv) / abs(rv) * 100)
    return 0.0


def _side_label(s: dict) -> str:
    if s.get("type") == "number":
        return str(s.get("value"))
    p = f"({s['period']})" if s.get("period") else ""
    return f"{s.get('indicator', '')}{p}"


def _compute_value(ohlcv_or_ev, side: dict, shift: int = 0) -> Optional[float]:
    """Backward-compat shim — original signature was (ohlcv: list, side: dict).

    Tests in test_scanners.py / test_scanner_condition_matrix.py call this
    directly with a raw OHLCV list; production code now goes through
    `_SymbolEvaluator.value()` for memoisation. Accept either to stay green.
    """
    ev = ohlcv_or_ev if isinstance(ohlcv_or_ev, _SymbolEvaluator) else _SymbolEvaluator(ohlcv_or_ev)
    return ev.value(side, shift)


def _eval_condition(ohlcv_or_ev, cond: dict) -> dict:
    """Backward-compat shim — original signature was (ohlcv: list, cond: dict)."""
    ev = ohlcv_or_ev if isinstance(ohlcv_or_ev, _SymbolEvaluator) else _SymbolEvaluator(ohlcv_or_ev)
    lv = ev.value(cond["left"])
    rv = ev.value(cond["right"])
    if lv is None or rv is None:
        return {"met": False, "desc": "Insufficient data", "margin": 0.0}

    ll, rl = _side_label(cond["left"]), _side_label(cond["right"])
    fmt = lambda v: f"{v:.4f}" if abs(v) < 1 else f"{v:.2f}"

    op = cond["operator"]
    if op in ("crosses_above", "crosses_below"):
        # Read previous-bar values from the SAME cached series — no
        # truncation, no re-seeding drift, no phantom crossovers.
        lv_prev = ev.value(cond["left"],  1)
        rv_prev = ev.value(cond["right"], 1)
        if lv_prev is None or rv_prev is None:
            return {"met": False, "desc": "Insufficient data for crossover", "margin": 0.0}
        if op == "crosses_above":
            met = lv_prev <= rv_prev and lv > rv
        else:
            met = lv_prev >= rv_prev and lv < rv
        direction = "crossed above" if op == "crosses_above" else "crossed below"
        # Margin for crossovers = current gap normalised to rv.
        margin = abs(lv - rv) / max(abs(rv), 1.0) * 100 if met else 0.0
        return {"met": met, "desc": f"{ll} {direction} {rl} ({fmt(lv)} vs {fmt(rv)})", "margin": margin}

    op_symbols = {"gt": ">", "gte": "≥", "lt": "<", "lte": "≤", "eq": "="}
    met = _compare(lv, op, rv)
    margin = _margin(lv, op, rv) if met else 0.0
    return {
        "met": met,
        "desc": f"{ll} {op_symbols.get(op, op)} {rl} ({fmt(lv)} vs {fmt(rv)})",
        "margin": margin,
    }


_scanners: dict[str, dict] = {}
_id_counter = [1]


def _init_defaults():
    if _scanners:
        return
    for d in DEFAULT_SCANNERS_DEF:
        sid = f"scanner-{_id_counter[0]}"
        _id_counter[0] += 1
        _scanners[sid] = {
            **d,
            "id": sid,
            "conditions": [{**c, "id": c.get("id") or _cid()} for c in d["conditions"]],
            "createdAt": datetime.utcnow().isoformat() + "Z",
            "updatedAt": datetime.utcnow().isoformat() + "Z",
        }


_init_defaults()


class ScannersService:
    def __init__(self, price: PriceService):
        self.price = price

    def get_all_scanners(self) -> list[dict]:
        return sorted(_scanners.values(), key=lambda s: s["createdAt"], reverse=True)

    def get_scanner_by_id(self, sid: str) -> Optional[dict]:
        return _scanners.get(sid)

    def create_scanner(self, data: dict) -> dict:
        sid = f"scanner-{_id_counter[0]}"
        _id_counter[0] += 1
        scanner = {
            "id": sid,
            "name": data.get("name") or "Untitled Scanner",
            "description": data.get("description") or "",
            "universe": data.get("universe") or ["NIFTY100"],
            "logic": data.get("logic") or "AND",
            "conditions": [{**c, "id": c.get("id") or _cid()} for c in (data.get("conditions") or [])],
            "createdAt": datetime.utcnow().isoformat() + "Z",
            "updatedAt": datetime.utcnow().isoformat() + "Z",
        }
        _scanners[sid] = scanner
        return scanner

    def update_scanner(self, sid: str, data: dict) -> Optional[dict]:
        existing = _scanners.get(sid)
        if not existing:
            return None
        updated = {
            **existing,
            **data,
            "id": sid,
            "conditions": [{**c, "id": c.get("id") or _cid()} for c in (data.get("conditions") or existing["conditions"])],
            "updatedAt": datetime.utcnow().isoformat() + "Z",
        }
        _scanners[sid] = updated
        return updated

    def delete_scanner(self, sid: str) -> bool:
        if sid in _scanners:
            del _scanners[sid]
            return True
        return False

    async def run_scanner(
        self,
        sid: str,
        progress_cb=None,
    ) -> dict:
        """Execute a scanner.

        `progress_cb` is an optional callable invoked at key phases so
        the async-job wrapper can stream live updates to the UI. It's
        called with kwargs:
          * stage="prefetch_fundamentals" | "scanning" | "done"
          * scanned=int, matched=int, failed=int, errors=int
            (sent after each symbol completes, scanning stage only)
          * total=int (sent once at start so the wrapper knows the universe size)

        When `progress_cb` is None (legacy sync path) the function
        behaves exactly as before — no overhead, no protocol change.
        """
        def _emit(**kwargs):
            """Local no-op-aware progress emitter. Centralises the
            None-check so the call sites stay clean."""
            if progress_cb is None:
                return
            try:
                progress_cb(**kwargs)
            except Exception as exc:
                logger.debug("progress_cb failed (continuing): %s", exc)

        scanner = _scanners.get(sid)
        if not scanner:
            return {"error": "Scanner not found"}

        symbols      = build_universe(scanner["universe"])
        # ── Quarantine pre-filter ──────────────────────────────────────────
        # Drop symbols that have been empirically flagged as "no usable
        # data in any provider" (delisted, SME-only, suspended, etc.).
        # These don't get surfaced as scanner errors anymore — they're
        # reported separately in the response envelope as
        # `quarantinedCount` so the user knows the scanner is aware of
        # them, rather than appearing to silently miss them.
        from . import symbol_quarantine_service as _qsvc  # noqa: PLC0415
        symbols, quarantined_symbols = _qsvc.filter_quarantined(symbols)
        if quarantined_symbols:
            logger.info(
                "scanner %s: skipping %d quarantined symbols (auto-detected dead): %s%s",
                sid, len(quarantined_symbols),
                ", ".join(quarantined_symbols[:5]),
                "…" if len(quarantined_symbols) > 5 else "",
            )

        conditions   = scanner["conditions"]
        logic        = scanner["logic"]
        market_open_at_start = _mcs.is_market_open()
        bars_needed  = _required_bars_for(scanner)
        # Minimum bars for any meaningful eval — at least 2 closes for
        # CHANGE_PCT, plus the largest period across conditions.
        min_eval_bars = max(2, min(bars_needed // 2, 35))

        _emit(total=len(symbols), stage="starting")

        # Fundamentals prefetch — only triggers when at least one
        # condition uses a fundamental indicator (PE_RATIO etc.). Warms
        # the in-process cache for the entire universe in parallel
        # BEFORE the per-symbol evaluation loop, so the actual
        # `_SymbolEvaluator.value()` reads hit a warm cache in O(1).
        # Cost is paid once per 12h per universe (the cache TTL).
        needs_fundamentals = any(
            (side or {}).get("indicator") in _FUNDAMENTAL_INDS
            for c in conditions
            for side in (c.get("left"), c.get("right"))
        )
        if needs_fundamentals:
            _emit(stage="prefetch_fundamentals")
            try:
                from . import fundamentals_service as _fs  # noqa: PLC0415
                await _fs.prefetch(symbols)
            except Exception as exc:
                logger.warning("Fundamentals prefetch failed (continuing without): %s", exc)

        _emit(stage="scanning")

        scan_errors: list[dict] = []

        def _evaluate(sym: str, h: list) -> Optional[dict]:
            if len(h) < min_eval_bars:
                # Honest "insufficient" vs silent skip — surface to scanErrors.
                scan_errors.append({
                    "symbol": sym,
                    "reason": "insufficient-history",
                    "got":    len(h),
                    "needed": min_eval_bars,
                })
                # Record failure ONLY for the zero-bars case. >0 bars but
                # below `min_eval_bars` is a genuine "thin history" /
                # "new listing" case — not a dead symbol, don't quarantine.
                if len(h) == 0:
                    try:
                        _qsvc.record_failure(sym, reason="no-data")
                    except Exception:
                        pass   # never let bookkeeping break the scan
                return None
            # >= min_eval_bars means the chain returned usable data.
            # Wipe any prior failure state so a previously-quarantined
            # symbol that's come back online gets re-enabled. Only fire
            # the write when the symbol is in the active quarantine set
            # — avoids a PG round-trip per healthy symbol on every scan.
            if _qsvc.is_quarantined(sym):
                try:
                    _qsvc.record_success(sym)
                except Exception:
                    pass
            ev = _SymbolEvaluator(h, symbol=sym)
            closes = ev.closes
            if len(closes) < 2:
                scan_errors.append({"symbol": sym, "reason": "insufficient-closes"})
                return None
            lc = closes[-1]
            pc = closes[-2]
            change   = lc - pc
            p_change = (change / pc) * 100 if pc else 0
            cond_results = [_eval_condition(ev, c) for c in conditions]
            met_count    = sum(1 for r in cond_results if r["met"])
            all_met = (met_count == len(conditions)) if logic == "AND" else (met_count > 0)
            if not all_met:
                return None
            # Score: weighted by per-condition margin so AND scanners aren't
            # all stuck at 100. Falls back to met-fraction × 100 when no
            # margins (e.g. all conditions are crossovers with zero gap).
            margins = [r["margin"] for r in cond_results if r["met"] and r["margin"] > 0]
            if margins:
                # Average margin, capped at 100, blended 70/30 with met fraction.
                avg_margin = min(100.0, sum(margins) / len(margins))
                met_frac   = met_count / len(conditions) * 100
                score      = round(0.7 * avg_margin + 0.3 * met_frac, 1)
            else:
                score = round(met_count / len(conditions) * 100, 1) if conditions else 0
            # Per-row asOf — last bar's date so the user can see when each
            # match's data was sealed (avoids the "single runAt" lie when a
            # 100-symbol scan takes 3 minutes).
            row_as_of = h[-1].get("date") if h else None
            row = {
                "symbol":             None,  # filled by caller
                "lastPrice":          lc,
                "change":             round(change, 2),
                "pChange":            round(p_change, 2),
                "volume":             h[-1].get("volume"),
                "matchedConditions":  [r["desc"] for r in cond_results if r["met"]],
                "failedConditions":   [r["desc"] for r in cond_results if not r["met"]],
                "conditionsMatched":  met_count,
                "totalConditions":    len(conditions),
                "score":              score,
                "asOf":               row_as_of,
            }
            # Hidden Gem Score — only attached for scanners in the
            # "Hidden Gems" category. Avoids paying the (cheap, pure
            # Python) score computation on every result row of every
            # scanner. Two extra fields: `hiddenGemScore` (0-100) and
            # `hiddenGemBreakdown` (array of strings explaining the
            # score) so the UI can render a tooltip without re-deriving.
            if scanner.get("category") == "Hidden Gems":
                f = ev._get_fundamentals()
                if f:
                    from . import fundamentals_service as _fs  # noqa: PLC0415
                    hg_score, hg_breakdown = _fs.compute_hidden_gem_score(f)
                    row["hiddenGemScore"]     = hg_score
                    row["hiddenGemBreakdown"] = hg_breakdown
                else:
                    row["hiddenGemScore"]     = None
                    row["hiddenGemBreakdown"] = ["fundamentals unavailable"]
            return row

        results: list[dict] = []
        market_state_changed = False

        # Live counters — closed over by _scan_one in the fast path
        # and incremented in-line in the live path. Both paths emit
        # progress through these so the polling client sees a unified
        # scanned/matched/failed/errors trio regardless of which mode
        # the scan is running in.
        scanned_n = 0
        matched_n = 0
        errors_n  = 0

        def _push_progress() -> None:
            # `failed` is the residual: we scanned it, didn't error, but
            # it didn't pass the conditions. Computed rather than tracked
            # so the three numbers can't disagree.
            failed_n = max(0, scanned_n - matched_n - errors_n)
            _emit(
                scanned=scanned_n, matched=matched_n,
                failed=failed_n,   errors=errors_n,
            )

        if not market_open_at_start:
            # ── FAST PATH: market closed → all data from disk → run parallel ──
            async def _scan_one(sym: str):
                nonlocal scanned_n, matched_n, errors_n
                try:
                    h = await self.price.get_historical_data(sym, bars_needed)
                    row = _evaluate(sym, h or [])
                    scanned_n += 1
                    if row:
                        matched_n += 1
                        # Stamp `symbol` BEFORE emitting so the live
                        # stream shipping to the UI carries the same
                        # field layout as the final sorted result.
                        # Without this, the partial-matches list would
                        # have `symbol: None` until the collection
                        # phase below mutates it.
                        row["symbol"] = sym
                        _emit(match=row)
                    _push_progress()
                    return row, sym
                except Exception as e:
                    scan_errors.append({
                        "symbol": sym,
                        "reason": "fetch-failed",
                        "error":  f"{type(e).__name__}: {e}",
                    })
                    scanned_n += 1
                    errors_n  += 1
                    _push_progress()
                    return None, sym

            # Bounded so a full-universe ("ALL") scan can't fire thousands of
            # simultaneous fetches at cache-cold symbols and trip a provider
            # ban; disk-cached symbols still complete near-instantly.
            _sem = asyncio.Semaphore(SCANNER_SCAN_CONCURRENCY)

            async def _bounded(sym: str):
                async with _sem:
                    return await _scan_one(sym)

            scanned = await asyncio.gather(*[_bounded(s) for s in symbols])
            for row, sym in scanned:
                if row:
                    # `row["symbol"]` was already set inside _scan_one
                    # for the live emit; this is now a no-op assignment
                    # kept for clarity (and as a safety net if a future
                    # refactor moves emit logic elsewhere).
                    row["symbol"] = sym
                    results.append(row)

        else:
            # ── LIVE PATH: market open → sequential with rate-limit delay ──
            for sym in symbols:
                try:
                    h = await self.price.get_historical_data(sym, bars_needed)
                    row = _evaluate(sym, h or [])
                    scanned_n += 1
                    if row:
                        matched_n += 1
                        row["symbol"] = sym
                        results.append(row)
                        _emit(match=row)
                    _push_progress()
                    await asyncio.sleep(RATE_LIMIT_DELAY_S)
                except Exception as e:
                    scan_errors.append({
                        "symbol": sym,
                        "reason": "fetch-failed",
                        "error":  f"{type(e).__name__}: {e}",
                    })
                    scanned_n += 1
                    errors_n  += 1
                    _push_progress()
                # Detect intra-scan market-state transition so the response
                # can warn the user that early symbols ran on live data and
                # later symbols ran on freshly-sealed EOD.
                if not market_state_changed and not _mcs.is_market_open():
                    market_state_changed = True

        _emit(stage="done")

        results.sort(key=lambda r: r["score"], reverse=True)
        _scanners[sid] = {
            **scanner,
            "lastRunAt":       datetime.utcnow().isoformat() + "Z",
            "lastResultCount": len(results),
        }

        if scan_errors:
            logger.info(
                "Scanner %s: %d/%d symbols had issues (first: %s)",
                sid, len(scan_errors), len(symbols), scan_errors[0],
            )

        return {
            "scannerId":          sid,
            "scannerName":        scanner["name"],
            "logic":              scanner["logic"],
            "runAt":              datetime.utcnow().isoformat() + "Z",
            "totalScanned":       len(symbols),
            "totalSucceeded":     len(symbols) - len(scan_errors),
            "totalMatched":       len(results),
            "results":            results,
            "scanErrors":         scan_errors,
            # Quarantined symbols are NOT scan errors — they're known
            # dead/unreachable names that the system has empirically
            # learned to skip. Surface them separately so the UI can
            # show "N symbols auto-skipped (delisted/no data)" without
            # cluttering the per-symbol error list. `quarantinedCount`
            # plus `totalScanned` equals the original universe size.
            "quarantinedCount":   len(quarantined_symbols),
            "quarantinedSymbols": quarantined_symbols,
            "barsRequested":      bars_needed,
            "marketOpenAtStart":  market_open_at_start,
            "marketStateChanged": market_state_changed,
        }

    async def run_adhoc(self, data: dict) -> dict:
        scanner = self.create_scanner(data)
        result = await self.run_scanner(scanner["id"])
        self.delete_scanner(scanner["id"])
        return result
