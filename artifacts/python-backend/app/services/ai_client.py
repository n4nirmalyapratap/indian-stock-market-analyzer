"""
Centralized AI client for the Indian Stock Market Analyzer.

Strategy (cheapest → reliable):
  1. OpenRouter :free models (zero cost, shared rate limits)
       • Primary  : google/gemma-4-31b-it:free      (Gemma 4, Google)
       • Fallback1: qwen/qwen3-next-80b-a3b-instruct:free  (Qwen 3 80B, Chinese)
       • Fallback2: meta-llama/llama-3.3-70b-instruct:free (Llama 3.3 70B, Meta)
  2. OpenAI gpt-5-nano (Replit-billed, very cheap, always available as last resort)

All OpenRouter models are on the :free tier — zero external API cost.
Env vars are provisioned automatically by the Replit AI Integrations system.

Usage:
    from app.services.ai_client import ask, ask_stream, AI_MODEL

    answer = await ask("Explain iron condor for a beginner")
    async for chunk in ask_stream("Summarise this SEBI circular: ..."):
        print(chunk, end="", flush=True)
"""

import os
import asyncio
import logging
from typing import AsyncGenerator, Optional

from openai import AsyncOpenAI

log = logging.getLogger(__name__)

# ── Model selection ────────────────────────────────────────────────────────────
# Free tier models via OpenRouter — zero external cost
AI_MODEL          = os.environ.get("AI_MODEL",         "google/gemma-4-31b-it:free")
AI_FALLBACK_MODEL = os.environ.get("AI_FALLBACK_MODEL","qwen/qwen3-next-80b-a3b-instruct:free")
AI_FALLBACK2      = "meta-llama/llama-3.3-70b-instruct:free"

# Reliable fallback via Replit-billed OpenAI (very low cost, always available)
_OPENAI_FALLBACK_MODEL = "gpt-4o-mini"

# ── Client singletons ──────────────────────────────────────────────────────────
_OR_BASE = os.environ.get("AI_INTEGRATIONS_OPENROUTER_BASE_URL", "")
_OR_KEY  = os.environ.get("AI_INTEGRATIONS_OPENROUTER_API_KEY",  "sk-or-dummy")

_OA_BASE = os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL", "")
_OA_KEY  = os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY",  "sk-dummy")

_or_client: Optional[AsyncOpenAI] = (
    AsyncOpenAI(base_url=_OR_BASE, api_key=_OR_KEY) if _OR_BASE else None
)
_oa_client: Optional[AsyncOpenAI] = (
    AsyncOpenAI(base_url=_OA_BASE, api_key=_OA_KEY) if _OA_BASE else None
)


def is_available() -> bool:
    """Return True if at least one AI client is configured."""
    return _or_client is not None or _oa_client is not None


# ── Retry helper ───────────────────────────────────────────────────────────────

_NO_TEMP_MODELS = ("gpt-5", "o4", "o3", "o1")   # gpt-5* and o-series don't support temperature

def _supports_temperature(model: str) -> bool:
    return not any(model.startswith(p) for p in _NO_TEMP_MODELS)


async def _call_with_retry(
    client: AsyncOpenAI,
    model: str,
    messages: list[dict],
    max_tokens: int,
    temperature: float,
    retries: int = 2,
    backoff: float = 8.0,
) -> str:
    """Try one model, retrying on 429 rate-limit errors with exponential backoff."""
    create_kwargs: dict = dict(
        model=model,
        messages=messages,
        max_completion_tokens=max_tokens,
    )
    if _supports_temperature(model):
        create_kwargs["temperature"] = temperature

    for attempt in range(retries + 1):
        try:
            resp = await client.chat.completions.create(**create_kwargs)
            return resp.choices[0].message.content or ""
        except Exception as exc:
            is_rate_limit = "429" in str(exc) or "rate" in str(exc).lower()
            if is_rate_limit and attempt < retries:
                wait = backoff * (2 ** attempt)
                log.info("Rate-limited on %s — retrying in %.0fs (attempt %d/%d)",
                         model, wait, attempt + 1, retries)
                await asyncio.sleep(wait)
            else:
                raise
    raise RuntimeError(f"All retries exhausted for {model}")


# ── Core helpers ───────────────────────────────────────────────────────────────

