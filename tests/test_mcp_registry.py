"""Focused persistence-boundary tests for the canonical MCP registry."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agents import mcp_registry


def server(**overrides) -> mcp_registry.MCPServer:
    values = {
        "id": "real-server",
        "name": "Real Server",
        "category": "search",
        "description": "A real registry entry",
        "license_spdx": "MIT",
        "homepage": "https://example.com/real",
        "repo_url": "https://github.com/example/real-server",
        "package_name": "real-mcp-server",
        "install_method": "uvx",
        "runtime_required": "python",
        "runtime_check_cmd": "python --version",
    }
    values.update(overrides)
    return mcp_registry.MCPServer(**values)


class MCPRegistryPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.registry_file = Path(self.tempdir.name) / "mcp_hub_registry.json"

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_save_rejects_test_fixture_before_write(self) -> None:
        with mock.patch.object(mcp_registry, "REGISTRY_FILE", str(self.registry_file)):
            mcp_registry.save_registry(
                [server(), server(id="test-server", package_name="test-mcp-server")]
            )

        persisted = json.loads(self.registry_file.read_text(encoding="utf-8"))
        self.assertEqual(["real-server"], [entry["id"] for entry in persisted])

    def test_load_rejects_fixture_already_present_on_disk(self) -> None:
        self.registry_file.write_text(
            json.dumps(
                [
                    server().to_dict(),
                    server(
                        id="external-fixture",
                        repo_url="https://github.com/test/test-server",
                    ).to_dict(),
                ]
            ),
            encoding="utf-8",
        )

        with (
            mock.patch.object(mcp_registry, "REGISTRY_FILE", str(self.registry_file)),
            mock.patch.object(mcp_registry, "SEED_ENTRIES", []),
        ):
            loaded = mcp_registry.load_registry()

        self.assertEqual(["real-server"], [entry.id for entry in loaded])


if __name__ == "__main__":
    unittest.main()
