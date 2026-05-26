"""
Centralized AI client for the Indian Stock Market Analyzer.

Provider priority:
  1. Groq  (GROQ_API_KEY secret)   — cycles through fast free models:
                                       1. llama-3.3-70b-versatile (primary)
                                       2. mixtral-8x7b-32768
                                       3. gemma2-9b-it
                                       4. llama-3.1-8b-instant
                                     500–900 tok/s, generous free tier, ~1 s per response.
  2. OpenRouter (AI_INTEGRATIONS_OPENROUTER_*)  — cascade of 6 models as fallback.

Text cascade (OpenRouter fallback):
  • Primary    : x-ai/grok-4-fast:free          (xAI, free, generous limits)
  • Fallback 1 : google/gemini-flash-1.5         (paid, cheap, fast)
  • Fallback 2 : anthropic/claude-3.5-sonnet     (paid, best quality)
  • Fallback 3 : google/gemma-4-31b-it:free      (free)
  • Fallback 4 : qwen/qwen3-30b-a3b:free         (free)
  • Fallback 5 : meta-llama/llama-3.3-70b-instruct:free  (free)

Vision cascade (OpenRouter only — Groq has no vision endpoint):
  • Primary    : x-ai/grok-2-vision-1212
  • Fallback 1 : google/gemini-flash-1.5
  • Fallback 2 : anthropic/claude-3.5-sonnet

All model IDs can be overridden via env / DB secrets (AI_MODEL,
AI_FALLBACK_MODEL, AI_VISION_MODEL).

Credentials are read from the DB secrets store first (admin-managed),
falling back to env vars. No restart required after updating secrets.

Usage:
    from app.services.ai_client import ask, ask_stream, ask_vision

    answer = await ask("Explain iron condor for a beginner")
    async for chunk in ask_stream("Summarise this SEBI circular: ..."):
        print(chunk, end="", flush=True)

    # base64-encoded image
    extracted = await ask_vision("Extract holdings as JSON.", image_b64=img_b64)
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


# ── Model constants ────────────────────────────────────────────────────────────

# Groq — primary fast provider, tried in order until one succeeds
_GROQ_BASE   = "https://api.groq.com/openai/v1"
GROQ_MODEL   = "llama-3.3-70b-versatile"   # primary; kept for back-compat
GROQ_MODELS  = [
    "llama-3.3-70b-versatile",  # primary — 500–900 tok/s
    "mixtral-8x7b-32768",       # fallback 1 — fast, free
    "gemma2-9b-it",             # fallback 2 — fast, free
    "llama-3.1-8b-instant",     # fallback 3 — fastest, smallest, free
]


# OpenRouter cascade — fallback when GROQ_API_KEY absent or Groq unavailable
AI_MODEL    = "x-ai/grok-4-fast:free"
_FALLBACK1  = "google/gemini-flash-1.5"
_FALLBACK2  = "anthropic/claude-3.5-sonnet"
_FALLBACK3  = "google/gemma-4-31b-it:free"
_FALLBACK4  = "qwen/qwen3-30b-a3b:free"
_FALLBACK5  = "meta-llama/llama-3.3-70b-instruct:free"

# Vision-capable cascade (OpenRouter only — Groq has no vision endpoint)
AI_VISION_MODEL   = "x-ai/grok-2-vision-1212"
_VISION_FALLBACK1 = "google/gemini-flash-1.5"
_VISION_FALLBACK2 = "anthropic/claude-3.5-sonnet"


def _get_ai_model() -> str:
    return _s("AI_MODEL", AI_MODEL)


def _get_ai_fallback1() -> str:
    return _s("AI_FALLBACK_MODEL", _FALLBACK1)


def _text_cascade(chosen: str = "") -> list[str]:
    """Return the ordered list of OpenRouter text models to try."""
    primary   = chosen or _get_ai_model()
    fallback1 = _get_ai_fallback1()
    return list(dict.fromkeys([
        primary, fallback1, _FALLBACK2, _FALLBACK3, _FALLBACK4, _FALLBACK5,
    ]))


def _vision_cascade(chosen: str = "") -> list[str]:
    """Return the ordered list of vision-capable models to try."""
    primary = chosen or _s("AI_VISION_MODEL", AI_VISION_MODEL)
    return list(dict.fromkeys([
        primary, _VISION_FALLBACK1, _VISION_FALLBACK2,
    ]))


# ── Lazy Groq client ───────────────────────────────────────────────────────────

_groq_client: Optional[AsyncOpenAI] = None
_groq_key_seen: str = ""


def _groq() -> Optional[AsyncOpenAI]:
    """Return (or lazily create) the Groq client. Returns None if no key."""
    global _groq_client, _groq_key_seen
    key = _s("GROQ_API_KEY", "")
    if not key:
        return None
    if key != _groq_key_seen:
        _groq_client = AsyncOpenAI(base_url=_GROQ_BASE, api_key=key)
        _groq_key_seen = key
    return _groq_client


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
    """Return True if at least one AI provider (Groq or OpenRouter) is configured."""
    return _groq() is not None or _or() is not None


# ── Groq fast call ─────────────────────────────────────────────────────────────

async def _groq_call(
    messages: list[dict],
    max_tokens: int,
    temperature: float,
) -> Optional[tuple[str, str]]:
    """
    Try each model in GROQ_MODELS in order with a 20 s timeout per model.
    Returns ``(response_text, model_name)`` for the first model that succeeds,
    or ``None`` if all fail (caller falls through to the OpenRouter cascade).
    """
    client = _groq()
    if not client:
        return None
    for groq_model in GROQ_MODELS:
        try:
            resp = await asyncio.wait_for(
                client.chat.completions.create(
                    model=groq_model,
                    messages=messages,
                    max_completion_tokens=max_tokens,
                    temperature=temperature,
                ),
                timeout=20,
            )
            text = resp.choices[0].message.content or ""
            log.info("AI: answered by groq/%s", groq_model)
            return text, groq_model
        except Exception as exc:
            log.warning(
                "Groq model %s failed, trying next: %s", groq_model, str(exc)[:120]
            )
    log.warning("All Groq models exhausted, falling back to OpenRouter")
    return None


# ── OpenRouter retry helper ────────────────────────────────────────────────────

async def _call_with_retry(
    client: AsyncOpenAI,
    model: str,
    messages: list[dict],
    max_tokens: int,
    temperature: float,
    retries: int = 2,
    backoff: float = 4.0,
) -> str:
    """
    Try one OpenRouter model, retrying on 429 rate-limit errors with
    exponential backoff.  Timeout reduced to 25 s (was 60 s) because Groq
    now handles the fast path; OpenRouter is a true fallback.
    """
    for attempt in range(retries + 1):
        try:
            resp = await asyncio.wait_for(
                client.chat.completions.create(
                    model=model,
                    messages=messages,
                    max_completion_tokens=max_tokens,
                    temperature=temperature,
                ),
                timeout=25,
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

    Provider order:
      1. Groq llama-3.3-70b-versatile  (fast, free — if GROQ_API_KEY set)
      2. OpenRouter cascade: Grok-4-Fast → Gemini Flash → Claude 3.5 →
         Gemma 4 → Qwen 3 → Llama 3.3  (if OpenRouter integration connected)
    """
    messages = [
        {"role": "system", "content": system},
        {"role": "user",   "content": prompt},
    ]

    # 1. Groq fast path
    if not model:   # only bypass Groq when a specific OR model is requested
        groq_result = await _groq_call(messages, max_tokens, temperature)
        if groq_result is not None:
            text, _groq_model = groq_result
            return text

    # 2. OpenRouter cascade
    or_c = _or()
    if not or_c:
        if _groq() is None:
            return (
                "[AI unavailable: no provider configured. "
                "Add GROQ_API_KEY secret (free at console.groq.com) or "
                "connect OpenRouter in Admin → Integrations.]"
            )
        return "[AI unavailable: every model in the cascade failed — please retry]"

    last_exc: Exception = RuntimeError("no models tried")
    for attempt_model in _text_cascade(model):
        try:
            result = await _call_with_retry(
                or_c, attempt_model, messages, max_tokens, temperature,
                retries=1, backoff=4.0,
            )
            log.info("AI: answered by %s", attempt_model)
            return result
        except Exception as exc:
            last_exc = exc
            log.warning("OpenRouter model %s unavailable: %s", attempt_model, str(exc)[:120])

    log.error("All models failed. Last error: %s", last_exc)
    return "[AI unavailable: every model in the cascade is rate-limited or offline — please retry in a minute]"


