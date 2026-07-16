# Building Effective AI Agents for Automation and Productivity

## Description
AI agents are goal-directed systems that autonomously plan, act, and adapt using LLMs as their reasoning engine. Building effective agents requires defining clear outcomes, giving the agent a persistent identity and memory, and connecting it to the right tools. This skill synthesises practitioner experience with Claude Code, Codex, and the Hermes Agent framework to provide a concrete, reproducible approach to agent construction.

## Core Concepts

* **Definition of Done (DOD)** — A precise, measurable success criterion written before the agent starts. Without a DOD the agent loops indefinitely or terminates too early.
* **Reverse prompting** — Asking the agent to restate the goal in its own words before acting, surfacing misunderstandings before wasted work begins.
* **Identity files** — Persistent system-prompt documents (e.g. `CLAUDE.md`, `AGENTS.md`) that anchor the agent's persona, constraints, and project knowledge across sessions.
* **Agent memory** — Short-term (context window), mid-term (conversation references), and long-term (external files or vector stores) memory layers.
* **Completion contracts** — A handshake protocol where the agent reports exactly how it satisfied each DOD criterion before considering the task finished.
* **Sub-agents and manager agents** — Hierarchical delegation: a manager agent breaks work into atomic subtasks and dispatches sub-agents to execute them in parallel.
* **Agent swarms** — Fleets of specialised agents coordinated by a shared task queue or a central orchestrator.
* **Tool-calling loops** — The ReAct (reason + act) cycle: the model reasons, selects a tool, observes the result, and reasons again until the DOD is satisfied.

## Steps

1. **Write the DOD first** — state the exact output format, acceptance criteria, and failure conditions before writing any prompt.
2. **Create an identity file** — add a `CLAUDE.md` or `AGENTS.md` at the project root containing the agent's role, constraints, available tools, and project-specific rules.
3. **Apply reverse prompting** — include in your system prompt: *"Before taking any action, restate the goal and your plan in one paragraph."*
4. **Configure memory** — in Claude settings enable "Reference chats" and "Generate memory from chat history" so the agent accumulates context across sessions.
5. **Wire tools** — connect web search (SearXNG or DuckDuckGo), web extraction (Firecrawl), file access (desktop app or MCP server), and any APIs the task requires.
6. **Install Claude Code and Superpowers** to give the agent terminal access, file editing, and browser automation inside the IDE.
7. **Build skills and workflows** — record repeatable multi-step sequences as named skills so the agent can invoke them by name rather than re-planning from scratch each time.
8. **Schedule recurring tasks** — use the built-in scheduler to run agent jobs automatically (daily research briefings, nightly code reviews, etc.).
9. **Implement a self-check loop** — after each subtask, prompt the agent to verify its output against the DOD before proceeding.
10. **Use a manager + sub-agent pattern for complex work** — the manager holds the DOD and delegates; sub-agents execute and report back.
11. **Token-optimise long-running agents** — summarise completed context periodically to stay within the model's context window without losing progress.
12. **Iterate on the identity file** — after each session, record what worked and what failed so future runs benefit from accumulated knowledge.

## Tools

* **Claude** — Primary reasoning model; supports tool-calling, multi-turn conversation, and computer use.
* **Claude Code** — IDE extension giving Claude terminal, file-system, and browser access inside VS Code / Cursor.
* **Codex** — OpenAI's code-focused agent, useful for pure coding tasks alongside Claude.
* **Hermes Agent** — Open-source local agent framework with built-in tool-calling and memory.
* **Superpowers** — Claude plugin that adds web search, scraping, and custom tool-calling to the Claude web interface.
* **Firecrawl** — Web scraping API that converts any URL to clean markdown; integrates via tool-calling.
* **SearXNG** — Free, self-hostable meta-search engine; used as a privacy-respecting web-search tool for agents.
* **DuckDuckGo Search** — Zero-config web search, useful as a lightweight search tool without API keys.
* **Record and Replay** — Browser automation tool for recording user flows and replaying them as agent actions.
* **Notion / Google Docs** — Document stores used for agent knowledge bases and output destinations.
* **Gmail / Google Drive** — Email and file connectors wired to agents via MCP or Zapier.

## Related Skills
* building_ai_agents_with_langchain
* running_large_models_locally

## Sources

| Date | Video | Transcript |
|------|-------|------------|
| 2026-07-15 | [You're Not Behind (Yet): How to Build Your First AI Agent (Full Guide)](https://youtu.be/Bm84BAtOfQw?is=ahImoTzYnRVzfR5t) | whisper |
| 2026-07-15 | [Codex and Claude Shipped Browser Updates. This Changes Everything.](https://youtu.be/juPDqb89dew?is=pb3WFUXn6KXAsWc0) | whisper |
| 2026-07-15 | [Claude Just Changed Completely: Here's How It Works (In 2026)](https://youtu.be/bj04doEDOY4?is=5JQU-XeZJQCPGKc2) | whisper |
| 2026-07-15 | [6 Claude Code GitHub Repos That Change Everything](https://youtu.be/L2JKgj7WzU4?is=PdIv7xTFQeAN-hd6) | whisper |
| 2026-07-15 | [OpenAI Just Merged ChatGPT and Codex. This Changes Everything. ](https://youtu.be/Fv0XfyLT3xU?is=9y4oL_AQ0iKtojbO) | whisper |
| 2026-07-15 | [Hermes Agent + Grok 4.5 Is INSANE!](https://youtube.com/watch?v=mCv8t7LZ5SA) | whisper |
| 2026-07-15 | [NEW Hermes Update Makes It 10X More Powerful](https://youtube.com/watch?v=zKAPTvv9TEw) | whisper |
| 2026-07-15 | [New Update Makes Hermes 60X More Powerful](https://youtube.com/watch?v=lTbk1Ko6r90) | whisper |
| 2026-07-15 | [Hermes Agent V0.18 Is GAME OVER](https://youtube.com/watch?v=ZrAVfs6wgVg) | whisper |
| 2026-07-16 | [Claude Just Changed Completely: Here's How It Works (In 2026)](https://youtu.be/bj04doEDOY4?is=k3_xn4Oa5rS7c0_D) | whisper |
