---
category: architecture
slug: provider-config-and-aliases
title: Provider Configuration and Secret Alias Map
confidence: verified
sources: []
updated_at: "2026-07-16T13:26:36.786897+00:00"
---

## Provider Status (verified 2026-07-16)

| Provider | State | Replit Secret | Notes |
|---|---|---|---|
| Groq | ✅ healthy | `GROQ` | Primary. Models: llama-3.3-70b-versatile, gemma2-9b-it, mixtral-8x7b |
| Gemini | ✅ healthy | `Gemini` | Fallback #2. Models: gemini-2.0-flash, gemini-1.5-flash-8b |
| OpenAI | ✅ healthy | `CHATGPT` | Fallback #3. Models: gpt-4o-mini, gpt-4o |
| HuggingFace | ⚠️ no_key | `HF_TOKEN` | Anonymous access on; stored key in local_keys.json is invalid — refresh needed |
| OpenRouter | ✅ in local_keys | `OPENROUTER_API_KEY` | Connected via local_keys.json; env var not set so provider router shows no_key |

## Nonstandard Secret Aliases (normalised at startup)

Two Replit Secrets were added under non-standard names. They are normalised in `agents/provider_router.py` at import time:

```python
_KEY_ALIASES = {
    "GROQFREE":  "GROQ",              # backup Groq key
    "Langchain": "LANGCHAIN_API_KEY", # LangSmith tracing key
}
# Sets standard name in os.environ only when not already present
```

`GROQFREE` is currently dormant because `GROQ` is already set. It activates automatically if `GROQ` is removed.
`LANGCHAIN_API_KEY` is now set (from the `Langchain` secret), enabling LangSmith tracing in any LangChain code.

## fieldnote_mcp GitHub Inclusion

As of 2026-07-16, `fieldnote_mcp/` is now included in the GitHub mirror.
- **Pushed:** `fieldnote_server.py`, `integrations_registry.py`
- **Excluded by name:** `local_keys.json`, `integration_agent_status.json`, `integration_dynamic.json`, `status.json`, `mcp_config.json`, `install.log`

## Unresolved Issues

| Issue | Single Required Action |
|---|---|
| HuggingFace token invalid | Go to huggingface.co/settings/tokens, create a new read token, paste it into the Integrations tab → HuggingFace card |
| OpenRouter key not in env (only in local_keys.json) | Save the OpenRouter key as a Replit Secret named `OPENROUTER_API_KEY` so the provider router picks it up at startup |
