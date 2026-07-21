# Project Status

Fieldnote is an active, experimental personal knowledge system. It ingests approved media and repository sources, produces structured skill notes, and publishes generated library indexes.

## Current state

- **Application:** Python 3.10 Flask service with autonomous ingestion, validation, discovery, and synchronization agents.
- **Data model:** generated Markdown skills under `skills/` plus assistant knowledge and graph indexes.
- **Operating mode:** free-first and local-first; paid providers are optional and must never be required for the basic pipeline.
- **Generated files:** `README.md`, `_brain.json`, and much of `skills/` are automation outputs. Update their generators instead of hand-editing outputs.
- **Quality posture:** repository metadata and deterministic structural validation are enforced by `scripts/check_repository_quality.py`.

## Known limitations

- A generated skill is a research note, not automatically trusted instructions or an installed capability.
- Provider availability and rate limits may temporarily degrade enrichment quality.
- Current validation is structural and offline; it does not prove third-party API availability or end-to-end scheduler execution.
- Secrets are runtime configuration only and must never appear in generated notes, logs, issues, commits, or artifacts.

## Safe verification

```bash
python scripts/check_repository_quality.py
python -m compileall -q agents fieldnote_mcp app.py main.py
```

These checks perform no network requests and do not start the Flask service or scheduler.
