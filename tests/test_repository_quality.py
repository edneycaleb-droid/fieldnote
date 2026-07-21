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
                "permissions:\n  contents: read\n"
                "timeout-minutes: 5\n"
                "persist-credentials: false\n"
                "dependency-smoke:\n"
                "if: github.event_name == 'pull_request'\n"
                'python-version: "3.11"\n'
                "poetry==1.8.5\n"
                "poetry install --no-interaction --no-ansi --no-root\n"
            ),
            "scripts/check_repository_quality.py": "# fixture\n",
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


if __name__ == "__main__":
    unittest.main()
