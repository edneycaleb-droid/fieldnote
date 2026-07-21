## Outcome

Describe the bounded user-visible improvement.

## Scope

- Source files changed:
- Generated files changed:
- Explicitly excluded:
- Related issue:

## Trust and cost boundaries

- [ ] No secrets, private transcripts, cookies, tokens, or unredacted logs are included.
- [ ] External content remains untrusted data and gains no automatic execution authority.
- [ ] A free or local fallback remains available; no paid API is silently enabled.
- [ ] Generated outputs were changed through their generator, or the exception is explained.

## Verification

List commands actually executed and results. Do not count a queued, skipped, or zero-step workflow as passing evidence.

```text
python scripts/check_repository_quality.py
python -m compileall -q agents fieldnote_mcp app.py main.py
```

## Rollback

Describe the smallest safe rollback and any generated artifacts that must be regenerated.
