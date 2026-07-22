#!/usr/bin/env python3
"""Offline structural quality gate for Fieldnote; executes no project code."""

from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    target = (ROOT / path).resolve()
    if ROOT not in target.parents:
        raise ValueError(f"path escapes repository: {path}")
    return target.read_text(encoding="utf-8")


def has(path: str, *needles: str) -> bool:
    try:
        text = read(path)
    except OSError:
        return False
    return all(needle in text for needle in needles)


def generated_skill_library_valid() -> bool:
    """Reject truncated generated skills without importing or executing project code."""
    skills_dir = ROOT / "skills"
    try:
        skill_files = list(skills_dir.glob("*.md"))
    except OSError:
        return False
    if not skill_files:
        return False
    for skill_file in skill_files:
        try:
            markdown = skill_file.read_text(encoding="utf-8").strip()
        except OSError:
            return False
        if markdown in {"fieldnote_skills", "skills"}:
            print(f"[FAIL] generated_skill_placeholder: {skill_file.relative_to(ROOT)}")
            return False
    return True


def generated_mcp_registry_valid() -> bool:
    """Reject committed test fixtures without importing or executing project code."""
    try:
        entries = json.loads(read("fieldnote_mcp/mcp_hub_registry.json"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(entries, list) or not entries:
        return False
    for entry in entries:
        if not isinstance(entry, dict):
            return False
        if (
            entry.get("package_name") == "test-mcp-server"
            or entry.get("repo_url") == "https://github.com/test/test-server"
            or entry.get("id") in {"test-server", "hc-stuck-verifier-server", "hc-after-stuck-server"}
        ):
            print(f"[FAIL] generated_mcp_test_fixture: {entry.get('id', '<missing-id>')}")
            return False
    return True


def main() -> int:
    try:
        tomllib.loads(read("pyproject.toml"))
    except (OSError, tomllib.TOMLDecodeError):
        pyproject_valid = False
    else:
        pyproject_valid = True

    checks = {
        "readme_status": has("README.md", "Fieldnote") and has("STATUS.md", "Known limitations"),
        "contributing": has("CONTRIBUTING.md", "Generated files", "deterministic offline gate"),
        "security": has("SECURITY.md", "private vulnerability", "Trust boundaries"),
        "codeowners": has(".github/CODEOWNERS", "* @edneycaleb-droid", "/agents/"),
        "issue_forms": has(".github/ISSUE_TEMPLATE/bug_report.yml", "validations:", "required: true")
        and has(".github/ISSUE_TEMPLATE/feature_request.yml", "Acceptance criteria"),
        "pull_request_template": has(".github/pull_request_template.md", "Trust and cost boundaries", "Rollback"),
        "dependency_policy": pyproject_valid
        and has(".github/dependabot.yml", "package-ecosystem: pip", "package-ecosystem: github-actions")
        and has(
            ".github/workflows/repository-quality.yml",
            "dependency-smoke:",
            "if: github.event_name == 'pull_request'",
            'python-version: "3.11"',
            "poetry==1.8.5",
            "poetry install --no-interaction --no-ansi --no-root",
        ),
        "deterministic_fallback": (ROOT / "scripts/check_repository_quality.py").is_file()
        and generated_skill_library_valid()
        and generated_mcp_registry_valid(),
        "safe_workflow": has(
            ".github/workflows/repository-quality.yml",
            "permissions:\n  contents: read",
            '- "README.md"',
            '- "skills/**"',
            '- "_brain.json"',
            "timeout-minutes: 5",
            "persist-credentials: false",
            "workflow_dispatch:",
        ),
        "clean_tracking": has(
            ".github/ISSUE_TEMPLATE/config.yml",
            "blank_issues_enabled: false",
            "security/advisories/new",
        ),
    }

    for name, passed in checks.items():
        print(f"[{'PASS' if passed else 'FAIL'}] {name}")
    passed = sum(checks.values())
    print(f"REPOSITORY_QUALITY_SCORE={passed}/{len(checks)}")
    print(f"REPOSITORY_STRUCTURE_SCORE={passed}/{len(checks)}")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
