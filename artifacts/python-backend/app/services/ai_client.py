"""
Centralized AI client for the Indian Stock Market Analyzer.

Routes every call through OpenRouter (one API key, many models). Cascade
prefers Grok first because the OpenRouter free tier on Google/Qwen/Llama
hits rate limits often; Grok-4-Fast is on a generous free tier and falls
through to paid Gemini → Claude → the original free models as backstops.

Text cascade:
  • Primary    : x-ai/grok-4-fast:free          (xAI, free, generous limits)
  • Fallback 1 : google/gemini-flash-1.5         (paid, cheap, fast)
  • Fallback 2 : anthropic/claude-3.5-sonnet     (paid, best quality)
  • Fallback 3 : google/gemma-4-31b-it:free      (free, original primary)
  • Fallback 4 : qwen/qwen3-30b-a3b:free         (free)
  • Fallback 5 : meta-llama/llama-3.3-70b-instruct:free  (free)

Vision cascade (for screenshot-style image input):
  • Primary    : x-ai/grok-2-vision-1212
  • Fallback 1 : google/gemini-flash-1.5         (multimodal-capable)
  • Fallback 2 : anthropic/claude-3.5-sonnet     (multimodal-capable)

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


# ── Model cascade ─────────────────────────────────────────────────────────────
# Grok first (generous free tier on OpenRouter), then paid Gemini/Claude for
# quality fallback, then the original three free models as last-resort.
# Anything in this list can be overridden via env or DB secrets.

AI_MODEL    = "x-ai/grok-4-fast:free"          # primary
_FALLBACK1  = "google/gemini-flash-1.5"         # paid but cheap
_FALLBACK2  = "anthropic/claude-3.5-sonnet"     # paid, best quality
_FALLBACK3  = "google/gemma-4-31b-it:free"      # original primary
_FALLBACK4  = "qwen/qwen3-30b-a3b:free"
_FALLBACK5  = "meta-llama/llama-3.3-70b-instruct:free"

# Vision-capable cascade for image inputs (screenshot extraction, etc.).
AI_VISION_MODEL    = "x-ai/grok-2-vision-1212"
_VISION_FALLBACK1  = "google/gemini-flash-1.5"
_VISION_FALLBACK2  = "anthropic/claude-3.5-sonnet"


def _get_ai_model() -> str:
    return _s("AI_MODEL", AI_MODEL)


def _get_ai_fallback1() -> str:
    return _s("AI_FALLBACK_MODEL", _FALLBACK1)


def _text_cascade(chosen: str = "") -> list[str]:
    """Return the ordered list of text models to try."""
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
    Cascade: Grok-4-Fast (free) → Gemini Flash → Claude 3.5 Sonnet → free
    fallbacks (Gemma 4 → Qwen 3 → Llama 3.3). Any model can be overridden
    via the AI_MODEL / AI_FALLBACK_MODEL env vars or DB secrets.
    """
    or_c = _or()
    if not or_c:
        return "[AI unavailable: OpenRouter integration not connected. Go to Admin → Integrations to enable it.]"

    messages = [
        {"role": "system", "content": system},
        {"role": "user",   "content": prompt},
    ]

    last_exc: Exception = RuntimeError("no models tried")
    for attempt_model in _text_cascade(model):
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

    log.error("All models failed. Last error: %s", last_exc)
    return "[AI unavailable: every model in the cascade is rate-limited or offline — please retry in a minute]"


async def ask_stream(
    prompt: str,
    system: str = "You are a helpful financial assistant specialising in Indian markets.",
    model: str  = "",
    max_tokens: int = 4096,
    temperature: float = 0.3,
) -> AsyncGenerator[str, None]:
    """
    Stream response tokens. Falls back to ask() if streaming fails (which
    runs the full Grok → Gemini → Claude → free-models cascade).
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
    last_exc: Exception = RuntimeError("no models tried")
    for attempt_model in _text_cascade(model):
        try:
            return await _call_with_retry(
                or_c, attempt_model, full_messages, max_tokens,
                temperature, retries=1, backoff=6.0,
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
    Goes through the standard cascade (Grok → Gemini → Claude → free models).
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

    Used for screenshot extraction (broker portfolio pages, etc.). Cascades
    Grok-2-vision → Gemini Flash → Claude 3.5 Sonnet. All three accept the
    OpenAI-style multimodal `messages` payload with an ``image_url`` block
    holding a data URI.

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
                retries=1, backoff=6.0,
            )
            log.info("AI Vision: answered by %s", attempt_model)
            return result
        except Exception as exc:
            last_exc = exc
            log.warning("Vision model %s unavailable: %s", attempt_model, str(exc)[:160])

    log.error("All vision models failed. Last error: %s", last_exc)
    return ""
