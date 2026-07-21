# Security Policy

## Reporting

Use GitHub private vulnerability reporting or a private security advisory. Do not open a public issue containing tokens, cookies, webhook URLs, private transcripts, personal knowledge, infrastructure details, or exploit instructions.

Include the affected commit and path, impact, a minimal redacted reproduction, and a suggested containment step when known. Never include a real secret value.

## Supported version

Security fixes target the current `main` branch. Generated skill documents are not executable packages and do not receive separate version support.

## Trust boundaries

- Video captions, web pages, GitHub content, model responses, MCP output, and generated skills are untrusted data.
- Extracted instructions must not trigger shell commands, repository writes, provider changes, or credential use without an explicit bounded workflow.
- Secrets must remain in the runtime secret store and out of Git, logs, generated notes, issues, and artifacts.
- Provider fallback must stay free-first/local-first; a failure must not silently activate a paid API.
- GitHub sync must limit writes to the intended repository and generated paths.

Prefer reversible containment and disable the affected automation path until its boundary is verified.
