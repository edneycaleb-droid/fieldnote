# mcp-go

## Description

A Go implementation of the Model Context Protocol (MCP), enabling seamless integration between LLM applications and external data sources and tools.

## Steps

- **Fast**: High-level interface means less code and faster development
- **Simple**: Build MCP servers with minimal boilerplate
- **Complete***: MCP Go aims to provide a full implementation of the core MCP specification
- Installation
- Quickstart
- What is MCP?
- Core Concepts
- Transports

## Tools

ray, Go

## Source

GitHub: [mark3labs/mcp-go](https://github.com/mark3labs/mcp-go) ⭐ 8,915

## README Excerpt

[](https://github.com/mark3labs/mcp-go/actions/workflows/ci.yml)
[](https://goreportcard.com/report/github.com/mark3labs/mcp-go)
[](https://pkg.go.dev/github.com/mark3labs/mcp-go)

[](https://agentrank-ai.com/tool/mark3labs--mcp-go/)
A Go implementation of the Model Context Protocol (MCP), enabling seamless integration between LLM applications and external data sources and tools.

[](http://www.youtube.com/watch?v=qoaeYMrXJH0 "Tutorial")

Discuss the SDK on Discord

```go
package main

import (

"context"

"fmt"

"github.com/mark3labs/mcp-go/mcp"

"github.com/mark3labs/mcp-go/server"
)

func main() {

// Create a new MCP server

s := server.NewMCPServer(

"Demo 🚀",

"1.0.0",

server.WithToolCapabilities(false),

)

// Add tool

tool := mcp.NewTool("hello_world",

mcp.WithDescription("Say hello to someone"),

mcp.WithString("name",

mcp.Required(),

mcp.Description("Name of the person to greet"),

),

)

// Add tool handler

s.AddTool(tool, helloHandler)

// Start the stdio server

if err := server.ServeStdio(s); err != nil {

fmt.Printf("Server error: %v\n", err)

}
}

func helloHandler(ctx context.Context, request mcp.CallToolRequest) (*mcp.CallToolResult, error) {

name, err := request.RequireString("name")

if err != nil {

return mcp.NewToolResultError(err.Error()), nil

}

return mcp.NewToolResultText(fmt.Sprintf("Hello, %s!", name)), nil
}
```

That's it!

MCP Go handles all the complex protocol details and server management, so you can focus on building great tools. It aims to be high-level and easy to use.

### Key features:
* **Fast**: High-level interface means less code and faster development
* **Simple**: Build MCP servers with minimal boilerplate
* **Complete***: MCP Go aims to provide a full implementation of the core MCP specification

(\*emphasis on *aims*)

🚨 🚧 🏗️ *MCP Go is under active development, as is the MCP specification itself. Core features are working but some advanced capabilities are still in progress.*

## Table of Contents

- Installat

## Sources

| Date | Video | Transcript |
|------|-------|------------|
| 2026-07-21 | [mark3labs/mcp-go](https://github.com/mark3labs/mcp-go) | github_readme |
