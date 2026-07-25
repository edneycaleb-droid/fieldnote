# Fieldnote Skill Quality Governance

Fieldnote stores research-derived skills. A generated skill is not automatically trusted instructions, an installed capability, or evidence that an upstream project is safe.

## Decision states

- **ALLOW** — attributable, actionable, sufficiently current, unique, and free of blocked instruction patterns. It may auto-sync as a normal skill.
- **REDUCE** — retained locally as a quarantined draft with findings. It may be enhanced, merged, or reviewed, but it does not auto-sync as trusted knowledge.
- **DENY** — contains a secret, critical executable or credential pattern, or lacks enough usable content. It must not be published.

## Quality gates

`agents/skill_quality.py` evaluates:

1. secret scanning;
2. title and description quality;
3. step count;
4. actionable rather than generic instructions;
5. tools and content depth;
6. multi-provider arena evidence when present;
7. source provenance;
8. draft/degraded status;
9. evidence freshness and half-life;
10. unsafe capability patterns;
11. duplicate content fingerprint;
12. Capability DNA for behavior-level comparison.

## Unsafe source salvage

Useful ideas from quarantined repositories may be retained as:

- schemas;
- checklists;
- architecture patterns;
- negative tests;
- simulation fixtures;
- safety controls;
- attributed concepts rewritten from first principles.

The following are removed or blocked:

- remote pipe-to-shell installation;
- credentials, wallet keys, seed phrases, or withdrawal-enabled access;
- permissionless infinite autonomy;
- CAPTCHA or anti-detection bypasses;
- live financial actions;
- security-control bypasses;
- silent shared-skill mutation or auto-promotion.

## Freshness

Evidence authority decays according to the subject:

- current facts, pricing, API state, and market data: 30 days;
- frameworks, models, agents, MCPs, deployments, and trading systems: 180 days;
- stable concepts: 365 days.

Stale skills remain searchable but cannot be treated as current without re-verification.

## OpenRouter policy

OpenRouter is disabled by default under the standing owner policy. Importing the `agents` package removes `OPENROUTER_API_KEY` from the process unless the owner explicitly sets:

```text
FIELDNOTE_ENABLE_OPENROUTER=1
```

That flag is a technical re-enable mechanism, not proof of owner approval by itself. Any future use should still be documented and reviewed.

## Audit

```bash
python scripts/audit_skills.py skills --output artifacts/skill-quality-report.json --fail-on critical
python -m unittest tests.test_skill_quality_governance -v
```

The full library audit deliberately permits noncritical drafts to remain in the historical repository while failing CI on critical secrets or executable/credential patterns.
