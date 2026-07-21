# MCP Registry Development and Deployment

## Description

The MCP Registry service acts as a central directory for Model Context Protocol (MCP) servers, akin to an app store. It allows clients to discover available MCP servers and enables developers to publish their own MCP server endpoints. This skill covers setting up the registry for local development, running pre-built Docker images, and understanding the process and authentication methods for publishing new MCP servers.

## Development Status

- **API Freeze (v0.1)**: The API is stable for a period, allowing integrators to confidently implement support while development continues on v1. (As of 2025-10-24)
- **Preview Launch**: The registry has launched in preview, with potential for breaking changes until a General Availability (GA) release. (As of 2025-09-08)

## Contributing

Collaboration occurs through Discord, GitHub Discussions, Issues, and Pull Requests.

## Quick Start: Local Development

### Prerequisites

- Docker
- Go 1.24.x
- ko
- golangci-lint v2.4.0

### Steps

1.  **Clone the repository**: `git clone https://github.com/modelcontextprotocol/registry.git`
2.  **Start the development environment**: Run `make dev-compose`. This command uses `ko` to build container images and loads them into Docker, starting the registry API and PostgreSQL.
3.  **Configure the environment**: If needed, configure the local environment using environment variables by referencing `.env.example`.
4.  **Offline Development (Optional)**: For offline development, set `MCP_REGISTRY_SEED_FROM` and `MCP_REGISTRY_ENABLE_REGISTRY_VALIDATION=false` before running `make dev-compose`.

## Running Pre-built Docker Images

1.  **Pull the image**: `docker pull ghcr.io/modelcontextprotocol/registry:latest`
2.  **Run the container**: `docker run -p 8080:8080 ghcr.io/modelcontextprotocol/registry:latest`
3.  **Configure PostgreSQL**: Ensure a PostgreSQL instance is running and configure the registry to connect via the `MCP_REGISTRY_DATABASE_URL` environment variable.

## Publishing MCP Servers

1.  **Build the publisher CLI**: Run `make publisher`.
2.  **Publish servers**: Use the `mcp-publisher` CLI tool to publish MCP servers to the registry.
3.  **Authentication**: Explore authentication methods for publishing, including GitHub OAuth, GitHub OIDC, DNS verification, and HTTP verification.
4.  **Validation**: Understand namespace ownership validation during the publishing process.

## Development Commands

- **Run tests and linting**: `make check`
- **View all commands**: `make help`

## Sources

| Date | Video | Transcript |
|------|-------|------------|
| 2026-07-21 | [modelcontextprotocol/registry](https://github.com/modelcontextprotocol/registry) | github_readme |
