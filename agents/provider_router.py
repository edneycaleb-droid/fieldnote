"""
Fieldnote Provider Router
Centralized AI provider state tracker with automatic quota-aware fallback.

Priority order (cheapest/freest first — never incur billing unless no free option exists):
  1. Groq         — free tier, fast (llama-3.3-70b-versatile → llama-3.1-8b-instant)
  2. Gemini       — free tier, generous limits (gemini-2.0-flash → gemini-1.5-flash)
  3. OpenAI       — billed; used ONLY when free options exhausted
  4. HuggingFace  — free serverless inference; anonymous OK, better with HF_TOKEN
  5. OpenRouter   — free-model router; requires OPENROUTER_API_KEY (free account)

Blackout rules:
  insufficient_quota / billing error  → 2-hour blackout (quota_exhausted)
  regular rate-limit (429)            → 30-second backout + backoff within the call (rate_limited)
  auth error (401 / 403)              → permanent blackout until restart (auth_error)
  model not found (404)               → try next model in the list, not a provider blackout
  no key configured                   → no_key (skipped silently, amber for optional providers)

The module singleton `_status` tracks state across all calls without requiring persistence.
"""
from __future__ import annotations

import logging
import os
import random
import time
from threading import Lock
from typing import Any

log = logging.getLogger("fieldnote.provider_router")

# ── Nonstandard secret alias normalisation ────────────────────────────────────
# Maps user-defined Replit Secret names → the standard env-var names the rest
# of the codebase expects.  Only fills the standard name when it is NOT already
# set; never overwrites a real primary key.  Values are never logged.
_KEY_ALIASES: dict[str, str] = {
    "GROQFREE":    "GROQ",              # backup Groq key stored under alternate name
    "Langchain":   "LANGCHAIN_API_KEY", # LangSmith tracing key stored under alternate name
    "Huggingface": "HF_TOKEN",          # HuggingFace secret stored under alternate name
}
for _ka_src, _ka_dst in _KEY_ALIASES.items():
    if os.getenv(_ka_src) and not os.getenv(_ka_dst):
        os.environ[_ka_dst] = os.environ[_ka_src]  # type: ignore[assignment]

# Map provider names to the env-var names the router reads
KEY_ENV_MAP: dict[str, str] = {
    "groq":        "GROQ",
    "gemini":      "Gemini",
    "openai":      "CHATGPT",
    "huggingface": "HF_TOKEN",
    "openrouter":  "OPENROUTER_API_KEY",
}


# ── Provider state constants ───────────────────────────────────────────────────

_STATE_HEALTHY = "healthy"
_STATE_RATE    = "rate_limited"     # short backout, auto-clears
_STATE_QUOTA   = "quota_exhausted"  # 2-hour blackout
_STATE_AUTH    = "auth_error"       # permanent until restart
_STATE_NO_KEY  = "no_key"           # key not configured

_QUOTA_BLACKOUT = 7200   # 2 hours in seconds
_RATE_BACKOUT   = 30     # 30 seconds

_lock   = Lock()
_status: dict[str, dict] = {}


def _now() -> float:
    return time.monotonic()


def _init_status() -> None:
    """Initialise state for each provider; picks up keys added without restart."""
    providers = {
        "groq":        os.getenv("GROQ_API_KEY") or os.getenv("GROQ"),
        "gemini":      os.getenv("Google_API_Key") or os.getenv("Gemini") or os.getenv("GOOGLE_API_KEY"),
        "openai":      os.getenv("CHATGPT") or os.getenv("OPENAI_API_KEY"),
        "huggingface": os.getenv("HF_TOKEN"),          # optional: anonymous access allowed
        "openrouter":  os.getenv("OPENROUTER_API_KEY"),  # optional: free account at openrouter.ai
    }
    with _lock:
        for provider, key in providers.items():
            if provider not in _status:
                _status[provider] = {
                    "state":      _STATE_HEALTHY if key else _STATE_NO_KEY,
                    "until":      0.0,
                    "last_error": "",
                }


_init_status()


