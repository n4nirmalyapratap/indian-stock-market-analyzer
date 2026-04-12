"""
Centralized AI client for the Indian Stock Market Analyzer.

Uses ONLY free, open-source models via OpenRouter (zero cost):
  • Primary  : google/gemma-4-31b-it:free        (Gemma 4, Google)
  • Fallback1: qwen/qwen3-30b-a3b:free            (Qwen 3, Chinese open-source)
  • Fallback2: meta-llama/llama-3.3-70b-instruct:free  (Llama 3.3, Meta)

NO paid services. NO OpenAI API key required.
The openai Python SDK is used purely as an HTTP client to hit OpenRouter's
free, OpenAI-compatible endpoint.

All credentials are read from the DB secrets store first (admin-managed),
falling back to environment variables. No restart required after updating secrets.

Usage:
    from app.services.ai_client import ask, ask_stream

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

# ── Secrets helper (DB-first, env fallback) ────────────────────────────────────

def _s(key: str, default: str = "") -> str:
    """Read a secret from DB first, then env var, then default."""
    try:
        from app.lib.secrets_store import get_secret  # noqa: PLC0415
        return get_secret(key, default)
    except Exception:
        return os.environ.get(key, default)


# ── Free model cascade (OpenRouter only) ──────────────────────────────────────
#   All three are :free tier — no charges, no API key billing.

AI_MODEL    = "google/gemma-4-31b-it:free"
_FALLBACK1  = "qwen/qwen3-30b-a3b:free"
_FALLBACK2  = "meta-llama/llama-3.3-70b-instruct:free"


def _get_ai_model() -> str:
    return _s("AI_MODEL", AI_MODEL)


def _get_ai_fallback1() -> str:
    return _s("AI_FALLBACK_MODEL", _FALLBACK1)


# ── Lazy OpenRouter client ─────────────────────────────────────────────────────

_or_creds: tuple[str, str] = ("", "")
_or_client: Optional[AsyncOpenAI] = None


def _or() -> Optional[AsyncOpenAI]:
    """Return (or lazily create) the OpenRouter client."""
    global _or_client, _or_creds
    base = _s("AI_INTEGRATIONS_OPENROUTER_BASE_URL", "")
    key  = _s("AI_INTEGRATIONS_OPENROUTER_API_KEY",  "sk-or-dummy")
    if base and (base, key) != _or_creds:
        _or_client = AsyncOpenAI(base_url=base, api_key=key)
        _or_creds  = (base, key)
    return _or_client if base else None


def is_available() -> bool:
    """Return True if the OpenRouter client is configured."""
    return _or() is not None


# ── Retry helper ───────────────────────────────────────────────────────────────

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
    for attempt in range(retries + 1):
        try:
            resp = await asyncio.wait_for(
                client.chat.completions.create(
                    model=model,
                    messages=messages,
                    max_completion_tokens=max_tokens,
                    temperature=temperature,
                ),
                timeout=60,
            )
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
    Tries free models in order: Gemma 4 → Qwen 3 → Llama 3.3
    All are free via OpenRouter — no charges.
    """
    or_c = _or()
    if not or_c:
        return "[AI unavailable: OpenRouter integration not connected. Go to Admin → Integrations to enable it.]"

    messages = [
        {"role": "system", "content": system},
        {"role": "user",   "content": prompt},
    ]

    chosen    = model or _get_ai_model()
    fallback1 = _get_ai_fallback1()
    cascade   = list(dict.fromkeys([chosen, fallback1, _FALLBACK2]))  # unique, ordered

    last_exc: Exception = RuntimeError("no models tried")
    for attempt_model in cascade:
        try:
            result = await _call_with_retry(
                or_c, attempt_model, messages, max_tokens, temperature,
                retries=1, backoff=6.0,
            )
            log.info("AI: answered by %s", attempt_model)
            return result
        except Exception as exc:
            last_exc = exc
            log.warning("OpenRouter model %s unavailable: %s", attempt_model, str(exc)[:120])

    log.error("All free models failed. Last error: %s", last_exc)
    return "[AI unavailable: all free models are rate-limited — please retry in a minute]"


async def ask_stream(
    prompt: str,
    system: str = "You are a helpful financial assistant specialising in Indian markets.",
    model: str  = "",
    max_tokens: int = 4096,
    temperature: float = 0.3,
) -> AsyncGenerator[str, None]:
    """
    Stream response tokens. Falls back to ask() if streaming fails.
    Uses free OpenRouter models only.
    """
    or_c = _or()
    if not or_c:
        yield "[AI unavailable]"
        return

    chosen = model or _get_ai_model()
    try:
        stream = await or_c.chat.completions.create(
            model=chosen,
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
        # Non-streaming fallback through the full free cascade
        text = await ask(prompt, system=system, model=model,
                         max_tokens=max_tokens, temperature=temperature)
        yield text


async def ask_json(
    prompt: str,
    system: str = "You are a helpful financial assistant. Always reply with valid JSON.",
    model: str  = "",
    max_tokens: int = 4096,
) -> str:
    """Same as ask() but requests JSON output."""
    if not is_available():
        return "{}"
    return await ask(prompt, system=system, model=model, max_tokens=max_tokens)


async def chat_with_history(
    messages: list[dict],
    system: str = "You are a helpful financial assistant specialising in Indian markets.",
    model: str  = "",
    max_tokens: int = 4096,
    temperature: float = 0.5,
) -> str:
    """Multi-turn chat. `messages` = [{"role": "user"|"assistant", "content": "..."}]."""
    or_c = _or()
    if not or_c:
        return "[AI unavailable]"

    full_messages = [{"role": "system", "content": system}] + messages
    chosen    = model or _get_ai_model()
    fallback1 = _get_ai_fallback1()
    cascade   = list(dict.fromkeys([chosen, fallback1, _FALLBACK2]))

    last_exc: Exception = RuntimeError("no models tried")
    for attempt_model in cascade:
        try:
            return await _call_with_retry(
                or_c, attempt_model, full_messages, max_tokens,
                temperature, retries=1, backoff=6.0,
            )
        except Exception as exc:
            last_exc = exc
            log.warning("OpenRouter chat model %s failed: %s", attempt_model, str(exc)[:120])

    log.error("All free chat models failed: %s", last_exc)
    return "[AI unavailable: all free models are rate-limited — please retry in a minute]"


async def ask_ai_async(
    system: str,
    history: list[dict],
    max_tokens: int = 1024,
    temperature: float = 0.5,
) -> str:
    """
    Convenience wrapper for the route layer.
    Takes a system prompt + conversation history and returns the AI reply.
    Uses free OpenRouter models only (Gemma 4 → Qwen 3 → Llama 3.3).
    """
    return await chat_with_history(
        messages=history,
        system=system,
        max_tokens=max_tokens,
        temperature=temperature,
    )
