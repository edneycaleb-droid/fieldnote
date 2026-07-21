# Implementing the Model Context Protocol with Go (mcp-go)

This skill covers how to use the `mcp-go` library to build servers that expose data and functionality to Large Language Models (LLMs) through the Model Context Protocol (MCP).

## What is MCP?

The Model Context Protocol (MCP) is a standardized way for LLM applications to securely interact with external data sources and tools. It allows LLMs to access information (via **Resources**) and perform actions (via **Tools**), much like a web API but specifically designed for LLM interactions.

## Key Features of mcp-go

- **Simplicity**: Minimal boilerplate code for building MCP servers.
- **Speed**: High-level interface for faster development.
- **Completeness**: Aims to provide a full implementation of the core MCP specification.

*Note: `mcp-go` and the MCP specification are under active development. Core features are functional, but advanced capabilities may still be in progress.*

## Installation

Install the `mcp-go` library using the Go package manager:

```bash
go get github.com/mark3labs/mcp-go
```

## Core Concepts and Implementation

### 1. The Server

The server is the central component that manages connections, ensures protocol compliance, and routes messages. It's created using `server.NewMCPServer`.

```go
import (
	"github.com/mark3labs/mcp-go/server"
)

// Create a basic server
s := server.NewMCPServer(
	"My Server",  // Server name
	"1.0.0",      // Version
)

// Start the server using stdio (for command-line interaction)
if err := server.ServeStdio(s); err != nil {
	log.Fatalf("Server error: %v", err)
}
```

### 2. Resources

Resources are used to expose data to LLMs. They can be static or dynamic (using URI templates).

**a. Static Resources:**

Expose fixed data, like a file.

```go
import (
	"context"
	"os"
	"github.com/mark3labs/mcp-go/mcp"
)

// Exposing a README file as a static resource
resource := mcp.NewResource(
	"docs://readme",
	"Project README",
	mcp.WithResourceDescription("The project's README file"),
	mcp.WithMIMEType("text/markdown"),
)

// Add resource with its handler
s.AddResource(resource, func(ctx context.Context, request mcp.ReadResourceRequest) ([]mcp.ResourceContents, error) {
	content, err := os.ReadFile("README.md")
	if err != nil {
		return nil, err
	}
	return []mcp.ResourceContents{
		mcp.TextResourceContents{
			URI:      "docs://readme",
			MIMEType: "text/markdown",
			Text:     string(content),
		},
	}, nil
})
```

**b. Dynamic Resources (Templates):**

Use URI templates to serve data based on parameters in the request URI.

```go
import (
	"context"
	"github.com/mark3labs/mcp-go/mcp"
)

// Dynamic resource for user profiles by ID
template := mcp.NewResourceTemplate(
	"users://{id}/profile",
	"User Profile",
	mcp.WithTemplateDescription("Returns user profile information"),
	mcp.WithTemplateMIMEType("application/json"),
)

// Add template with its handler
s.AddResourceTemplate(template, func(ctx context.Context, request mcp.ReadResourceRequest) ([]mcp.ResourceContents, error) {
	// Extract ID from the URI (server handles matching)
	userID := extractIDFromURI(request.Params.URI) // Implement this extraction logic
	profile, err := getUserProfile(userID)  // Your DB/API call here
	if err != nil {
		return nil, err
	}
	return []mcp.ResourceContents{
		mcp.TextResourceContents{
			URI:      request.Params.URI,
			MIMEType: "application/json",
			Text:     profile,
		},
	}, nil
})
```

### 3. Tools

Tools allow LLMs to perform actions and have side effects, similar to POST requests.

**a. Synchronous Tools:**

Execute immediately and return a result.

```go
import (
	"context"
	"fmt"
	"github.com/mark3labs/mcp-go/mcp"
)

// Define a simple calculator tool
calculatorTool := mcp.NewTool("calculate",
	mcp.WithDescription("Perform basic arithmetic operations"),
	mcp.WithString("operation",
		mcp.Required(),
		mcp.Description("The operation to perform (add, subtract, multiply, divide)"),
		mcp.Enum("add", "subtract", "multiply", "divide"),
	),
	mcp.WithNumber("x",
		mcp.Required(),
		mcp.Description("First number"),
	),
	mcp.WithNumber("y",
		mcp.Required(),
		mcp.Description("Second number"),
	),
)

// Add the calculator handler
s.AddTool(calculatorTool, func(ctx context.Context, request mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	// Use helper functions for type-safe argument access
	op, err := request.RequireString("operation")
	if err != nil {
		return mcp.NewToolResultError(err.Error()), nil
	}
	x, err := request.RequireFloat("x")
	if err != nil {
		return mcp.NewToolResultError(err.Error()), nil
	}
	y, err := request.RequireFloat("y")
	if err != nil {
		return mcp.NewToolResultError(err.Error()), nil
	}

	var result float64
	switch op {
	case "add":
		result = x + y
	case "subtract":
		result = x - y
	case "multiply":
		result = x * y
	case "divide":
		if y == 0 {
			return mcp.NewToolResultError("cannot divide by zero"), nil
		}
		result = x / y
	}

	return mcp.NewToolResultText(fmt.Sprintf("%.2f", result)), nil
})
```

