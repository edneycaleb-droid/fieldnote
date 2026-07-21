# LightAgent

## Description

LightAgent: Lightweight Python framework for OpenAI-compatible agents with tools, memory, guardrails, tracing, lifecycle hooks, multi-agent collaboration, and workflows.

## Steps

- **[2026-07-10]** LightAgent v0.9.3 Released: Completes runtime hook lifecycle coverage and hardens streaming tool safety
- **[2026-06-24]** LightAgent v0.9.0 Development: Adds checkpointed LightFlow workflows with resume/rerun support, approva
- **[2026-06-14]** LightAgent v0.8.1 Development: Adds MemoryScope metadata conventions, stricter MemoryPolicy provenance
- **[2026-06-02]** LightAgent v0.8.0 Development: Adds initial LightFlow workflow orchestration for deterministic multi-st
- **[2026-05-29]** LightAgent v0.7.0 Development: Adds opt-in trace observability with structured run/model/tool/error eve
- **[2026-05-28]** LightAgent v0.6.5 Released: Adds opt-in structured run results, structured streaming events, catchable
- **[2026-05-27]** LightAgent v0.6.4 Released: Improves runtime tool dispatch reliability, adds structured error codes and
- **Lightweight and Efficient** 🚀: Minimalist design, quick deployment, suitable for various application scenarios. (No La

## Tools

llamaindex, langchain, openai, vllm, agent-framework, agent-hooks, agents, ai-agent, lifecycle-hooks, llm, mcp, multi-agent

## Source

GitHub: [wanxingai/LightAgent](https://github.com/wanxingai/LightAgent) ⭐ 1,182

## README Excerpt

English |

简体中文 |

繁體中文 |

Español |

Français |

Deutsch |

日本語 |

한국어 |

Português |

Русский

LightAgent🚀 – small footprint, big potential. 🌟(Open-source Agentic framework)

LightAgent is an ultra‑lightweight, open‑source framework that now natively supports Skills — letting you compose reusable capabilities with persistent memory, tool use, and tree‑of‑thought reasoning. It streamlines multi‑agent collaboration (build self‑learning agents in one step), connects to MCP over stdio and SSE, runs on any modern LLM (OpenAI, DeepSeek, Qwen, and more), and outputs OpenAI‑compatible streaming APIs for instant drop‑in with any chat interface. Small, modular, and skill‑ready — spin it up in five minutes.

---
## News
- **[2026-07-10]** LightAgent v0.9.3 Released: Completes runtime hook lifecycle coverage and hardens streaming tool safety with `max_tool_iterations`, consistent `on_error` / `after_run` closure, and expanded regression coverage.
- **[2026-06-24]** LightAgent v0.9.0 Development: Adds checkpointed LightFlow workflows with resume/rerun support, approval nodes, richer step status and trace metadata, reusable Guardrails templates, stronger MemoryPolicy controls, and the first SharedMemoryPool prototype.
- **[2026-06-14]** LightAgent v0.8.1 Development: Adds MemoryScope metadata conventions, stricter MemoryPolicy provenance filters, and guidance for separating trace, user memory, self-reflection memory, and LightSwarm delegation state.
- **[2026-06-02]** LightAgent v0.8.0 Development: Adds initial LightFlow workflow orchestration for deterministic multi-step agent execution with DAG dependencies, step output passing, retries, and flow trace events.
- **[2026-05-29]** LightAgent v0.7.0 Development: Adds opt-in trace observability with structured run/model/tool/error events, `agent.export_trace()`, and prompt-safe model request summaries for production debugging.
- **[2026-05-28]** LightAgent v0.6.5 Released: Adds opt-in structured run results, structured streaming

## Sources

| Date | Video | Transcript |
|------|-------|------------|
| 2026-07-21 | [wanxingai/LightAgent](https://github.com/wanxingai/LightAgent) | github_readme |