def _get_key(provider: str) -> str:
    if provider == "groq":
        return os.getenv("GROQ_API_KEY") or os.getenv("GROQ") or os.getenv("GROQFREE") or ""
    if provider == "gemini":
        return (os.getenv("Google_API_Key") or os.getenv("Gemini")
                or os.getenv("GOOGLE_API_KEY") or "")
    if provider == "openai":
        return os.getenv("CHATGPT") or os.getenv("OPENAI_API_KEY") or ""
    if provider == "huggingface":
        return os.getenv("HF_TOKEN") or os.getenv("Huggingface") or ""
    if provider == "openrouter":
        return os.getenv("OPENROUTER_API_KEY") or ""
    return ""


# Providers that work without an API key (anonymous, lower rate limits)
_ANONYMOUS_OK: set[str] = {"huggingface"}


def _classify_error(err: str) -> str:
    """Return the blackout category for an error string.
    429 is checked FIRST — it is always a short rate-limit, never quota_exhausted,
    even when the message text happens to contain the word 'quota'.
    """
    el = err.lower()
    # HTTP 429 / explicit rate-limit keywords → short 30-s backout
    if ("429" in err or "rate_limit" in el or "rate limit" in el
            or "rate_limit_reached" in el or "too_many_requests" in el
            or "too many requests" in el):
        return _STATE_RATE
    # Billing / quota exhaustion → 2-hour blackout
    if ("insufficient_quota" in el or "exceeded your current quota" in el
            or "billing" in el or "payment" in el or "resource_exhausted" in el
            or "quota_exceeded" in el):
        return _STATE_QUOTA
    # Auth errors → permanent blackout until restart
    if ("401" in err or "403" in err or "invalid_api_key" in el
            or "invalid api key" in el or "permission_denied" in el
            or "unauthenticated" in el):
        return _STATE_AUTH
    return ""


def _mark_error(provider: str, err: str) -> str:
    """Update provider state based on the error; return the state category."""
    kind = _classify_error(err)
    if not kind:
        return ""
    with _lock:
        current = _status[provider]["state"]
        if kind == _STATE_QUOTA:
            _status[provider]["state"] = _STATE_QUOTA
            _status[provider]["until"] = _now() + _QUOTA_BLACKOUT
        elif kind == _STATE_AUTH:
            _status[provider]["state"] = _STATE_AUTH
            _status[provider]["until"] = float("inf")
        elif kind == _STATE_RATE:
            # Only bump to rate_limited if not already in a worse state
            if current not in (_STATE_QUOTA, _STATE_AUTH):
                _status[provider]["state"] = _STATE_RATE
                _status[provider]["until"] = _now() + _RATE_BACKOUT
        _status[provider]["last_error"] = err[:400]
    log.warning("Provider %s -> %s: %s", provider, kind, err[:120])
    return kind


def _mark_healthy(provider: str) -> None:
    with _lock:
        if _status[provider]["state"] in (_STATE_RATE, _STATE_QUOTA):
            _status[provider]["state"] = _STATE_HEALTHY
            _status[provider]["until"] = 0.0


def _is_available(provider: str) -> bool:
    if not _get_key(provider) and provider not in _ANONYMOUS_OK:
        return False
    with _lock:
        s     = _status.get(provider, {})
        state = s.get("state", _STATE_HEALTHY)
        if state == _STATE_HEALTHY:
            return True
        if state == _STATE_AUTH:
            return False
        # rate_limited or quota_exhausted: check if blackout expired
        if _now() >= s.get("until", 0.0):
            s["state"] = _STATE_HEALTHY
            s["until"] = 0.0
            return True
        return False


# ── Model lists ────────────────────────────────────────────────────────────────

GROQ_MODELS   = [
    "llama-3.3-70b-versatile",    # best quality
    "llama-3.1-8b-instant",       # fast, lower quota pressure
    "gemma2-9b-it",               # different family = separate quota bucket
    "mixtral-8x7b-32768",         # Mixtral — another quota bucket
    "llama3-8b-8192",             # legacy alias fallback
]
GEMINI_MODELS = ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-flash-8b"]
OPENAI_MODELS = ["gpt-4o-mini", "gpt-4o"]


# ── Low-level provider calls ───────────────────────────────────────────────────

