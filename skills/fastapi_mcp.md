# fastapi_mcp

## Description

Expose your FastAPI endpoints as Model Context Protocol (MCP) tools, with Auth!

## Steps

- **Authentication** built in, using your existing FastAPI dependencies!
- **FastAPI-native:** Not just another OpenAPI -> MCP converter
- **Zero/Minimal configuration** required - just point it at your FastAPI app and it works
- **Preserving schemas** of your request models and response models
- **Preserve documentation** of all your endpoints, just as it is in Swagger
- **Flexible deployment** - Mount your MCP server to the same app, or deploy separately
- **ASGI transport** - Uses FastAPI's ASGI interface directly for efficient communication
- **Native dependencies**: Secure your MCP endpoints using familiar FastAPI `Depends()` for authentication and authorizati

## Tools

fastapi, authentication, authorization, claude, cursor, llm, mcp, mcp-server, mcp-servers, modelcontextprotocol, openapi, windsurf

## Source

GitHub: [tadata-org/fastapi_mcp](https://github.com/tadata-org/fastapi_mcp) ⭐ 11,951

## README Excerpt

Built by Tadata

FastAPI-MCP

Expose your FastAPI endpoints as Model Context Protocol (MCP) tools, with Auth!

[](https://pypi.org/project/fastapi-mcp/)
[](https://pypi.org/project/fastapi-mcp/)
[](#)
[](https://github.com/tadata-org/fastapi_mcp/actions/workflows/ci.yml)
[](https://codecov.io/gh/tadata-org/fastapi_mcp)

## Features

- **Authentication** built in, using your existing FastAPI dependencies!

- **FastAPI-native:** Not just another OpenAPI -> MCP converter

- **Zero/Minimal configuration** required - just point it at your FastAPI app and it works

- **Preserving schemas** of your request models and response models

- **Preserve documentation** of all your endpoints, just as it is in Swagger

- **Flexible deployment** - Mount your MCP server to the same app, or deploy separately

- **ASGI transport** - Uses FastAPI's ASGI interface directly for efficient communication

## Hosted Solution

If you prefer a managed hosted solution check out tadata.com.

## Installation

We recommend using uv, a fast Python package installer:

```bash
uv add fastapi-mcp
```

Alternatively, you can install with pip:

```bash
pip install fastapi-mcp
```

## Basic Usage

The simplest way to use FastAPI-MCP is to add an MCP server directly to your FastAPI application:

```python
from fastapi import FastAPI
from fastapi_mcp import FastApiMCP

app = FastAPI()

mcp = FastApiMCP(app)

# Mount the MCP server directly to your FastAPI app
mcp.mount()
```

That's it! Your auto-generated MCP server is now available at `https://app.base.url/mcp`.

## Documentation, Examples and Advanced Usage

FastAPI-MCP provides comprehensive documentation. Additionaly, check out the examples directory for code samples demonstrating these features in action.

## FastAPI-first Approach

FastAPI-MCP is designed as a native extension of FastAPI, not just a converter that generates MCP tools from your API. This approach offers several key advantages:

- **Native dependencies**: Secure your MCP endpoints usin

## Sources

| Date | Video | Transcript |
|------|-------|------------|
| 2026-07-21 | [tadata-org/fastapi_mcp](https://github.com/tadata-org/fastapi_mcp) | github_readme |
