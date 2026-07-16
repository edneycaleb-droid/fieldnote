"""
Fieldnote Integration Registry
================================
Single source of truth for every third-party service Fieldnote can connect to.

To add a new integration:
  1. Append an entry to REGISTRY with the required fields (see below).
  2. Add a `def _verify_<id>(key: str) -> dict` returning {ok, detail?, error?}.
  3. Register it in _VERIFIERS.
  That's it — UI, API routes, and the Integration Agent auto-render from here.

auth_type values:
  "api_key"  — user pastes a key; shown with input box + provider link
  "oauth"    — provider redirect or device-flow; shown with Connect button
  "none"     — no auth needed (informational entry only)
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request

log = logging.getLogger("fieldnote.integrations")


# ── Registry ──────────────────────────────────────────────────────────────────

REGISTRY: list[dict] = [

    # ── LLM providers ────────────────────────────────────────────────────────

    {
        "id":              "groq",
        "label":           "Groq",
        "tagline":         "Primary LLM — llama-3.3-70b, gemma2, mixtral · 14k tokens/min free",
        "description":     (
            "The core AI engine for all skill extraction and enhancement. "
            "Free tier includes 14,400 tokens/min and 6,000 req/day — no credit card ever."
        ),
        "auth_type":       "api_key",
        "key_env":         "GROQ",
        "key_url":         "https://console.groq.com/keys",
        "key_url_label":   "Get free Groq key →",
        "key_placeholder": "gsk_…",
        "required":        True,
        "free":            True,
        "icon":            "⚡",
        "color":           "#f97316",
        "category":        "llm",
        "badge_text":      "REQUIRED",
        "docs_url":        "https://console.groq.com/docs/openai",
        "setup_steps": [
            "Go to <strong>console.groq.com</strong> and create a free account (no credit card).",
            "Click <strong>API Keys</strong> in the left sidebar.",
            "Click <strong>Create API Key</strong>, give it any name.",
            "Copy the key — it starts with <code>gsk_</code>.",
            "Paste it in the box below and click <strong>Authenticate</strong>.",
        ],
        "features_unlocked": [
            "llama-3.3-70b-versatile — primary extraction model",
            "Educator lens + Practitioner lens in AI Arena",
            "Judge synthesis step for highest-quality output",
            "gemma2-9b-it and mixtral-8x7b as automatic fallbacks",
            "Groq Whisper transcription (8 hours audio/day free)",
        ],
    },

    {
        "id":              "gemini",
        "label":           "Google Gemini",
        "tagline":         "Fallback LLM — gemini-2.0-flash · 1,500 req/day free",
        "description":     (
            "Free secondary LLM. ⚠️ Use an <strong>AI Studio key</strong> from "
            "aistudio.google.com — Cloud Console keys have zero quota and will not work."
        ),
        "auth_type":       "api_key",
        "key_env":         "Gemini",
        "key_url":         "https://aistudio.google.com/app/apikey",
        "key_url_label":   "Get free AI Studio key →",
        "key_placeholder": "AIza…",
        "required":        False,
        "free":            True,
        "icon":            "🔷",
        "color":           "#4285f4",
        "category":        "llm",
        "badge_text":      "FREE",
        "docs_url":        "https://ai.google.dev/tutorials/quickstart",
        "setup_steps": [
            "Go to <strong>aistudio.google.com</strong> (NOT console.cloud.google.com).",
            "Sign in with your Google account.",
            "Click <strong>Get API key</strong> → <strong>Create API key</strong>.",
            "Copy the key — it starts with <code>AIza</code>.",
            "Paste it below and click <strong>Authenticate</strong>.",
            "⚠️ If you see a quota error, you used the Cloud Console — delete it and use AI Studio.",
        ],
        "features_unlocked": [
            "gemini-2.0-flash-exp as fallback LLM (1,500 req/day free)",
            "Reduces Groq quota pressure during heavy extraction runs",
            "gemini-1.5-flash and gemini-1.5-pro as secondary fallbacks",
        ],
    },

    {
        "id":              "openrouter",
        "label":           "OpenRouter",
        "tagline":         "50+ free models — Llama, Mistral, Gemma · free account",
        "description":     (
            "Routes to 50+ models including free Llama-3, Mistral-7B, and Gemma. "
            "Free account, no credit card required. Key created in under a minute."
        ),
        "auth_type":       "api_key",
        "key_env":         "OPENROUTER_API_KEY",
        "key_url":         "https://openrouter.ai/keys",
        "key_url_label":   "Get free OpenRouter key →",
        "key_placeholder": "sk-or-…",
        "required":        False,
        "free":            True,
        "icon":            "🔀",
        "color":           "#8b5cf6",
        "category":        "llm",
        "badge_text":      "FREE",
        "docs_url":        "https://openrouter.ai/docs",
        "setup_steps": [
            "Go to <strong>openrouter.ai</strong> and create a free account.",
            "Click your profile avatar → <strong>Keys</strong>.",
            "Click <strong>Create Key</strong> and give it a name.",
            "Copy the key — it starts with <code>sk-or-</code>.",
            "Paste it below and click <strong>Authenticate</strong>.",
        ],
        "features_unlocked": [
            "50+ free models including llama-3.2-3b-instruct:free",
            "mistral-7b-instruct:free and gemma-7b-it:free",
            "Quaternary LLM fallback — extra resilience when others rate-limit",
            "Access to 200+ total models (many with free tiers)",
        ],
    },

    {
        "id":              "huggingface",
        "label":           "HuggingFace",
        "tagline":         "Serverless inference — Qwen 72B, Llama · free read token",
        "description":     (
            "Anonymous access already works. A free read token unlocks higher rate limits "
            "and larger models like Qwen2.5-72B-Instruct."
        ),
        "auth_type":       "api_key",
        "key_env":         "HF_TOKEN",
        "key_url":         "https://huggingface.co/settings/tokens/new?tokenType=read",
        "key_url_label":   "Get free HF read token →",
        "key_placeholder": "hf_…",
        "required":        False,
        "free":            True,
        "icon":            "🤗",
        "color":           "#ff9d00",
        "category":        "llm",
        "badge_text":      "FREE",
        "docs_url":        "https://huggingface.co/docs/api-inference/index",
        "setup_steps": [
            "Go to <strong>huggingface.co</strong> and create a free account.",
            "Go to <strong>Settings → Access Tokens</strong>.",
            "Click <strong>New token</strong>, select type <strong>Read</strong>.",
            "Copy the token — it starts with <code>hf_</code>.",
            "Paste it below and click <strong>Authenticate</strong>.",
            "Note: anonymous access already works — this just unlocks higher limits.",
        ],
        "features_unlocked": [
            "Qwen2.5-72B-Instruct via serverless inference",
            "Llama-3.1-8B-Instruct and 1,000s of open models",
            "Tertiary LLM fallback (after Groq and Gemini)",
            "Higher rate limits vs anonymous access",
        ],
    },

    {
        "id":              "openai",
        "label":           "OpenAI",
        "tagline":         "Optional paid upgrade — GPT-4o-mini · Groq covers this for free",
        "description":     (
            "Optional quality upgrade — not required for full functionality. "
            "Groq llama-3.3-70b already handles everything OpenAI does, for free."
        ),
        "auth_type":       "api_key",
        "key_env":         "CHATGPT",
        "key_url":         "https://platform.openai.com/api-keys",
        "key_url_label":   "Create OpenAI key →",
        "key_placeholder": "sk-…",
        "required":        False,
        "free":            False,
        "icon":            "🤖",
        "color":           "#10a37f",
        "category":        "llm",
        "badge_text":      "PAID",
        "docs_url":        "https://platform.openai.com/docs",
        "setup_steps": [
            "Create an account at <strong>platform.openai.com</strong>.",
            "Add a payment method in <strong>Settings → Billing</strong>.",
            "Go to <strong>API Keys → Create new secret key</strong>.",
            "Copy the key — it starts with <code>sk-</code>.",
            "Paste it below and click <strong>Authenticate</strong>.",
            "💡 This is optional — Groq provides equivalent quality for free.",
        ],
        "features_unlocked": [
            "GPT-4o-mini as a paid quality backup (already covered by Groq free)",
            "GPT-4o for premium extraction if needed",
            "Position #3 in fallback chain — only used when free tiers exhausted",
        ],
    },

    # ── Infrastructure ────────────────────────────────────────────────────────

    {
        "id":              "github",
        "label":           "GitHub",
        "tagline":         "Repo sync + autonomous skill discovery · free PAT",
        "description":     (
            "Pushes all skills + source code to your GitHub repo and powers the "
            "autonomous discovery agent. Requires a classic PAT with 'repo' scope."
        ),
        "auth_type":       "api_key",
        "key_env":         "GITHUBPAT",
        "key_url":         "https://github.com/settings/tokens/new?scopes=repo&description=Fieldnote",
        "key_url_label":   "Create GitHub PAT (repo scope) →",
        "key_placeholder": "ghp_… or github_pat_…",
        "required":        False,
        "free":            True,
        "icon":            "🐙",
        "color":           "#6e40c9",
        "category":        "sync",
        "badge_text":      "FREE",
        "docs_url":        "https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/creating-a-personal-access-token",
        "setup_steps": [
            "Log into <strong>github.com</strong> and go to your profile.",
            "Navigate to <strong>Settings → Developer settings → Personal access tokens → Tokens (classic)</strong>.",
            "Click <strong>Generate new token (classic)</strong>.",
            "Under <strong>Select scopes</strong>, check the <strong>repo</strong> checkbox (all sub-items).",
            "Click <strong>Generate token</strong> and copy it immediately.",
            "Paste it below and click <strong>Authenticate</strong>.",
        ],
        "features_unlocked": [
            "Skill library automatically pushed to your GitHub repo",
            "Autonomous GitHub Discovery Agent (every 2h — finds new repos)",
            "Free-alternative pairing saved to GitHub",
            "Source code mirrored to repo (app.py, agents/, templates/)",
            "ChatGPT knowledge base synced to repository",
        ],
    },
]


# ── Verification functions ─────────────────────────────────────────────────────

def _http_get(url: str, headers: dict) -> tuple[int, str]:
    req = urllib.request.Request(
        url, headers={**headers, "User-Agent": "Fieldnote/1.0"}
    )
    try:
        with urllib.request.urlopen(req, timeout=9) as resp:
            return resp.status, resp.read(1024).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read(512).decode("utf-8", errors="replace")
        except Exception:
            pass
        return exc.code, body
    except Exception as exc:
        return 0, str(exc)


def _verify_groq(key: str) -> dict:
    status, body = _http_get(
        "https://api.groq.com/openai/v1/models",
        {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    if status == 200:
        return {"ok": True,  "detail": "Connected — llama-3.3-70b ready"}
    if status == 401:
        return {"ok": False, "error": "Invalid API key — check at console.groq.com/keys"}
    if status == 429:
        return {"ok": True,  "detail": "Key valid — currently rate-limited (auto-clears in 30 s)"}
    return {"ok": False, "error": f"Groq returned HTTP {status}"}


def _verify_gemini(key: str) -> dict:
    status, body = _http_get(
        f"https://generativelanguage.googleapis.com/v1beta/models?key={key}&pageSize=1",
        {"Content-Type": "application/json"},
    )
    if status == 200:
        return {"ok": True,  "detail": "Connected — gemini-2.0-flash ready"}
    if status == 400 and "API_KEY" in body.upper():
        return {"ok": False, "error": "Invalid API key format"}
    if status == 403:
        return {"ok": False, "error": "Key valid but quota is zero — use AI Studio key, not Cloud Console"}
    if status == 401:
        return {"ok": False, "error": "Invalid API key"}
    return {"ok": False, "error": f"Gemini returned HTTP {status}"}


def _verify_openrouter(key: str) -> dict:
    status, body = _http_get(
        "https://openrouter.ai/api/v1/models",
        {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    if status == 200:
        return {"ok": True,  "detail": "Connected — 50+ free models available"}
    if status == 401:
        return {"ok": False, "error": "Invalid API key"}
    return {"ok": False, "error": f"OpenRouter returned HTTP {status}"}


def _verify_huggingface(key: str) -> dict:
    status, body = _http_get(
        "https://huggingface.co/api/whoami-v2",
        {"Authorization": f"Bearer {key}"},
    )
    if status == 200:
        try:
            data = json.loads(body)
            name = data.get("name") or data.get("fullname") or "user"
        except Exception:
            name = "user"
        return {"ok": True,  "detail": f"Authenticated as {name} — serverless inference ready"}
    if status == 401:
        return {"ok": False, "error": "Invalid token"}
    return {"ok": False, "error": f"HuggingFace returned HTTP {status}"}


def _verify_openai(key: str) -> dict:
    status, body = _http_get(
        "https://api.openai.com/v1/models",
        {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    if status == 200:
        return {"ok": True,  "detail": "Connected — GPT-4o-mini available"}
    if status == 401:
        return {"ok": False, "error": "Invalid API key"}
    if status == 429:
        return {"ok": True,  "detail": "Key valid — rate limited (quota OK)"}
    return {"ok": False, "error": f"OpenAI returned HTTP {status}"}


def _verify_github(key: str) -> dict:
    status, body = _http_get(
        "https://api.github.com/user",
        {
            "Authorization":        f"Bearer {key}",
            "Accept":               "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    if status == 200:
        try:
            login = json.loads(body).get("login", "user")
        except Exception:
            login = "user"
        return {"ok": True,  "detail": f"Connected as @{login} — repo sync ready"}
    if status == 401:
        return {"ok": False, "error": "Invalid token — needs 'repo' scope on a classic PAT"}
    if status == 403:
        return {"ok": False, "error": "Token lacks required 'repo' scope"}
    return {"ok": False, "error": f"GitHub returned HTTP {status}"}


_VERIFIERS: dict[str, object] = {
    "groq":        _verify_groq,
    "gemini":      _verify_gemini,
    "openrouter":  _verify_openrouter,
    "huggingface": _verify_huggingface,
    "openai":      _verify_openai,
    "github":      _verify_github,
}


# ── Public API ─────────────────────────────────────────────────────────────────

def verify_integration(integration_id: str, key: str) -> dict:
    """
    Call the provider API to verify `key`.
    Returns {"ok": bool, "detail"?: str, "error"?: str}.
    """
    fn = _VERIFIERS.get(integration_id)
    if not fn:
        return {"ok": True, "detail": "Saved — no live verification available for this provider"}
    try:
        return fn(key)  # type: ignore[call-arg]
    except Exception as exc:
        log.warning("Verify error for %s: %s", integration_id, exc)
        return {"ok": False, "error": str(exc)[:120]}


def get_all_statuses(local_keys_file: str | None = None) -> list[dict]:
    """
    Return REGISTRY + dynamic agent suggestions, each enriched with:
      status:        'connected' | 'pending' | 'error' | 'anonymous'
      status_detail: human-readable status string
      has_key:       bool
      last_checked:  ISO timestamp from agent (if available)
    """
    # Load persisted keys
    saved: dict = {}
    if local_keys_file:
        try:
            with open(local_keys_file) as f:
                saved = json.load(f)
        except Exception:
            pass

    # Load agent health-check timestamps
    agent_checks: dict = {}
    try:
        import json as _j
        from pathlib import Path as _P
        agent_status = _j.loads(_P("fieldnote_mcp/integration_agent_status.json").read_text())
        agent_checks = agent_status.get("checks", {})
    except Exception:
        pass

    # Load dynamic (agent-suggested) integrations
    dynamic: list[dict] = []
    try:
        from agents.integration_agent import get_dynamic_registry
        dynamic = get_dynamic_registry()
    except Exception:
        pass

    all_entries = REGISTRY + dynamic
    result: list[dict] = []

    for entry in all_entries:
        e       = dict(entry)
        key_env = entry.get("key_env", "")
        key_val = (os.environ.get(key_env) or "").strip() if key_env else ""
        if not key_val and key_env:
            key_val = saved.get(key_env, "").strip()

        e["has_key"] = bool(key_val)

        # Last-checked info from the agent
        chk = agent_checks.get(entry["id"], {})
        e["last_checked"] = chk.get("last_checked")
        e["agent_detail"] = chk.get("detail", "")

        # Suggestions: if a key_env is set and the key is now present the
        # user has connected it — drop the card so the suggestion clears.
        if entry.get("is_suggestion"):
            if key_env and key_val:
                continue   # already connected — don't show as a suggestion
            e["status"]        = "suggested"
            e["status_detail"] = "Agent suggestion based on your skill library"
            result.append(e)
            continue

        # HuggingFace works anonymously
        if not key_val and entry["id"] == "huggingface":
            e["status"]        = "anonymous"
            e["status_detail"] = "Works anonymously — token unlocks higher limits"
            result.append(e)
            continue

        if not key_val:
            e["status"]        = "pending"
            e["status_detail"] = "No key configured"
            result.append(e)
            continue

        # Live provider-router state (for LLM providers)
        router_state = _get_provider_router_state(entry["id"])
        if router_state == "auth_error":
            e["status"]        = "error"
            e["status_detail"] = "Authentication failed — key rejected by provider"
        elif router_state in ("healthy", "rate_limited", "quota_exhausted"):
            e["status"]        = "connected"
            e["status_detail"] = chk.get("detail") or "Connected"
        else:
            # Key saved but router hasn't attempted it yet (non-LLM or first boot)
            e["status"]        = "connected"
            e["status_detail"] = chk.get("detail") or "Key configured"

        result.append(e)

    return result


def _get_provider_router_state(integration_id: str) -> str:
    try:
        import agents.provider_router as pr
        pr._init_status()
        with pr._lock:
            s = pr._status.get(integration_id, {})
        return s.get("state", "unknown")
    except Exception:
        return "unknown"