async def ask_with_meta(
    prompt: str,
    system: str = "You are a helpful financial assistant specialising in Indian markets.",
    model: str  = "",
    max_tokens: int = 4096,
    temperature: float = 0.3,
) -> tuple[str, str]:
    """
    Like ask() but also returns the provider/model label that answered.

    Returns ``(response_text, model_label)`` where ``model_label`` is e.g.:
      * ``"groq/llama-3.3-70b-versatile"``  — one of the Groq fallbacks
      * ``"openrouter/x-ai/grok-4-fast:free"``  — OpenRouter model
      * ``"none"`` — every provider was unavailable

    Use this instead of ask() when the caller needs to record which model
    was used (e.g. the AI Analyst pipeline's ``models_used`` field).
    """
    messages = [
        {"role": "system", "content": system},
        {"role": "user",   "content": prompt},
    ]

    # 1. Groq fast path
    if not model:
        groq_result = await _groq_call(messages, max_tokens, temperature)
        if groq_result is not None:
            text, groq_model = groq_result
            return text, f"groq/{groq_model}"

    # 2. OpenRouter cascade
    or_c = _or()
    if not or_c:
        if _groq() is None:
            return (
                "[AI unavailable: no provider configured. "
                "Add GROQ_API_KEY secret (free at console.groq.com) or "
                "connect OpenRouter in Admin → Integrations.]",
                "none",
            )
        return "[AI unavailable: every model in the cascade failed — please retry]", "none"

    last_exc: Exception = RuntimeError("no models tried")
    for attempt_model in _text_cascade(model):
        try:
            result = await _call_with_retry(
                or_c, attempt_model, messages, max_tokens, temperature,
                retries=1, backoff=4.0,
            )
            log.info("AI: answered by %s", attempt_model)
            return result, f"openrouter/{attempt_model}"
        except Exception as exc:
            last_exc = exc
            log.warning("OpenRouter model %s unavailable: %s", attempt_model, str(exc)[:120])

    log.error("All models failed. Last error: %s", last_exc)
    return (
        "[AI unavailable: every model in the cascade is rate-limited or offline — please retry in a minute]",
        "none",
    )


