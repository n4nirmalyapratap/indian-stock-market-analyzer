"""
LLM-based sentiment classification for news headlines.

Why this module exists (audit 2026-07):
  The news feed's bullish/bearish/neutral tags came from VADER — a
  social-media lexicon, not a financial one. On a 43-headline battery of
  typical ET/Mint/Moneycontrol phrasing it scored 53% (near coin-flip for
  3 classes) with *inverted* calls on standard market language:
    * "Sensex tanks as investors book profits"     → bullish  (wrong)
    * "Morgan Stanley upgrades India to overweight" → bearish  (wrong)
    * "Railway stocks on fire: hit upper circuit"   → bearish  (wrong)
  Those labels feed the News Feed UI, the Market Sentiment engine's
  35%-weighted news leg, the tri-factor sentiment score, and the AI
  Analyst prompt — so one bad classifier poisoned four surfaces.

This module routes classification through the app's own AI stack
(ai_client: Groq llama-3.3-70b primary → OpenRouter cascade):
  * Headlines are classified in batches per LLM call — strict JSON out,
    temperature 0 for determinism.
  * Per-headline labels are cached 24 h (a headline's sentiment never
    changes), so a typical 8-minute feed refresh only sends NEW
    headlines to the LLM.
  * On any failure (no provider configured, rate-limit, malformed JSON,
    timeout) articles keep their VADER label and stay marked
    sentimentVia="vader" — consumers can tell LLM labels from fallback.
  * A short cooldown avoids re-paying provider timeouts on every request
    when the whole cascade is down.

Contract for apply_llm_sentiment(articles) — mutates dicts in place:
    sentiment    → "bullish" | "bearish" | "neutral"
    sentimentVia → "llm"   (classified by the AI stack)
                   "vader" (lexicon fallback label kept)
                   "none"  (no classifier ran; defaulted to neutral)
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Optional

from . import ai_client

logger = logging.getLogger(__name__)

_LABELS = ("bullish", "bearish", "neutral")

# Tuning
_BATCH_SIZE       = 25      # headlines per LLM call
_MAX_PARALLEL     = 3       # concurrent LLM calls (Groq free tier friendly)
_PASS_TIMEOUT     = 45.0    # hard budget for one whole classification pass
_MAX_TOKENS       = 1024    # 25 labels ≈ 350 tokens; generous head-room
_COOLDOWN_SECONDS = 300.0   # skip LLM after a total-failure pass

# Per-headline label cache — sentiment of a given headline never changes.
_CACHE_TTL = 24 * 3600
_CACHE_MAX = 4000
_label_cache: dict[str, tuple[float, str]] = {}

# Cooldown marker: when a pass yields zero successful batches while a
# provider *was* configured, skip the LLM until this timestamp.
_llm_down_until: float = 0.0


def _cache_key(text: str) -> str:
    return re.sub(r"\W+", "", text.lower())[:120]


def _cache_get(text: str) -> Optional[str]:
    ent = _label_cache.get(_cache_key(text))
    if ent and time.time() - ent[0] < _CACHE_TTL:
        return ent[1]
    return None


def _cache_put(text: str, label: str) -> None:
    if len(_label_cache) >= _CACHE_MAX:
        # Evict the oldest quarter in one sweep — O(n log n) but rare.
        oldest = sorted(_label_cache.items(), key=lambda kv: kv[1][0])
        for k, _ in oldest[: _CACHE_MAX // 4]:
            _label_cache.pop(k, None)
    _label_cache[_cache_key(text)] = (time.time(), label)


# ── Prompt ────────────────────────────────────────────────────────────────────

_SYSTEM = (
    "You are a financial news sentiment classifier specialising in Indian "
    "stock markets (NSE/BSE). You reply with strict JSON only — no prose, "
    "no explanations, no markdown fences."
)

_PROMPT_HEADER = """Classify the market sentiment of each numbered Indian stock-market news headline.

Labels:
  bullish — positive for the stock/sector/market the headline is about (or for Indian equities broadly)
  bearish — negative for the stock/sector/market the headline is about
  neutral — routine/administrative/no clear direction (schedules, board-meeting dates, mixed or balanced signals)

Domain rules (Indian markets):
- "profit booking" / "investors book profits" = selling pressure -> bearish
- "hits upper circuit" / "locked in upper circuit" -> bullish; "lower circuit" -> bearish
- Broker calls: upgrade / overweight / raise target -> bullish; downgrade / underweight / cut target -> bearish
- "profit falls / declines / misses estimates" -> bearish even though the word "profit" appears
- RBI rate cut -> generally bullish for equities; rate hike / hawkish stance -> bearish
- FII/DII buying or inflows -> bullish; selling / outflows -> bearish
- Rising NPA, SEBI probe/ban, fraud, default, insolvency, indictment -> bearish
- Judge for the primary subject of the headline; for broad-market headlines judge the Nifty/Sensex direction.
- If genuinely ambiguous, prefer neutral.

