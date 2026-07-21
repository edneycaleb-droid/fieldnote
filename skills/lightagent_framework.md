# LightAgent: Lightweight Python Agent Framework

## Description

LightAgent is an ultra-lightweight, open-source Python framework designed for building AI agents, emphasizing modularity, efficiency, and ease of integration. It supports features like memory management, tool integration, complex reasoning with Tree of Thought (ToT), multi-agent collaboration, workflow orchestration, and OpenAI-compatible streaming APIs for seamless integration with chat interfaces.

## Key Features

*   **Lightweight and Efficient**: Minimalist design for quick deployment, suitable for various application scenarios.
*   **Memory Support**: Supports custom long-term memory for each user, natively integrating with modules like `mem0`.
*   **Tool Integration**: Easily integrate custom tools for expanded agent capabilities.
*   **Multi-Agent Collaboration**: Facilitates complex interactions and task delegation using `LightSwarm`.
*   **Workflow Orchestration**: Enables deterministic multi-step workflows with `LightFlow`, including dependency management and retries.
*   **Advanced Reasoning**: Supports Tree of Thought (ToT) for more complex problem-solving.
*   **Observability**: Features trace observability for debugging and analysis, along with runtime hooks for lifecycle event management.
*   **Safety**: Includes guardrails for input, tool, and output validation.
*   **Streaming API**: OpenAI-compatible streaming for real-time responses.

## Getting Started

1.  Install the LightAgent framework using pip: `pip install lightagent`.
2.  Optionally install mem0ai for memory support: `pip install mem0ai`.
3.  Initialize a LightAgent instance, specifying the model, API key, and base URL.
4.  Run agent queries using `agent.run(query)`.

## Advanced Usage

*   For structured results and trace data, use `agent.run(query, result_format='object', trace=True)`.
*   Export trace data using `agent.export_trace()`.
*   Implement multi-agent collaboration using `LightSwarm` for intent recognition and task delegation.
*   Orchestrate deterministic multi-step workflows using `LightFlow`, defining dependencies, retries, and checkpoints.
*   Integrate custom tools by providing them during `LightAgent` initialization.
*   Configure guardrails for input, tool, and output safety.
*   Utilize runtime hooks for observing, replacing, or blocking lifecycle payloads.

## Sources

| Date | Video | Transcript |
|------|-------|------------|
| 2026-07-21 | [wanxingai/LightAgent](https://github.com/wanxingai/LightAgent) | github_readme |
