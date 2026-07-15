"""
Fieldnote Code Sync — file watcher that keeps the GitHub repo current.

Polls file mtimes every POLL_SECS seconds.  When anything changes it
waits DEBOUNCE_SECS for the burst to settle, then calls sync_code()
once.  Also runs an unconditional push every FALLBACK_MINS minutes so
the repo can never be more than FALLBACK_MINS out of date even if the
watcher missed something.

Usage:
    import agents.code_sync as code_sync
    code_sync.start()       # call once at app startup
    code_sync.status()      # dict for /api/sync/status
"""
from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("fieldnote.code_sync")

POLL_SECS     = 10     # how often to scan mtimes
DEBOUNCE_SECS = 6      # settle window after last change
FALLBACK_MINS = 10     # unconditional push interval (minutes)

WORKSPACE = Path(__file__).parent.parent

# Mirror the exclusion lists from github_sync so we watch the same files
WATCH_EXTENSIONS = {".py", ".html", ".css", ".js", ".md", ".txt",
                    ".toml", ".nix", ".json"}
WATCH_EXCLUDE_DIRS = {
    "__pycache__", ".fieldnote_mirror", "fieldnote_repos",
    "fieldnote_skills", ".git", "node_modules", ".agents",
    "fieldnote_mcp", ".pythonlibs",
}
WATCH_EXCLUDE_FILES = {
    "local_keys.json", ".env",
    ".replit", "replit.nix", "replit.toml",  # never push Replit internals
}
WATCH_MAX_DEPTH = 4


# ── State (all guarded by _lock) ─────────────────────────────────────────────

_lock          = threading.Lock()
_mtimes: dict[str, float] = {}
_last_change   = 0.0          # epoch of last detected file change
_last_push     = 0.0          # epoch of last successful push
_pushes_ok     = 0
_pushes_err    = 0
_last_error    = ""
_running       = False
_started_at    = ""


# ── File scanning ─────────────────────────────────────────────────────────────

def _scan_files() -> dict[str, float]:
    """Return {rel_path: mtime} for all watched files in workspace."""
    result: dict[str, float] = {}
    try:
        for root, dirs, files in os.walk(WORKSPACE):
            root_path = Path(root)
            # Prune excluded dirs in-place so os.walk skips them
            dirs[:] = [
                d for d in dirs
                if d not in WATCH_EXCLUDE_DIRS
                and not d.startswith(".")
                or d == ".replit"
            ]
            rel_root = root_path.relative_to(WORKSPACE)
            depth    = len(rel_root.parts)
            if depth > WATCH_MAX_DEPTH:
                dirs.clear()
                continue
            for fname in files:
                if fname in WATCH_EXCLUDE_FILES:
                    continue
                fpath = root_path / fname
                if fpath.suffix not in WATCH_EXTENSIONS:
                    continue
                try:
                    result[str(fpath.relative_to(WORKSPACE))] = fpath.stat().st_mtime
                except Exception:
                    pass
    except Exception as e:
        log.debug("scan_files error: %s", e)
    return result


def _detect_changes(old: dict[str, float], new: dict[str, float]) -> list[str]:
    changed = []
    for path, mtime in new.items():
        if old.get(path) != mtime:
            changed.append(path)
    for path in old:
        if path not in new:
            changed.append(path)
    return changed


# ── Push helper ───────────────────────────────────────────────────────────────

def _do_push(label: str) -> None:
    global _last_push, _pushes_ok, _pushes_err, _last_error
    try:
        import agents.github_sync as gs
        result = gs.sync_code(label=label)
        with _lock:
            if result.get("ok"):
                _last_push  = time.time()
                _pushes_ok += 1
                _last_error = ""
                log.info("Code sync: pushed (%s) — %d files", label, result.get("changed", 0))
            else:
                _pushes_err += 1
                _last_error  = result.get("error", "unknown")
                log.warning("Code sync: push failed (%s) — %s", label, _last_error)
    except Exception as exc:
        with _lock:
            _pushes_err += 1
            _last_error  = str(exc)
        log.error("Code sync: exception during push: %s", exc)


# ── Watcher loop ──────────────────────────────────────────────────────────────

def _watch_loop() -> None:
    global _mtimes, _last_change, _running

    log.info("Code watcher started (poll=%ds debounce=%ds fallback=%dmin)",
             POLL_SECS, DEBOUNCE_SECS, FALLBACK_MINS)

    # Initial scan (baseline — don't push on startup, startup sync handles it)
    with _lock:
        _mtimes = _scan_files()

    pending_push = False
    last_change_local = 0.0

    while True:
        time.sleep(POLL_SECS)

        now      = time.time()
        new_snap = _scan_files()

        with _lock:
            changed = _detect_changes(_mtimes, new_snap)
            if changed:
                _last_change     = now
                last_change_local = now
                pending_push     = True
                log.debug("Watcher: %d file(s) changed: %s", len(changed), changed[:5])
            _mtimes = new_snap

        # Debounce: wait for burst to settle
        if pending_push and (now - last_change_local) >= DEBOUNCE_SECS:
            pending_push = False
            _do_push(f"watch:{len(changed) if changed else '?'}files")

        # Fallback: push unconditionally every FALLBACK_MINS
        with _lock:
            lp = _last_push
        if (now - lp) >= FALLBACK_MINS * 60:
            _do_push("fallback")


# ── Public API ────────────────────────────────────────────────────────────────

def start() -> None:
    """Start the file watcher daemon thread.  Safe to call multiple times."""
    global _running, _started_at
    with _lock:
        if _running:
            return
        _running    = True
        _started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    threading.Thread(target=_watch_loop, daemon=True, name="fn-code-watcher").start()
    log.info("Code sync watcher started")


def push_now(label: str = "manual") -> dict:
    """Trigger an immediate push (non-blocking)."""
    threading.Thread(target=_do_push, args=(label,), daemon=True,
                     name="fn-code-push").start()
    return {"ok": True, "queued": True, "label": label}


def status() -> dict:
    """Return current watcher state for the API."""
    with _lock:
        return {
            "running":     _running,
            "started_at":  _started_at,
            "last_change": _last_change and _ts_to_iso(_last_change) or None,
            "last_push":   _last_push   and _ts_to_iso(_last_push)   or None,
            "pushes_ok":   _pushes_ok,
            "pushes_err":  _pushes_err,
            "last_error":  _last_error,
            "files_watched": len(_mtimes),
            "poll_secs":   POLL_SECS,
            "debounce_secs": DEBOUNCE_SECS,
            "fallback_mins": FALLBACK_MINS,
        }


def _ts_to_iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec="seconds")
