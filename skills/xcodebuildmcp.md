# XcodeBuildMCP

## Description

A Model Context Protocol (MCP) server and CLI that provides tools for agent use when working on iOS and macOS projects.

## Steps

- macOS 14.5 or later
- Xcode 16.x or later
- Node.js 18.x or later (not required for Homebrew installation)
- **MCP Skill**: Primes the agent with instructions on how to use the MCP server's tools (optional when using the MCP serv
- **CLI Skill**: Primes the agent with instructions on how to navigate the CLI (recommended when using the CLI).
- XcodeBuildMCP requests xcodebuild to skip macro validation to avoid errors when building projects that use Swift Macros.
- Device tools require code signing to be configured in Xcode. See Device Code Signing.
- Installation: https://xcodebuildmcp.com/docs/installation

## Tools

mcp, mcp-server, model-context-protocol, model-context-protocol-servers, tag-production, xcode, xcodebuild, TypeScript

## Source

GitHub: [getsentry/XcodeBuildMCP](https://github.com/getsentry/XcodeBuildMCP) ⭐ 6,101

## README Excerpt

A Model Context Protocol (MCP) server and CLI that provides tools for agent use when working on iOS and macOS projects.

[](https://github.com/getsentry/XcodeBuildMCP/actions/workflows/ci.yml)
[](https://badge.fury.io/js/xcodebuildmcp) [](https://opensource.org/licenses/MIT) [](https://nodejs.org/) [](https://developer.apple.com/xcode/) [](https://www.apple.com/macos/) [](https://modelcontextprotocol.io/) [](https://deepwiki.com/getsentry/XcodeBuildMCP) [](https://www.agentaudit.dev/skills/xcodebuildmcp)

## Installation

XcodeBuildMCP ships as a single package with two modes: a **CLI** for direct terminal use and an **MCP server** for AI coding agents. Either install method gives you both.

### Option A — Homebrew

```bash
brew tap getsentry/xcodebuildmcp
brew install xcodebuildmcp
```

### Option B — npm (Node.js 18+)

```bash
npm install -g xcodebuildmcp@latest
```

Verify either install:
```bash
xcodebuildmcp --help
```

### Connect your MCP client

Drop-in config snippets for Cursor, Claude Code, Codex, can be found in the official docs page MCP Clients. Most clients can also run the MCP server on demand via `npx -y xcodebuildmcp@latest mcp` without a global install.

## Requirements

- macOS 14.5 or later
- Xcode 16.x or later
- Node.js 18.x or later (not required for Homebrew installation)

## Skills

XcodeBuildMCP now includes two optional agent skills:

- **MCP Skill**: Primes the agent with instructions on how to use the MCP server's tools (optional when using the MCP server).

- **CLI Skill**: Primes the agent with instructions on how to navigate the CLI (recommended when using the CLI).

To install with a global binary:

```bash
xcodebuildmcp init
```

Or install directly via npx without a global install:

```bash
npx -y xcodebuildmcp@latest init
```

For further information on installing skills, see Agent Skills.

## Notes

- XcodeBuildMCP requests xcodebuild to skip macro validation to avoid errors when building projects that use Swift Macros.
- Device

## Sources

| Date | Video | Transcript |
|------|-------|------------|
| 2026-07-21 | [getsentry/XcodeBuildMCP](https://github.com/getsentry/XcodeBuildMCP) | github_readme |
