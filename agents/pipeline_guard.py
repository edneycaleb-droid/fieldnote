"""
pipeline_guard.py — pre-save skill sanitizer
=============================================
Runs immediately after _judge_arena() returns a skill dict, before any
downstream code touches the data.  Validates every field, auto-fixes bad
types / None values, and emits a live summary so the user can see it
working in the log panel.

Never raises — always returns a valid, usable skill dict.
"""

from __future__ import annotations
import re, uuid, logging
from typing import Callable

log = logging.getLogger(__name__)

# ── Field spec ────────────────────────────────────────────────────────────────
# (field_name, expected_type, default_value, required)
_STRING_FIELDS = [
    ("action",         "create"),
    ("enhance_target", None),
    ("skill_name",     ""),
    ("title",          ""),
    ("description",    ""),
    ("skill_markdown", ""),
]
_LIST_FIELDS = [
    ("steps",           []),
    ("tools",           []),
    ("python_packages", []),
    ("concepts",        []),
    ("tags",            []),
    ("related_skills",  []),
]
_VALID_ACTIONS = {"create", "enhance"}


# ── Public entry point ────────────────────────────────────────────────────────

def sanitize(skill: object, emit: Callable[[str, str], None]) -> dict:
    """
    Validate and fix `skill` in-place.  Returns a guaranteed-clean dict.
    Calls emit() to stream each fix into the SSE log panel.

    Parameters
    ----------
    skill : the raw dict returned by _judge_arena() — may be None or malformed
    emit  : the run_job emit(msg, kind) callback

    Returns
    -------
    A clean dict with all required fields present and correct types.
    """
    fixes: list[str] = []

    # ── Guard: skill must be a dict ───────────────────────────────────────────
    if not isinstance(skill, dict):
        fixes.append(f"skill was {type(skill).__name__}, replaced with empty dict")
        skill = {}

    # ── String fields ─────────────────────────────────────────────────────────
    for field, default in _STRING_FIELDS:
        raw = skill.get(field)
        if raw is None or isinstance(raw, (dict, list)):
            if raw is not None:
                fixes.append(f"{field}: was {type(raw).__name__}, reset to default")
            if default is not None:
                skill[field] = default
            else:
                skill[field] = None
        elif not isinstance(raw, str):
            coerced = str(raw).strip()
            fixes.append(f"{field}: coerced {type(raw).__name__} → str")
            skill[field] = coerced
        else:
            skill[field] = raw.strip()

    # ── action must be valid ──────────────────────────────────────────────────
    if skill.get("action") not in _VALID_ACTIONS:
        old = skill.get("action")
        skill["action"] = "create"
        fixes.append(f"action: '{old}' not valid, reset to 'create'")

    # ── skill_name: generate fallback if empty/invalid ───────────────────────
    sn = skill.get("skill_name", "")
    sn_clean = re.sub(r"[^a-z0-9_]", "_", sn.lower()).strip("_") if sn else ""
    if not sn_clean:
        # Derive from title as last resort, then random
        title = skill.get("title", "")
        if title:
            sn_clean = re.sub(r"[^a-z0-9_]", "_", title.lower()).strip("_")[:40]
        if not sn_clean:
            sn_clean = f"skill_{uuid.uuid4().hex[:6]}"
        fixes.append(f"skill_name: was empty/invalid, generated '{sn_clean}'")
        skill["skill_name"] = sn_clean

    # ── title: fall back to skill_name if empty ───────────────────────────────
    if not skill.get("title"):
        skill["title"] = skill["skill_name"].replace("_", " ").title()
        fixes.append(f"title: was empty, derived from skill_name")

    # ── description: ensure string ────────────────────────────────────────────
    if not skill.get("description"):
        skill["description"] = skill.get("title", "")
        if not skill["description"]:
            skill["description"] = "Extracted from video."
        fixes.append("description: was empty, used title as fallback")

    # ── skill_markdown: build minimal fallback if missing ─────────────────────
    if not skill.get("skill_markdown"):
        title    = skill.get("title", "Skill")
        desc     = skill.get("description", "")
        steps    = skill.get("steps", [])
        step_md  = "\n".join(f"- {s}" for s in steps if isinstance(s, str)) if steps else "- See video."
        skill["skill_markdown"] = f"# {title}\n\n{desc}\n\n## Steps\n\n{step_md}\n"
        fixes.append("skill_markdown: was empty, generated minimal markdown")

    # ── List fields ───────────────────────────────────────────────────────────
    for field, default in _LIST_FIELDS:
        raw = skill.get(field)
        if raw is None:
            skill[field] = list(default)
        elif isinstance(raw, str):
            # AI sometimes returns a comma-separated string
            skill[field] = [x.strip() for x in raw.split(",") if x.strip()]
            fixes.append(f"{field}: string → split into list ({len(skill[field])} items)")
        elif not isinstance(raw, list):
            skill[field] = list(default)
            fixes.append(f"{field}: was {type(raw).__name__}, reset to []")
        else:
            # Ensure every element is a string
            cleaned = []
            for item in raw:
                if isinstance(item, str) and item.strip():
                    cleaned.append(item.strip())
                elif item is not None and not isinstance(item, (dict, list)):
                    cleaned.append(str(item).strip())
                elif isinstance(item, dict):
                    # e.g. {"name": "tool"} → try to extract the value
                    val = next((v for v in item.values() if isinstance(v, str)), None)
                    if val:
                        cleaned.append(val.strip())
            if len(cleaned) != len([x for x in raw if x]):
                fixes.append(f"{field}: cleaned {len(raw)} → {len(cleaned)} items")
            skill[field] = cleaned

    # ── python_packages: strip anything with spaces (not a real pkg name) ─────
    pkgs = skill.get("python_packages", [])
    clean_pkgs = [p for p in pkgs if isinstance(p, str) and p and " " not in p]
    if len(clean_pkgs) != len(pkgs):
        fixes.append(f"python_packages: removed {len(pkgs)-len(clean_pkgs)} invalid entries")
    skill["python_packages"] = clean_pkgs

    # ── Emit summary ──────────────────────────────────────────────────────────
    if fixes:
        emit(
            f"🛡  Pipeline guard: {len(fixes)} fix(es) applied — "
            + "; ".join(fixes[:3])
            + (" …" if len(fixes) > 3 else ""),
            "warning",
        )
        log.warning("pipeline_guard fixes: %s", fixes)
    else:
        emit("🛡  Pipeline guard: all fields clean ✓", "info")

    return skill
