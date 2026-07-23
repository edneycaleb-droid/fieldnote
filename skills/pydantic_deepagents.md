# pydantic-deepagents

## Description

Open-source, self-hosted Claude Code - a terminal AI assistant and the Python framework behind it. Tool-calling, sandboxed execution, multi-agent teams, skills, checkpoints, unlimited context - on Pyd

## Steps

- **2026-06-01** &nbsp;**v0.3.24** — **Live Run Forking** — split an in-flight `agent.run()` into N parallel branches with
- **2026-06-01** &nbsp;**v0.3.23** — **MCP client support** (framework + CLI). Connect GitHub, Figma (OAuth), Context7, De
- **2026-06-01** &nbsp;**v0.3.23** — **Automatic fallback-model retry** — `fallback_model=` wraps your primary in a `Fallb
- **2026-04-22** &nbsp;**v0.3.17** — LiteParse document parsing (`include_liteparse=True`) — PDFs, DOCX, XLSX, PPTX, and i
- **2026-04-10** &nbsp;**v0.3.5** — Headless runner (`pydantic-deep run`), Docker sandbox with named workspaces, browser a

## Tools

pydantic, crewai, docker, ollama, gemini, langgraph, openai, anthropic, agent-framework, ai-agents, claude-code, cli

## Source

GitHub: [vstorm-co/pydantic-deepagents](https://github.com/vstorm-co/pydantic-deepagents) ⭐ 993

## README Excerpt

Pydantic Deep Agents

Open-source Claude Code — that you can also build on.

A self-hosted terminal AI assistant and the Python framework behind it.

Use it today, or ship your own agent in one function call. Any model. 100% type-safe. MIT.

Docs &middot;

PyPI &middot;

Forking &middot;

Why &middot;

CLI &middot;

Framework &middot;

Examples

---

**Pydantic Deep Agents is two things in one repo:**

🖥️ **A terminal AI assistant** — a self-hosted, open-source alternative to Claude Code. Install it, point it at any model, and it plans, edits files, runs commands, searches the web, remembers across sessions, spawns sub-agents, and connects to MCP servers. Almost everything Claude Code does — on the model *you* choose.

🐍 **A Python framework** — the *exact same harness* behind a single function call. `create_deep_agent()` hands a model a filesystem, shell, planning, memory, sub-agents, sandboxed execution, MCP, and unlimited context. Build your own assistant, research agent, or coding tool without rewiring the plumbing every time.

Both run on **Pydantic AI**, work with **any model** (Claude, GPT, Gemini, local), and are **100% type-safe** and MIT-licensed — and they share one trick nothing else has: **Live Run Forking**, splitting a single run into parallel branches an AI judge merges back together.

## Two ways to use it

### 🖥️ 1. Use the assistant

A Claude-Code-style TUI in your terminal, on **any** model — no Python setup (the script installs `uv` + the CLI for you):

```bash
curl -fsSL https://raw.githubusercontent.com/vstorm-co/pydantic-deep/main/install.sh | bash
pydantic-deep
```

> Windows / manual: `pip install "pydantic-deep[cli]"`

### 🐍 2. Build your own

One function call gives you a full deep agent:

```bash
pip install pydantic-deep
```

```python
from pydantic_deep import create_deep_agent

agent = create_deep_agent(model="anthropic:claude-sonnet-4-6")
result = await agent.run("Build a REST API for auth")
```

---

## ⑂ Live Run Forking — the feat

## Sources

| Date | Video | Transcript |
|------|-------|------------|
| 2026-07-23 | [vstorm-co/pydantic-deepagents](https://github.com/vstorm-co/pydantic-deepagents) | github_readme |