def _call_groq(prompt: str, max_tokens: int, json_mode: bool) -> str:
    from groq import Groq
    client = Groq(api_key=_get_key("groq"))
    kwargs: dict = dict(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
    )
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    last_err: Any = None
    for model in GROQ_MODELS:
        try:
            resp = client.chat.completions.create(model=model, **kwargs)
            _mark_healthy("groq")
            return resp.choices[0].message.content
        except Exception as e:
            err = str(e)
            last_err = e
            if any(k in err for k in ("decommissioned", "404", "model_not_found")):
                continue  # try next model
            kind = _mark_error("groq", err)
            if kind in (_STATE_QUOTA, _STATE_AUTH):
                raise  # escalate immediately — blackout set
            if kind == _STATE_RATE:
                # Rate-limited on this model — try next smaller model immediately,
                # do NOT sleep here (caller has fallback providers waiting)
                log.warning("Groq rate-limited on %s, trying next model", model)
                continue
            raise  # unexpected error
    # All models rate-limited: mark provider and raise so router falls through to Gemini
    _mark_error("groq", "429 rate_limit all_models")
    raise RuntimeError("All Groq models rate-limited. Last: " + str(last_err))


def _call_gemini(prompt: str, max_tokens: int, json_mode: bool) -> str:
    import google.generativeai as genai
    genai.configure(api_key=_get_key("gemini"))
    # response_mime_type added in SDK >=0.4; we use prompt instruction for compat
    if json_mode:
        prompt = prompt + chr(10) + chr(10) + "Respond with valid JSON only. No markdown fences or prose."
    gen_cfg: dict[str, Any] = {"max_output_tokens": max_tokens, "temperature": 0.2}
    last_err: Any = None
    for model_name in GEMINI_MODELS:
        try:
            model = genai.GenerativeModel(model_name, generation_config=gen_cfg)
            resp  = model.generate_content(prompt)
            _mark_healthy("gemini")
            return resp.text
        except Exception as e:
            err = str(e)
            last_err = e
            if any(k in err for k in ("404", "not found", "deprecated")):
                continue  # try next model
            kind = _mark_error("gemini", err)
            if kind in (_STATE_QUOTA, _STATE_AUTH):
                raise
            raise
    raise RuntimeError("All Gemini models failed. Last: " + str(last_err))


def _call_openai(prompt: str, max_tokens: int, json_mode: bool) -> str:
    from openai import OpenAI
    client = OpenAI(api_key=_get_key("openai"))
    kwargs: dict = dict(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=0.2,
    )
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    last_err: Any = None
    for model in OPENAI_MODELS:
        try:
            resp = client.chat.completions.create(model=model, **kwargs)
            _mark_healthy("openai")
            return resp.choices[0].message.content
        except Exception as e:
            err = str(e)
            last_err = e
            if "404" in err or "model_not_found" in err:
                continue
            _mark_error("openai", err)
            raise
    raise RuntimeError("All OpenAI models failed. Last: " + str(last_err))


# ── Low-level chat (multi-turn) calls ─────────────────────────────────────────

def _call_groq_chat(messages: list, max_tokens: int, temperature: float) -> str:
    from groq import Groq
    client = Groq(api_key=_get_key("groq"))
    last_err: Any = None
    for model in GROQ_MODELS:
        for attempt in range(2):
            try:
                resp = client.chat.completions.create(
                    model=model, messages=messages,
                    max_tokens=max_tokens, temperature=temperature,
                )
                _mark_healthy("groq")
                return resp.choices[0].message.content
            except Exception as e:
                err = str(e)
                last_err = e
                if any(k in err for k in ("decommissioned", "404", "model_not_found")):
                    break
                kind = _mark_error("groq", err)
                if kind in (_STATE_QUOTA, _STATE_AUTH):
                    raise
                if kind == _STATE_RATE:
                    time.sleep(2 ** attempt + random.uniform(0, 1))
                    continue
                raise
    raise RuntimeError("Groq chat failed. Last: " + str(last_err))


def _call_gemini_chat(messages: list, max_tokens: int, temperature: float) -> str:
    import google.generativeai as genai
    genai.configure(api_key=_get_key("gemini"))
    # Flatten OpenAI-format messages to a single prompt
    parts = []
    for m in messages:
        role    = m.get("role", "user")
        content = m.get("content", "")
        if role == "system":
            parts.insert(0, "SYSTEM: " + content)
        elif role == "assistant":
            parts.append("Assistant: " + content)
        else:
            parts.append("User: " + content)
    prompt  = chr(10).join(parts)
    gen_cfg: dict[str, Any] = {"max_output_tokens": max_tokens, "temperature": temperature}
    try:
        model = genai.GenerativeModel("gemini-2.0-flash", generation_config=gen_cfg)
        resp  = model.generate_content(prompt)
        _mark_healthy("gemini")
        return resp.text
    except Exception as e:
        _mark_error("gemini", str(e))
        raise


