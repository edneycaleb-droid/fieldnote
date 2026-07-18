"""
Fieldnote MCP Capability Router
=================================
Routes Fieldnote tasks to the healthiest installed MCP server for a given capability.

Capabilities:
  web_search | transcription | web_crawl | git_read | vector_search | file_read | doc_convert

Circuit breaker (per server):
  3 failures within 5 min  → OPEN  (calls return None immediately)
  10 min cooldown          → HALF_OPEN (one probe allowed)
  probe success            → CLOSED
  probe failure            → OPEN (reset timer)

Never raises — all exceptions are caught and logged.
Max 2 MCP attempts per call_tool invocation before falling through to fallback_fn.
"""
from __future__ import annotations

import logging
import time
from threading import Lock
from typing import Any, Callable, Optional

log = logging.getLogger("fieldnote.mcp_router")

_CB_FAILURES_THRESHOLD  = 3
_CB_WINDOW_S            = 300   # 5 minutes
_CB_COOLDOWN_S          = 600   # 10 minutes
_MAX_MCP_ATTEMPTS       = 2
_STATS_RESET_INTERVAL_S = 3600  # 1 hour

_lock  = Lock()
_stats: dict[str, dict] = {}  # entry_id → {successes, failures, total_latency_ms, last_reset}
_cb:    dict[str, dict] = {}  # entry_id → {state, failure_times, opened_at}


# ── Circuit breaker ────────────────────────────────────────────────────────────

def _now() -> float:
    return time.monotonic()


def _cb_state(entry_id: str) -> str:
    """Return 'CLOSED', 'OPEN', or 'HALF_OPEN'."""
    with _lock:
        cb = _cb.get(entry_id, {"state": "CLOSED", "failure_times": [], "opened_at": 0.0})
        _cb[entry_id] = cb
        state = cb.get("state", "CLOSED")
        if state == "OPEN":
            if _now() - cb.get("opened_at", 0.0) >= _CB_COOLDOWN_S:
                cb["state"] = "HALF_OPEN"
                return "HALF_OPEN"
        return state


def _cb_record_success(entry_id: str) -> None:
    with _lock:
        cb = _cb.setdefault(entry_id, {"state": "CLOSED", "failure_times": [], "opened_at": 0.0})
        cb["state"] = "CLOSED"
        cb["failure_times"] = []


def _cb_record_failure(entry_id: str) -> str:
    """Record failure; return new state (CLOSED|OPEN)."""
    with _lock:
        cb = _cb.setdefault(entry_id, {"state": "CLOSED", "failure_times": [], "opened_at": 0.0})
        now = _now()
        # Prune old failures outside the window
        cb["failure_times"] = [t for t in cb.get("failure_times", []) if now - t <= _CB_WINDOW_S]
        cb["failure_times"].append(now)
        if len(cb["failure_times"]) >= _CB_FAILURES_THRESHOLD:
            cb["state"] = "OPEN"
            cb["opened_at"] = now
            log.warning("mcp_router: circuit OPEN for %s (%d failures in %ds)",
                        entry_id, len(cb["failure_times"]), _CB_WINDOW_S)
            return "OPEN"
        return cb.get("state", "CLOSED")


# ── Stats tracking ─────────────────────────────────────────────────────────────

def _ensure_stats(entry_id: str) -> None:
    with _lock:
        if entry_id not in _stats:
            _stats[entry_id] = {
                "successes": 0, "failures": 0,
                "total_latency_ms": 0, "last_reset": _now(),
            }
        elif _now() - _stats[entry_id]["last_reset"] > _STATS_RESET_INTERVAL_S:
            _stats[entry_id] = {
                "successes": 0, "failures": 0,
                "total_latency_ms": 0, "last_reset": _now(),
            }


def _record_success(entry_id: str, latency_ms: int) -> None:
    _ensure_stats(entry_id)
    with _lock:
        _stats[entry_id]["successes"] += 1
        _stats[entry_id]["total_latency_ms"] += latency_ms


def _record_failure(entry_id: str) -> None:
    _ensure_stats(entry_id)
    with _lock:
        _stats[entry_id]["failures"] += 1


def success_rate(entry_id: str) -> float:
    _ensure_stats(entry_id)
    with _lock:
        s = _stats[entry_id]
        total = s["successes"] + s["failures"]
        return s["successes"] / total if total else 1.0


