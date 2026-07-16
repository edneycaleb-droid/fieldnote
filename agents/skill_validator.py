"""
skill_validator.py — extraction-layer validation
=================================================
Validates and normalises a raw dict returned by json.loads() of any LLM
extraction call BEFORE the dict enters _judge_arena().

This is the first defence layer.  pipeline_guard.sanitize() is the second
layer that runs after judge_arena.  Both must remain in place.

The root failure mode that both layers prevent:
  LLM writes: {"steps": null, "tools": null}
  Python:     dict.get("steps", []) → None   (key exists; default ignored)
  Downstream: len(None)  → TypeError: object of type 'NoneType' has no len()

Public API
----------
  validate_extraction(raw_dict, context="") -> dict
      Always returns a dict with all six list fields guaranteed to be real lists.
      Never raises.
"""

from __future__ import annotations
import logging
from typing import Any

log = logging.getLogger("fieldnote.skill_validator")

_LIST_FIELDS = (
    "steps", "tools", "concepts", "tags", "python_packages", "related_skills",
)
_STR_FIELDS = (
    "action", "skill_name", "title", "description", "skill_markdown", "enhance_target",
)
_VALID_ACTIONS = {"create", "enhance"}


def _to_list(v: Any) -> list:
    """Convert any value to a list, treating None as empty."""
    if isinstance(v, list):
        return [str(x).strip() for x in v if x is not None and str(x).strip()]
    if v is None:
        return []
    if isinstance(v, str):
        return [x.strip() for x in v.split(",") if x.strip()]
    return []


def validate_extraction(d: Any, context: str = "") -> dict:
    """
    Normalise an LLM extraction result dict.

    Parameters
    ----------
    d       : raw object from json.loads() — may be None, a non-dict, or a dict
              with null list fields.
    context : caller label for log messages (e.g. "chatgpt" or "groq").

    Returns
    -------
    A dict with every list field guaranteed to be a real list (never None),
    and every string field guaranteed to be a str (or None for enhance_target).
    """
    fixes: list[str] = []

    if not isinstance(d, dict):
        fixes.append(f"root was {type(d).__name__}, replaced with {{}}")
        log.warning("validate_extraction[%s]: %s", context, fixes[-1])
        d = {}

    # ── List fields — the primary null-safety target ──────────────────────────
    for field in _LIST_FIELDS:
        raw = d.get(field)
        if not isinstance(raw, list):
            converted = _to_list(raw)
            if raw is not None:
                fixes.append(f"{field}: {type(raw).__name__} → list({len(converted)})")
            d[field] = converted

    # ── String fields — coerce non-strings and strip ──────────────────────────
    for field in _STR_FIELDS:
        raw = d.get(field)
        if field == "enhance_target":
            # allowed to be None
            if raw is not None and not isinstance(raw, str):
                d[field] = str(raw).strip() or None
        elif raw is None:
            d[field] = ""
        elif not isinstance(raw, str):
            d[field] = str(raw).strip()
            fixes.append(f"{field}: {type(raw).__name__} → str")
        else:
            d[field] = raw.strip()

    if fixes:
        log.warning("validate_extraction[%s]: %d fix(es): %s", context, len(fixes), "; ".join(fixes))

    return d