def _call_openai_chat(messages: list, max_tokens: int, temperature: float) -> str:
    from openai import OpenAI
    client = OpenAI(api_key=_get_key("openai"))
    last_err: Any = None
    for model in OPENAI_MODELS:
        try:
            resp = client.chat.completions.create(
                model=model, messages=messages,
                max_tokens=max_tokens, temperature=temperature,
            )
            _mark_healthy("openai")
            return resp.choices[0].message.content
        except Exception as e:
            err = str(e)
            last_err = e
            if "404" in err or "model_not_found" in err:
                continue
            _mark_error("openai", err)
            raise
    raise RuntimeError("OpenAI chat failed. Last: " + str(last_err))



# ── HuggingFace Serverless Inference ──────────────────────────────────────────

HF_MODELS = [
    "meta-llama/Llama-3.1-8B-Instruct",
    "mistralai/Mistral-7B-Instruct-v0.3",
]


def _call_huggingface(prompt: str, max_tokens: int, json_mode: bool) -> str:
    try:
        from huggingface_hub import InferenceClient
    except ImportError:
        raise RuntimeError("huggingface_hub not installed; run: pip install huggingface_hub")
    # Preserve the raw token so we can distinguish "token present but bad" from
    # "anonymous access".  Do NOT use `or None` on a truthy-but-invalid token —
    # that would silently strip it and hide the auth error from the user.
    raw_token: str = _get_key("huggingface")
    token = raw_token if raw_token else None   # None → anonymous, "" → anonymous
    client = InferenceClient(token=token)
    if json_mode:
        prompt = prompt + chr(10) + chr(10) + "Respond with valid JSON only. No markdown fences."
    last_err: Any = None
    for model in HF_MODELS:
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=0.2,
            )
            _mark_healthy("huggingface")
            return resp.choices[0].message.content
        except Exception as e:
            err = str(e)
            last_err = e
            if "404" in err or ("model" in err.lower() and "not found" in err.lower()):
                continue
            kind = _mark_error("huggingface", err)
            # When the user has explicitly configured a token and it is rejected,
            # do NOT silently degrade to anonymous access — surface the auth error
            # immediately so the Integrations card can show ⚠ Auth Error.
            if kind == _STATE_AUTH and raw_token:
                raise RuntimeError(
                    "HuggingFace token rejected (401 auth_error). "
                    "Check your HF_TOKEN in the Integrations tab. "
                    "Original error: " + err[:200]
                ) from e
            if kind in (_STATE_QUOTA, _STATE_AUTH):
                raise
            if kind == _STATE_RATE:
                time.sleep(5)
                continue
            raise
    raise RuntimeError("All HuggingFace models failed. Last: " + str(last_err))


