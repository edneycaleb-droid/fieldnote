---
name: ai-ecosystem-curator
description: Evaluate AI tools, repositories, models, MCP servers, agent frameworks, research feeds, and infrastructure for this repository. Use when considering a new component, importing research, changing agent architecture, or preserving ecosystem decisions.
metadata:
  short-description: Evaluate and govern AI ecosystem changes
---

# AI Ecosystem Curator

Canonical skill and full operating standard:

`https://github.com/edneycaleb-droid/hermes-ai-knowledge-ops/blob/main/.chatgpt/skills/ai-ecosystem-curator/SKILL.md`

Canonical decision registry:

`https://github.com/edneycaleb-droid/hermes-ai-knowledge-ops/blob/main/00_AI_ECOSYSTEM_INDEX.md`

## Required workflow

1. Verify the official owner, repository, documentation, release channel, license, and maintenance status.
2. Inspect scripts, hooks, network access, telemetry, credential handling, filesystem access, browser access, and update behavior.
3. Separate useful architectural ideas from software that is safe and mature enough to install.
4. Prefer local-first, open-source, auditable, provider-neutral components.
5. Test new components in an isolated branch, worktree, container, VM, or sandbox without real credentials or production secrets.
6. Classify the result as **ADOPT**, **PILOT**, **WATCH**, **REFERENCE**, **QUARANTINE**, or **REJECT**.
7. Require tests, reversibility, documentation, and evidence before promotion.
8. Record durable findings in the root `00_AI_ECOSYSTEM_INDEX.md` and canonical Hermes registry.

Do not let unverified agents, models, browser tools, or install scripts access production infrastructure, private browser sessions, employer data, DoD data, personal credentials, or destructive GitHub permissions.
