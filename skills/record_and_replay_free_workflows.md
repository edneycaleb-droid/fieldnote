---
name: record-and-replay-free-workflows
description: Record a demonstrated browser or desktop workflow, convert it into a parameterized reusable skill, and replay it safely without paid Computer Use, Clay, or macOS-only dependencies. Use for repetitive workflows with stable steps and clear success criteria.
---

# Record and Replay Free Workflows

## When to use

Use this workflow when a task is repetitive, depends on personal defaults, or is easier to demonstrate than describe. Prefer Playwright recording for browser tasks and desktop recording only for native applications.

When live capture is unavailable or inefficient, prefer a trimmed screen recording. Video-first capture is model-neutral, reusable, and avoids spending inference time on pauses or corrections.

## Inputs

- Workflow name and goal
- Inputs that change between runs
- Target application or starting URL
- Success criteria
- Any destructive or externally visible steps

## Learn mode

1. Define the goal, variable inputs, and observable success state.
2. Choose browser recording for websites or desktop recording for native applications.
3. Keep the demonstration short and complete.
4. Never record passwords, tokens, private keys, or sensitive personal data.
5. Stop recording immediately after the success state is reached.
6. Replace typed values with `${VARIABLE}` placeholders.
7. Mark publish, send, delete, purchase, permission, and submission steps as destructive.
8. Add verification criteria and failure behavior.
9. Dry-run the workflow and inspect every step.
10. Export the validated workflow to `SKILL.md`.

## Video-first learn mode

1. Record a clean demonstration with OBS, ShareX, Snipping Tool, Xbox Game Bar, or another local recorder.
2. Re-record mistakes or trim dead air before analysis.
3. Ingest the finished video into an immutable run directory.
4. Extract sampled frames with FFmpeg and speech with local faster-whisper when narration exists.
5. Analyze frames and transcript with a local Ollama vision model.
6. Require every generated step to cite frame or transcript evidence.
7. Export one model-neutral playbook plus Codex, Claude, and Gemini instruction files.

```bash
rrf video-ingest demo.mp4 --runs runs --transcribe
rrf video-playbook runs/RUN_ID --model qwen3-vl:30b
rrf export-playbook runs/RUN_ID/playbook.json --output exports/workflow
```

## Implement mode

```bash
rrf record "Workflow name" --output workflows/workflow.yml
rrf replay workflows/workflow.yml
rrf replay workflows/workflow.yml --execute --input VARIABLE=value
rrf export-skill workflows/workflow.yml --output skills/workflow/SKILL.md
```

For browser workflows:

```bash
rrf browser-record https://example.com --output workflows/browser_workflow.py
```

## Safety rules

- Dry-run by default.
- Require explicit `--execute` to control the computer.
- Store secrets only in runtime environment variables.
- Require confirmation before destructive actions.
- Preserve PyAutoGUI's corner failsafe.
- Stop when verification fails; do not improvise around authentication or permission barriers.
- Re-record workflows after meaningful interface changes.

## Verification

- The workflow file validates against the schema.
- Every changing value is parameterized.
- No secret appears in the workflow or skill.
- Destructive actions have confirmation gates.
- The replay reaches the stated success criteria.
- A dry-run and automated test suite pass before distribution.
