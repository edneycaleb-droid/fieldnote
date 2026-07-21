# forge

## Description

A Python framework for self-hosted LLM tool-calling and multi-step agentic workflows

## Steps

- **Not an agent orchestrator.** Forge sits inside one agentic loop and makes its tool calls reliable. Multi-agent graphs,
- **Not a coding harness.** Forge is domain-agnostic. If you're building a coding agent (or already using one like opencod
- **Proxy server** — Drop-in proxy (`python -m forge.proxy`) speaking both the OpenAI chat-completions and Anthropic Messa
- **WorkflowRunner** — Define tools, pick a backend, run structured agent loops. Forge manages the full lifecycle: system
- **Guardrails middleware** — Use forge's reliability stack (composable middleware) inside your own orchestration loop. Yo
- A running LLM backend (see below)
- **Managed mode** spins up the backend for you. Supported backends: `llamaserver`, `llamafile`, `ollama`, `vllm` (use `--
- **External mode** is backend-agnostic — forge talks `POST /v1/chat/completions` to whatever you point `--backend-url` at

## Tools

anthropic, pydantic, openai, vllm, docker, ollama, ray, agentic-ai, agentic-workflow, agents, function-calling, llama-cpp

## Source

GitHub: [antoinezambelli/forge](https://github.com/antoinezambelli/forge) ⭐ 2,189

## README Excerpt

# forge

[](https://pypi.org/project/forge-guardrails/)
[](https://github.com/antoinezambelli/forge/actions/workflows/tests.yml)
[](https://codecov.io/gh/antoinezambelli/forge)
[](https://www.python.org/downloads/)
[](LICENSE)

A reliability layer for self-hosted LLM tool-calling. You give forge a set of tools; the model calls whichever it wants in whatever order. Workflow structure is opt-in — `required_steps`, `prerequisites`, and `terminal_tool` let you constrain the loop when you need to, but forge's guardrails (rescue parsing, retry nudges, response validation) apply with zero required steps too.

Forge takes an 8B local model from single digits to 84% across forge's 26-scenario v0.7.0 eval suite — and even lifts Sonnet 4.6 from 85% to 98% on the same workload (Anthropic numbers measured in v0.6.0; not re-run in v0.7.0 since the cost is non-trivial).

**What forge isn't:**
- **Not an agent orchestrator.** Forge sits inside one agentic loop and makes its tool calls reliable. Multi-agent graphs, DAG planners, and cross-agent coordination are out of scope.
- **Not a coding harness.** Forge is domain-agnostic. If you're building a coding agent (or already using one like opencode, aider, Cline), proxy mode lifts your existing harness with forge's guardrails — no rewrite.

**Three ways to use it:**

- **Proxy server** — Drop-in proxy (`python -m forge.proxy`) speaking both the OpenAI chat-completions and Anthropic Messages (`/v1/messages`) APIs, sitting between any client and a local model server. Point OpenAI-compatible tools (opencode, Continue, aider) **or Claude Code** at it and forge applies guardrails transparently — the client thinks it's talking to a smarter model. Most popular entry point.

- **WorkflowRunner** — Define tools, pick a backend, run structured agent loops. Forge manages the full lifecycle: system prompts, tool execution, context compaction, and guardrails. **SlotWorker** adds priority-queued access to a shared inference slot with auto-preemptio

## Sources

| Date | Video | Transcript |
|------|-------|------------|
| 2026-07-21 | [antoinezambelli/forge](https://github.com/antoinezambelli/forge) | github_readme |
