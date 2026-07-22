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

## Video-to-playbook mode

Record the task using OBS, ShareX, Snipping Tool, Xbox Game Bar, or any screen recorder, then provide the finished MP4:

```bash
rrf video-ingest demo.mp4 --runs runs --interval 3 --transcribe
rrf video-playbook runs/RUN_ID --model qwen3-vl:30b
rrf export-playbook runs/RUN_ID/playbook.json --output exports/my-workflow
```

This creates an immutable evidence bundle containing the source hash, sampled frames, optional local Whisper transcript, manifest, and model-neutral playbook. The exporter writes:

- `PLAYBOOK.md`
- `SKILL.md` for Codex
- `CLAUDE.md`
- `GEMINI.md`

The default visual model is your local Ollama `qwen3-vl:30b`; change `--model` to any Ollama vision model. Video processing uses local FFmpeg, and transcription uses optional `faster-whisper`. No video or frames leave the computer.

Trim recordings before ingestion when possible. A concise recording avoids analyzing dead air and produces clearer evidence than an improvised live session.
