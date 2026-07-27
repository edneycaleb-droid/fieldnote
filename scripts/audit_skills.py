#!/usr/bin/env python3
"""Audit Fieldnote Markdown skills without network access or upstream execution."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agents.skill_quality import audit_skill_directory


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", nargs="?", default=str(ROOT / "skills"))
    parser.add_argument("--output", default=str(ROOT / "artifacts" / "skill-quality-report.json"))
    parser.add_argument(
        "--fail-on",
        choices=("none", "deny", "critical"),
        default="critical",
        help="Exit nonzero for any denied skill, only critical-risk denied skills, or never.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = audit_skill_directory(args.directory)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"FIELDNOTE_SKILLS_TOTAL={report['total']}")
    for decision, count in sorted(report["counts"].items()):
        print(f"FIELDNOTE_SKILLS_{decision.upper()}={count}")
    print(f"FIELDNOTE_SKILL_REPORT={output}")

    if args.fail_on == "none":
        return 0
    denied = [record for record in report["skills"] if record["decision"] == "deny"]
    if args.fail_on == "deny":
        return 1 if denied else 0
    critical = [record for record in denied if record.get("risk_level") == "critical"]
    return 1 if critical else 0


if __name__ == "__main__":
    raise SystemExit(main())
