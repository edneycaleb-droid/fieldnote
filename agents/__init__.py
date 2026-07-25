"""Fieldnote agent package policy bootstrap.

OpenRouter is disabled by standing owner policy. Importing any ``agents.*`` module
removes its key from the process unless the owner explicitly sets
``FIELDNOTE_ENABLE_OPENROUTER=1``. This keeps legacy router code fail-closed while
preserving a deliberate future re-approval path.
"""
from __future__ import annotations

import os


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


OPENROUTER_EXPLICITLY_ENABLED = _truthy(os.getenv("FIELDNOTE_ENABLE_OPENROUTER"))
if not OPENROUTER_EXPLICITLY_ENABLED:
    os.environ.pop("OPENROUTER_API_KEY", None)
    os.environ["FIELDNOTE_OPENROUTER_POLICY"] = "disabled_requires_explicit_owner_reapproval"
else:
    os.environ["FIELDNOTE_OPENROUTER_POLICY"] = "explicitly_enabled"