async def ask_stream(
    prompt: str,
    system: str = "You are a helpful financial assistant specialising in Indian markets.",
    model: str  = "",
    max_tokens: int = 4096,
    temperature: float = 0.3,
) -> AsyncGenerator[str, None]:
    """
    Stream response tokens.

    Tries Groq first (non-streaming but fast enough at 500 tok/s that the
    full response arrives in ~1–2 s).  Falls back to OpenRouter streaming,
    or to the full ask() cascade if streaming itself fails.
    """
    messages = [
        {"role": "system", "content": system},
        {"role": "user",   "content": prompt},
    ]

    # 1. Groq fast path (returns full text, yield it as one chunk)
    if not model:
        groq_result = await _groq_call(messages, max_tokens, temperature)
        if groq_result is not None:
            text, _groq_model = groq_result
            yield text
            return

    # 2. OpenRouter streaming
    or_c = _or()
    if not or_c:
        yield "[AI unavailable]"
        return

    chosen = model or _get_ai_model()
    try:
        stream = await or_c.chat.completions.create(
            model=chosen,
            messages=messages,
            max_completion_tokens=max_tokens,
            temperature=temperature,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta
    except Exception:
        # Non-streaming fallback through the full cascade
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
    """
    Multi-turn chat. `messages` = [{"role": "user"|"assistant", "content": "..."}].
    Tries Groq first, then OpenRouter cascade.
    """
    full_messages = [{"role": "system", "content": system}] + messages

    # 1. Groq fast path
    if not model:
        groq_result = await _groq_call(full_messages, max_tokens, temperature)
        if groq_result is not None:
            text, _groq_model = groq_result
            return text

    # 2. OpenRouter cascade
    or_c = _or()
    if not or_c:
        return "[AI unavailable]"

    last_exc: Exception = RuntimeError("no models tried")
    for attempt_model in _text_cascade(model):
        try:
            return await _call_with_retry(
                or_c, attempt_model, full_messages, max_tokens,
                temperature, retries=1, backoff=4.0,
            )
        except Exception as exc:
            last_exc = exc
            log.warning("OpenRouter chat model %s failed: %s", attempt_model, str(exc)[:120])

    log.error("All chat models failed: %s", last_exc)
    return "[AI unavailable: every model in the cascade is rate-limited or offline — please retry in a minute]"


async def ask_ai_async(
    system: str,
    history: list[dict],
    max_tokens: int = 1024,
    temperature: float = 0.5,
) -> str:
    """
    Convenience wrapper for the route layer.
    Takes a system prompt + conversation history and returns the AI reply.
    Goes through Groq first, then the standard OpenRouter cascade.
    """
    return await chat_with_history(
        messages=history,
        system=system,
        max_tokens=max_tokens,
        temperature=temperature,
    )


# ── Vision (image-input) helper ───────────────────────────────────────────────

async def ask_vision(
    prompt: str,
    *,
    image_b64: str,
    image_mime: str = "image/jpeg",
    system: str = "You are a helpful financial assistant specialising in Indian markets.",
    model: str = "",
    max_tokens: int = 2048,
    temperature: float = 0.1,
) -> str:
    """
    Send a prompt + base64-encoded image and return the model's response.

    Vision stays on OpenRouter only — Groq does not expose a vision endpoint.
    Cascades Grok-2-vision → Gemini Flash → Claude 3.5 Sonnet.

    Parameters
    ----------
    prompt :
        The text instruction (e.g. "Extract holdings as JSON.").
    image_b64 :
        The raw image bytes, base64-encoded (no data URI prefix needed).
    image_mime :
        MIME type of the image — ``image/jpeg``, ``image/png``, ``image/webp``.
    """
    or_c = _or()
    if not or_c:
        return "[AI unavailable: OpenRouter integration not connected.]"

    data_uri = f"data:{image_mime};base64,{image_b64}"
    messages = [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": [
                {"type": "text",      "text": prompt},
                {"type": "image_url", "image_url": {"url": data_uri}},
            ],
        },
    ]

    last_exc: Exception = RuntimeError("no vision models tried")
    for attempt_model in _vision_cascade(model):
        try:
            result = await _call_with_retry(
                or_c, attempt_model, messages, max_tokens, temperature,
                retries=1, backoff=4.0,
            )
            log.info("AI Vision: answered by %s", attempt_model)
            return result
        except Exception as exc:
            last_exc = exc
            log.warning("Vision model %s unavailable: %s", attempt_model, str(exc)[:160])

    log.error("All vision models failed. Last error: %s", last_exc)
    return ""
