#!/usr/bin/env python3
"""Test-only MCP stdio fixture used by the offline verifier suite."""
from __future__ import annotations

import json
import os
import sys
import time

MODE = os.environ.get("FAKE_MCP_MODE", "success")

for line in sys.stdin:
    request = json.loads(line)
    method = request.get("method")
    request_id = request.get("id")
    if MODE == "silent":
        time.sleep(10)
        continue
    if MODE == "malformed":
        sys.stdout.write("{not-json}\n")
        sys.stdout.flush()
        continue
    if method == "initialize":
        result = {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}, "resources": {}},
            "serverInfo": {"name": "fieldnote-test-fixture", "version": "1.0"},
        }
    elif method == "tools/list":
        result = {"tools": [{"name": "read", "description": "read-only fixture"}]}
    elif method == "resources/list":
        result = {"resources": []}
    else:
        continue
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": request_id, "result": result}) + "\n")
    sys.stdout.flush()
