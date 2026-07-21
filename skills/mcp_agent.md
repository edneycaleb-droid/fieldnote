# mcp-agent

## Description

Build effective agents using Model Context Protocol and simple workflow patterns

## Steps

- **Full MCP support**: It _fully_ implements MCP, and handles the pesky business of managing the lifecycle of MCP server
- **Effective agent patterns**: It implements every pattern described in Anthropic's Building Effective Agents in a _compo
- **Durable agents**: It works for simple agents and scales to sophisticated workflows built on Temporal so you can pause,
- `llms-full.txt`: contains entire documentation.
- `llms.txt`: sitemap listing key pages in the docs.
- docs MCP server
- Minimal example
- Quickstart

## Tools

anthropic, openai, pydantic, agents, ai-agents, llm, llms, mcp, model-context-protocol, python

## Source

GitHub: [lastmile-ai/mcp-agent](https://github.com/lastmile-ai/mcp-agent) ⭐ 8,464

## README Excerpt

Build effective agents with Model Context Protocol using simple, composable patterns.

Examples

|

Building Effective Agents

|

MCP

## Overview

**`mcp-agent`** is a simple, composable framework to build effective agents using Model Context Protocol.

> [!Note]
> mcp-agent's vision is that _MCP is all you need to build agents, and that simple patterns are more robust than complex architectures for shipping high-quality agents_.

`mcp-agent` gives you the following:

1. **Full MCP support**: It _fully_ implements MCP, and handles the pesky business of managing the lifecycle of MCP server connections so you don't have to.
2. **Effective agent patterns**: It implements every pattern described in Anthropic's Building Effective Agents in a _composable_ way, allowing you to chain these patterns together.
3. **Durable agents**: It works for simple agents and scales to sophisticated workflows built on Temporal so you can pause, resume, and recover without any API changes to your agent.

Altogether, this is the simplest and easiest way to build robust agent applications.

We welcome all kinds of contributions, feedback and your help in improving this project.

**Minimal example**

```python
import asyncio

from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM

app = MCPApp(name="hello_world")

async def main():

async with app.run():

agent = Agent(

name="finder",

instruction="Use filesystem and fetch to answer questions.",

server_names=["filesystem", "fetch"],

)

async with agent:

llm = await agent.attach_llm(OpenAIAugmentedLLM)

answer = await llm.generate_str("Summarize README.md in two sentences.")

print(answer)

if __name__ == "__main__":

asyncio.run(main())

# Add your LLM API key to `mcp_agent.secrets.yaml` or set it in env.
# The Getting Started guide walks through configuration and secrets in detail.

```

## At a glance

Build an Agent

Connect LLMs to MCP serv

## Sources

| Date | Video | Transcript |
|------|-------|------------|
| 2026-07-21 | [lastmile-ai/mcp-agent](https://github.com/lastmile-ai/mcp-agent) | github_readme |