def _call_huggingface_chat(messages: list, max_tokens: int, temperature: float) -> str:
    try:
        from huggingface_hub import InferenceClient
    except ImportError:
        raise RuntimeError("huggingface_hub not installed")
    raw_token: str = _get_key("huggingface")
    token = raw_token if raw_token else None
    client = InferenceClient(token=token)
    try:
        resp = client.chat.completions.create(
            model=HF_MODELS[0],
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        _mark_healthy("huggingface")
        return resp.choices[0].message.content
    except Exception as e:
        err = str(e)
        kind = _mark_error("huggingface", err)
        # Same as _call_huggingface: don't silently degrade a bad token to anonymous.
        if kind == _STATE_AUTH and raw_token:
            raise RuntimeError(
                "HuggingFace token rejected (auth_error). "
                "Check your HF_TOKEN in the Integrations tab. "
                "Original error: " + err[:200]
            ) from e
        raise


# ── OpenRouter Free-Model Router ───────────────────────────────────────────────

OPENROUTER_MODELS = [
    "openrouter/auto",
    "meta-llama/llama-3.2-3b-instruct:free",
    "mistralai/mistral-7b-instruct:free",
]


def _call_openrouter(prompt: str, max_tokens: int, json_mode: bool) -> str:
    key = _get_key("openrouter")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY not configured — get a free key at openrouter.ai")
    from openai import OpenAI
    client = OpenAI(
        api_key=key,
        base_url="https://openrouter.ai/api/v1",
        default_headers={"HTTP-Referer": "https://fieldnote.app", "X-Title": "Fieldnote"},
    )
    kwargs: dict = dict(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=0.2,
    )
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    last_err: Any = None
    for model in OPENROUTER_MODELS:
        try:
            resp = client.chat.completions.create(model=model, **kwargs)
            _mark_healthy("openrouter")
            return resp.choices[0].message.content
        except Exception as e:
            err = str(e)
            last_err = e
            if "404" in err or "model_not_found" in err.lower():
                continue
            kind = _mark_error("openrouter", err)
            if kind in (_STATE_QUOTA, _STATE_AUTH):
                raise
            if kind == _STATE_RATE:
                time.sleep(3)
                continue
            raise
    raise RuntimeError("All OpenRouter models failed. Last: " + str(last_err))


def _call_openrouter_chat(messages: list, max_tokens: int, temperature: float) -> str:
    key = _get_key("openrouter")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY not configured")
    from openai import OpenAI
    client = OpenAI(
        api_key=key,
        base_url="https://openrouter.ai/api/v1",
        default_headers={"HTTP-Referer": "https://fieldnote.app", "X-Title": "Fieldnote"},
    )
    try:
        resp = client.chat.completions.create(
            model=OPENROUTER_MODELS[0],
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        _mark_healthy("openrouter")
        return resp.choices[0].message.content
    except Exception as e:
        _mark_error("openrouter", str(e))
        raise


# ── Public API ─────────────────────────────────────────────────────────────────

# Ordered: free first, billed last, then free-tier-with-optional-key
_PROVIDERS = ["groq", "gemini", "openai", "huggingface", "openrouter"]

# Providers that are genuinely free (no billing risk).
# Use call_llm_free_only() / call_chat_free_only() to guarantee zero spend.
FREE_PROVIDERS = ["groq", "gemini", "huggingface", "openrouter"]

_IMPL: dict[str, Any] = {
    "groq":        _call_groq,
    "gemini":      _call_gemini,
    "openai":      _call_openai,
    "huggingface": _call_huggingface,
    "openrouter":  _call_openrouter,
}

_CHAT_IMPL: dict[str, Any] = {
    "groq":        _call_groq_chat,
    "gemini":      _call_gemini_chat,
    "openai":      _call_openai_chat,
    "huggingface": _call_huggingface_chat,
    "openrouter":  _call_openrouter_chat,
}



def refresh_provider_key(provider: str) -> None:
    """Reset a provider from no_key / auth_error to healthy so it is retried.
    Call after saving a new API key so changes take effect without restart."""
    _init_status()
    with _lock:
        if provider in _status:
            current = _status[provider].get("state", _STATE_HEALTHY)
            if current in (_STATE_NO_KEY, _STATE_AUTH, _STATE_QUOTA):
                _status[provider]["state"] = _STATE_HEALTHY
                _status[provider]["until"] = 0.0
                _status[provider]["last_error"] = ""
                log.info("Provider %s key refreshed → healthy", provider)


def mark_provider_auth_error(provider: str, detail: str = "") -> None:
    """
    Permanently mark a provider as auth_error from outside the router
    (e.g. from integrations_registry.verify_integration after a 401).

    This ensures the Integrations card reflects bad-token state immediately,
    without waiting for a failed LLM call to set it implicitly.
    HuggingFace special case: only mark auth_error when a token is actually
    configured — anonymous-only access is never an auth error.
    """
    _init_status()
    # For HuggingFace, anonymous access is valid.  Only mark auth_error when
    # a token was explicitly provided and got rejected.
    if provider == "huggingface" and not _get_key("huggingface"):
        log.debug("mark_provider_auth_error: skipped HF (no token configured — anonymous OK)")
        return
    with _lock:
        if provider in _status:
            _status[provider]["state"]      = _STATE_AUTH
            _status[provider]["until"]      = float("inf")
            _status[provider]["last_error"] = detail or "auth_error set by external verification"
    log.warning("Provider %s → auth_error (set by external verification): %s", provider, detail[:120])


def call_llm_smart(prompt: str, max_tokens: int = 4000, json_mode: bool = True) -> str:
    """
    Route to the best available provider; fall back down the list.
    Priority: Groq → Gemini → OpenAI → HuggingFace → OpenRouter.
    OpenAI is only reached when all free providers are exhausted.
    Raises RuntimeError only when ALL five providers are exhausted.
    """
    _init_status()  # pick up keys added without restart
    tried: list[str] = []
    for provider in _PROVIDERS:
        if not _is_available(provider):
            continue
        try:
            result = _IMPL[provider](prompt, max_tokens, json_mode)
            log.debug("call_llm_smart: used %s", provider)
            return result
        except Exception as e:
            tried.append(provider + ": " + str(e)[:80])
            log.warning("Provider %s failed in call_llm_smart, trying next: %s",
                        provider, str(e)[:100])
            continue
    raise RuntimeError("All providers exhausted. Errors: " + " | ".join(tried))


def call_llm_free_only(prompt: str, max_tokens: int = 4000, json_mode: bool = True) -> str:
    """
    Like call_llm_smart but **never touches OpenAI** — zero billing risk.
    Priority: Groq → Gemini → HuggingFace → OpenRouter.
    Use this for background agents, discovery, enhancement, and any
    task where incurring cost is unacceptable.
    Raises RuntimeError if all free providers are exhausted.
    """
    _init_status()
    tried: list[str] = []
    for provider in FREE_PROVIDERS:
        if not _is_available(provider):
            continue
        try:
            result = _IMPL[provider](prompt, max_tokens, json_mode)
            log.debug("call_llm_free_only: used %s", provider)
            return result
        except Exception as e:
            tried.append(provider + ": " + str(e)[:80])
            log.warning("Provider %s failed in call_llm_free_only, trying next: %s",
                        provider, str(e)[:100])
            continue
    raise RuntimeError(
        "All free providers exhausted (Groq, Gemini, HuggingFace, OpenRouter). "
        "Errors: " + " | ".join(tried)
    )


def call_chat_smart(
    messages: list,
    max_tokens: int = 900,
    temperature: float = 0.7,
) -> tuple[str, str]:
    """
    Route multi-turn chat to the best available provider.
    Returns (response_text, provider_name_used).
    Priority: Groq → Gemini → OpenAI → HuggingFace → OpenRouter.
    """
    _init_status()
    tried: list[str] = []
    for provider in _PROVIDERS:
        if not _is_available(provider):
            continue
        try:
            result = _CHAT_IMPL[provider](messages, max_tokens, temperature)
            return result, provider
        except Exception as e:
            tried.append(provider + ": " + str(e)[:80])
            log.warning("Provider %s failed in call_chat_smart, trying next: %s",
                        provider, str(e)[:100])
            continue
    raise RuntimeError("All providers exhausted for chat. Errors: " + " | ".join(tried))


def call_chat_free_only(
    messages: list,
    max_tokens: int = 900,
    temperature: float = 0.7,
) -> tuple[str, str]:
    """
    Multi-turn chat that **never touches OpenAI** — zero billing risk.
    Returns (response_text, provider_name_used).
    Priority: Groq → Gemini → HuggingFace → OpenRouter.
    """
    _init_status()
    tried: list[str] = []
    for provider in FREE_PROVIDERS:
        if not _is_available(provider):
            continue
        try:
            result = _CHAT_IMPL[provider](messages, max_tokens, temperature)
            return result, provider
        except Exception as e:
            tried.append(provider + ": " + str(e)[:80])
            log.warning("Provider %s failed in call_chat_free_only, trying next: %s",
                        provider, str(e)[:100])
            continue
    raise RuntimeError(
        "All free providers exhausted for chat (Groq, Gemini, HuggingFace, OpenRouter). "
        "Errors: " + " | ".join(tried)
    )


# ── Paid-fallback toggle ──────────────────────────────────────────────────────

ALLOW_PAID_FALLBACK: bool = False  # off by default — no billing risk


def set_paid_fallback(enabled: bool) -> None:
    """Toggle whether OpenAI (billed) is included in the provider list.
    When False, OpenAI is excluded even if CHATGPT key is configured."""
    global ALLOW_PAID_FALLBACK
    ALLOW_PAID_FALLBACK = bool(enabled)
    log.info("Paid fallback set to: %s", ALLOW_PAID_FALLBACK)


def _available_providers(allow_paid: bool = False) -> list[str]:
    """Return the ordered provider list, optionally including OpenAI."""
    global ALLOW_PAID_FALLBACK
    use_paid = allow_paid or ALLOW_PAID_FALLBACK
    return [p for p in _PROVIDERS if use_paid or p != "openai"]


def call_llm_for_lens(
    lens: str,
    prompt: str,
    max_tokens: int = 4000,
    json_mode: bool = True,
    allow_paid: bool = False,
) -> str:
    """
    Lens-aware provider routing that spreads concurrent lenses across different
    providers to avoid concurrent 429s:

    • "educator"     → Groq first (primary), then Gemini, HuggingFace, OpenRouter
    • "practitioner" → Gemini first (avoids concurrent Groq drain), then Groq,
                       HuggingFace, OpenRouter
    • "judge"        → Gemini first, then Groq, HuggingFace, OpenRouter
    • anything else  → standard call_llm_smart order

    This replaces the fragile time.sleep(4) in the practitioner extractor.
    Raises RuntimeError when all available providers are exhausted.
    """
    _init_status()

    # Lens-specific provider preference order
    if lens == "educator":
        preferred = ["groq", "gemini", "huggingface", "openrouter"]
    elif lens in ("practitioner", "judge"):
        preferred = ["gemini", "groq", "huggingface", "openrouter"]
    else:
        preferred = list(FREE_PROVIDERS)

    if allow_paid or ALLOW_PAID_FALLBACK:
        # Append openai at the end as last resort when paid fallback enabled
        if "openai" not in preferred:
            preferred.append("openai")

    tried: list[str] = []
    for provider in preferred:
        if not _is_available(provider):
            continue
        try:
            result = _IMPL[provider](prompt, max_tokens, json_mode)
            log.debug("call_llm_for_lens[%s]: used %s", lens, provider)
            return result
        except Exception as e:
            tried.append(f"{provider}: {str(e)[:80]}")
            log.warning(
                "call_llm_for_lens[%s]: %s failed, trying next: %s",
                lens, provider, str(e)[:100],
            )
            continue

    raise RuntimeError(
        f"All providers exhausted for lens '{lens}'. Errors: {' | '.join(tried)}"
    )


def add_preflight_check() -> dict[str, str]:
    """
    Ping each available provider with a minimal prompt to assess readiness.
    Returns a dict mapping provider → "ok" | "rate_limited" | "quota_exhausted" |
    "auth_error" | "no_key" | "error:<msg>".
    Does NOT block the caller; results are informational only.
    """
    _init_status()
    results: dict[str, str] = {}
    mini_prompt = "Say 'ok' in one word."
    for provider in _PROVIDERS:
        if not _get_key(provider) and provider not in _ANONYMOUS_OK:
            results[provider] = "no_key"
            continue
        with _lock:
            state = _status.get(provider, {}).get("state", _STATE_HEALTHY)
        if state != _STATE_HEALTHY:
            results[provider] = state
            continue
        try:
            _IMPL[provider](mini_prompt, 10, False)
            results[provider] = "ok"
        except Exception as e:
            kind = _classify_error(str(e))
            results[provider] = kind if kind else f"error:{str(e)[:60]}"
    return results


def provider_status() -> dict:
    """
    Return live status dict for each provider.
    Used by /api/provider-status endpoint and the UI health bar.
    """
    _init_status()
    now = _now()
    out: dict[str, dict] = {}
    for provider in _PROVIDERS:
        key = _get_key(provider)
        if not key:
            # Anonymous-OK providers show no_key (amber, not red) but are still usable
            out[provider] = {"state": "no_key", "retry_in": None, "last_error": "",
                             "anonymous_ok": provider in _ANONYMOUS_OK}
            continue
        with _lock:
            s     = dict(_status.get(provider, {}))
        state = s.get("state", _STATE_HEALTHY)
        until = s.get("until", 0.0)
        # Auto-heal expired blackouts for the status report
        if state in (_STATE_RATE, _STATE_QUOTA) and until != float("inf") and now >= until:
            state = _STATE_HEALTHY
        retry_in = None
        if state in (_STATE_RATE, _STATE_QUOTA) and until != float("inf"):
            retry_in = max(0, int(until - now))
        out[provider] = {
            "state":        state,
            "retry_in":     retry_in,
            "last_error":   s.get("last_error", "")[:200],
            "anonymous_ok": provider in _ANONYMOUS_OK,
        }
    return out
