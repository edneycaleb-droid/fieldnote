# loushang

## Description

AI-native agent harness for coding workflows by python: multi-model LLM orchestration, stateful sessions, tool governance,   traceable delivery, and provider routing for GPT, Claude, DeepSeek, Qwen, K

## Steps

- `loushang code`: a coding-focused CLI and terminal workbench.
- `loushang.ai`: a provider-aware AI SDK with model registry, streaming, tool calls, and cost helpers.
- Sessions: persistent coding sessions with resume, fork, export, and diagnostics.
- Tools: built-in coding tools and configurable tool surfaces.
- Extensions: project-level extension hooks, custom tools, dynamic resources, and commands.
- Methods and skills: method-guided coding turns and reusable workflow assets.
- Method: a structured work contract that defines roles, phases, workflow, constraints, artifacts, and acceptance expectat
- Session: a durable coding conversation and execution record that can be resumed, forked, exported, and inspected.

## Tools

redis, openai, agent, agent-harness, agentic, chatgpt, claude, claude-code, codex, coding, deepseek, dynamic-workflows

## Source

GitHub: [zhnt/loushang](https://github.com/zhnt/loushang) ⭐ 803

## README Excerpt

# Loushang

English | 中文

Loushang is a method-native AI work system for running complex work from intent to verified delivery.

Current focus: `loushang code`, a CLI and terminal workbench for software development with model routing, persistent sessions, tools, extensions, and method-guided delivery.

## Why Loushang

Modern AI agents can plan and act, but complex work still breaks down when context is lost, execution cannot be resumed, tools are hard to govern, and results are not verified.

Loushang treats methods, stages, roles, tools, sessions, and work products as runtime objects. The goal is not just to make agents smarter, but to make complex work more reliable, recoverable, auditable, and deliverable.

Method is the work contract, work is the runtime fact, agent is the execution kernel, ai is the model access layer, harness is the cross-product substrate, coding is the V1 product surface, tui is the terminal presentation, and channel is the boundary protocol—together organizing complex knowledge work into a runnable, recoverable, verifiable, and evolvable system.

## What You Can Use Today

- `loushang code`: a coding-focused CLI and terminal workbench.
- `loushang.ai`: a provider-aware AI SDK with model registry, streaming, tool calls, and cost helpers.
- Sessions: persistent coding sessions with resume, fork, export, and diagnostics.
- Tools: built-in coding tools and configurable tool surfaces.
- Extensions: project-level extension hooks, custom tools, dynamic resources, and commands.
- Methods and skills: method-guided coding turns and reusable workflow assets.

## Quick Start

Loushang is in early development. The recommended path is to run it from source.

```bash
git clone https://github.com/zhnt/loushang.git
cd loushang

uv venv .venv
source .venv/bin/activate
uv pip install -e ".[dev]"

loushang --help
loushang --list-models
loushang --list-commands
loushang -p "Inspect this repository and summarize what it does."
```

You can also run `make bootst

## Sources

| Date | Video | Transcript |
|------|-------|------------|
| 2026-07-24 | [zhnt/loushang](https://github.com/zhnt/loushang) | github_readme |
