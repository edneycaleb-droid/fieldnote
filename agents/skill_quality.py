"""Fieldnote skill quality, provenance, freshness, and quarantine gates.

The public ``quality_gate(skill)`` API remains compatible with the existing pipeline,
but the report now measures whether a skill is attributable, actionable, current enough,
non-duplicative, and safe to publish—not only whether it contains enough text.

The module is deliberately stdlib-only. It never installs, imports, or executes code
mentioned by a skill. Markdown and upstream instructions are always treated as data.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse


SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_\-]?key|secret|token|password)\s*[:=]\s*['\"][^'\"]{8,}['\"]"),
    re.compile(r"sk-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"ghp_[A-Za-z0-9_]{20,}"),
    re.compile(r"gsk_[A-Za-z0-9_]{20,}"),
    re.compile(r"AIza[A-Za-z0-9_\-]{35,}"),
]

CRITICAL_INSTRUCTION_PATTERNS = [
    ("remote_pipe_shell", re.compile(r"(?is)(curl|wget)[^\n|]{0,240}\|\s*(sh|bash|zsh|powershell)")),
    ("credential_material", re.compile(r"(?i)\b(seed phrase|wallet private key|withdrawal-enabled key)\b")),
]

HIGH_RISK_INSTRUCTION_PATTERNS = [
    ("permissionless_autonomy", re.compile(r"(?i)\b(do not ask (?:the user for )?permission|never stop|assume the human is asleep)\b")),
    ("anti_detection", re.compile(r"(?i)\b(captcha bypass|fingerprint spoof(?:ing)?|anti-detection browsing|proxy rotation to evade)\b")),
    ("live_financial_action", re.compile(r"(?i)\b(place live orders?|connect (?:a )?wallet|copy trad(?:e|ing)|enable withdrawals?)\b")),
    ("security_bypass", re.compile(r"(?i)\b(disable (?:the )?(?:firewall|antivirus)|bypass access controls?)\b")),
    ("silent_mutation", re.compile(r"(?i)\b(silently (?:rewrite|modify|evolve)|auto-promote(?:s|d)?)\b")),
]

URL_PATTERN = re.compile(r"https://[^\s)>\]]+")
DATE_PATTERN = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")
GENERIC_STEP_PATTERNS = [
    re.compile(r"(?i)^watch the (?:full )?video"),
    re.compile(r"(?i)^follow the tutorial"),
    re.compile(r"(?i)^learn more at"),
    re.compile(r"(?i)^see (?:the )?(?:source|documentation|readme)"),
]


class QualityDecision(str, Enum):
    ALLOW = "allow"
    REDUCE = "reduce"
    DENY = "deny"


@dataclass(frozen=True)
class GateFinding:
    gate: str
    passed: bool
    reason: str
    evidence: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class QualityReport:
    score: float
    decision: QualityDecision
    findings: list[GateFinding]
    summary: str
    fingerprint: str = ""
    capability_dna: dict[str, Any] = field(default_factory=dict)
    risk_level: str = "low"
    freshness: str = "unknown"

    def to_dict(self) -> dict:
        return {
            "score": round(self.score, 3),
            "decision": self.decision.value,
            "findings": [finding.to_dict() for finding in self.findings],
            "summary": self.summary,
            "fingerprint": self.fingerprint,
            "capability_dna": self.capability_dna,
            "risk_level": self.risk_level,
            "freshness": self.freshness,
        }

    @property
    def allowed(self) -> bool:
        return self.decision != QualityDecision.DENY

    @property
    def should_sync(self) -> bool:
        return self.decision == QualityDecision.ALLOW


DCA_LEVELS = [
    {"level": 1, "label": "Initial", "days_to_next": 14},
    {"level": 2, "label": "2-week update", "days_to_next": 30},
    {"level": 3, "label": "Monthly merge", "days_to_next": 90},
    {"level": 4, "label": "Quarterly", "days_to_next": None},
]


def dca_schedule(current_level: int = 1, last_enhanced: str | None = None) -> dict:
    today = datetime.now(timezone.utc)
    try:
        last = datetime.fromisoformat(last_enhanced.replace("Z", "+00:00")) if last_enhanced else today
    except (AttributeError, ValueError):
        last = today
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    level_cfg = next((item for item in DCA_LEVELS if item["level"] == current_level), DCA_LEVELS[0])
    days = level_cfg["days_to_next"]
    next_dt = (last + timedelta(days=days)).date().isoformat() if days else None
    return {
        "level": current_level,
        "label": level_cfg["label"],
        "last_enhanced": last.date().isoformat(),
        "next_enhancement": next_dt,
        "due": next_dt is not None and today.date().isoformat() >= next_dt,
    }


def advance_dca(schedule: dict) -> dict:
    next_level = min(int(schedule.get("level", 1)) + 1, len(DCA_LEVELS))
    return dca_schedule(next_level, datetime.now(timezone.utc).isoformat())


def skills_due_for_enhancement(index: dict) -> list[str]:
    return [name for name, meta in index.items() if meta.get("_dca", {}).get("due", False)]


def normalize_markdown(markdown: str) -> str:
    """Normalize content for duplicate detection without erasing meaningful steps."""
    text = re.sub(r"(?is)\n##\s+sources?\b.*$", "", markdown)
    text = URL_PATTERN.sub("<URL>", text)
    text = DATE_PATTERN.sub("<DATE>", text)
    text = re.sub(r"(?m)^>\s*⚠️.*$", "", text)
    text = re.sub(r"\s+", " ", text).strip().lower()
    return text


def skill_fingerprint(markdown: str) -> str:
    return hashlib.sha256(normalize_markdown(markdown).encode("utf-8")).hexdigest()


def _headings(markdown: str) -> list[str]:
    return [match.group(1).strip().lower() for match in re.finditer(r"(?m)^#{1,3}\s+(.+?)\s*$", markdown)]


def capability_dna(skill: dict) -> dict[str, Any]:
    markdown = str(skill.get("skill_markdown") or "")
    tools = sorted({str(item).strip().lower() for item in skill.get("tools", []) if str(item).strip()})
    tags = sorted({str(item).strip().lower() for item in skill.get("tags", []) if str(item).strip()})
    concepts = sorted({str(item).strip().lower() for item in skill.get("concepts", []) if str(item).strip()})
    payload = {
        "tools": tools,
        "tags": tags,
        "concepts": concepts,
        "headings": _headings(markdown),
        "has_steps": bool(skill.get("steps")),
        "has_sources": bool(_source_urls(markdown)),
    }
    payload["hash"] = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
    return payload


def _source_urls(markdown: str) -> list[str]:
    urls = []
    for url in URL_PATTERN.findall(markdown):
        cleaned = url.rstrip(".,;:")
        parsed = urlparse(cleaned)
        if parsed.scheme == "https" and parsed.netloc:
            urls.append(cleaned)
    return sorted(set(urls))


def _source_dates(markdown: str) -> list[datetime]:
    dates = []
    for value in DATE_PATTERN.findall(markdown):
        try:
            dates.append(datetime.fromisoformat(value).replace(tzinfo=timezone.utc))
        except ValueError:
            continue
    return dates


def _freshness_window_days(skill: dict, markdown: str) -> int:
    haystack = " ".join(
        [
            str(skill.get("title") or ""),
            str(skill.get("description") or ""),
            " ".join(map(str, skill.get("tags", []))),
            markdown[:4000],
        ]
    ).lower()
    if any(token in haystack for token in ("latest", "current price", "pricing", "api version", "breaking news", "market data")):
        return 30
    if any(token in haystack for token in ("framework", "library", "model", "mcp", "agent", "deployment", "trading")):
        return 180
    return 365


def _gate_secrets(markdown: str) -> GateFinding:
    for pattern in SECRET_PATTERNS:
        match = pattern.search(markdown)
        if match:
            snippet = match.group(0)[:40].replace("\n", " ")
            return GateFinding("secret_scan", False, "possible_credential_detected", {"snippet": snippet + "…"})
    return GateFinding("secret_scan", True, "no_secrets_detected")


def _gate_title(skill: dict) -> GateFinding:
    title = str(skill.get("title") or "").strip()
    return GateFinding("title", len(title) >= 5, "title_present" if len(title) >= 5 else "title_missing_or_too_short", {"length": len(title)})


def _gate_description(skill: dict) -> GateFinding:
    description = str(skill.get("description") or "").strip()
    passed = len(description) >= 20
    return GateFinding("description", passed, "description_present" if passed else "description_too_short", {"length": len(description)})


def _gate_steps(skill: dict) -> GateFinding:
    steps = [str(item).strip() for item in skill.get("steps", []) if str(item).strip()]
    passed = len(steps) >= 3
    return GateFinding("steps", passed, "sufficient_steps" if passed else "too_few_steps", {"count": len(steps), "minimum": 3})


def _gate_actionable(skill: dict, markdown: str) -> GateFinding:
    steps = [str(item).strip() for item in skill.get("steps", []) if str(item).strip()]
    if not steps:
        section = re.search(r"(?is)##\s+steps\s*(.+?)(?:\n##|\Z)", markdown)
        if section:
            steps = [re.sub(r"^[\-*\d.()\s]+", "", line).strip() for line in section.group(1).splitlines() if line.strip()]
    generic = [step for step in steps if any(pattern.search(step) for pattern in GENERIC_STEP_PATTERNS)]
    concrete = [step for step in steps if len(step.split()) >= 4 and step not in generic]
    passed = len(concrete) >= 2
    return GateFinding("actionable", passed, "concrete_instructions_present" if passed else "instructions_are_generic_or_missing", {"concrete": len(concrete), "generic": len(generic)})


def _gate_tools(skill: dict) -> GateFinding:
    count = len([item for item in skill.get("tools", []) if str(item).strip()])
    return GateFinding("tools", count >= 1, "tools_present" if count else "no_tools_extracted", {"count": count})


def _gate_markdown(skill: dict) -> GateFinding:
    markdown = str(skill.get("skill_markdown") or "").strip()
    passed = len(markdown) >= 160
    return GateFinding("markdown", passed, "markdown_present" if passed else "markdown_too_short", {"length": len(markdown)})


def _gate_arena(skill: dict) -> GateFinding:
    arena = skill.get("_arena", {})
    if not arena:
        return GateFinding("arena", True, "no_arena_data_single_provider")
    merged = int(arena.get("steps_merged", 0))
    return GateFinding("arena", merged >= 3, "arena_merge_acceptable" if merged >= 3 else "arena_merge_too_thin", {"steps_merged": merged, "minimum": 3})


def _gate_provenance(markdown: str) -> GateFinding:
    urls = _source_urls(markdown)
    has_source_heading = bool(re.search(r"(?im)^##\s+sources?\b", markdown))
    passed = has_source_heading and bool(urls)
    domains = sorted({urlparse(url).netloc.lower() for url in urls})
    return GateFinding("provenance", passed, "source_chain_present" if passed else "source_heading_or_url_missing", {"urls": len(urls), "domains": domains})


def _gate_draft(markdown: str, skill: dict) -> GateFinding:
    draft = bool(skill.get("_baseline") or skill.get("_degraded") or skill.get("_pending_enhancement")) or bool(
        re.search(r"(?i)auto-extracted draft|pending ai enhancement|baseline-only", markdown)
    )
    return GateFinding("draft_status", not draft, "enhanced_skill" if not draft else "draft_or_degraded_skill")


def _gate_freshness(skill: dict, markdown: str, now: datetime) -> GateFinding:
    dates = _source_dates(markdown)
    if not dates:
        return GateFinding("freshness", False, "source_date_missing", {"status": "unknown"})
    newest = max(dates)
    age_days = max(0, (now - newest).days)
    window = _freshness_window_days(skill, markdown)
    if age_days <= window:
        status = "current" if age_days <= window / 2 else "decaying"
        return GateFinding("freshness", True, f"evidence_{status}", {"status": status, "age_days": age_days, "half_life_days": window})
    return GateFinding("freshness", False, "evidence_stale", {"status": "stale", "age_days": age_days, "half_life_days": window})


def _gate_safety(markdown: str) -> GateFinding:
    critical = []
    high = []
    for name, pattern in CRITICAL_INSTRUCTION_PATTERNS:
        if pattern.search(markdown):
            critical.append(name)
    for name, pattern in HIGH_RISK_INSTRUCTION_PATTERNS:
        if pattern.search(markdown):
            high.append(name)
    passed = not critical and not high
    reason = "no_unsafe_instruction_patterns" if passed else "unsafe_instruction_patterns_require_quarantine"
    return GateFinding("unsafe_capabilities", passed, reason, {"critical": critical, "high": high})


def _gate_duplicate(markdown: str, known_fingerprints: Iterable[str] | None) -> GateFinding:
    fingerprint = skill_fingerprint(markdown)
    duplicate = fingerprint in set(known_fingerprints or [])
    return GateFinding("duplicate", not duplicate, "unique_content_fingerprint" if not duplicate else "duplicate_content_fingerprint", {"fingerprint": fingerprint})


_WEIGHTS: dict[str, float] = {
    "title": 0.06,
    "description": 0.09,
    "steps": 0.10,
    "actionable": 0.14,
    "tools": 0.06,
    "markdown": 0.06,
    "arena": 0.04,
    "provenance": 0.16,
    "draft_status": 0.08,
    "freshness": 0.08,
    "unsafe_capabilities": 0.08,
    "duplicate": 0.03,
    "secret_scan": 0.02,
}


def quality_gate(
    skill: dict,
    known_fingerprints: Iterable[str] | None = None,
    *,
    now: datetime | None = None,
) -> QualityReport:
    """Run all gates and return an ALLOW/REDUCE/DENY quality report.

    ``REDUCE`` is the quarantine-compatible state: save locally with quality findings,
    but do not sync or promote it as a trusted skill. ``DENY`` is reserved for secrets
    or critical executable/credential patterns.
    """

    markdown = str(skill.get("skill_markdown") or "")
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)

    gate_results = {
        "secret_scan": _gate_secrets(markdown),
        "title": _gate_title(skill),
        "description": _gate_description(skill),
        "steps": _gate_steps(skill),
        "actionable": _gate_actionable(skill, markdown),
        "tools": _gate_tools(skill),
        "markdown": _gate_markdown(skill),
        "arena": _gate_arena(skill),
        "provenance": _gate_provenance(markdown),
        "draft_status": _gate_draft(markdown, skill),
        "freshness": _gate_freshness(skill, markdown, current),
        "unsafe_capabilities": _gate_safety(markdown),
        "duplicate": _gate_duplicate(markdown, known_fingerprints),
    }
    findings = list(gate_results.values())
    score = round(sum(weight for name, weight in _WEIGHTS.items() if gate_results[name].passed), 3)

    safety_evidence = gate_results["unsafe_capabilities"].evidence
    critical = list(safety_evidence.get("critical", []))
    high = list(safety_evidence.get("high", []))
    has_secret = not gate_results["secret_scan"].passed

    if has_secret or critical:
        decision = QualityDecision.DENY
    elif high or not gate_results["draft_status"].passed or not gate_results["duplicate"].passed:
        decision = QualityDecision.REDUCE
    elif score >= 0.75 and gate_results["provenance"].passed and gate_results["actionable"].passed:
        decision = QualityDecision.ALLOW
    elif score >= 0.45:
        decision = QualityDecision.REDUCE
    else:
        decision = QualityDecision.DENY

    failed = [finding.gate for finding in findings if not finding.passed]
    risk_level = "critical" if has_secret or critical else "high" if high else "medium" if failed else "low"
    freshness = str(gate_results["freshness"].evidence.get("status", "unknown"))
    summary = f"Score {score:.2f} → {decision.value.upper()}"
    if failed:
        summary += " | Issues: " + ", ".join(failed)

    return QualityReport(
        score=score,
        decision=decision,
        findings=findings,
        summary=summary,
        fingerprint=skill_fingerprint(markdown),
        capability_dna=capability_dna(skill),
        risk_level=risk_level,
        freshness=freshness,
    )


def markdown_to_skill(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    markdown = path.read_text(encoding="utf-8")
    title_match = re.search(r"(?m)^#\s+(.+?)\s*$", markdown)
    description = ""
    for line in markdown.splitlines()[1:]:
        cleaned = line.strip().lstrip(">").strip()
        if cleaned and not cleaned.startswith("#") and not cleaned.startswith("⚠️"):
            description = cleaned
            break
    steps_match = re.search(r"(?is)##\s+steps\s*(.+?)(?:\n##|\Z)", markdown)
    steps = []
    if steps_match:
        steps = [re.sub(r"^[\-*\d.()\s]+", "", line).strip() for line in steps_match.group(1).splitlines() if line.strip()]
    tools_match = re.search(r"(?is)##\s+tools(?:\s*&\s*technologies)?\s*(.+?)(?:\n##|\Z)", markdown)
    tools = []
    if tools_match:
        tools = [item.strip(" `") for item in re.split(r"[,\n]", tools_match.group(1)) if item.strip(" `")]
    return {
        "title": title_match.group(1).strip() if title_match else path.stem.replace("_", " ").title(),
        "description": description,
        "steps": steps,
        "tools": tools,
        "skill_markdown": markdown,
        "_baseline": "auto-extracted draft" in markdown.lower(),
    }


def audit_skill_directory(directory: str | Path) -> dict[str, Any]:
    directory = Path(directory)
    records = []
    fingerprints: set[str] = set()
    for path in sorted(directory.glob("*.md")):
        skill = markdown_to_skill(path)
        report = quality_gate(skill, fingerprints)
        fingerprints.add(report.fingerprint)
        records.append({"path": str(path), **report.to_dict()})
    counts = {decision.value: sum(record["decision"] == decision.value for record in records) for decision in QualityDecision}
    return {"skills": records, "counts": counts, "total": len(records)}