async def ask(
    prompt: str,
    system: str = "You are a helpful financial assistant specialising in Indian markets.",
    model: str  = "",
    max_tokens: int = 4096,
    temperature: float = 0.3,
) -> str:
    """
    Send a prompt and return the full response.

    Tries free OpenRouter models first (Gemma 4 → Qwen → Llama), then falls
    back to OpenAI nano if all free models are rate-limited.
    """
    if not is_available():
        return "[AI unavailable: env vars not set]"

    messages = [
        {"role": "system", "content": system},
        {"role": "user",   "content": prompt},
    ]

    # 1) Try free OpenRouter cascade
    if _or_client:
        chosen = model or AI_MODEL
        free_cascade = [chosen, AI_FALLBACK_MODEL, AI_FALLBACK2]
        seen: set[str] = set()
        unique = [m for m in free_cascade if not (m in seen or seen.add(m))]  # type: ignore

        for attempt_model in unique:
            try:
                result = await _call_with_retry(
                    _or_client, attempt_model, messages, max_tokens, temperature,
                    retries=1, backoff=6.0,
                )
                log.info("AI: answered by %s", attempt_model)
                return result
            except Exception as exc:
                log.warning("OpenRouter model %s unavailable: %s", attempt_model, str(exc)[:80])

    # 2) Reliable fallback — OpenAI nano (Replit-billed, minimal cost)
    if _oa_client:
        log.info("AI: falling back to OpenAI %s", _OPENAI_FALLBACK_MODEL)
        try:
            result = await _call_with_retry(
                _oa_client, _OPENAI_FALLBACK_MODEL, messages, max_tokens, temperature,
                retries=2, backoff=4.0,
            )
            return result
        except Exception as exc:
            log.error("OpenAI fallback also failed: %s", exc)

    return "[AI unavailable: all models failed — please retry later]"


async def ask_stream(
    prompt: str,
    system: str = "You are a helpful financial assistant specialising in Indian markets.",
    model: str  = "",
    max_tokens: int = 4096,
    temperature: float = 0.3,
) -> AsyncGenerator[str, None]:
    """
    Stream response tokens. Falls back to ask() if streaming fails.
    Usage:
        async for chunk in ask_stream("Explain SEBI rule 9.1"):
            print(chunk, end="", flush=True)
    """
    if not is_available():
        yield "[AI unavailable]"
        return

    chosen = model or AI_MODEL
    client = _or_client or _oa_client
    use_model = chosen if _or_client else _OPENAI_FALLBACK_MODEL

    try:
        stream = await client.chat.completions.create(  # type: ignore
            model=use_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": prompt},
            ],
            max_completion_tokens=max_tokens,
            temperature=temperature,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta
    except Exception:
        # Non-streaming fallback
        text = await ask(prompt, system=system, model=model, max_tokens=max_tokens,
                         temperature=temperature)
        yield text


async def ask_json(
    prompt: str,
    system: str = "You are a helpful financial assistant. Always reply with valid JSON.",
    model: str  = "",
    max_tokens: int = 4096,
) -> str:
    """Same as ask() but requests JSON output. Falls back gracefully."""
    if not is_available():
        return "{}"
    # Only OpenAI reliably supports JSON mode; use plain ask() for OpenRouter models
    return await ask(prompt, system=system, model=model, max_tokens=max_tokens)


async def chat_with_history(
    messages: list[dict],
    system: str = "You are a helpful financial assistant specialising in Indian markets.",
    model: str  = "",
    max_tokens: int = 4096,
    temperature: float = 0.5,
) -> str:
    """Multi-turn chat. `messages` = [{"role": "user"|"assistant", "content": "..."}]."""
    if not is_available():
        return "[AI unavailable]"
    full_messages = [{"role": "system", "content": system}] + messages
    chosen = model or AI_MODEL
    if _or_client:
        try:
            return await _call_with_retry(_or_client, chosen, full_messages, max_tokens,
                                          temperature, retries=1, backoff=6.0)
        except Exception as exc:
            log.warning("OpenRouter chat failed: %s", exc)
    if _oa_client:
        return await _call_with_retry(_oa_client, _OPENAI_FALLBACK_MODEL, full_messages,
                                      max_tokens, temperature, retries=2, backoff=4.0)
    return "[AI unavailable]"


async def ask_ai_async(
    system: str,
    history: list[dict],
    max_tokens: int = 1024,
    temperature: float = 0.5,
) -> str:
    """
    Convenience wrapper for the route layer: takes a system prompt and a
    conversation history list and returns the AI reply text.
    Falls back through the full model chain (OpenRouter → OpenAI gpt-4o-mini).
    """
    return await chat_with_history(
        messages=history,
        system=system,
        max_tokens=max_tokens,
        temperature=temperature,
    )
