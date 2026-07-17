"""
Fieldnote Auto-Agent — headless job functions for the scheduler.

enhance_due_skills() — re-run extraction on DCA-due skills
sync_github()        — full push of all skills to GitHub
process_watchlist()  — pick up new URLs from watchlist.json and process them

All functions run synchronously (the scheduler wraps them in threads).
They log to 'fieldnote.auto_agent' and return a result dict.
"""
from __future__ import annotations

import json
import logging
import os
import queue
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

log = logging.getLogger("fieldnote.auto_agent")

WATCHLIST_PATH = os.path.join(os.path.dirname(__file__), "..", "watchlist.json")
WATCHLIST_PATH = os.path.normpath(WATCHLIST_PATH)

# ── Lazy imports (avoids circular imports at module load time) ─────────────────

def _app():
    import app as _a
    return _a

def _github_sync():
    import agents.github_sync as _gs
    return _gs

def _skill_quality():
    import agents.skill_quality as _sq
    return _sq


# ── Watchlist helpers ─────────────────────────────────────────────────────────

def load_watchlist() -> list[dict]:
    if not os.path.exists(WATCHLIST_PATH):
        return []
    try:
        with open(WATCHLIST_PATH) as f:
            return json.load(f)
    except Exception:
        return []

def save_watchlist(entries: list[dict]) -> None:
    with open(WATCHLIST_PATH, "w") as f:
        json.dump(entries, f, indent=2)

def add_to_watchlist(url: str, label: str = "") -> dict:
    entries = load_watchlist()
    for e in entries:
        if e.get("url") == url:
            return {"ok": False, "error": "URL already in watchlist", "entry": e}
    entry = {
        "url":        url,
        "label":      label or url,
        "added_at":   _now_iso(),
        "status":     "pending",   # pending | processing | done | error
        "skill_name": None,
        "error":      None,
        "processed_at": None,
    }
    entries.append(entry)
    save_watchlist(entries)
    return {"ok": True, "entry": entry}

def remove_from_watchlist(url: str) -> dict:
    entries = load_watchlist()
    before  = len(entries)
    entries = [e for e in entries if e.get("url") != url]
    save_watchlist(entries)
    return {"ok": True, "removed": before - len(entries)}


# ── Headless run_job wrapper ───────────────────────────────────────────────────

def _headless_run(url: str, video_id: str,
                  force_enhance: str | None = None,
                  timeout: int = 600) -> dict:
    """
    Spawn run_job in the background, drain its queue silently, and return
    the final 'done' payload.  force_enhance pins the skill_name so the
    pipeline always enhances that skill instead of creating a new one.
    """
    a = _app()

    job_id = str(uuid.uuid4())[:8]
    a._jobs[job_id] = {
        "queue":         queue.Queue(),
        "done":          False,
        "headless":      True,
        "force_enhance": force_enhance,
    }

    result: dict = {}
    finished = threading.Event()
    fallback_events: list[str] = []   # collect provider fallback log lines for job result

    def drain():
        q = a._jobs[job_id]["queue"]
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                msg = q.get(timeout=5)
                if msg.get("type") == "log":
                    text = msg.get("msg", "")
                    kind = msg.get("kind", "info")
                    log.debug("[headless %s] %s", job_id, text)
                    # Capture provider fallback log lines so they surface in job result
                    if kind in ("warning", "success") and (
                        "fallback" in text.lower() or "⚡" in text or "⚠" in text or "✓" in text
                    ):
                        fallback_events.append(text)
                elif msg.get("type") == "done":
                    result.update(msg)
                    break
            except Exception:
                if a._jobs[job_id].get("done"):
                    break
        finished.set()

    drain_thread = threading.Thread(target=drain, daemon=True,
                                    name=f"fn-drain-{job_id}")
    drain_thread.start()

    threading.Thread(target=a.run_job, args=(job_id, url, video_id),
                     daemon=True, name=f"fn-headless-{job_id}").start()

    finished.wait(timeout=timeout + 10)
    # Include any captured provider fallback events in the result dict
    if fallback_events:
        result["provider_fallbacks"] = fallback_events
    return result


