# Project Status

Fieldnote is an active, experimental personal knowledge system. It ingests approved media and repository sources, produces structured skill notes, and publishes generated library indexes.

## Current state

- **Application:** Python 3.10 Flask service with autonomous ingestion, validation, discovery, and synchronization agents.
- **Data model:** generated Markdown skills under `skills/` plus assistant knowledge and graph indexes.
- **Operating mode:** free-first and local-first; paid providers are optional and must never be required for the basic pipeline.
- **Generated files:** `README.md`, `_brain.json`, and much of `skills/` are automation outputs. Update their generators instead of hand-editing outputs.
- **Quality posture:** repository metadata, deterministic structural validation, supply-chain quarantine, MCP protocol boundaries, scheduler overlap controls, source provenance, evidence freshness, duplicate fingerprints, Capability DNA, and unsafe-instruction screening are exercised by offline tests.
- **Trust states:** only `ALLOW` skills may auto-sync as trusted knowledge. `REDUCE` skills remain local and quarantined; `DENY` skills are blocked.
- **Provider policy:** OpenRouter is disabled unless Caleb explicitly re-approves it and `FIELDNOTE_ENABLE_OPENROUTER=1` is deliberately set.
- **Autonomous agents:** GitHub discovery, enrichment recovery, integration health, MCP health, and ecosystem-policy audits run on bounded recurring schedules while the Fieldnote service is online. GitHub Actions independently reruns the offline evidence suite every six hours.

## Known limitations

- A generated skill is a research note, not automatically trusted instructions or an installed capability.
- Discovered repositories, Python packages, tools, and MCP servers enter a durable quarantine. They receive zero activation authority until immutable source, license, exact version, artifact digest, read-only capability, and sandbox evidence exist.
- Automatic host `pip`, `uvx`, `npx`, editable dependency installation, and discovered repository execution are blocked.
- Provider availability and rate limits may temporarily degrade enrichment quality.
- Current validation is structural and offline; it does not prove third-party API availability or end-to-end scheduler execution.
- Evidence freshness windows are policy defaults, not proof that unchanged material remains accurate throughout the entire window.
- Secrets are runtime configuration only and must never appear in generated notes, logs, issues, commits, or artifacts.

## Safe verification

```bash
python scripts/check_repository_quality.py
python scripts/audit_skills.py skills --output artifacts/skill-quality-report.json --fail-on critical
python -m unittest discover -s tests -v
python -m compileall -q agents fieldnote_mcp app.py main.py
```

These checks perform no network requests and do not start the Flask service or scheduler.
