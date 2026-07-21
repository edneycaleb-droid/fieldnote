"""Deterministic tests for fail-closed ecosystem candidate handling."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agents import supply_chain_policy as policy


class SupplyChainPolicyTests(unittest.TestCase):
    def good_candidate(self) -> dict:
        return {
            "kind": "mcp",
            "repo": "example/read-only-mcp",
            "source_commit": "a" * 40,
            "source_digest": "b" * 64,
            "license_spdx": "MIT",
            "package": "read-only-mcp==1.2.3",
            "install_method": "pip",
            "artifact_sha256": "c" * 64,
            "credential_env": "EXAMPLE_READ_TOKEN",
            "write_capable": False,
        }

    def test_complete_read_only_candidate_is_structurally_validated_not_activated(self) -> None:
        result = policy.evaluate(self.good_candidate())
        self.assertEqual("structurally_validated", result["state"])
        self.assertEqual([], result["gaps"])
        self.assertFalse(result["activation_authority"])
        self.assertFalse(result["host_execution"])
        self.assertFalse(result["credentials_accessed"])

    def test_untrusted_or_mutable_candidate_fails_closed(self) -> None:
        candidate = self.good_candidate()
        candidate.update({
            "source_commit": "main",
            "license_spdx": "UNKNOWN",
            "package": "read-only-mcp",
            "artifact_sha256": "",
            "write_capable": True,
        })
        result = policy.evaluate(candidate)
        self.assertEqual("quarantined", result["state"])
        self.assertEqual(
            ["approved_license", "artifact_digest", "exact_package_version",
             "immutable_source_commit", "read_only_capability"],
            result["gaps"],
        )

    def test_queue_is_atomic_private_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "queue.json"
            first = policy.quarantine([self.good_candidate()], path=path)[0]
            second = policy.quarantine([self.good_candidate()], path=path)[0]
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(first["candidate_id"], second["candidate_id"])
            self.assertEqual(1, len(payload["candidates"]))
            self.assertEqual(0o600, path.stat().st_mode & 0o777)

    def test_discovery_helpers_do_not_execute_subprocesses(self) -> None:
        item = {
            "full_name": "example/tool",
            "repo_name": "tool",
            "is_mcp": True,
            "url": "https://github.com/example/tool",
            "npm_package": "example-tool",
        }
        with tempfile.TemporaryDirectory() as temporary:
            with (
                mock.patch.object(policy, "DEFAULT_QUEUE", Path(temporary) / "queue.json"),
                mock.patch("subprocess.run") as run,
                mock.patch("subprocess.Popen") as popen,
            ):
                result = policy.quarantine_github_results([item], source="test")
        self.assertEqual("quarantined", result[0]["state"])
        run.assert_not_called()
        popen.assert_not_called()

    def test_architecture_contract_has_exactly_ten_controls(self) -> None:
        score = policy.architecture_score()
        self.assertEqual("10/10", score["score"])
        self.assertEqual(10, len(score["controls"]))
        self.assertTrue(all(score["controls"].values()))
        self.assertFalse(score["execution_evidence"])
        self.assertFalse(score["activation_authority"])


if __name__ == "__main__":
    unittest.main()