def avg_latency_ms(entry_id: str) -> float:
    _ensure_stats(entry_id)
    with _lock:
        s = _stats[entry_id]
        return s["total_latency_ms"] / s["successes"] if s["successes"] else 0.0


def get_circuit_state(entry_id: str) -> str:
    return _cb_state(entry_id)


def get_all_stats() -> dict:
    """Return per-server stats for the ops dashboard."""
    result = {}
    servers_ids = set(list(_stats.keys()) + list(_cb.keys()))
    for eid in servers_ids:
        result[eid] = {
            "success_rate":  round(success_rate(eid), 3),
            "avg_latency_ms": round(avg_latency_ms(eid), 1),
            "circuit_state": _cb_state(eid),
        }
    return result


# ── Router ─────────────────────────────────────────────────────────────────────

def route(capability: str) -> Optional[str]:
    """
    Return the entry_id of the best available server for the given capability.
    Best = installed + enabled + healthy state + circuit CLOSED/HALF_OPEN
    Sorted by success_rate desc, avg_latency asc.
    Returns None if no suitable server is available.
    """
    try:
        from agents.mcp_registry import get_by_capability
        candidates = get_by_capability(capability)
    except Exception as exc:
        log.warning("mcp_router.route: could not load registry: %s", exc)
        return None

    eligible = []
    for srv in candidates:
        if not srv.enabled:
            continue
        if srv.health_state not in ("connected", "degraded"):
            continue
        cb = _cb_state(srv.id)
        if cb == "OPEN":
            continue
        eligible.append(srv)

    if not eligible:
        return None

    eligible.sort(key=lambda s: (-success_rate(s.id), avg_latency_ms(s.id)))
    return eligible[0].id


<<<<<<< Updated upstream
_CALL_TIMEOUT_S = 30   # per-call end-to-end timeout for tool invocations


=======
<<<<<<< HEAD
=======
_CALL_TIMEOUT_S = 30   # per-call end-to-end timeout for tool invocations


>>>>>>> 48a9224 (sync(scheduler): 1 source file(s) updated)
>>>>>>> Stashed changes
def _call_server(entry_id: str, tool_name: str, args: dict) -> Any:
    """
    Invoke a tool on a running MCP server.
    In Fieldnote's sandbox we use subprocess stdio — start, call, terminate.
    Returns the tool result or raises on failure.
<<<<<<< Updated upstream

    All subprocess reads use select() with a hard deadline; no call can block
    indefinitely regardless of server behaviour.
=======
<<<<<<< HEAD
>>>>>>> Stashed changes
    """
    import os
    import select as _select
    import subprocess
    import json as _json

    from agents.mcp_registry import get_by_id
    from agents.mcp_verifier import _build_command, _kill, _notify, _parse_rpc, _OUTPUT_CAP
<<<<<<< Updated upstream
=======
    import subprocess, os, json as _json
