"""
agents/provider_router.py

Centralised AI-provider router with quota/health tracking.

Priority order : Groq → OpenAI → Gemini
States         : healthy | rate_limited | quota_exhausted | auth_error
Blackout times : quota_exhausted → 2 hrs, auth_error → permanent (until restart),
                 rate_limited   → 30 s (soft; exponential backoff inside the call)
"""
import os, time, threading, logging, random
from typing import Optional

log = logging.getLogger(__name__)

QUOTA_BLACKOUT = 7200       # 2 hours
RATE_BLACKOUT  = 30         # 30 seconds
AUTH_BLACKOUT  = float("inf")

GROQ_MODELS   = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "llama3-8b-8192"]
OPENAI_MODELS = ["gpt-4o-mini", "gpt-4o"]


class ProviderRouter:
    """Thread-safe provider router that tracks quota/health per provider."""

    def __init__(self):
        self._lock  = threading.Lock()
        self._state = {
            "groq":   {"state": "healthy", "since": 0.0, "error": ""},
            "openai": {"state": "healthy", "since": 0.0, "error": ""},
            "gemini": {"state": "healthy", "since": 0.0, "error": ""},
        }

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _is_available(self, provider: str) -> bool:
        with self._lock:
            s     = self._state[provider]
            state = s["state"]
            if state == "healthy":
                return True
            if state == "auth_error":
                return False
            duration = QUOTA_BLACKOUT if state == "quota_exhausted" else RATE_BLACKOUT
            if time.time() - s["since"] > duration:
                s["state"] = "healthy"
                s["error"] = ""
                log.info("Provider %s recovered from %s", provider, state)
                return True
            return False

    def _blackout(self, provider: str, state: str, error: str):
        with self._lock:
            self._state[provider] = {
                "state": state,
                "since": time.time(),
                "error": error[:200],
            }
        log.warning("Provider %s → %s: %s", provider, state, error[:120])

    @staticmethod
    def _classify_error(err: str) -> str:
        """Return the blackout state for an error string (or 'error' for generic)."""
        el = err.lower()
        if "401" in err or "invalid_api_key" in el or "authentication" in el:
            return "auth_error"
        # OpenAI quota: "insufficient_quota" / "quota_exceeded"
        # Groq quota:   "rate_limit_exceeded" with "quota" mention or "insufficient"
        if ("insufficient_quota" in el or "quota_exceeded" in el or
                ("429" in err and ("quota" in el or "insufficient" in el or
                                   "credit" in el or "billing" in el))):
            return "quota_exhausted"
        if "429" in err or "rate_limit" in el or "rate limit" in el:
            return "rate_limited"
        return "error"

    # ── Per-provider callers ──────────────────────────────────────────────────

    def _call_groq(self, prompt: str = "", messages: Optional[list] = None,
                   max_tokens: int = 4000, json_mode: bool = True,
                   temperature: float = 0.2) -> str:
        from groq import Groq
        api_key = os.getenv("GROQ_API_KEY") or os.getenv("GROQ")
        if not api_key:
            raise RuntimeError("Groq API key not configured")
        client = Groq(api_key=api_key)
        if messages is None:
            messages = [{"role": "user", "content": prompt}]
        kwargs: dict = dict(messages=messages, max_tokens=max_tokens,
                            temperature=temperature)
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        last_err = None
        for model in GROQ_MODELS:
            for attempt in range(3):
                try:
                    resp = client.chat.completions.create(model=model, **kwargs)
                    return resp.choices[0].message.content
                except Exception as e:
                    err   = str(e)
                    last_err = e
                    cls   = self._classify_error(err)
                    if cls in ("quota_exhausted", "auth_error"):
                        self._blackout("groq", cls, err)
                        raise
                    if any(k in err for k in ("decommissioned", "404", "model_not_found")):
                        break   # try next model
                    if cls == "rate_limited":
                        wait = (2 ** attempt) + random.uniform(0, 1)
                        time.sleep(wait)
                        continue
                    raise
        raise RuntimeError(f"All Groq models failed. Last: {last_err}")

    def _call_openai(self, prompt: str = "", messages: Optional[list] = None,
                     max_tokens: int = 4000, json_mode: bool = True,
                     temperature: float = 0.2) -> str:
        from openai import OpenAI
        api_key = os.getenv("CHATGPT") or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OpenAI API key not configured")
        client = OpenAI(api_key=api_key)
        if messages is None:
            messages = [{"role": "user", "content": prompt}]
        kwargs: dict = dict(messages=messages, max_tokens=max_tokens,
                            temperature=temperature)
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        last_err = None
        for model in OPENAI_MODELS:
            try:
                resp = client.chat.completions.create(model=model, **kwargs)
                return resp.choices[0].message.content
            except Exception as e:
                last_err = e
                err  = str(e)
                cls  = self._classify_error(err)
                if cls in ("quota_exhausted", "auth_error"):
                    self._blackout("openai", cls, err)
                    raise
                if "404" in err or "model_not_found" in err:
                    continue   # try next model
                raise
        raise RuntimeError(f"All OpenAI models failed. Last: {last_err}")

    def _call_gemini(self, prompt: str = "", messages: Optional[list] = None,
                     max_tokens: int = 4000, json_mode: bool = True,
                     temperature: float = 0.2) -> str:
        api_key = (os.getenv("Google_API_Key") or os.getenv("Gemini") or
                   os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))
        if not api_key:
            raise RuntimeError("Gemini API key not configured")
        try:
            import google.generativeai as genai
        except ImportError:
            raise RuntimeError("google-generativeai package not installed")
        genai.configure(api_key=api_key)
        # Flatten message list into a single prompt
        if messages:
            parts = []
            for m in messages:
                role    = m.get("role", "user")
                content = m.get("content", "")
                if role == "system":
                    parts.append(f"[System]: {content}")
                else:
                    parts.append(f"[{role.capitalize()}]: {content}")
            full_prompt = chr(10) + chr(10).join(parts)
        else:
            full_prompt = prompt
        if json_mode:
            full_prompt += chr(10) + chr(10) + "Respond with valid JSON only. No markdown fences."
        try:
            model = genai.GenerativeModel(
                "gemini-2.0-flash",
                generation_config={
                    "max_output_tokens": max_tokens,
                    "temperature": temperature,
                },
            )
            resp = model.generate_content(full_prompt)
            return resp.text
        except Exception as e:
            err = str(e)
            cls = self._classify_error(err)
            if cls in ("quota_exhausted", "auth_error"):
                self._blackout("gemini", cls, err)
            raise

    # ── Public API ────────────────────────────────────────────────────────────

    def call_llm_smart(self, prompt: str = "", max_tokens: int = 4000,
                       json_mode: bool = True, messages: Optional[list] = None,
                       temperature: float = 0.2) -> tuple[str, str]:
        """
        Try AI providers in order (Groq → OpenAI → Gemini), skipping blacked-out ones.

        Returns (content: str, provider_name: str).
        Raises RuntimeError if all available providers fail.
        """
        providers = [
            ("groq",   self._call_groq),
            ("openai", self._call_openai),
            ("gemini", self._call_gemini),
        ]
        last_err = None
        for name, fn in providers:
            if not self._is_available(name):
                log.info("Skipping provider %s (blacked out)", name)
                continue
            try:
                content = fn(
                    prompt=prompt, messages=messages,
                    max_tokens=max_tokens, json_mode=json_mode,
                    temperature=temperature,
                )
                log.debug("call_llm_smart: succeeded with %s", name)
                return content, name
            except Exception as e:
                last_err = e
                cls = self._classify_error(str(e))
                if cls in ("quota_exhausted", "auth_error"):
                    log.warning("Provider %s blacked out (%s), trying next", name, cls)
                else:
                    log.warning("Provider %s failed (%s), trying next", name, str(e)[:80])
                continue
        raise RuntimeError(
            "All AI providers exhausted or unavailable. Last error: " + str(last_err)
        )

    def provider_status(self) -> dict:
        """
        Return health state for each provider.
        Shape: { name: { state, seconds_until_retry, error } }
        """
        result = {}
        with self._lock:
            for name, s in self._state.items():
                state = s["state"]
                until = 0
                if state == "quota_exhausted":
                    until = max(0, QUOTA_BLACKOUT - (time.time() - s["since"]))
                elif state == "rate_limited":
                    until = max(0, RATE_BLACKOUT - (time.time() - s["since"]))
                result[name] = {
                    "state":               state,
                    "seconds_until_retry": int(until),
                    "error":               s["error"],
                }
        return result


# ── Module-level singleton ────────────────────────────────────────────────────

_router = ProviderRouter()


def call_llm_smart(prompt: str = "", max_tokens: int = 4000,
                   json_mode: bool = True, messages: Optional[list] = None,
                   temperature: float = 0.2) -> tuple[str, str]:
    """Module-level wrapper — returns (content, provider_name)."""
    return _router.call_llm_smart(
        prompt=prompt, max_tokens=max_tokens,
        json_mode=json_mode, messages=messages,
        temperature=temperature,
    )


def provider_status() -> dict:
    """Return current health state for all providers."""
    return _router.provider_status()