# ── Job: enhance_due_skills ───────────────────────────────────────────────────

def enhance_due_skills() -> dict:
    """
    Check the DCA enhancement queue and re-run extraction on every due skill.
    Called by the scheduler every 6 hours.
    """
    a  = _app()
    sq = _skill_quality()

    index = a.load_index()
    due   = sq.skills_due_for_enhancement(index)

    if not due:
        log.info("Auto-enhance: no skills due")
        return {"enhanced": 0, "errors": 0, "skipped": 0}

    log.info("Auto-enhance: %d skills due → %s", len(due), due)
    ok = err = skipped = 0

    for skill_name in due:
        meta = index.get(skill_name, {})
        url  = meta.get("url") or meta.get("source_url")
        if not url:
            log.warning("Auto-enhance: '%s' has no stored URL — skipping", skill_name)
            skipped += 1
            continue

        video_id = a.extract_video_id(url)
        if not video_id:
            log.warning("Auto-enhance: bad URL for '%s' — skipping", skill_name)
            skipped += 1
            continue

        log.info("Auto-enhance: enhancing '%s' from %s", skill_name, url)
        try:
            result = _headless_run(url, video_id, force_enhance=skill_name)
            if result.get("ok"):
                ok += 1
                log.info("Auto-enhance: '%s' done", skill_name)
            else:
                err += 1
                log.error("Auto-enhance: '%s' failed → %s",
                           skill_name, result.get("error"))
        except Exception as exc:
            err += 1
            log.error("Auto-enhance: '%s' exception → %s", skill_name, exc)

        # Pause between enhancements to avoid rate-limit hammering
        time.sleep(10)

    return {"enhanced": ok, "errors": err, "skipped": skipped, "total": len(due)}


# ── Job: sync_github ──────────────────────────────────────────────────────────

def sync_github() -> dict:
    """Push all skills to the fieldnote GitHub mirror. Called every 24 h."""
    a  = _app()
    gs = _github_sync()

    index = a.load_index()
    result = gs.sync_all(a.SKILLS_DIR, index)
    log.info("Auto-sync: %s", result)
    return result


# ── Job: process_watchlist ────────────────────────────────────────────────────

def process_watchlist() -> dict:
    """
    Pick up the next pending URL from watchlist.json and process it.
    Runs every hour — processes ONE URL per cycle to keep load steady.
    """
    a = _app()

    entries = load_watchlist()
    pending = [e for e in entries if e.get("status") == "pending"]

    if not pending:
        return {"processed": 0, "pending": 0}

    entry    = pending[0]
    url      = entry["url"]
    video_id = a.extract_video_id(url)

    if not video_id:
        entry["status"] = "error"
        entry["error"]  = "Could not extract video ID"
        save_watchlist(entries)
        return {"processed": 0, "pending": len(pending), "error": entry["error"]}

    # Mark processing
    entry["status"] = "processing"
    save_watchlist(entries)

    log.info("Watchlist: processing %s", url)
    try:
        result = _headless_run(url, video_id, timeout=600)
        if result.get("ok"):
            entry["status"]       = "done"
            entry["skill_name"]   = result.get("skill_name")
            entry["processed_at"] = _now_iso()
            log.info("Watchlist: done → skill '%s'", entry["skill_name"])
        else:
            entry["status"] = "error"
            entry["error"]  = result.get("error", "unknown")
            log.error("Watchlist: error → %s", entry["error"])
    except Exception as exc:
        entry["status"] = "error"
        entry["error"]  = str(exc)
        log.error("Watchlist: exception → %s", exc)

    save_watchlist(entries)
    return {
        "processed": 1,
        "pending":   len(pending) - 1,
        "skill_name": entry.get("skill_name"),
        "status":     entry["status"],
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
