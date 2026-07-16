"""
Integration Agent
=================
Autonomous agent that manages the Integrations hub at runtime.

Responsibilities every 30 minutes:
  1. Health-check all connected integrations (live API call per provider)
  2. Auto-detect keys added via Replit Secrets UI but not yet in local_keys.json
  3. Scan skill-library tools and suggest missing / complementary integrations
  4. Maintain fieldnote_mcp/integration_agent_status.json (UI polls this)
  5. Push notable events (new connections, failures, recoveries) to Intel Feed

To add a new tool→integration hint: append to TOOL_INTEGRATION_HINTS below.
No other changes needed — everything else is data-driven.
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

log = logging.getLogger("fieldnote.integration_agent")

STATUS_FILE  = Path("fieldnote_mcp/integration_agent_status.json")
DYNAMIC_FILE = Path("fieldnote_mcp/integration_dynamic.json")

_write_lock = Lock()

# ── Tool → integration suggestion map ─────────────────────────────────────────
# When extracted skills mention these tool names the agent adds a suggestion card.
TOOL_INTEGRATION_HINTS: dict[str, dict] = {
    "pinecone": {
        "label": "Qdrant — free Pinecone alternative",
        "icon": "📌", "color": "#dc2626",
        "key_url": "https://qdrant.tech/documentation/quick-start/",
        "key_url_label": "Qdrant quick-start guide →",
        "description": "Your skills reference Pinecone. Qdrant is a free self-hosted vector DB with identical capabilities.",
    },
    "weaviate": {
        "label": "Qdrant — free Weaviate alternative",
        "icon": "🔎", "color": "#dc2626",
        "key_url": "https://qdrant.tech/documentation/quick-start/",
        "key_url_label": "Qdrant quick-start guide →",
        "description": "Your skills reference Weaviate. Qdrant replicates its search API and is free to self-host.",
    },
    "wandb": {
        "label": "Weights & Biases — ML experiment tracking",
        "icon": "📊", "color": "#ffbe00",
        "key_url": "https://wandb.ai/authorize",
        "key_url_label": "Get free W&B API key →",
        "description": "Your skills reference W&B. A free account covers unlimited personal experiments.",
    },
    "langsmith": {
        "label": "LangSmith — LangChain tracing",
        "icon": "🔗", "color": "#f97316",
        "key_env": "LANGCHAIN_API_KEY",
        "key_placeholder": "lsv2_pt_...",
        "key_url": "https://smith.langchain.com/settings",
        "key_url_label": "Create LangSmith API key →",
        "description": "Your skills reference LangSmith. Free tier covers tracing for personal projects.",
    },
    "cohere": {
        "label": "FastEmbed — free Cohere embeddings alternative",
        "icon": "🧮", "color": "#0f766e",
        "key_url": "https://qdrant.github.io/fastembed/",
        "key_url_label": "FastEmbed docs →",
        "description": "Your skills reference Cohere embeddings. FastEmbed runs locally on CPU for free.",
    },
    "replicate": {
        "label": "Ollama — free Replicate alternative",
        "icon": "🦙", "color": "#7c3aed",
        "key_url": "https://ollama.com/download",
        "key_url_label": "Download Ollama →",
        "description": "Your skills reference Replicate. Ollama runs 100+ models locally for free.",
    },
    "assemblyai": {
        "label": "Groq Whisper — free AssemblyAI alternative",
        "icon": "🎙", "color": "#f97316",
        "key_url": "https://console.groq.com/keys",
        "key_url_label": "Get Groq key (already in stack) →",
        "description": "Your skills reference AssemblyAI. Groq Whisper is already in the stack and free.",
    },
    "elevenlabs": {
        "label": "Coqui TTS — free ElevenLabs alternative",
        "icon": "🔊", "color": "#059669",
        "key_url": "https://github.com/coqui-ai/TTS",
        "key_url_label": "Coqui TTS GitHub →",
        "description": "Your skills reference ElevenLabs. Coqui TTS is open-source and runs locally.",
    },
    "anthropic": {
        "label": "Groq — free Claude alternative",
        "icon": "⚡", "color": "#f97316",
        "key_url": "https://console.groq.com/keys",
        "key_url_label": "Get free Groq key →",
        "description": "Your skills reference Anthropic. Groq runs Llama-3.3-70b free — already primary.",
    },
    "stability ai": {
        "label": "Diffusers — free Stability AI alternative",
        "icon": "🎨", "color": "#7c3aed",
        "key_url": "https://huggingface.co/docs/diffusers",
        "key_url_label": "Diffusers docs →",
        "description": "Your skills reference Stability AI. HuggingFace Diffusers runs SD locally for free.",
    },
    "mistral api": {
        "label": "Ollama + Mistral — free Mistral API alternative",
        "icon": "💨", "color": "#0284c7",
        "key_url": "https://ollama.com/library/mistral",
        "key_url_label": "Ollama Mistral model →",
        "description": "Your skills reference the paid Mistral API. Ollama runs Mistral locally free.",
    },
}


# ── Utilities ──────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_status() -> dict:
    try:
        return json.loads(STATUS_FILE.read_text())
    except Exception:
        return {
            "last_run": None,
            "checks": {},
            "suggestions": [],
            "events": [],
            "newly_connected": [],
            "summary": {},
        }


def _save_status(status: dict) -> None:
    with _write_lock:
        STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATUS_FILE.write_text(json.dumps(status, indent=2, default=str))


def _load_dynamic() -> list:
    try:
        return json.loads(DYNAMIC_FILE.read_text())
    except Exception:
        return []


def _save_dynamic(entries: list) -> None:
    with _write_lock:
        DYNAMIC_FILE.parent.mkdir(parents=True, exist_ok=True)
        DYNAMIC_FILE.write_text(json.dumps(entries, indent=2, default=str))


def get_dynamic_registry() -> list:
    """Return agent-discovered integration entries (used by get_all_statuses)."""
    return _load_dynamic()


def get_status() -> dict:
    """Return latest agent status for the /api/integration-agent/status route."""
    return _load_status()


# ── Main entry point ───────────────────────────────────────────────────────────

def run_agent() -> dict:
    """
    Called by the scheduler every 30 minutes.
    Returns a summary dict logged by the scheduler.
    """
    log.info("Integration agent: starting run…")
    status = _load_status()

    # 1. Health-check all connected integrations
    health = _health_check_all(status)

    # 2. Auto-detect keys added via Replit Secrets UI
    new_keys = _detect_new_env_keys()

    # 3. Suggest integrations based on skill tools in the library
    dynamic = _load_dynamic()
    suggestions = _suggest_from_skill_tools(dynamic)

    # 4. Build event log (newest first, capped at 100)
    new_events = health["events"] + new_keys["events"]
    all_events = new_events + status.get("events", [])
    all_events = all_events[:100]

    # 5. Persist status
    status.update({
        "last_run":        _now_iso(),
        "checks":          health["checks"],
        "suggestions":     suggestions,
        "events":          all_events,
        "newly_connected": new_keys["connected"],
        "summary": {
            "verified":        health["verified"],
            "newly_failed":    health["newly_failed"],
            "newly_connected": new_keys["connected"],
            "suggestion_count": len(suggestions),
        },
    })
    _save_status(status)

    # 6. Persist dynamic suggestions for the UI
    _save_dynamic(suggestions)

    # 7. Push to knowledge base if something notable happened
    if new_keys["connected"] or health["newly_failed"]:
        _write_knowledge_event(status, new_keys, health)

    summary = status["summary"]
    log.info("Integration agent: done — %s", summary)
    return summary


# ── Health check ───────────────────────────────────────────────────────────────

def _health_check_all(status: dict) -> dict:
    """Re-verify every connected integration against its live API."""
    from fieldnote_mcp.integrations_registry import verify_integration, get_all_statuses
    import app as _a

    checks       = dict(status.get("checks", {}))
    events: list = []
    newly_failed: list[str] = []
    verified     = 0

    try:
        current = get_all_statuses(local_keys_file=_a.LOCAL_KEYS_FILE)
    except Exception as exc:
        log.warning("Could not load integration statuses: %s", exc)
        return {"checks": checks, "events": [], "newly_failed": [], "verified": 0}

    for entry in current:
        iid = entry["id"]
        if entry["status"] not in ("connected",):
            continue  # only re-verify already-connected integrations

        # Retrieve the saved key
        key = (os.environ.get(entry["key_env"]) or "").strip()
        if not key:
            try:
                import json as _j
                with open(_a.LOCAL_KEYS_FILE) as f:
                    key = _j.load(f).get(entry["key_env"], "").strip()
            except Exception:
                pass
        if not key:
            continue

        prev_state = checks.get(iid, {}).get("state")
        result     = verify_integration(iid, key)
        now        = _now_iso()

        checks[iid] = {
            "state":        "ok" if result["ok"] else "error",
            "detail":       result.get("detail") or result.get("error", ""),
            "last_checked": now,
        }

        if result["ok"]:
            verified += 1
            if prev_state == "error":
                events.append({"ts": now, "type": "recovered", "iid": iid,
                               "msg": f"✓ {entry['label']} connection recovered"})
                log.info("Integration %s recovered", iid)
        else:
            newly_failed.append(iid)
            if prev_state != "error":
                events.append({"ts": now, "type": "failed", "iid": iid,
                               "msg": f"⚠ {entry['label']} verification failed: {result.get('error','')}"})
            log.warning("Integration %s health check failed: %s", iid, result.get("error"))

        time.sleep(0.4)  # polite pacing between API calls

    return {
        "checks":       checks,
        "events":       events,
        "newly_failed": newly_failed,
        "verified":     verified,
    }


# ── Auto key detection ─────────────────────────────────────────────────────────

def _detect_new_env_keys() -> dict:
    """
    Scan os.environ for integration env-var names that are set (e.g. via
    Replit Secrets UI) but not yet persisted to local_keys.json.
    Auto-save and activate them.

    Note: nonstandard secret aliases (GROQFREE → GROQ, Langchain → LANGCHAIN_API_KEY)
    are normalised at import time in agents/provider_router.py, so by the time this
    function runs the standard names are already visible in os.environ if the
    nonstandard aliases were the only source.  This function only needs to handle
    the canonical key_env values registered in the REGISTRY.
    """
    from fieldnote_mcp.integrations_registry import REGISTRY
    import app as _a

    connected: list[str] = []
    events:    list[dict] = []

    try:
        import json as _j
        with open(_a.LOCAL_KEYS_FILE) as f:
            saved = _j.load(f)
    except Exception:
        saved = {}

    for entry in REGISTRY:
        env_var   = entry["key_env"]
        if not env_var:
            continue
        env_val   = os.environ.get(env_var, "").strip()
        local_val = saved.get(env_var, "").strip()

        if env_val and not local_val:
            log.info("Integration agent: auto-detected %s from env", entry["id"])
            try:
                _a.save_local_key(env_var, env_val)
                # Refresh provider router if this is an LLM provider
                try:
                    import agents.provider_router as pr
                    if entry["id"] in getattr(pr, "KEY_ENV_MAP", {}):
                        pr.refresh_provider_key(entry["id"])
                        pr._init_status()
                except Exception:
                    pass
                connected.append(entry["id"])
                events.append({
                    "ts":   _now_iso(),
                    "type": "auto_detected",
                    "iid":  entry["id"],
                    "msg":  f"🔑 Auto-activated {entry['label']} key from Replit Secrets",
                })
            except Exception as exc:
                log.warning("Auto-detect save failed for %s: %s", entry["id"], exc)

    return {"connected": connected, "events": events}


# ── Skill-tool suggestions ─────────────────────────────────────────────────────

def _suggest_from_skill_tools(existing_dynamic: list) -> list:
    """
    Scan all extracted skill tools.
    For each tool in TOOL_INTEGRATION_HINTS not already covered, add a suggestion.
    """
    from fieldnote_mcp.integrations_registry import REGISTRY
    import app as _a

    registry_ids = {e["id"] for e in REGISTRY}
    existing_ids = {e["id"] for e in existing_dynamic}

    # Collect all tool names from the skill index
    all_tools_lower: set[str] = set()
    try:
        index = _a.load_index()
        for meta in index.values():
            for tool in meta.get("tools", []):
                all_tools_lower.add(tool.lower().strip())
    except Exception as exc:
        log.warning("Could not load skill index for suggestions: %s", exc)
        return list(existing_dynamic)

    suggestions = [e for e in existing_dynamic]  # keep existing
    existing_suggestion_ids = {e["id"] for e in suggestions}

    for tool_key, hint in TOOL_INTEGRATION_HINTS.items():
        sid = "suggest-" + tool_key.replace(" ", "-")
        if sid in registry_ids or sid in existing_suggestion_ids:
            continue
        # Check if this tool appears anywhere in the skill library
        if any(tool_key in t for t in all_tools_lower):
            log.info("Integration agent: suggesting %s (tool '%s' found in skills)", sid, tool_key)
            suggestions.append({
                "id":              sid,
                "label":           hint["label"],
                "tagline":         f"Agent suggestion — detected: {tool_key}",
                "description":     hint["description"],
                "auth_type":       "api_key",
                "key_env":         hint.get("key_env", ""),
                "key_url":         hint["key_url"],
                "key_url_label":   hint.get("key_url_label", "Learn more →"),
                "key_placeholder": hint.get("key_placeholder", ""),
                "required":        False,
                "free":            True,
                "icon":            hint.get("icon", "💡"),
                "color":           hint.get("color", "#6366f1"),
                "category":        "suggested",
                "badge_text":      "SUGGESTED",
                "is_suggestion":   True,
                "setup_steps":     [
                    f"Your skills reference '{tool_key}' — this integration would complement them.",
                    hint["description"],
                    f"Visit the link below to set it up.",
                ],
                "features_unlocked": [
                    f"Better workflow integration for {tool_key}-based skills",
                ],
            })

    return suggestions


# ── Knowledge base event ───────────────────────────────────────────────────────

def _write_knowledge_event(status: dict, new_keys: dict, health: dict) -> None:
    """Write a notable event to assistant_knowledge/ for ChatGPT to see."""
    try:
        import agents.github_sync as gs
        import re as _re

        parts: list[str] = []
        if new_keys["connected"]:
            parts.append(f"**Auto-activated keys:** {', '.join(new_keys['connected'])}")
        if health["newly_failed"]:
            parts.append(f"**Failed verifications:** {', '.join(health['newly_failed'])}")

        if not parts:
            return

        content = (
            "## Integration Agent Event\n\n"
            + "\n".join(f"- {p}" for p in parts) + "\n\n"
            f"**Verified successfully:** {health.get('verified', 0)}\n"
            f"**Timestamp:** {_now_iso()}\n\n"
            "This event was recorded automatically by the Integration Agent."
        )
        slug = "integration-agent-" + _now_iso()[:10]
        gs.sync_knowledge_entry({
            "category":   "session_learnings",
            "slug":       slug,
            "title":      "Integration Agent Health Event",
            "content":    content,
            "sources":    [],
            "confidence": "verified",
        })
    except Exception as exc:
        log.warning("Could not write knowledge event: %s", exc)
