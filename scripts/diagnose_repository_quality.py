#!/usr/bin/env python3
"""Produce detailed offline diagnostics for Fieldnote's published quality gate."""
from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FULL_COMMIT_SHA = re.compile(r"[0-9a-fA-F]{40}")


def load_quality_module():
    path = ROOT / "scripts" / "check_repository_quality.py"
    spec = importlib.util.spec_from_file_location("fieldnote_repository_quality", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def placeholder_skills() -> list[str]:
    results = []
    for path in sorted((ROOT / "skills").glob("*.md")):
        try:
            text = path.read_text(encoding="utf-8").strip()
        except OSError:
            results.append(f"{path.relative_to(ROOT)}:unreadable")
            continue
        if text in {"fieldnote_skills", "skills"}:
            results.append(str(path.relative_to(ROOT)))
    return results


def mcp_test_fixtures() -> list[dict]:
    path = ROOT / "fieldnote_mcp" / "mcp_hub_registry.json"
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [{"error": "registry_unreadable"}]
    fixtures = []
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict):
            fixtures.append({"error": "non_object_entry"})
            continue
        if (
            entry.get("package_name") == "test-mcp-server"
            or entry.get("repo_url") == "https://github.com/test/test-server"
            or entry.get("id") in {"test-server", "hc-stuck-verifier-server", "hc-after-stuck-server"}
        ):
            fixtures.append({"id": entry.get("id"), "package_name": entry.get("package_name"), "repo_url": entry.get("repo_url")})
    return fixtures


def mutable_workflow_actions() -> list[dict]:
    workflow_files = list(ROOT.glob(".github/workflows/*.yml"))
    workflow_files += list(ROOT.glob(".github/workflows/*.yaml"))
    workflow_files += list(ROOT.glob("tools/**/.github/workflows/*.yml"))
    workflow_files += list(ROOT.glob("tools/**/.github/workflows/*.yaml"))
    results = []
    for path in sorted(set(workflow_files)):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            stripped = line.strip()
            if not stripped.startswith("- uses:"):
                continue
            target = stripped.removeprefix("- uses:").split("#", 1)[0].strip()
            if target.startswith("./"):
                continue
            _, separator, ref = target.rpartition("@")
            if not separator or not FULL_COMMIT_SHA.fullmatch(ref):
                results.append({"path": str(path.relative_to(ROOT)), "line": number, "target": target})
    return results


def main() -> int:
    quality = load_quality_module()
    details = {
        "placeholder_skills": placeholder_skills(),
        "mcp_test_fixtures": mcp_test_fixtures(),
        "mutable_workflow_actions": mutable_workflow_actions(),
        "function_results": {
            "generated_skill_library_valid": quality.generated_skill_library_valid(),
            "generated_mcp_registry_valid": quality.generated_mcp_registry_valid(),
            "workflow_actions_pinned": quality.workflow_actions_pinned(),
        },
    }
    print(json.dumps(details, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
