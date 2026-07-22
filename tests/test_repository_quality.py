"""Focused tests for the published ten-control repository quality rubric."""

from __future__ import annotations

import importlib.util
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "check_repository_quality.py"
SPEC = importlib.util.spec_from_file_location("check_repository_quality", MODULE_PATH)
assert SPEC and SPEC.loader
quality = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(quality)


class RepositoryQualityRubricTests(unittest.TestCase):
    def make_root(self) -> Path:
        root = Path(self.tempdir.name)
        files = {
            "README.md": "Fieldnote\n",
            "STATUS.md": "Known limitations\n",
            "CONTRIBUTING.md": "Generated files\ndeterministic offline gate\n",
            "SECURITY.md": "private vulnerability\nTrust boundaries\n",
            ".github/CODEOWNERS": "* @edneycaleb-droid\n/agents/ @edneycaleb-droid\n",
            ".github/ISSUE_TEMPLATE/bug_report.yml": "validations:\n  required: true\n",
            ".github/ISSUE_TEMPLATE/feature_request.yml": "Acceptance criteria\n",
            ".github/ISSUE_TEMPLATE/config.yml": (
                "blank_issues_enabled: false\n"
                "url: https://github.com/example/project/security/advisories/new\n"
            ),
            ".github/pull_request_template.md": "Trust and cost boundaries\nRollback\n",
            ".github/dependabot.yml": (
                "package-ecosystem: pip\n"
                "package-ecosystem: github-actions\n"
            ),
            ".github/workflows/repository-quality.yml": (
                "workflow_dispatch:\n"
                '      - "README.md"\n'
                '      - "skills/**"\n'
                '      - "_brain.json"\n'
                "permissions:\n  contents: read\n"
                "timeout-minutes: 5\n"
                "persist-credentials: false\n"
                "dependency-smoke:\n"
                "if: github.event_name == 'pull_request'\n"
                'python-version: "3.11"\n'
                "poetry==1.8.5\n"
                "poetry install --no-interaction --no-ansi --no-root\n"
                "      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1\n"
            ),
            ".github/workflows/example.yml": (
                "permissions:\n  contents: read\n"
                "jobs:\n  validate:\n    timeout-minutes: 5\n    steps:\n"
                "      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1\n"
            ),
            "scripts/check_repository_quality.py": "# fixture\n",
            "fieldnote_mcp/mcp_hub_registry.json": '[{"id": "real-server", "package_name": "real", "repo_url": "https://github.com/example/real"}]\n',
            "skills/example.md": "# Example skill\n\n" + ("Deterministic, source-backed skill content. " * 3) + "\n",
            "pyproject.toml": "[project]\nname = \"fieldnote\"\nversion = \"0.0.0\"\n",
        }
        for relative, text in files.items():
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        return root

    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = self.make_root()

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def run_quality(self) -> tuple[int, str]:
        output = io.StringIO()
        with mock.patch.object(quality, "ROOT", self.root), redirect_stdout(output):
            result = quality.main()
        return result, output.getvalue()

    def test_exact_published_rubric_passes_at_ten_of_ten(self) -> None:
        result, output = self.run_quality()
        self.assertEqual(0, result)
        self.assertIn("[PASS] clean_tracking", output)
        self.assertIn("REPOSITORY_QUALITY_SCORE=10/10", output)

    def test_missing_clean_tracking_cannot_receive_full_credit(self) -> None:
        (self.root / ".github/ISSUE_TEMPLATE/config.yml").unlink()
        result, output = self.run_quality()
        self.assertEqual(1, result)
        self.assertIn("[FAIL] clean_tracking", output)
        self.assertIn("REPOSITORY_QUALITY_SCORE=9/10", output)

    def test_missing_dependency_resolution_cannot_receive_full_credit(self) -> None:
        workflow = self.root / ".github/workflows/repository-quality.yml"
        workflow.write_text(
            workflow.read_text(encoding="utf-8").replace(
                "poetry install --no-interaction --no-ansi --no-root\n", ""
            ),
            encoding="utf-8",
        )
        result, output = self.run_quality()
        self.assertEqual(1, result)
        self.assertIn("[FAIL] dependency_policy", output)
        self.assertIn("REPOSITORY_QUALITY_SCORE=9/10", output)

    def test_generated_content_must_trigger_validation(self) -> None:
        workflow = self.root / ".github/workflows/repository-quality.yml"
        workflow.write_text(
            workflow.read_text(encoding="utf-8").replace('      - "skills/**"\n', ""),
            encoding="utf-8",
        )
        result, output = self.run_quality()
        self.assertEqual(1, result)
        self.assertIn("[FAIL] safe_workflow", output)
        self.assertIn("REPOSITORY_QUALITY_SCORE=9/10", output)

    def test_truncated_generated_skill_cannot_receive_full_credit(self) -> None:
        (self.root / "skills/example.md").write_text("fieldnote_skills\n", encoding="utf-8")
        result, output = self.run_quality()
        self.assertEqual(1, result)
        self.assertIn("[FAIL] deterministic_fallback", output)
        self.assertIn("REPOSITORY_QUALITY_SCORE=9/10", output)

    def test_committed_mcp_test_fixture_cannot_receive_full_credit(self) -> None:
        registry = self.root / "fieldnote_mcp/mcp_hub_registry.json"
        registry.write_text(
            '[{"id": "hc-stuck-verifier-server", "package_name": "test-mcp-server", '
            '"repo_url": "https://github.com/test/test-server"}]\n',
            encoding="utf-8",
        )
        result, output = self.run_quality()
        self.assertEqual(1, result)
        self.assertIn("[FAIL] generated_mcp_test_fixture", output)
        self.assertIn("[FAIL] deterministic_fallback", output)
        self.assertIn("REPOSITORY_QUALITY_SCORE=9/10", output)

    def test_mutable_workflow_action_cannot_receive_full_credit(self) -> None:
        workflow = self.root / ".github/workflows/example.yml"
        workflow.write_text(
            workflow.read_text(encoding="utf-8").replace(
                "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
                "actions/checkout@v4",
            ),
            encoding="utf-8",
        )
        result, output = self.run_quality()
        self.assertEqual(1, result)
        self.assertIn("[FAIL] mutable_workflow_action", output)
        self.assertIn("[FAIL] safe_workflow", output)
        self.assertIn("REPOSITORY_QUALITY_SCORE=9/10", output)


if __name__ == "__main__":
    unittest.main()
