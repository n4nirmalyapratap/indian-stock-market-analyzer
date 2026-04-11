"""
Centralized AI client for the Indian Stock Market Analyzer.

Strategy (cheapest → reliable):
  1. OpenRouter :free models (zero cost, shared rate limits)
       • Primary  : google/gemma-4-31b-it:free      (Gemma 4, Google)
       • Fallback1: qwen/qwen3-next-80b-a3b-instruct:free  (Qwen 3 80B, Chinese)
       • Fallback2: meta-llama/llama-3.3-70b-instruct:free (Llama 3.3 70B, Meta)
  2. OpenAI gpt-4o-mini (Replit-billed, very cheap, always available as last resort)

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


# ── Model selection ────────────────────────────────────────────────────────────
AI_FALLBACK2           = "meta-llama/llama-3.3-70b-instruct:free"
_OPENAI_FALLBACK_MODEL = "gpt-4o-mini"


def _get_ai_model() -> str:
    return _s("AI_MODEL", "google/gemma-4-31b-it:free")


def _get_ai_fallback() -> str:
    return _s("AI_FALLBACK_MODEL", "qwen/qwen3-next-80b-a3b-instruct:free")


# ── Lazy client factory ────────────────────────────────────────────────────────
# Clients are built on first call (or when credentials change) so that
# secrets set via the admin panel take effect without a server restart.

_or_creds: tuple[str, str] = ("", "")
_oa_creds: tuple[str, str] = ("", "")
_or_client: Optional[AsyncOpenAI] = None
_oa_client: Optional[AsyncOpenAI] = None


def _or() -> Optional[AsyncOpenAI]:
    """Return (or lazily create) the OpenRouter client."""
    global _or_client, _or_creds
    base = _s("AI_INTEGRATIONS_OPENROUTER_BASE_URL", "")
    key  = _s("AI_INTEGRATIONS_OPENROUTER_API_KEY",  "sk-or-dummy")
    if base and (base, key) != _or_creds:
        _or_client = AsyncOpenAI(base_url=base, api_key=key)
        _or_creds  = (base, key)
    return _or_client if base else None


def _oa() -> Optional[AsyncOpenAI]:
    """Return (or lazily create) the OpenAI client."""
    global _oa_client, _oa_creds
    base = _s("AI_INTEGRATIONS_OPENAI_BASE_URL", "")
    key  = _s("AI_INTEGRATIONS_OPENAI_API_KEY",  "sk-dummy")
    if base and (base, key) != _oa_creds:
        _oa_client = AsyncOpenAI(base_url=base, api_key=key)
        _oa_creds  = (base, key)
    return _oa_client if base else None


def is_available() -> bool:
    """Return True if at least one AI client is configured."""
    return _or() is not None or _oa() is not None


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
            resp = await asyncio.wait_for(client.chat.completions.create(**create_kwargs), timeout=30)
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
    or_c = _or()
    oa_c = _oa()
    if not or_c and not oa_c:
        return "[AI unavailable: no API credentials set]"

    messages = [
        {"role": "system", "content": system},
        {"role": "user",   "content": prompt},
    ]

    # 1) Try free OpenRouter cascade
    if or_c:
        chosen = model or _get_ai_model()
        free_cascade = [chosen, _get_ai_fallback(), AI_FALLBACK2]
        seen: set[str] = set()
        unique = [m for m in free_cascade if not (m in seen or seen.add(m))]  # type: ignore

        for attempt_model in unique:
            try:
                result = await _call_with_retry(
                    or_c, attempt_model, messages, max_tokens, temperature,
                    retries=1, backoff=6.0,
                )
                log.info("AI: answered by %s", attempt_model)
                return result
            except Exception as exc:
                log.warning("OpenRouter model %s unavailable: %s", attempt_model, str(exc)[:80])

    # 2) Reliable fallback — OpenAI gpt-4o-mini (Replit-billed, minimal cost)
    if oa_c:
        log.info("AI: falling back to OpenAI %s", _OPENAI_FALLBACK_MODEL)
        try:
            result = await _call_with_retry(
                oa_c, _OPENAI_FALLBACK_MODEL, messages, max_tokens, temperature,
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
    or_c = _or()
    oa_c = _oa()
    if not or_c and not oa_c:
        yield "[AI unavailable]"
        return

    chosen = model or _get_ai_model()
    client = or_c or oa_c
    use_model = chosen if or_c else _OPENAI_FALLBACK_MODEL

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
    or_c = _or()
    oa_c = _oa()
    if not or_c and not oa_c:
        return "[AI unavailable]"
    full_messages = [{"role": "system", "content": system}] + messages
    chosen = model or _get_ai_model()
    if or_c:
        try:
            return await _call_with_retry(or_c, chosen, full_messages, max_tokens,
                                          temperature, retries=1, backoff=6.0)
        except Exception as exc:
            log.warning("OpenRouter chat failed: %s", exc)
    if oa_c:
        return await _call_with_retry(oa_c, _OPENAI_FALLBACK_MODEL, full_messages,
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
