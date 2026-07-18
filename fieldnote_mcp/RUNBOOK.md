# Fieldnote MCP Hub — Operator Runbook

## Architecture Overview

```
┌──────────────────────────────────────────────────────┐
│                    Fieldnote App                      │
│                                                      │
│  ┌──────────────┐   ┌───────────────┐               │
│  │ MCP Registry │   │ MCP Verifier  │               │
│  │ (data model) │   │ (handshake)   │               │
│  └──────┬───────┘   └──────┬────────┘               │
│         │                  │                         │
│  ┌──────▼──────────────────▼────────┐               │
│  │          MCP Router               │               │
│  │  capability → healthiest server   │               │
│  │  circuit breaker per server       │               │
│  └──────────────────────────────────┘               │
│                                                      │
│  ┌──────────────────────────────────┐               │
│  │       Scheduled Jobs              │               │
│  │  mcp_health  (every 15 min)       │               │
│  │  mcp_refresh (every 24 h)         │               │
│  └──────────────────────────────────┘               │
└──────────────────────────────────────────────────────┘
```

## Security Model

- **Credentials** are injected at subprocess spawn time only, via `os.environ`.
  They are never logged, never returned in API responses, never written to disk
  in plaintext (except through the existing protected `local_keys.json` flow).
- **Output cap**: 50 KB per subprocess read prevents memory exhaustion.
- **Timeout**: 30 s total per verification/call. SIGTERM → SIGKILL on exit.
- **Write-capable servers** (servers whose `write_capable=True`) are disabled
  by default. The operator must explicitly enable them.
- **Filesystem scope**: MCP filesystem servers receive only approved read-only
  paths. No server is given write access to the Fieldnote skills directory.
- **License allowlist**: Only servers with SPDX license identifiers in
  `APPROVED_LICENSES` are permitted. Others are quarantined automatically.
- **Package identity**: PyPI packages are verified to belong to the expected
  repo owner before installation.

## Supported Transports

| Transport    | Status      | Notes                                              |
|-------------|-------------|-----------------------------------------------------|
| stdio        | ✅ Supported | Default for uvx/pip/npm servers                    |
| Streamable HTTP | ⚠ Not supported | "remote transport not yet supported in Replit sandbox" |
| SSE          | ⚠ Not supported | Same as above                                      |

## Capability → Task Mapping

| Fieldnote Capability | Used For                          |
|---------------------|-----------------------------------|
| `web_search`         | Research queries, link lookup     |
| `web_crawl`          | Full-page content extraction      |
| `transcription`      | Audio/video → text                |
| `git_read`           | Reading GitHub repos, READMEs     |
| `vector_search`      | Semantic similarity lookup        |
| `file_read`          | Local file and database access    |
| `doc_convert`        | PDF/DOCX → Markdown conversion    |

## Routing Policy

1. Only `connected` or `degraded` servers are eligible.
2. Circuit must be CLOSED or HALF_OPEN.
3. Sorted by `success_rate DESC`, `avg_latency_ms ASC`.
4. Max 2 MCP server attempts per `call_tool` invocation.
5. After MCP exhaustion, Fieldnote's own native fallback is called.
6. `call_tool` never raises — returns `None` on total failure.

## Circuit Breaker States

```
CLOSED ──(3 failures in 5 min)──→ OPEN ──(10 min cooldown)──→ HALF_OPEN
  ▲                                                                  │
  └────────────────(probe success)──────────────────────────────────┘
  OPEN ◄──────────(probe failure)──────────────────────────────────┘
```

## Lifecycle States

| State              | Meaning                                          |
|-------------------|--------------------------------------------------|
| `not_installed`    | Not installed yet — show Install button          |
| `installing`       | uvx/pip/npm install in progress                  |
| `verifying`        | Protocol handshake in progress                   |
| `connected`        | Handshake succeeded — fully operational          |
| `degraded`         | Responds but slow or partial capabilities        |
| `offline`          | Was connected, now unreachable                   |
| `quarantined`      | Bad license or package identity — blocked        |
| `runtime_missing`  | Node.js / Python not found                       |
| `missing_credential` | Required env var not set                       |

## Recovery Procedure

### Server offline
1. Check `GET /api/mcp-hub/health` for error details.
2. Click **Test** in the Hub UI to re-run the protocol handshake.
3. If `runtime_missing`: install the required runtime (Node.js or Python).
4. If `missing_credential`: add the required API key in Integrations tab.
5. The 15-minute `mcp_health` scheduler job re-verifies automatically.

### Circuit breaker stuck open
- The circuit auto-resets after 10 minutes if the server recovers.
- Force reset: `POST /api/mcp-hub/verify/<id>` re-runs the handshake and
  clears the breaker on success.

### Quarantined server
- A quarantined server cannot be enabled until the quarantine reason is
  resolved. Check `quarantine_reason` in `GET /api/mcp-hub/registry`.
- `unverified_license`: The server's SPDX license is not in the allowlist.
  If incorrect, update the registry entry and restart.
- `package_identity_mismatch`: The PyPI package doesn't match the expected
  repo owner. This indicates a potential supply-chain issue — do not enable.

## Operator Commands

```bash
# View full registry
curl http://localhost:5000/api/mcp-hub/registry | python -m json.tool

# Check health summary
curl http://localhost:5000/api/mcp-hub/health

# View capability map
curl http://localhost:5000/api/mcp-hub/capabilities

# Install a server
curl -X POST http://localhost:5000/api/mcp-hub/install/exa-search

# Verify a server (re-run handshake)
curl -X POST http://localhost:5000/api/mcp-hub/verify/exa-search

# Enable / disable
curl -X POST http://localhost:5000/api/mcp-hub/enable/exa-search
curl -X POST http://localhost:5000/api/mcp-hub/disable/exa-search

# Uninstall
curl -X POST http://localhost:5000/api/mcp-hub/uninstall/exa-search

# Migration report (existing connections import)
curl http://localhost:5000/api/mcp-hub/migration-report

# Trigger health check now
curl -X POST http://localhost:5000/api/scheduler/run/mcp_health

# Trigger version refresh now
curl -X POST http://localhost:5000/api/scheduler/run/mcp_refresh
```

## Scheduled Job Summary

| Job Name      | Interval | Action                                           |
|--------------|----------|--------------------------------------------------|
| `mcp_health`  | 15 min   | Re-verify all enabled servers; emit Intel event on state change |
| `mcp_refresh` | 24 h     | Check PyPI/npm for newer versions; flag major bumps |

## File Locations

| File                                    | Purpose                              |
|----------------------------------------|--------------------------------------|
| `fieldnote_mcp/mcp_hub_registry.json`  | Persisted registry with runtime state |
| `fieldnote_mcp/status.json`            | Legacy MCP connections (migrated in) |
| `fieldnote_mcp/migration_report.json`  | First-startup migration results      |
| `fieldnote_mcp/RUNBOOK.md`             | This file                            |
| `agents/mcp_registry.py`               | Registry data model + validation     |
| `agents/mcp_verifier.py`               | Protocol handshake verifier          |
| `agents/mcp_router.py`                 | Capability router + circuit breaker  |
| `agents/mcp_agent.py`                  | Installer / lifecycle management     |
