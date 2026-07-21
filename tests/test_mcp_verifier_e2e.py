"""Offline end-to-end tests for the MCP verifier boundary."""
from __future__ import annotations

import os
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from agents import mcp_verifier

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fieldnote_mcp" / "verified_servers" / "test_fixture_mcp.py"


def entry(mode: str = "success") -> SimpleNamespace:
    return SimpleNamespace(
        id=f"fixture-{mode}",
        package_name="",
        install_method="local",
        local_path=str(FIXTURE),
        runtime_required="none",
        credential_env="FAKE_MCP_MODE",
    )


class MCPVerifierEndToEndTests(unittest.TestCase):
    def test_complete_handshake_and_capability_probes(self) -> None:
        with mock.patch.dict(os.environ, {"FAKE_MCP_MODE": "success"}, clear=False):
            result = mcp_verifier.verify_server(entry(), timeout_s=3)
        self.assertTrue(result.ok, result.diagnostics)
        self.assertEqual(1, result.diagnostics["tools_count"])
        self.assertEqual(0, result.diagnostics["resources_count"])

    def test_silent_server_obeys_hard_deadline(self) -> None:
        started = time.monotonic()
        with mock.patch.dict(os.environ, {"FAKE_MCP_MODE": "silent"}, clear=False):
            result = mcp_verifier.verify_server(entry("silent"), timeout_s=1)
        elapsed = time.monotonic() - started
        self.assertFalse(result.ok)
        self.assertEqual("timeout", result.error_code)
        self.assertLess(elapsed, 2.5)

    def test_malformed_server_fails_closed(self) -> None:
        with mock.patch.dict(os.environ, {"FAKE_MCP_MODE": "malformed"}, clear=False):
            result = mcp_verifier.verify_server(entry("malformed"), timeout_s=2)
        self.assertFalse(result.ok)
        self.assertEqual("malformed_json", result.error_code)

    def test_package_manager_health_check_is_blocked(self) -> None:
        mutable = SimpleNamespace(
            id="mutable",
            package_name="untrusted-latest",
            install_method="npm",
            runtime_required="none",
            credential_env="",
        )
        with mock.patch("subprocess.Popen") as popen:
            result = mcp_verifier.verify_server(mutable, timeout_s=1)
        self.assertFalse(result.ok)
        self.assertEqual("config_error", result.error_code)
        popen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