Headlines:
"""

_PROMPT_FOOTER = """
Reply with ONLY a JSON array, one object per headline, exactly this shape:
[{"i": 1, "s": "bullish"}, {"i": 2, "s": "neutral"}]"""


def _build_prompt(texts: list[str]) -> str:
    lines = [f"{i}. {t}" for i, t in enumerate(texts, start=1)]
    return _PROMPT_HEADER + "\n".join(lines) + _PROMPT_FOOTER


# ── LLM reply parsing ─────────────────────────────────────────────────────────

def _parse_labels(raw: str, n: int) -> dict[int, str]:
    """Extract {1-based index → label} from an LLM reply.

    Tolerates markdown fences, surrounding prose, bare-string arrays, and
    alternative key names. Anything unparseable is simply dropped — the
    caller falls back to VADER for those indices.
    """
    if not raw:
        return {}
    txt = raw.strip()
    start, end = txt.find("["), txt.rfind("]")
    if start == -1 or end <= start:
        return {}
    try:
        data = json.loads(txt[start: end + 1])
    except Exception:
        return {}
    if not isinstance(data, list):
        return {}

    out: dict[int, str] = {}
    for pos, item in enumerate(data):
        if isinstance(item, str):
            idx: object = pos + 1
            label: object = item
        elif isinstance(item, dict):
            idx = item.get("i", item.get("index"))
            label = item.get("s", item.get("sentiment", item.get("label")))
        else:
            continue
        try:
            idx_i = int(idx)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
        if not isinstance(label, str):
            continue
        label_s = label.strip().lower()
        if 1 <= idx_i <= n and label_s in _LABELS:
            out[idx_i] = label_s
    return out


# ── LLM calls ─────────────────────────────────────────────────────────────────

async def _classify_batch(texts: list[str]) -> dict[int, str]:
    """One LLM call for up to _BATCH_SIZE headlines. Returns {} on failure."""
    prompt = _build_prompt(texts)
    try:
        raw, model_label = await ai_client.ask_with_meta(
            prompt,
            system=_SYSTEM,
            max_tokens=_MAX_TOKENS,
            temperature=0.0,
        )
    except Exception as exc:
        logger.warning("news sentiment: LLM call failed: %s", str(exc)[:160])
        return {}
    if model_label == "none" or raw.lstrip().startswith("[AI unavailable"):
        return {}
    parsed = _parse_labels(raw, len(texts))
    if not parsed:
        logger.warning(
            "news sentiment: unparseable reply from %s: %.120s", model_label, raw
        )
    return parsed


async def classify_texts(texts: list[str]) -> list[Optional[str]]:
    """Classify a list of headline texts.

    Returns a label per input position, or None where classification was
    not possible (caller keeps its fallback label). Cached labels are
    reused; only uncached texts hit the LLM.
    """
    global _llm_down_until
    labels: list[Optional[str]] = [None] * len(texts)
    if not texts:
        return labels
    try:
        if not ai_client.is_available():
            return labels
    except Exception:
        return labels
    if time.time() < _llm_down_until:
        return labels

    todo: list[int] = []
    for i, t in enumerate(texts):
        t = (t or "").strip()
        if not t:
            continue
        hit = _cache_get(t)
        if hit is not None:
            labels[i] = hit
        else:
            todo.append(i)
    if not todo:
        return labels

    batches = [todo[j: j + _BATCH_SIZE] for j in range(0, len(todo), _BATCH_SIZE)]
    sem = asyncio.Semaphore(_MAX_PARALLEL)

    async def _one(batch: list[int]) -> dict[int, str]:
        async with sem:
            return await _classify_batch([texts[i] for i in batch])

    try:
        results = await asyncio.wait_for(
            asyncio.gather(*[_one(b) for b in batches], return_exceptions=True),
            timeout=_PASS_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.warning("news sentiment: pass timed out after %.0fs", _PASS_TIMEOUT)
        _llm_down_until = time.time() + _COOLDOWN_SECONDS
        return labels

    any_success = False
    for batch, res in zip(batches, results):
        if isinstance(res, Exception) or not isinstance(res, dict) or not res:
            continue
        any_success = True
        for k, orig_i in enumerate(batch, start=1):
            lab = res.get(k)
            if lab:
                labels[orig_i] = lab
                _cache_put(texts[orig_i], lab)

    if not any_success:
        # Provider configured but every batch failed — cool down so we don't
        # re-pay the timeouts on every feed request.
        _llm_down_until = time.time() + _COOLDOWN_SECONDS
        logger.warning(
            "news sentiment: all %d batches failed; falling back to VADER "
            "for %.0fs", len(batches), _COOLDOWN_SECONDS,
        )
    return labels


# ── Public entry point ────────────────────────────────────────────────────────

def _article_text(a: dict) -> str:
    title = (a.get("title") or "").strip()
    summary = (a.get("summary") or "").strip()
    return f"{title} — {summary[:160]}" if summary else title


async def apply_llm_sentiment(articles: list[dict]) -> dict:
    """Overwrite each article's `sentiment` with an LLM label where possible.

    Mutates articles in place and returns {"llm": n, "fallback": m} counts.
    Never raises — a total failure leaves every article on its fallback
    label with provenance intact.
    """
    stats = {"llm": 0, "fallback": 0}
    if not articles:
        return stats
    try:
        labels = await classify_texts([_article_text(a) for a in articles])
    except Exception as exc:
        logger.warning("news sentiment: pass failed: %s", str(exc)[:160])
        labels = [None] * len(articles)

    for a, lab in zip(articles, labels):
        if lab:
            a["sentiment"] = lab
            a["sentimentVia"] = "llm"
            stats["llm"] += 1
        else:
            if a.get("sentiment") in _LABELS:
                # Keep the VADER label; mark provenance if the fetcher didn't.
                a.setdefault("sentimentVia", "vader")
            else:
                # e.g. Tavily articles arrive with sentiment=None.
                a["sentiment"] = "neutral"
                a["sentimentVia"] = "none"
            stats["fallback"] += 1
    return stats
