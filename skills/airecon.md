# airecon

## Description

AIRecon is an autonomous cybersecurity agent that combines a self-hosted Large Language Model (Ollama) with a Kali Linux Docker sandbox and a Textual TUI. It is designed to automate security assessmen

## Steps

- **Privacy First** — Target intelligence, tool output, and reports never leave your machine.
- **Caido Native** — 5 built-in tools: list, replay, automate (`§FUZZ§`), findings, scope.
- **Full Stack** — Kali sandbox + browser automation + custom fuzzer + Schemathesis API fuzzing + Semgrep SAST.
- **Skills Knowledge Base** — 57 built-in skill files, 289 keyword → skill auto-mappings. Extended by **airecon-skills** —
- **Local Security Knowledge Base** — Optional **airecon-dataset** indexes ~1.09M security records (CVEs, red team techniq
- SQLite memory DB at `~/.airecon/memory/airecon.db` storing sessions, findings, patterns, target intel, tool usage, model
- Adaptive learning state at `~/.airecon/learning/global_learning.json` (tool performance stats, strategy patterns, observ
- Per-target memory files under `~/.airecon/memory/by_target/` when persisted, containing endpoints, vulns, WAF bypasses,

## Tools

gemini, ollama, sqlite, openai, docker, ai-agents, automation, bugbounty, cli, penetration-testing, python, reconnaissance

## Source

GitHub: [pikpikcu/airecon](https://github.com/pikpikcu/airecon) ⭐ 799

## README Excerpt

AI-Powered Autonomous Penetration Testing Agent

AIRecon is an autonomous penetration testing agent that combines a self-hosted **Ollama LLM** with a **Kali Linux Docker sandbox**, native **Caido proxy integration**, a structured **RECON → ANALYSIS → EXPLOIT → REPORT pipeline**, and a real-time **Textual TUI** — completely offline, no API keys required.

---

## Why AIRecon?

Commercial API-based models (OpenAI GPT-4, Claude, Gemini) become prohibitively expensive for recursive, autonomous recon workflows that can require thousands of LLM calls per session.

AIRecon is built 100% for local, private operation.

| Feature | AIRecon | Cloud-based agents |
|---------|---------|-------------------|
| API keys required | **No** | Yes |
| Target data sent to cloud | **No** | Yes |
| Works offline | **Yes** | No |
| Caido integration | **Native** | None |
| Session resume | **Yes** | Varies |
| Local knowledge base | **~1.09M records** | None |

- **Privacy First** — Target intelligence, tool output, and reports never leave your machine.
- **Caido Native** — 5 built-in tools: list, replay, automate (`§FUZZ§`), findings, scope.
- **Full Stack** — Kali sandbox + browser automation + custom fuzzer + Schemathesis API fuzzing + Semgrep SAST.
- **Skills Knowledge Base** — 57 built-in skill files, 289 keyword → skill auto-mappings. Extended by **airecon-skills** — a community skill library with 57 additional CLI-based playbooks for CTF, bug bounty, and pentesting.
- **Local Security Knowledge Base** — Optional **airecon-dataset** indexes ~1.09M security records (CVEs, red team techniques, CTF writeups, nuclei templates, bug bounty payloads) into local SQLite FTS5. The LLM calls `dataset_search` autonomously before attempting unfamiliar techniques — grounding its decisions in real indexed data.

---

## Pipeline

```
RECON → ANALYSIS → EXPLOIT → REPORT
```

Each phase has specific objectives, recommended tools, and automatic transition criteria. Phase enforcement is **soft** — the

## Sources

| Date | Video | Transcript |
|------|-------|------------|
| 2026-07-24 | [pikpikcu/airecon](https://github.com/pikpikcu/airecon) | github_readme |
