# headroom

## Description

Compress tool outputs, logs, files, and RAG chunks before they reach the LLM. 20% fewer tokens for coding agents, 60-95% fewer tokens for JSON, same answers. Library, proxy, MCP server.

## Steps

- **Library** — `compress(messages)` in Python or TypeScript, inline in any app
- **Proxy** — `headroom proxy --port 8787`, zero code changes, any language
- **Agent wrap** — `headroom wrap claude|codex|grok|copilot|cursor|aider|opencode|cline|continue|goose|openhands|openclaw|
- **MCP server** — `headroom_compress`, `headroom_retrieve`, `headroom_stats` for any MCP client
- **Cross-agent memory** — shared store across Claude, Codex, Gemini, Grok, auto-dedup
- **`headroom learn`** — mines failed sessions, writes corrections to `CLAUDE.local.md` (default, gitignored) or `CLAUDE.m
- **Output token reduction** — trims what the model *writes back* (not just what you send): drops ceremony/restated code a
- **Reversible (CCR)** — originals are cached for retrieval on demand

## Tools

gemini, pytorch, anthropic, openai, langchain, agent, claude-code, compression, context-engineering, context-window, cursor, fastapi

## Source

GitHub: [headroomlabs-ai/headroom](https://github.com/headroomlabs-ai/headroom) ⭐ 61,768

## README Excerpt

██╗  ██╗███████╗ █████╗ ██████╗ ██████╗  ██████╗  ██████╗ ███╗

███╗

██║  ██║██╔════╝██╔══██╗██╔══██╗██╔══██╗██╔═══██╗██╔═══██╗████╗ ████║

███████║█████╗  ███████║██║  ██║██████╔╝██║

██║██║

██║██╔████╔██║

██╔══██║██╔══╝  ██╔══██║██║  ██║██╔══██╗██║

██║██║

██║██║╚██╔╝██║

██║  ██║███████╗██║  ██║██████╔╝██║  ██║╚██████╔╝╚██████╔╝██║ ╚═╝ ██║

╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚═════╝ ╚═╝  ╚═╝ ╚═════╝  ╚═════╝ ╚═╝

╚═╝

The context compression layer for AI agents

60–95% fewer tokens (for JSON data), 15-20% fewer tokens (for coding agents) · library · proxy · MCP · content-aware compressors · local-first · reversible

Docs ·

Install ·

Proof ·

Agents ·

Discord ·

llms.txt

AI agents / LLMs: read /llms.txt here, or fetch the live index / full docs blob.

---

Headroom compresses everything your AI agent reads — tool outputs, logs, RAG chunks, files, and conversation history — before it reaches the LLM. Same answers, fraction of the tokens.

Live: 10,144 → 1,260 tokens — same FATAL found.

## What it does

- **Library** — `compress(messages)` in Python or TypeScript, inline in any app
- **Proxy** — `headroom proxy --port 8787`, zero code changes, any language
- **Agent wrap** — `headroom wrap claude|codex|grok|copilot|cursor|aider|opencode|cline|continue|goose|openhands|openclaw|vibe|omp|zcode` in one command; undo with `headroom unwrap `
- **MCP server** — `headroom_compress`, `headroom_retrieve`, `headroom_stats` for any MCP client
- **Cross-agent memory** — shared store across Claude, Codex, Gemini, Grok, auto-dedup
- **`headroom learn`** — mines failed sessions, writes corrections to `CLAUDE.local.md` (default, gitignored) or `CLAUDE.md` / `AGENTS.md` / `GEMINI.md` / `GROK.md`
- **Output token reduction** — trims what the model *writes back* (not just what you send): drops ceremony/restated code and skips deep "thinking" on routine steps. See Output token reduction.
- **Reversible (CCR)** — originals are cached for retrieval on demand

## How it works (30 seconds)

`

## Sources

| Date | Video | Transcript |
|------|-------|------------|
| 2026-07-24 | [headroomlabs-ai/headroom](https://github.com/headroomlabs-ai/headroom) | github_readme |