**b. Task-Augmented Tools (Asynchronous):**

For long-running operations, tools can be configured to run asynchronously. This prevents blocking and allows clients to poll for results.

- **`TaskSupportForbidden`**: Default; tool cannot be invoked as a task.
- **`TaskSupportOptional`**: Tool can be invoked synchronously or as a task.
- **`TaskSupportRequired`**: Tool *must* be invoked as a task.

```go
// Example: A tool that requires task execution
processBatchTool := mcp.NewTool("process_batch",
	mcp.WithDescription("Process a batch of items asynchronously"),
	mcp.WithTaskSupport(mcp.TaskSupportRequired),
	mcp.WithArray("items",
		mcp.Description("Array of items to process"),
		mcp.WithStringItems(),
		mcp.Required(),
	),
)

// Task tool handler returns CreateTaskResult
s.AddTaskTool(processBatchTool, func(ctx context.Context, request mcp.CallToolRequest) (*mcp.CreateTaskResult, error) {
	items := request.GetStringSlice("items", []string{})
	// Long-running work here...
	for _, item := range items {
		select {
		case <-ctx.Done():
			return nil, ctx.Err() // Task was cancelled
		default:
			processItem(item) // Your processing logic
		}
	}
	// Server manages Task ID and status
	return &mcp.CreateTaskResult{Task: mcp.Task{}},
})
```

**Task Execution Flow:**
1. Client calls the tool with a task parameter.
2. Server immediately returns a task ID.
3. The tool executes asynchronously in the background.
4. Client polls `tasks/result` endpoint using the task ID to get the result.
5. Server can send status notifications upon completion.

**Hybrid Tools (Optional Task Support):**

Tools with `TaskSupportOptional` can be called either synchronously or asynchronously.

```go
// Tool with optional task support
analyzeTool := mcp.NewTool("analyze_data",
	mcp.WithDescription("Analyze data - can run sync or async"),
	mcp.WithTaskSupport(mcp.TaskSupportOptional),
	mcp.WithString("data", mcp.Required()),
)

// Use AddTaskTool for hybrid tools
s.AddTaskTool(analyzeTool, func(ctx context.Context, request mcp.CallToolRequest) (*mcp.CreateTaskResult, error) {
	// This handler runs for both sync and async calls
	data := request.GetString("data", "")
	result := analyzeData(data) // Your analysis logic

	// If called as a task, return CreateTaskResult
	if request.IsTask() {
		return &mcp.CreateTaskResult{Task: mcp.Task{}},
	}

	// If called synchronously, return CallToolResult
	return mcp.NewToolResultText(result), nil
})
```

### 4. Server Configuration Options

When creating the server, you can enable various capabilities:

- **Tool Capabilities**: `server.WithToolCapabilities(bool)`
- **Task Capabilities**: `server.WithTaskCapabilities(listTasks, cancel, toolCallTasks)`
- **Recovery**: `server.WithRecovery()` (handles panics)
- **Max Concurrent Tasks**: `server.WithMaxConcurrentTasks(int)` (limits running tasks)

```go
s := server.NewMCPServer(
	"Task Server",
	"1.0.0",
	server.WithTaskCapabilities(true, true, true), // Enable task listing, cancellation, and tool call tasks
	server.WithMaxConcurrentTasks(10), // Limit to 10 concurrent tasks
	server.WithRecovery(),
)
```

## Related Skills

- **[LLM Tool Use](llm_tool_use)**: General concepts of LLMs interacting with external tools.
- **[Go Programming Fundamentals](go_programming_fundamentals)**: Essential knowledge for working with the `mcp-go` library.

## Sources

| Date | Video | Transcript |
|------|-------|------------|
| 2026-07-21 | [mark3labs/mcp-go](https://github.com/mark3labs/mcp-go) | github_readme |