=======

    All subprocess reads use select() with a hard deadline; no call can block
    indefinitely regardless of server behaviour.
    """
    import os
    import select as _select
    import subprocess
    import json as _json

    from agents.mcp_registry import get_by_id
    from agents.mcp_verifier import _build_command, _kill, _notify, _parse_rpc, _OUTPUT_CAP
>>>>>>> 48a9224 (sync(scheduler): 1 source file(s) updated)
>>>>>>> Stashed changes

    entry = get_by_id(entry_id)
    if entry is None:
        raise RuntimeError(f"entry {entry_id!r} not found in registry")

    cmd = _build_command(entry)
    if not cmd:
        raise RuntimeError(f"no command for {entry_id}")

<<<<<<< Updated upstream
=======
<<<<<<< HEAD
    t0 = time.monotonic()
=======
>>>>>>> Stashed changes
    t0       = time.monotonic()
    deadline = t0 + _CALL_TIMEOUT_S

    def _timed_out() -> bool:
        return time.monotonic() >= deadline

    def _read_bounded() -> bytes:
        """Read with deadline; raises RuntimeError on timeout."""
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError("call timeout (deadline exceeded)")
        try:
            rlist, _, _ = _select.select([proc.stdout], [], [], remaining)
        except Exception:
            rlist = [proc.stdout]
        if not rlist:
            raise RuntimeError("call timeout (no data from server)")
        data = proc.stdout.read(_OUTPUT_CAP)   # type: ignore[union-attr]
        if data is None or data == b"":
            raise RuntimeError("call timeout (server closed stdout)")
        return data

<<<<<<< Updated upstream
=======
>>>>>>> 48a9224 (sync(scheduler): 1 source file(s) updated)
>>>>>>> Stashed changes
    proc = subprocess.Popen(
        cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, env={**os.environ}, text=False,
    )
    try:
<<<<<<< Updated upstream
        # ── initialize ────────────────────────────────────────────────────────
=======
<<<<<<< HEAD
        # initialize
=======
        # ── initialize ────────────────────────────────────────────────────────
>>>>>>> 48a9224 (sync(scheduler): 1 source file(s) updated)
>>>>>>> Stashed changes
        proc.stdin.write(_json.dumps({  # type: ignore[union-attr]
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "fieldnote-router", "version": "1.0"},
            },
        }).encode() + b"\n")
        proc.stdin.flush()  # type: ignore[union-attr]
<<<<<<< Updated upstream
=======
<<<<<<< HEAD
        raw = proc.stdout.read(_OUTPUT_CAP)  # type: ignore[union-attr]
=======
>>>>>>> Stashed changes

        if _timed_out():
            raise RuntimeError("call timeout (before initialize response)")
        raw = _read_bounded()
<<<<<<< Updated upstream
=======
>>>>>>> 48a9224 (sync(scheduler): 1 source file(s) updated)
>>>>>>> Stashed changes
        init_resp = _parse_rpc(raw)
        if not init_resp or "error" in init_resp:
            raise RuntimeError("initialize failed")

        _notify(proc, "notifications/initialized", {})

<<<<<<< Updated upstream
=======
<<<<<<< HEAD
        # call tool
=======
>>>>>>> Stashed changes
        if _timed_out():
            raise RuntimeError("call timeout (after initialize, before tool call)")

        # ── tools/call ────────────────────────────────────────────────────────
<<<<<<< Updated upstream
=======
>>>>>>> 48a9224 (sync(scheduler): 1 source file(s) updated)
>>>>>>> Stashed changes
        proc.stdin.write(_json.dumps({  # type: ignore[union-attr]
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": tool_name, "arguments": args},
        }).encode() + b"\n")
        proc.stdin.flush()  # type: ignore[union-attr]
<<<<<<< Updated upstream

        raw2 = _read_bounded()
=======
<<<<<<< HEAD
        raw2 = proc.stdout.read(_OUTPUT_CAP)  # type: ignore[union-attr]
=======

        raw2 = _read_bounded()
>>>>>>> 48a9224 (sync(scheduler): 1 source file(s) updated)
>>>>>>> Stashed changes
        tool_resp = _parse_rpc(raw2)
        if not tool_resp:
            raise RuntimeError("no response from tool call")
        if "error" in tool_resp:
            raise RuntimeError(str(tool_resp["error"])[:200])

        latency_ms = int((time.monotonic() - t0) * 1000)
        _record_success(entry_id, latency_ms)
        _cb_record_success(entry_id)
        return tool_resp.get("result")
    except Exception:
        _record_failure(entry_id)
        _cb_record_failure(entry_id)
        raise
    finally:
        _kill(proc)


def call_tool(
    capability:  str,
    tool_name:   str,
    args:        dict,
    fallback_fn: Optional[Callable] = None,
) -> Any:
    """
    Route to the best available MCP server for capability, call tool_name(args).
    On failure, try the next server (up to _MAX_MCP_ATTEMPTS total).
    If all MCP servers fail, call fallback_fn() if provided.
    Returns None if everything fails. NEVER raises.
    """
    try:
        from agents.mcp_registry import get_by_capability
        candidates = get_by_capability(capability)
    except Exception as exc:
        log.warning("mcp_router.call_tool: registry load failed: %s", exc)
        candidates = []

    attempts = 0
    for srv in candidates:
        if attempts >= _MAX_MCP_ATTEMPTS:
            break
        if not srv.enabled:
            continue
        if srv.health_state not in ("connected", "degraded"):
            continue
        cb = _cb_state(srv.id)
        if cb == "OPEN":
            continue
        attempts += 1
        try:
            result = _call_server(srv.id, tool_name, args)
            log.debug("mcp_router: %s/%s succeeded via %s", capability, tool_name, srv.id)
            return result
        except Exception as exc:
            log.warning("mcp_router: %s/%s failed on %s: %s", capability, tool_name, srv.id, exc)

    # All MCP attempts exhausted — try native fallback
    if fallback_fn is not None:
        try:
            return fallback_fn()
        except Exception as exc:
            log.warning("mcp_router: fallback_fn failed: %s", exc)

    return None
