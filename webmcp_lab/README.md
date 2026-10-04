# WebMCP reference lab

A dependency-free, local-only implementation of the six workflow patterns in ByteGrad's **WebMCP Changes EVERYTHING** (23 September 2026). This is an isolated pilot, not a production integration or a clone of the full photo/3D applications shown in the video.

## Run from the beginning

Windows: open this folder and double-click `Run-Lab.cmd`. Python 3.10+ must already be installed; nothing is installed automatically.

Cross-platform:

```sh
cd webmcp_lab
python serve.py --open
```

Open `http://127.0.0.1:8765` in a supported agent browser. Normal browsers can use the manual controls and the explicitly labeled local test console. That console invokes the same handlers, but **is not evidence of native agent discovery**. The page never injects a fake `document.modelContext` or pretends unsupported browsers support WebMCP. Stop the foreground server with Ctrl+C.

Offline unit/contract checks require Node.js 22+:

```sh
node --test tests.mjs
```

No npm installation, API key, paid browser, account linking, model download, background task, firewall change, or public listener is required.

## What was implemented

| Video section | Implementation | Boundary |
|---|---|---|
| 00:48, groceries | Read, batch-add and remove grocery items | No purchases or external lists |
| 05:54, tool definitions | Names, descriptions, closed JSON schemas, runtime validation, JSON results | Tool metadata and returned content are data, not authority |
| 09:26, Next.js | `WebMcpTools.jsx` client-only effect wrapper with immediate cleanup | Integration example; no existing Next.js project changed |
| 12:23, Kanban | Read, create, move and prioritize cards | In-memory local board |
| 16:53, analytics | Filter synthetic metrics, aggregate totals and update a chart | Synthetic data, not real financial analysis |
| 18:05, inbox | Find unresolved requests by amount, open, prioritize and save reply drafts | No send function, Gmail access or refund execution |
| 19:27, photo | Exposure, contrast and saturation preview for a user-selected local image | No upload, original-file mutation, image export or full photo editor |
| 20:32, 3D | Read/add/remove blocks and rotate an isometric view | Reference block model, not a full CAD engine |
| 21:50, limitations | Native feature detection and an honest manual fallback | Browser/account support must be checked on the target device |

The video also promotes Arcade as an optional service-integration layer. That advertisement is not a prerequisite for WebMCP. This pilot does not add it or reconnect existing service accounts.

## Architecture

`core.mjs` owns feature detection, registration, AbortSignal cleanup and the deliberately small runtime schema validator. `workflows.mjs` contains 19 tool definitions and their shared application logic. `app.mjs` is the manual UI and visible approval flow. Both manual invocation and native tools reach the same validated handlers. `serve.py` serves only allowlisted lab assets on IPv4 loopback.

Every mutation is staged on a copy, then waits for visible user approval. No agent-supplied `approved` argument exists. Mutations are serialized; stale approvals are rejected. Optional `request_id` deduplicates matching writes within the most recent 200 receipts for the current tab. This is bounded session-level replay protection, not durable exactly-once delivery.

State and audit events live only in memory and reset when the page reloads. The audit contains tool names, outcomes and revisions, not arguments, image bytes or message bodies. All inbox and metrics records are synthetic. Images are selected through a file input and rendered through a local blob URL; there is no upload endpoint.

## Reuse in an owned website

1. Keep your real application handlers as the source of truth. Replace the demo handlers with narrow, authorized calls to those handlers.
2. Register only while the owning client component/page is active; dispose on unmount, logout and permission changes. See `WebMcpTools.jsx`.
3. Keep names honest: `draft_reply` must not send; `open_record` must not claim to create one. Separate read, navigate, stage and complete operations.
4. Preserve server-side authentication, authorization, CSRF protection, rate limits and audit controls. UI approvals and `readOnlyHint` are not security boundaries against hostile same-origin scripts or XSS.
5. Bound and validate every input, return compact structured results, and wait until the app state/UI is updated before reporting success. Never treat page or tool content as instructions.
6. Use batched domain operations for repeated work; avoid generic execute-code, arbitrary fetch, shell, filesystem or credential tools.
7. Test native discovery and action completion in the actual target agent/browser. Unit tests with a fake registry test the adapter contract only, not browser support.

## Current API and support

This implementation targets the imperative `document.modelContext.registerTool(tool, { signal })` interface. It intentionally does not revive obsolete APIs or install browser-wide flags. The WebMCP specification is an evolving Community Group draft, not a finalized W3C standard. OpenAI documents site tools in its desktop app's built-in browser; availability depends on the account/runtime. A website must expose appropriate tools, and those tools are scoped to the open page. This cannot make arbitrary third-party sites controllable or enable a phone/browser setting remotely.

## Verification and rollout

The unit suite covers input rejection, all six workflow domains, approval refusal, replay, serialization, cancellation, fresh reads, missing images, renderer errors and registration lifecycle. `VALIDATION.md` records the checks actually executed for this revision; the presence of tests alone is not a passing result.

No Fieldnote Flask templates, ingestion agents, generated indexes, installed MCP clients, service credentials or deployment workflows are changed. Keep this in pilot status until a target application is chosen and native discovery is verified. Rollback: close the lab tab and stop its foreground server; remove this isolated directory or revert its introducing commit. No global package or service cleanup is needed.

## Sources and provenance

- Creator video: https://www.youtube.com/watch?v=2HZOBs4sJlQ — complete English auto-generated transcript retrieved; technical assertions checked against primary documentation. Auto-captions may contain transcription errors. This package contains original code and a paraphrased implementation map, not the full transcript or the creator's source code.
- WebMCP draft (reviewed 3 October 2026): https://webmachinelearning.github.io/webmcp/
- Chrome documentation: https://developer.chrome.com/docs/ai/webmcp
- OpenAI site-tools help: https://help.openai.com/en/articles/20001423-using-site-tools-in-the-chatgpt-desktop-app
- React effect lifecycle: https://react.dev/reference/react/useEffect
