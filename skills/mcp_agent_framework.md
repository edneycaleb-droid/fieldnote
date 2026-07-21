# mcp-agent Framework for Building Effective Agents

This guide details how to use the `mcp-agent` Python framework to construct robust, composable AI agents. It emphasizes full support for the Model Context Protocol (MCP) and the integration of effective agent patterns described by Anthropic.

## Key Features

*   **Full MCP Support**: Manages MCP server connections and lifecycles.
*   **Composable Patterns**: Implements and allows chaining of effective agent patterns.
*   **Durable Agents**: Scales to sophisticated workflows using Temporal for pausing, resuming, and recovery.
*   **MCP-Native Integration**: Connects seamlessly with any MCP server without custom adapters.
*   **Production Ready**: Includes features like Temporal-backed durability, structured logging, and cloud deployment.

## Getting Started

### Installation

It is recommended to use `uv` for project management.

1.  **Install `mcp-agent`**:
    ```bash
    uv add mcp-agent
    ```
    Alternatively, use pip:
    ```bash
    pip install mcp-agent
    ```

2.  **Install LLM Provider Packages**: Add optional packages for specific LLM providers.
    ```bash
    uv add "mcp-agent[openai, anthropic, google, azure, bedrock]"
    ```

### Project Scaffolding

Use the `mcp-agent` CLI to initialize a new project:

```bash
mkdir hello-mcp-agent && cd hello-mcp-agent
uvx mcp-agent init
```

### Configuration

Settings are loaded from `mcp_agent.config.yaml` and `mcp_agent.secrets.yaml`. Secrets should be kept out of source control.

**`mcp_agent.config.yaml` example:**
```yaml
execution_engine: asyncio
logger:
  transports: [console]
  level: debug
mcp:
  servers:
    fetch:
      command: "uvx"
      args: ["mcp-server-fetch"]
    filesystem:
      command: "npx"
      args:
        - "-y"
        - "@modelcontextprotocol/server-filesystem"
    openai:
      default_model: gpt-4o
```

**`mcp_agent.secrets.yaml` example (gitignored):**
```yaml
openai:
  api_key: "${OPENAI_API_KEY}"
```

## Core Components

### `MCPApp`

The central runtime that initializes configuration, logging, tracing, and the execution engine.

```python
from mcp_agent.app import MCPApp

app = MCPApp(name="finder_app")

async def main():
    async with app.run() as running_app:
        logger = running_app.logger
        logger.info("App ready", data={"servers": list(running_app.context.server_registry.registry)})
```

### Agents & `AgentSpec`

Agents combine instructions with MCP servers and functions they can call. `AgentSpec` definitions can be loaded from files.

```python
from mcp_agent.agents.agent import Agent

agent = Agent(
    name="finder",
    instruction="Use filesystem and fetch to answer questions.",
    server_names=["filesystem", "fetch"],
)

async with agent:
    tools = await agent.list_tools()
    # ... interact with the agent ...
```

### Augmented LLM

Wraps LLM provider SDKs with agent tools, memory, and structured output capabilities. Use `generate_str` for text and `generate_structured` for Pydantic models.

```python
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM
from pydantic import BaseModel

class Summary(BaseModel):
    title: str
    verdict: str

async with agent:
    llm = await agent.attach_llm(OpenAIAugmentedLLM)
    report = await llm.generate_str(
        message="Draft a 3-sentence release note from CHANGELOG.md",
        request_params=RequestParams(maxTokens=400, temperature=0.2),
    )
    structured = await llm.generate_structured(
        message="Return a JSON object with `title` and `verdict` summarising the README.",
        response_model=Summary,
    )
```

### Workflows & Decorators

`@app.workflow` decorators transform coroutines into durable workflows and tools, compatible with both `asyncio` and Temporal.

```python
from datetime import timedelta
from mcp_agent.executor.workflow import Workflow, WorkflowResult

@app.workflow
class PublishArticle(Workflow[WorkflowResult[str]]):
    @app.workflow_task(schedule_to_close_timeout=timedelta(minutes=5))
    async def draft(self, topic: str) -> str:
        return f"- intro to {topic}\n- highlights\n- next steps"

    @app.workflow_run
    async def run(self, topic: str) -> WorkflowResult[str]:
        outline = await self.draft(topic)
        return WorkflowResult(value=outline)
```

### MCP Integration

Connect to existing MCP servers programmatically or aggregate them.

```python
from mcp_agent.mcp.gen_client import gen_client

async with app.run():
    # Example: Get a client for a registered server
    fetch_client = await gen_client("fetch")
    # Use fetch_client to interact with the fetch MCP server
```

## Running Examples

Clone the repository or scaffold a new project and navigate to the `examples` directory.

```bash
cd examples/basic/mcp_basic_agent
# Configure secrets (e.g., cp mcp_agent.secrets.yaml.example mcp_agent.secrets.yaml)
uv run main.py
```

## Concepts

*   **Model Context Protocol (MCP)**: A protocol for communication between AI models and external tools/services.
*   **Composable Agent Patterns**: Reusable workflow structures for building agent behaviors (e.g., map-reduce, router).
*   **Durable Agents**: Agents capable of maintaining state and resuming execution across failures, often using runtimes like Temporal.
*   **Augmented LLM**: An LLM enhanced with tools, memory, and structured output capabilities.
*   **MCP Servers**: Services that expose functionality via the MCP, such as `fetch` for web requests or `filesystem` for file access.
*   **Workflows**: Defined sequences of operations, often decorated for execution as tasks or services.
*   **Configuration & Secrets**: Mechanisms for managing application settings and sensitive credentials.

## Sources

| Date | Video | Transcript |
|------|-------|------------|
| 2026-07-21 | [lastmile-ai/mcp-agent](https://github.com/lastmile-ai/mcp-agent) | github_readme |
