# Headroom: Context Compression for AI Agents

Headroom is a powerful tool designed to optimize AI agent performance by implementing a context compression layer. It significantly reduces the number of tokens sent to Large Language Models (LLMs) by compressing various data types, including tool outputs, logs, files, and Retrieval Augmented Generation (RAG) chunks. This compression leads to substantial cost savings and can improve processing speed, all while aiming to preserve the accuracy of the LLM's responses.

## Key Features

*   **Token Reduction**: Achieves significant token savings, ranging from 60-95% for JSON and 15-20% for coding agents, by compressing input data to lower token counts, reducing costs and improving processing speed.
*   **Multiple Integration Modes**: Offers flexibility with library (inline Python/TypeScript), proxy (zero code changes), agent wrap (automates setup for specific agents), and turnkey local deployment options.
*   **Output Token Reduction**: Optionally reduces the number of tokens in the LLM's output using `HEADROOM_OUTPUT_SHAPER=1`.
*   **Learning Terseness**: Can automatically learn and apply optimal terseness settings based on past sessions using `headroom learn --verbosity`.
*   **Measurement Tools**: Provides commands like `headroom perf`, `headroom dashboard`, and `headroom output-savings` to monitor performance and measure savings.

## Getting Started

1.  **Installation**: Install Headroom using `uv tool install --python 3.13 'headroom-ai[all]'` or `pip install 'headroom-ai[all]'`.
2.  **Deployment**: Choose your operating mode:
    *   **Turnkey Local**: `headroom deploy`
    *   **Agent Wrap**: `headroom wrap <agent>` (e.g., `headroom wrap copilot --subscription -- --model <model_name>` for Copilot CLI)
    *   **Proxy**: `headroom proxy --port 8787` (for drop-in interception)
    *   **Library**: Import `from headroom import compress` for inline usage.
3.  **Verification**: Use `headroom doctor` for a health check and to verify setup and routing.
4.  **Monitoring**: Observe live savings with `headroom perf` or `headroom dashboard`.

## Advanced Features

*   **Output Shaper**: Enable output token reduction by setting `export HEADROOM_OUTPUT_SHAPER=1` and restarting the proxy or using `headroom wrap`.
*   **Terseness Learning**: Use `headroom learn --verbosity` to automatically learn optimal terseness settings.
*   **Savings Measurement**: Measure output token savings with `headroom output-savings` or by setting `export HEADROOM_OUTPUT_HOLDOUT=0.1`.
*   **Agent Integration**: Consult the Agent compatibility matrix and use `headroom wrap <agent>` or manual setup for specific integrations.
*   **Copilot Authentication**: For GitHub Copilot CLI subscription mode, use `headroom copilot-auth login`.

## Supported Tools & Concepts

Headroom integrates with various tools and concepts including:

*   **Tools**: Claude, Docker, bash, Python, LLM, FastAPI, CrewAI, Pydantic, OpenAI, LangChain, Anthropic, Bedrock, GitHub Copilot CLI.
*   **Concepts**: Context Compression, Token Optimization, AI Agent Workflow, Proxy Server, Local-First AI, Content-Aware Compression, Reversible Compression, Output Token Reduction, Agent Memory, Prompt Engineering, Agent Wrapping, MCP Server.

## Sources

| Date | Video | Transcript |
|------|-------|------------|
| 2026-07-24 | [headroomlabs-ai/headroom](https://github.com/headroomlabs-ai/headroom) | github_readme |
