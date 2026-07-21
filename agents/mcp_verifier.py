"""
Fieldnote MCP Protocol Verifier
================================
Performs a real MCP JSON-RPC handshake against a stdio server subprocess.

Protocol:  MCP 2024-11-05
Transport: stdio (stdin/stdout JSON-RPC)

Security contract:
  • 30 s total timeout per verification
  • 50 KB output cap per read
  • Credentials injected at spawn time only — never logged or returned
  • Diagnostics contain only sanitized metadata: protocol_version, tools_count,
    resources_count, latency_ms, error_code

Usage:
    from agents.mcp_verifier import verify_server
    result = verify_server(registry_entry)
    # result.ok, result.error_code, result.diagnostics
"""
from __future__ import annotations

import json
import logging
import os
import select
import shutil
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from typing import Any, Optional

log = logging.getLogger("fieldnote.mcp_verifier")

_TIMEOUT_S       = 30      # total verification timeout
_OUTPUT_CAP      = 50_000  # bytes — max stdout per read
_PROTO_VERSION   = "2024-11-05"

# Read-only tools we are allowed to call during a smoke test
_SMOKE_WHITELIST: set[str] = {
    "list_tools", "list_resources", "get_resource",
    "search", "fetch", "read_file", "read",
}


# ── Result dataclass ───────────────────────────────────────────────────────────

@dataclass
class VerifyResult:
    ok:               bool
    error_code:       str = ""          # runtime_missing | rpc_error | timeout | crash | malformed_json | no_response
    missing_runtime:  str = ""          # e.g. "node" or "python"
    diagnostics: dict = field(default_factory=dict)


# ── Public API ─────────────────────────────────────────────────────────────────

def verify_server(entry: Any, timeout_s: int = _TIMEOUT_S) -> VerifyResult:
    """
    Start entry's subprocess, run MCP initialize handshake, call tools/list
    and resources/list, shut down cleanly.

    entry: agents.mcp_registry.MCPServer (duck-typed to avoid circular import)
    """
    t0 = time.monotonic()

    # ── 1. Check runtime availability ─────────────────────────────────────────
    if entry.runtime_required and entry.runtime_required != "none":
        runtime_bin = _runtime_binary(entry.runtime_required)
        if runtime_bin is None:
            log.warning("mcp_verifier: %s — runtime %r not found", entry.id, entry.runtime_required)
            return VerifyResult(
                ok=False,
                error_code="runtime_missing",
                missing_runtime=entry.runtime_required,
                diagnostics={"error": f"{entry.runtime_required} runtime not installed"},
            )

    # ── 2. Resolve command ────────────────────────────────────────────────────
    try:
        cmd = _build_command(entry)
    except Exception as exc:
        return VerifyResult(ok=False, error_code="config_error",
                            diagnostics={"error": str(exc)[:200]})

    if not cmd:
        return VerifyResult(ok=False, error_code="config_error",
                            diagnostics={"error": "no command configured"})

    # ── 3. Spawn with a minimal environment and isolated temporary cwd ───────
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
    }
    credential_env = str(getattr(entry, "credential_env", "") or "")
    if credential_env and credential_env in os.environ:
        env[credential_env] = os.environ[credential_env]

    proc: Optional[subprocess.Popen] = None
    with tempfile.TemporaryDirectory(prefix="fieldnote-mcp-verify-") as workdir:
        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                cwd=workdir,
                text=False,
            )
        except FileNotFoundError as exc:
            return VerifyResult(ok=False, error_code="runtime_missing",
                                missing_runtime=cmd[0] if cmd else "?",
                                diagnostics={"error": str(exc)[:200]})
        except Exception as exc:
            return VerifyResult(ok=False, error_code="spawn_error",
                                diagnostics={"error": str(exc)[:200]})

        try:
            return _run_handshake(proc, entry, t0, timeout_s)
        finally:
            _kill(proc)


# ── Internal helpers ───────────────────────────────────────────────────────────

def _runtime_binary(runtime: str) -> Optional[str]:
    if runtime == "python":
        return shutil.which("python3") or shutil.which("python")
    if runtime == "node":
        return shutil.which("node")
    return shutil.which(runtime)


def _build_command(entry: Any) -> list[str]:
    """Build only an already-installed, immutable local command."""
    method = entry.install_method
    if method in {"uvx", "pip", "npm"}:
        raise RuntimeError("package-manager execution is blocked during health verification")
    if method == "local" and getattr(entry, "local_path", ""):
        path = os.path.realpath(entry.local_path)
        trusted_root = os.path.realpath("fieldnote_mcp/verified_servers")
        if path != trusted_root and not path.startswith(trusted_root + os.sep):
            raise RuntimeError("local MCP path is outside verified_servers")
        return ["python", path]
    return []


def _read_response(proc: subprocess.Popen, deadline: float) -> Optional[bytes]:
    """Read one bounded JSON-RPC line without allowing buffered reads to exceed the deadline."""
    if proc.stdout is None:
        return None
    fd = proc.stdout.fileno()
    output = bytearray()
    while len(output) < _OUTPUT_CAP:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        try:
            readable, _, _ = select.select([fd], [], [], remaining)
        except Exception:
            return None
        if not readable:
            return None
        try:
            chunk = os.read(fd, min(4096, _OUTPUT_CAP - len(output)))
        except OSError:
            return None
        if not chunk:
            return bytes(output) or None
        output.extend(chunk)
        newline = output.find(b"\n")
        if newline >= 0:
            return bytes(output[: newline + 1])
    return bytes(output)


