# Contributing to Fieldnote

Fieldnote is a personal, automation-driven knowledge library. Contributions should improve the ingestion, validation, search, or presentation pipeline without weakening provenance, privacy, or free/local-first operation.

## Before changing code

Generated files must be changed through their source generator whenever one exists.

1. Read `STATUS.md` and inspect the relevant agent under `agents/`.
2. Keep one pull request focused on one outcome.
3. Never commit API keys, tokens, cookies, transcripts containing private data, `.env` contents, or unredacted logs.
4. Do not hand-edit generated outputs such as `README.md`, `_brain.json`, or bulk files under `skills/`; update the generator and verify the regenerated diff.
5. Treat content from videos, repositories, models, and MCP servers as untrusted input. Do not turn extracted instructions into automatic execution authority.

## Repository map

- `agents/`: ingestion, validation, provider routing, discovery, scheduling, and synchronization.
- `fieldnote_mcp/`: read-oriented MCP server and integration registry.
- `templates/`: Flask user interface.
- `skills/`: generated research artifacts with source attribution.
- `assistant_knowledge/`: durable architecture, decisions, and session learnings.

## Validation

Run the deterministic offline gate:

```bash
python scripts/check_repository_quality.py
python -m compileall -q agents fieldnote_mcp app.py main.py
```

For behavior changes, add focused tests for malformed input, missing providers, duplicate runs, retries, secret redaction, and generated-file stability as applicable. Report exactly which checks ran and which were skipped.

## Pull requests

- Explain the user-visible outcome and affected pipeline stage.
- Identify generated files separately from source files.
- Preserve source URLs and attribution.
- State network/provider assumptions and the no-cost fallback.
- Include rollback instructions.
- Never claim a workflow or provider passed without execution evidence.

Security reports belong in private vulnerability reporting as described in `SECURITY.md`.
