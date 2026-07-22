# Fieldnote Record & Replay Free

A local-first, cross-platform workaround for macOS-only Record & Replay. It records stable desktop actions into editable YAML, replays them with safety gates, exports reusable Codex-style skills, and delegates browser workflows to Playwright's selector-aware recorder.

## Why two recorders?

- `rrf browser-record` uses Playwright Codegen for resilient selectors and browser assertions.
- `rrf record` captures desktop clicks, scrolling, timing, and hotkeys for native applications.

Desktop coordinates are less durable than browser selectors. Record short workflows, keep application windows in a known position, and add verification checkpoints.

## Install

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate
pip install -e ".[browser,test]"
playwright install chromium
```

Windows users can run `install-windows.ps1` to create the environment and desktop shortcuts.

## Record a desktop workflow

```bash
rrf record "Publish repository promo" --output workflows/publish-promo.yml
```

Press `F12` to stop. Text is deliberately not recorded. Add text steps manually with placeholders such as `${REPO_URL}` to prevent credentials or personal information from entering the workflow.

## Safe replay

Dry-run is the default:

```bash
rrf replay workflows/publish-promo.yml --input REPO_URL=https://github.com/owner/repo
```

Execute only after reviewing the plan:

```bash
rrf replay workflows/publish-promo.yml --execute --input REPO_URL=https://github.com/owner/repo
```

Moving the mouse to a screen corner triggers PyAutoGUI's emergency failsafe. Steps marked `destructive: true` require confirmation unless `--yes` is explicitly supplied.

## Browser workflows

```bash
rrf browser-record https://example.com --output workflows/example.py
```

Playwright opens a browser, records selector-based Python, and supports assertions. Do not record passwords or authentication tokens.

## Export a reusable skill

```bash
rrf export-skill workflows/publish-promo.yml --output skills/publish-repository-promo/SKILL.md
```

## Free stack

| Need | Free implementation |
|---|---|
| Browser recording | Playwright Codegen |
| Desktop event capture | pynput |
| Desktop replay | PyAutoGUI |
| Workflow storage | YAML files in Git |
| Secrets | Runtime environment variables |
| Scheduling | Windows Task Scheduler, cron, or GitHub Actions |
| Team distribution | Git repository or Codex plugin package |

No Clay, paid Computer Use plan, cloud recording service, or API credits are required.
