"""Focused regression tests for generated-skill synchronization."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agents import github_sync


class GitHubSkillSyncTests(unittest.TestCase):
    def test_placeholder_payload_is_rejected_before_mirror_access(self) -> None:
        with mock.patch.object(github_sync, "_token", side_effect=AssertionError("token read")), \
             mock.patch.object(github_sync, "_ensure_mirror", side_effect=AssertionError("mirror access")):
            self.assertFalse(github_sync.sync_skill("example", "fieldnote_skills", {}))

    def test_rendered_skill_is_written_to_the_mirror(self) -> None:
        markdown = "# Example\n\nSubstantive, source-backed guidance.\n"
        with tempfile.TemporaryDirectory() as tempdir, \
             mock.patch.object(github_sync, "MIRROR_DIR", Path(tempdir)), \
             mock.patch.object(github_sync, "_token", return_value="test-token"), \
             mock.patch.object(github_sync, "_ensure_mirror", return_value=True), \
             mock.patch.object(github_sync, "_build_readme", return_value="# Fieldnote\n"), \
             mock.patch.object(github_sync, "_commit_and_push", return_value=True):
            self.assertTrue(github_sync.sync_skill("example", markdown, {}))
            saved = Path(tempdir, "skills", "example.md").read_text(encoding="utf-8")
            self.assertEqual(markdown, saved)

    def test_discovery_paths_do_not_resync_the_directory_name(self) -> None:
        root = Path(__file__).resolve().parents[1]
        expected_rendered_syncs = {
            "agents/github_discovery.py": 2,
            "agents/discovery_enrichment.py": 1,
        }
        for relative, minimum_count in expected_rendered_syncs.items():
            source = (root / relative).read_text(encoding="utf-8")
            self.assertNotIn("sync_skill(skill_name, _a.SKILLS_DIR", source)
            self.assertGreaterEqual(
                source.count("sync_skill(skill_name, _a._read_existing_markdown(skill_name)"),
                minimum_count,
            )


if __name__ == "__main__":
    unittest.main()
