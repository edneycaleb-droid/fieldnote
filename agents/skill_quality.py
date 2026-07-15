"""
Fieldnote Skill Quality Gate
Adapted from hermes_live_readiness (ai-crypto-trading-bot).

  GateFinding  — typed pass/fail result with evidence dict
  quality_gate — runs all checks, returns findings + confidence score
  ALLOW / REDUCE / DENY decision (from execution_contract.py)
  secret_scan  — SECRET_PATTERNS from readiness_gates.py
  dca_schedule — from Hummingbot DCAExecutor: multi-level enhancement plan

Philosophy (from SimpleTrend README):
  "Prove a simple, explainable edge before layering on complexity."
  Gates are minimal and auditable. Every threshold has a clear rationale.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any


# ── Secret patterns (from readiness_gates.py) ────────────────────────────────

SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_\-]?key|secret|token|password)\s*[:=]\s*['\"][^'\"]{8,}['\"]"),
    re.compile(r"sk-[A-Za-z0-9_\-]{20,}"),        # OpenAI key format
    re.compile(r"ghp_[A-Za-z0-9_]{20,}"),          # GitHub PAT
    re.compile(r"gsk_[A-Za-z0-9_]{20,}"),          # Groq key
    re.compile(r"AIza[A-Za-z0-9_\-]{35,}"),        # Google API key
]


# ── Core types (from execution_contract.py) ───────────────────────────────────

class QualityDecision(str, Enum):
    ALLOW  = "allow"    # score >= 0.70  → save + sync to GitHub
    REDUCE = "reduce"   # score 0.40-0.69 → save with quality flag
    DENY   = "deny"     # score <  0.40  → skip save entirely


@dataclass(frozen=True)
class GateFinding:
    gate:     str
    passed:   bool
    reason:   str
    evidence: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class QualityReport:
    score:    float            # 0.0 – 1.0
    decision: QualityDecision
    findings: list[GateFinding]
    summary:  str

    def to_dict(self) -> dict:
        return {
            "score":    round(self.score, 3),
            "decision": self.decision.value,
            "findings": [f.to_dict() for f in self.findings],
            "summary":  self.summary,
        }

    @property
    def allowed(self) -> bool:
        return self.decision != QualityDecision.DENY

    @property
    def should_sync(self) -> bool:
        return self.decision == QualityDecision.ALLOW


# ── DCA enhancement schedule (from Hummingbot DCAExecutor) ───────────────────
# Each skill has N enhancement levels, placed at increasing time intervals.
# Level 1 = initial extraction. Level 2 = 14-day re-run. Level 3 = 30-day deep merge.

DCA_LEVELS = [
    {"level": 1, "label": "Initial",      "days_to_next": 14},
    {"level": 2, "label": "2-week update", "days_to_next": 30},
    {"level": 3, "label": "Monthly merge", "days_to_next": 90},
    {"level": 4, "label": "Quarterly",     "days_to_next": None},  # terminal
]


def dca_schedule(current_level: int = 1, last_enhanced: str | None = None) -> dict:
    """Return the DCA enhancement schedule entry for a skill."""
    today = datetime.now(timezone.utc)
    last  = datetime.fromisoformat(last_enhanced) if last_enhanced else today
    level_cfg = next((l for l in DCA_LEVELS if l["level"] == current_level), DCA_LEVELS[0])
    days = level_cfg["days_to_next"]
    next_dt = (last + timedelta(days=days)).date().isoformat() if days else None
    due_today = (
        next_dt is not None and
        datetime.now(timezone.utc).date().isoformat() >= next_dt
    )
    return {
        "level":            current_level,
        "label":            level_cfg["label"],
        "last_enhanced":    last.date().isoformat(),
        "next_enhancement": next_dt,
        "due":              due_today,
    }


def advance_dca(schedule: dict) -> dict:
    """Move to the next enhancement level after a successful enhance pass."""
    next_level = min(schedule.get("level", 1) + 1, len(DCA_LEVELS))
    return dca_schedule(next_level, datetime.now(timezone.utc).isoformat())


def skills_due_for_enhancement(index: dict) -> list[str]:
    """Return skill names whose DCA schedule shows due=True."""
    due = []
    for name, meta in index.items():
        sched = meta.get("_dca", {})
        if sched.get("due", False):
            due.append(name)
    return due


# ── Individual gates ──────────────────────────────────────────────────────────

def _gate_secrets(markdown: str) -> GateFinding:
    for pat in SECRET_PATTERNS:
        m = pat.search(markdown)
        if m:
            snippet = m.group(0)[:40].replace("\n", " ")
            return GateFinding("secret_scan", False, "possible_credential_detected",
                               {"snippet": snippet + "…"})
    return GateFinding("secret_scan", True, "no_secrets_detected")


def _gate_title(skill: dict) -> GateFinding:
    title = (skill.get("title") or "").strip()
    if len(title) >= 5:
        return GateFinding("title", True, "title_present", {"length": len(title)})
    return GateFinding("title", False, "title_missing_or_too_short", {"title": title})


def _gate_description(skill: dict) -> GateFinding:
    desc = (skill.get("description") or "").strip()
    if len(desc) >= 20:
        return GateFinding("description", True, "description_present", {"length": len(desc)})
    return GateFinding("description", False, "description_too_short", {"length": len(desc)})


def _gate_steps(skill: dict) -> GateFinding:
    steps = skill.get("steps", [])
    n = len(steps)
    if n >= 3:
        return GateFinding("steps", True, "sufficient_steps", {"count": n})
    return GateFinding("steps", False, "too_few_steps", {"count": n, "minimum": 3})


def _gate_tools(skill: dict) -> GateFinding:
    tools = skill.get("tools", [])
    n = len(tools)
    if n >= 1:
        return GateFinding("tools", True, "tools_present", {"count": n})
    return GateFinding("tools", False, "no_tools_extracted", {"count": 0})


def _gate_markdown(skill: dict) -> GateFinding:
    md = (skill.get("skill_markdown") or "").strip()
    if len(md) >= 100:
        return GateFinding("markdown", True, "markdown_present", {"length": len(md)})
    return GateFinding("markdown", False, "markdown_too_short", {"length": len(md)})


def _gate_arena(skill: dict) -> GateFinding:
    arena = skill.get("_arena", {})
    if not arena:
        return GateFinding("arena", True, "no_arena_data_single_provider")
    sm = arena.get("steps_merged", 0)
    if sm >= 3:
        return GateFinding("arena", True, "arena_merge_acceptable",
                           {"steps_merged": sm})
    return GateFinding("arena", False, "arena_merge_too_thin",
                       {"steps_merged": sm, "minimum": 3})


# ── Master quality gate ───────────────────────────────────────────────────────

# Point weights — each gate contributes to the 0.0-1.0 confidence score.
# Total possible from positive gates = 1.0
_WEIGHTS: dict[str, float] = {
    "title":       0.10,
    "description": 0.20,
    "steps":       0.25,
    "tools":       0.15,
    "markdown":    0.15,
    "arena":       0.10,
    "secret_scan": 0.05,  # small base — secrets cause a hard deduction
}
_SECRET_PENALTY = 0.40   # applied on top of weight loss if secrets found


def quality_gate(skill: dict) -> QualityReport:
    """Run all gates and return a QualityReport with ALLOW/REDUCE/DENY decision."""
    markdown = skill.get("skill_markdown") or ""
    findings: list[GateFinding] = []

    gate_results: dict[str, GateFinding] = {
        "secret_scan": _gate_secrets(markdown),
        "title":       _gate_title(skill),
        "description": _gate_description(skill),
        "steps":       _gate_steps(skill),
        "tools":       _gate_tools(skill),
        "markdown":    _gate_markdown(skill),
        "arena":       _gate_arena(skill),
    }
    findings = list(gate_results.values())

    # Score
    score = 0.0
    for gate_name, weight in _WEIGHTS.items():
        if gate_results[gate_name].passed:
            score += weight

    # Hard penalty for secrets — subtract extra even if the gate "passed" weight wasn't earned
    if not gate_results["secret_scan"].passed:
        score = max(0.0, score - _SECRET_PENALTY)

    score = round(min(score, 1.0), 3)

    # Decision  (from execution_contract DecisionAction)
    if score >= 0.70:
        decision = QualityDecision.ALLOW
    elif score >= 0.40:
        decision = QualityDecision.REDUCE
    else:
        decision = QualityDecision.DENY

    failed_gates = [f.gate for f in findings if not f.passed]
    summary = (
        f"Score {score:.2f} → {decision.value.upper()}"
        + (f" | Issues: {', '.join(failed_gates)}" if failed_gates else " | All gates passed")
    )

    return QualityReport(score=score, decision=decision, findings=findings, summary=summary)
