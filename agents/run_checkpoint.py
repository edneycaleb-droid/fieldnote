"""
run_checkpoint.py — atomic JSON checkpoint store for fault-tolerant runs.

Each checkpoint is a JSON file in `.checkpoints/<run_id>.json`.
Writes are atomic (write to .tmp then os.replace) so a crash can never
produce a half-written file.

Schema (all fields optional at any stage):
{
    "run_id":            str,
    "video_id":          str,
    "url":               str,
    "stage":             str,   # "transcript"|"extraction"|"judge"|"queued"|"degraded"|"done"
    "transcript":        str,
    "transcript_method": str,
    "metadata":          dict,
    "skill_a":           dict | null,
    "skill_b":           dict | null,
    "provider_attempts": [{"provider": str, "error": str, "error_class": str}],
    "queued_at":         str,   # ISO-8601 UTC
    "recovered_at":      str | null,
    "recovery_attempts": int,
    "degraded":          bool,
    "skill_name":        str | null,   # set when degraded skill already saved
    "timestamp":         str,   # last-updated ISO-8601 UTC
}
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Optional

log = logging.getLogger("fieldnote.run_checkpoint")

_CHECKPOINT_DIR = ".checkpoints"


def _ensure_dir() -> None:
    os.makedirs(_CHECKPOINT_DIR, exist_ok=True)


def _path(run_id: str) -> str:
    # Sanitise run_id — must be alphanumeric/dash/underscore only
    safe = "".join(c for c in run_id if c.isalnum() or c in "-_")[:64]
    return os.path.join(_CHECKPOINT_DIR, f"{safe}.json")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def save_checkpoint(run_id: str, data: dict) -> None:
    """
    Atomically persist `data` as a checkpoint for `run_id`.
    `data` is merged onto any existing checkpoint so callers only need
    to supply changed fields.
    """
    _ensure_dir()
    path     = _path(run_id)
    tmp_path = path + ".tmp"

    # Load existing checkpoint to merge
    existing: dict = {}
    try:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                existing = json.load(fh)
    except Exception:
        existing = {}

    merged = {**existing, **data, "run_id": run_id, "timestamp": _now_iso()}

    try:
        with open(tmp_path, "w", encoding="utf-8") as fh:
            json.dump(merged, fh, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
        log.debug("Checkpoint saved: %s [stage=%s]", run_id, merged.get("stage", "?"))
    except Exception as exc:
        log.error("Checkpoint save failed for %s: %s", run_id, exc)
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


def load_checkpoint(run_id: str) -> Optional[dict]:
    """Return the checkpoint dict for `run_id`, or None if not found."""
    path = _path(run_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:
        log.error("Checkpoint load failed for %s: %s", run_id, exc)
        return None


def delete_checkpoint(run_id: str) -> None:
    """Remove a checkpoint file; silently ignores missing files."""
    path = _path(run_id)
    try:
        os.unlink(path)
        log.debug("Checkpoint deleted: %s", run_id)
    except FileNotFoundError:
        pass
    except Exception as exc:
        log.warning("Checkpoint delete failed for %s: %s", run_id, exc)


def list_pending_checkpoints() -> list[dict]:
    """
    Return all checkpoints whose stage is 'queued' or 'degraded'.
    These are jobs that need auto-recovery when a free provider is available.
    """
    _ensure_dir()
    results: list[dict] = []
    try:
        for fname in os.listdir(_CHECKPOINT_DIR):
            if not fname.endswith(".json") or fname.endswith(".tmp"):
                continue
            fpath = os.path.join(_CHECKPOINT_DIR, fname)
            try:
                with open(fpath, encoding="utf-8") as fh:
                    cp = json.load(fh)
                stage = cp.get("stage", "")
                if stage in ("queued", "degraded"):
                    results.append(cp)
            except Exception:
                continue
    except Exception as exc:
        log.error("list_pending_checkpoints failed: %s", exc)
    return results


_STALE_DAYS             = 7
_MAX_RECOVERY_ATTEMPTS  = 3
_PURGE_LOG_FILE         = os.path.join(_CHECKPOINT_DIR, "_purge_log.json")


def list_stale_checkpoints() -> list[dict]:
    """
    Return queued/degraded checkpoints that have exhausted auto-recovery
    (recovery_attempts >= 3) AND are older than 7 days.
    These will never self-recover and should be purged.
    """
    _ensure_dir()
    cutoff = datetime.now(timezone.utc).timestamp() - _STALE_DAYS * 86400
    results: list[dict] = []
    try:
        for fname in os.listdir(_CHECKPOINT_DIR):
            if not fname.endswith(".json") or fname.endswith(".tmp"):
                continue
            if fname.startswith("_"):   # skip meta files like _purge_log.json
                continue
            fpath = os.path.join(_CHECKPOINT_DIR, fname)
            try:
                with open(fpath, encoding="utf-8") as fh:
                    cp = json.load(fh)
                if cp.get("stage", "") not in ("queued", "degraded"):
                    continue
                if cp.get("recovery_attempts", 0) < _MAX_RECOVERY_ATTEMPTS:
                    continue
                # Must also be older than STALE_DAYS
                age_ts = cp.get("queued_at") or cp.get("timestamp", "")
                if age_ts:
                    try:
                        if datetime.fromisoformat(age_ts).timestamp() > cutoff:
                            continue   # not old enough yet
                    except Exception:
                        pass
                results.append(cp)
            except Exception:
                continue
    except Exception as exc:
        log.error("list_stale_checkpoints failed: %s", exc)
    return results


def purge_stale_checkpoints() -> list[dict]:
    """
    Delete all stale checkpoints (exhausted retries + older than 7 days).
    Appends each purged entry to the persistent purge log.
    Returns the list of purged checkpoint dicts.
    """
    stale  = list_stale_checkpoints()
    purged: list[dict] = []
    now    = _now_iso()
    for cp in stale:
        run_id = cp.get("run_id")
        if not run_id:
            continue
        delete_checkpoint(run_id)
        entry = {
            "run_id":            run_id,
            "skill_name":        cp.get("skill_name"),
            "video_id":          cp.get("video_id"),
            "queued_at":         cp.get("queued_at"),
            "recovery_attempts": cp.get("recovery_attempts", 0),
            "reason":            "max_retries_exceeded_and_stale",
            "purged_at":         now,
        }
        purged.append(entry)
        log.info(
            "Purged stale checkpoint: %s (skill=%s, attempts=%d)",
            run_id, cp.get("skill_name"), cp.get("recovery_attempts", 0),
        )
    if purged:
        _append_purge_log(purged)
    return purged


def _append_purge_log(entries: list[dict]) -> None:
    """Append purge events to the persistent purge log file."""
    _ensure_dir()
    existing: list = []
    try:
        if os.path.exists(_PURGE_LOG_FILE):
            with open(_PURGE_LOG_FILE, encoding="utf-8") as fh:
                existing = json.load(fh)
    except Exception:
        existing = []
    combined = existing + entries
    # Keep the most recent 500 entries
    combined = combined[-500:]
    try:
        tmp = _PURGE_LOG_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(combined, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, _PURGE_LOG_FILE)
    except Exception as exc:
        log.error("_append_purge_log failed: %s", exc)


def load_purge_log() -> list[dict]:
    """Return all recorded purge events, newest first."""
    try:
        if os.path.exists(_PURGE_LOG_FILE):
            with open(_PURGE_LOG_FILE, encoding="utf-8") as fh:
                entries = json.load(fh)
            return list(reversed(entries))
    except Exception:
        pass
    return []


def checkpoint_for_video(video_id: str) -> Optional[dict]:
    """
    Find the most recent checkpoint for a given video_id.
    Returns the checkpoint dict or None.
    """
    _ensure_dir()
    best: Optional[dict] = None
    best_ts: str = ""
    try:
        for fname in os.listdir(_CHECKPOINT_DIR):
            if not fname.endswith(".json") or fname.endswith(".tmp"):
                continue
            fpath = os.path.join(_CHECKPOINT_DIR, fname)
            try:
                with open(fpath, encoding="utf-8") as fh:
                    cp = json.load(fh)
                if cp.get("video_id") == video_id:
                    ts = cp.get("timestamp", "")
                    if ts > best_ts:
                        best = cp
                        best_ts = ts
            except Exception:
                continue
    except Exception:
        pass
    return best