def _send_rpc(proc: subprocess.Popen, method: str, params: dict, req_id: int) -> None:
    """Write one JSON-RPC request to proc.stdin."""
    msg = json.dumps({
        "jsonrpc": "2.0",
        "id": req_id,
        "method": method,
        "params": params,
    }) + "\n"
    assert proc.stdin is not None
    proc.stdin.write(msg.encode())
    proc.stdin.flush()


def _notify(proc: subprocess.Popen, method: str, params: dict) -> None:
    msg = json.dumps({"jsonrpc": "2.0", "method": method, "params": params}) + "\n"
    assert proc.stdin is not None
    try:
        proc.stdin.write(msg.encode())
        proc.stdin.flush()
    except BrokenPipeError:
        pass


def _parse_rpc(raw: bytes) -> Optional[dict]:
    """Parse the first complete JSON object from raw bytes."""
    if not raw:
        return None
    try:
        # MCP servers emit one JSON object per line
        for line in raw.split(b"\n"):
            line = line.strip()
            if line and line.startswith(b"{"):
                return json.loads(line)
    except Exception:
        pass
    return None


def _run_handshake(proc: subprocess.Popen, entry: Any,
                   t0: float, timeout_s: int) -> VerifyResult:

    deadline = t0 + timeout_s

    def _timed_out() -> bool:
        return time.monotonic() >= deadline

    # ── initialize ─────────────────────────────────────────────────────────────
    try:
        _send_rpc(proc, "initialize", {
            "protocolVersion": _PROTO_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "fieldnote-verifier", "version": "1.0"},
        }, req_id=1)
    except Exception as exc:
        return VerifyResult(ok=False, error_code="rpc_error",
                            diagnostics={"error": str(exc)[:200]})

    if _timed_out():
        return VerifyResult(ok=False, error_code="timeout",
                            diagnostics={"error": "timeout before initialize response"})

    raw = _read_response(proc, deadline)
    if raw is None:
        return VerifyResult(ok=False, error_code="timeout",
                            diagnostics={"error": "no response to initialize"})

    init_resp = _parse_rpc(raw)
    if init_resp is None:
        rc = proc.poll()
        if rc is not None and rc != 0:
            return VerifyResult(ok=False, error_code="crash",
                                diagnostics={"error": f"process exited {rc}"})
        return VerifyResult(ok=False, error_code="malformed_json",
                            diagnostics={"error": "could not parse initialize response"})

    if "error" in init_resp:
        return VerifyResult(ok=False, error_code="rpc_error",
                            diagnostics={"error": str(init_resp["error"])[:200]})

    result = init_resp.get("result", {})
    protocol_version = result.get("protocolVersion", "unknown")
    server_caps = result.get("capabilities", {})

    # ── notifications/initialized ──────────────────────────────────────────────
    _notify(proc, "notifications/initialized", {})

    # ── tools/list ────────────────────────────────────────────────────────────
    tools_count = 0
    if "tools" in server_caps and not _timed_out():
        try:
            _send_rpc(proc, "tools/list", {}, req_id=2)
            raw2 = _read_response(proc, deadline)
            if raw2 is not None:
                tr = _parse_rpc(raw2)
                if tr and "result" in tr:
                    tools_count = len(tr["result"].get("tools", []))
            # If raw2 is None here it's a post-initialize timeout — log but continue
            elif _timed_out():
                log.debug("mcp_verifier: %s tools/list timed out (post-initialize)", entry.id)
        except Exception as exc:
            log.debug("mcp_verifier: %s tools/list error: %s", entry.id, exc)

    # ── resources/list ────────────────────────────────────────────────────────
    resources_count = 0
    if "resources" in server_caps and not _timed_out():
        try:
            _send_rpc(proc, "resources/list", {}, req_id=3)
            raw3 = _read_response(proc, deadline)
            if raw3 is not None:
                rr = _parse_rpc(raw3)
                if rr and "result" in rr:
                    resources_count = len(rr["result"].get("resources", []))
            elif _timed_out():
                log.debug("mcp_verifier: %s resources/list timed out (post-initialize)", entry.id)
        except Exception as exc:
            log.debug("mcp_verifier: %s resources/list error: %s", entry.id, exc)

    latency_ms = int((time.monotonic() - t0) * 1000)

    return VerifyResult(
        ok=True,
        diagnostics={
            "protocol_version":  protocol_version,
            "tools_count":       tools_count,
            "resources_count":   resources_count,
            "latency_ms":        latency_ms,
        },
    )


def _kill(proc: Optional[subprocess.Popen]) -> None:
    """Graceful SIGTERM then SIGKILL."""
    if proc is None:
        return
    try:
        proc.stdin.close()  # type: ignore[union-attr]
    except Exception:
        pass
    try:
        proc.terminate()
        proc.wait(timeout=3)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
