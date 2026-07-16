---
category: session_learnings
slug: skill-quality-audit-2026-07-16
title: Skill Quality Audit — Before/After 2026-07-16
confidence: verified
sources: []
updated_at: "2026-07-16T13:26:21.912741+00:00"
---

## Skill Quality Baseline and Repairs — 2026-07-16

### Pre-Repair State

| Skill | Score | Key Issues |
|---|---|---|
| `building_ai_agents` | 2/10 | Markdown body was a single paragraph — no `##` sections despite 10 sources and 8 enhance passes. 41 index tools, most Whisper hallucinations. |
| `running_large_models_locally` | 4/10 | Structured but corrupted tool names: AntiRaz, DS4, Lama CPP (not real). vLLM miscapitalised. Ollama entirely absent. No commands. |
| `building_ai_agents_with_langchain` | 5/10 | Best-structured. Real code snippets. But "Deep Agents" is a hallucinated package. Missing LCEL/RAG/tool-calling. Wrong tags. |

### Repairs Applied

**`building_ai_agents`** — Full markdown rebuild:
- Added `## Core Concepts`, `## Steps` (12 steps), `## Tools` (11 real tools)
- Index tools: 41 mixed/corrupted → 15 verified (Claude, Claude Code, Codex, Hermes Agent, Superpowers, Firecrawl, SearXNG, DuckDuckGo Search, Record and Replay, Notion/Google Docs/Gmail/Google Drive/Zoom/Twitter)
- Preserved original Sources table (10 source videos)

**`running_large_models_locally`** — Corrected and expanded:
- Removed AntiRaz, DS4 (Whisper transcription errors, not real tools)
- Fixed `Lama CPP` → `llama.cpp`, `VLLM` → `vLLM`
- Added ollama, llamafile, LM Studio, Hugging Face Hub CLI
- Added 8 concrete CLI commands; added quantisation/GGUF concepts

**`building_ai_agents_with_langchain`** — Fixed and expanded:
- Removed `Deep Agents` (hallucinated — does not exist on PyPI)
- Added LCEL pipe syntax, RAG pipeline with Chroma, tool-calling with `@tool`, LangSmith tracing setup
- Fixed tags: removed `cloudcode`, added `langchain`, `rag`
- Fixed python_packages: added langchain-groq, langchain-openai, langgraph, langsmith

### Corrupted-Name Root Cause
Whisper transcription of fast speech produces plausible-sounding but wrong tool names. All real tool names validated against GitHub search and PyPI.

### Quality Standard for Future Skills
A quality skill file must have: `## Description`, `## Core Concepts`, `## Steps` (numbered, actionable), `## Tools` (validated names), `## Related Skills`, `## Sources`. Code blocks required for any tool with a CLI or Python API. Tool names must be cross-checked against PyPI/GitHub before saving.
