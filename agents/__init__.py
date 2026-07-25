"""Fieldnote agent package policy bootstrap.

Standing owner policies are enforced before any submodule is imported:

- OpenRouter is disabled unless ``FIELDNOTE_ENABLE_OPENROUTER=1`` is explicitly set.
- Only skills whose stored quality decision is ``allow`` may auto-sync to GitHub.
  Draft, duplicate, stale, or high-risk skills remain local and reviewable.
"""
from __future__ import annotations

import os
from typing import Any


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


OPENROUTER_EXPLICITLY_ENABLED = _truthy(os.getenv("FIELDNOTE_ENABLE_OPENROUTER"))
if not OPENROUTER_EXPLICITLY_ENABLED:
    os.environ.pop("OPENROUTER_API_KEY", None)
    os.environ["FIELDNOTE_OPENROUTER_POLICY"] = "disabled_requires_explicit_owner_reapproval"
else:
    os.environ["FIELDNOTE_OPENROUTER_POLICY"] = "explicitly_enabled"


def _quality_decision(index: dict[str, Any], skill_name: str) -> str:
    quality = (index.get(skill_name) or {}).get("_quality") or {}
    return str(quality.get("decision") or "").strip().lower()


def quality_allows_sync(index: dict[str, Any], skill_name: str) -> bool:
    """Return True only for explicitly ALLOW-scored skills."""
    return _quality_decision(index, skill_name) == "allow"


# Patch the existing sync module at package import so every caller—including app.py—
# receives the same fail-closed policy without duplicating sync implementations.
try:
    from . import github_sync as _github_sync

    _original_sync_skill = _github_sync.sync_skill

    def _governed_sync_skill(skill_name: str, markdown: str, index: dict) -> bool:
        if not quality_allows_sync(index, skill_name):
            return False
        return _original_sync_skill(skill_name, markdown, index)

    _github_sync.sync_skill = _governed_sync_skill
except Exception:
    # Import failures remain visible when the actual submodule is imported. The policy
    # functions above stay available for offline validators and tests.
    pass
