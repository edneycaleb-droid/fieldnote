"""
agents/discovery_enrichment.py — Enrichment queue for GitHub discovery baseline skills.

Maintains a persistent queue of baseline skills awaiting AI enrichment.
Supports exponential backoff, quota-aware scheduling, and a pause/resume flag.
"""
from __future__ import annotations

import json
import logging
import os
import random
import time
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger("fieldnote.discovery_enrichment")

# ── Constants ─────────────────────────────────────────────────────────────────

MAX_RETRIES: int = 10  # Items exceeding this retry count are quarantined (dropped).

# ── Paths ─────────────────────────────────────────────────────────────────────

def _queue_path() -> str:
    import app as _a
    return os.path.join(_a.SKILLS_DIR, "_enrichment_queue.json")

def _state_path() -> str:
    import app as _a
    return os.path.join(_a.SKILLS_DIR, "_enrichment_state.json")


# ── Queue persistence ──────────────────────────────────────────────────────────

def load_queue() -> list[dict]:
    path = _queue_path()
    if not os.path.exists(path):
        return []
    try:
        with open(path) as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_queue(items: list[dict]) -> None:
    path = _queue_path()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    import uuid
    tmp = path + f".{os.getpid()}.{uuid.uuid4().hex}.tmp"
    with open(tmp, "w") as f:
        json.dump(items, f, indent=2)
    os.replace(tmp, path)


# ── State (paused flag + migration sentinel) ───────────────────────────────────

def _load_state() -> dict:
    path = _state_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


def _save_state(state: dict) -> None:
    path = _state_path()
    import uuid
    tmp = path + f".{os.getpid()}.{uuid.uuid4().hex}.tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, path)


def is_paused() -> bool:
    return bool(_load_state().get("paused", False))


def set_paused(paused: bool) -> None:
    state = _load_state()
    state["paused"] = paused
    _save_state(state)


def migration_done() -> bool:
    return bool(_load_state().get("migration_done", False))


def set_migration_done() -> None:
    state = _load_state()
    state["migration_done"] = True
    _save_state(state)


# ── Queue operations ────────────────────────────────────────────────────────────

def enqueue(full_name: str, stars: int, retry_count: int = 0,
            fingerprint: str = "") -> None:
    """Add a repo to the enrichment backlog (idempotent — skips if already queued)."""
    items = load_queue()
    # Idempotency: skip if already in queue
    if any(item["full_name"] == full_name for item in items):
        return
    items.append({
        "full_name":     full_name,
        "stars":         stars,
        "retry_count":   retry_count,
        "fingerprint":   fingerprint,
        "next_attempt_at": _now_iso(),   # eligible immediately
        "enqueued_at":   _now_iso(),
    })
    save_queue(items)
    log.info("Enrichment queue: enqueued %s (stars=%d)", full_name, stars)


def enqueue_priority(full_name: str, stars: int, fingerprint: str = "") -> None:
    """Push a repo to the FRONT of the enrichment queue for immediate processing.
    Removes any existing entry for the same repo first (de-dup + re-prioritise)."""
    items = load_queue()
    # Remove existing entry so we can re-insert at the front
    items = [it for it in items if it["full_name"] != full_name]
    priority_item = {
        "full_name":       full_name,
        "stars":           stars,
        "retry_count":     0,
        "fingerprint":     fingerprint,
        "next_attempt_at": _now_iso(),   # eligible immediately
        "enqueued_at":     _now_iso(),
        "_priority":       True,
    }
    items.insert(0, priority_item)
    save_queue(items)
    log.info("Enrichment queue: priority-enqueued %s (stars=%d)", full_name, stars)


def dequeue_next(provider_available: bool = True) -> dict | None:
    """
    Return the highest-star item whose next_attempt_at <= now and at least one
    free provider is available.  Returns None if nothing is ready.
    """
    if not provider_available:
        return None
    now_iso = _now_iso()
    items = load_queue()
    # Filter to ready items
    ready = [
        item for item in items
        if item.get("next_attempt_at", now_iso) <= now_iso
    ]
    if not ready:
        return None
    # Highest star count first
    ready.sort(key=lambda x: x.get("stars", 0), reverse=True)
    return ready[0]


def mark_failed(item: dict, reason: str) -> None:
    """Exponential backoff: 5 min × 2^retry (±20% jitter), max 4 hours.

    If retry_count exceeds MAX_RETRIES the item is permanently removed from the
    queue (quarantined) to prevent an unbounded retry storm.
    """
    items = load_queue()
    for i, q in enumerate(items):
        if q["full_name"] == item["full_name"]:
            retry = q.get("retry_count", 0) + 1
            if retry > MAX_RETRIES:
                log.warning(
                    "Enrichment queue: %s exceeded MAX_RETRIES (%d) — "
                    "removing from queue to prevent retry storm. Last error: %s",
                    item["full_name"], MAX_RETRIES, str(reason)[:200],
                )
                items = [q2 for q2 in items if q2["full_name"] != item["full_name"]]
                save_queue(items)
                return
            base_secs = min(5 * 60 * (2 ** retry), 4 * 3600)
            jitter = base_secs * 0.2 * (random.random() * 2 - 1)
            delay = max(300, int(base_secs + jitter))
            next_attempt = _iso_after_secs(delay)
            items[i] = {
                **q,
                "retry_count":     retry,
                "next_attempt_at": next_attempt,
                "last_error":      str(reason)[:200],
                "last_failed_at":  _now_iso(),
            }
            log.info("Enrichment queue: %s failed (%s), retry %d in %d s",
                     item["full_name"], reason[:60], retry, delay)
            break
    save_queue(items)


def mark_succeeded(item: dict) -> None:
    """Remove the item from the queue."""
    items = load_queue()
    items = [q for q in items if q["full_name"] != item["full_name"]]
    save_queue(items)
    log.info("Enrichment queue: %s succeeded — removed from backlog", item["full_name"])


def queue_depth() -> int:
    return len(load_queue())


def clear_queue() -> int:
    """Remove all items from the queue. Returns count removed."""
    items = load_queue()
    count = len(items)
    save_queue([])
    return count


# ── Provider availability helper ───────────────────────────────────────────────

def any_free_provider_available() -> bool:
    """Return True if at least one free provider (Groq or Gemini) is available."""
    try:
        import agents.provider_router as pr
        return pr._is_available("groq") or pr._is_available("gemini")
    except Exception:
        return False


# ── Scheduled enrichment run ───────────────────────────────────────────────────

def enrich_backlog() -> dict:
    """
    Process up to 3 backlog items per call.
    Called by the scheduler every 10 minutes.
    Respects the pause flag and provider availability.
    """
    if is_paused():
        log.info("Enrichment queue: paused — skipping run")
        return {"status": "paused", "processed": 0}

    if not any_free_provider_available():
        log.info("Enrichment queue: no free providers available — deferring")
        return {"status": "no_providers", "processed": 0}

    processed = enriched = failed = 0
    MAX_PER_RUN = 3

    # Pause semantics: is_paused() is checked at entry (above) AND between
    # items (below), but NEVER mid-item.  An item whose _enrich_one() call has
    # already started will always run to completion — pausing cannot abort
    # in-flight work.  Once it finishes, the between-item check prevents the
    # next item from starting.  This is intentional: do not add an is_paused()
    # call inside _enrich_one without revisiting this contract and updating the
    # test "test_pause_mid_run_does_not_abort_in_progress_item".
    for _ in range(MAX_PER_RUN):
        # Re-check pause between items so a pause requested while the previous
        # item was running takes effect before we start the next one.
        if is_paused():
            log.info("Enrichment queue: paused mid-run — stopping before next item")
            break
        item = dequeue_next(provider_available=True)
        if not item:
            break
        full_name = item["full_name"]
        log.info("Enrichment queue: enriching %s (retry=%d)", full_name, item.get("retry_count", 0))
        try:
            _enrich_one(item)
            mark_succeeded(item)
            enriched += 1
        except Exception as exc:
            log.warning("Enrichment queue: %s failed: %s", full_name, exc)
            mark_failed(item, str(exc))
            failed += 1
        processed += 1
        time.sleep(3)   # polite gap between API calls

    return {"status": "ok", "processed": processed, "enriched": enriched, "failed": failed}


def _enrich_one(item: dict) -> None:
    """Attempt AI enrichment for one backlog item. Raises on failure."""
    import agents.github_discovery as gd
    import app as _a

    full_name = item["full_name"]
    parts = full_name.split("/", 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid full_name: {full_name}")

    owner, repo_name = parts

    # Fetch current README
    readme = gd._fetch_readme(owner, repo_name)
    if not readme or len(readme) < 50:
        raise ValueError(f"README unavailable for {full_name}")

    # Build minimal repo dict
    index = _a.load_index()
    disc_log = gd.load_discovery_log()
    entry = disc_log.get(full_name, {})

    repo: dict[str, Any] = {
        "full_name":   full_name,
        "html_url":    f"https://github.com/{full_name}",
        "description": entry.get("description", ""),
        "stars":       item.get("stars", 0),
        "language":    entry.get("language", ""),
        "topics":      entry.get("topics", []),
        "owner":       owner,
        "name":        repo_name,
        "_readme_words": readme.split(),
    }

    # Extract using AI
    skill = gd._extract_from_repo(repo, readme, index)
    if skill is None:
        raise RuntimeError(f"Both lenses returned None for {full_name}")

    # Gate enrichment output — a DENY means the AI produced something weaker
    # than the baseline it would replace; raise so the item stays in the queue
    # for retry rather than overwriting a usable baseline with low-quality output.
    from agents.skill_quality import quality_gate, QualityDecision
    gate_report = quality_gate(skill)
    if gate_report.decision == QualityDecision.DENY:
        raise RuntimeError(
            f"Enrichment quality gate DENY for {full_name}: {gate_report.summary}"
        )
    log.info("Enrichment quality gate: %s → %s", full_name, gate_report.summary)

    # Save upgraded skill + update discovery log — both wrapped together so a
    # mid-run failure (e.g. disk write error) keeps _baseline=True in the index
    # and records the error in the discovery log for the next retry.
    try:
        skill_name, action = gd._save_discovered_skill(skill, repo, index)
        index = _a.load_index()

        # Sync to GitHub (non-fatal)
        try:
            import agents.github_sync as gs
            gs.sync_skill(skill_name, _a.SKILLS_DIR, index)
        except Exception as e:
            log.warning("GitHub sync failed for enriched skill %s: %s", skill_name, e)

        # Update discovery log to mark baseline cleared
        disc_log = gd.load_discovery_log()
        existing = disc_log.get(full_name, {})
        disc_log[full_name] = {
            **existing,
            "processed_at":       _now_iso(),
            "skill_name":         skill_name,
            "action":             "enriched",
            "enrichment_queued":  False,
            "enriched_at":        _now_iso(),
            "_baseline":          False,
        }
        gd.save_discovery_log(disc_log)
        log.info("Enrichment: upgraded %s → '%s' (%s)", full_name, skill_name, action)

    except Exception as save_exc:
        # The save or log-update failed after AI extraction succeeded.
        # _baseline remains True in the index (the skill write was incomplete).
        # Record the attempt in the discovery log so future retries have context,
        # then re-raise so enrich_backlog() calls mark_failed with backoff.
        reason = f"save_or_log_failed: {save_exc}"
        log.warning("Enrichment save/log failed for %s: %s", full_name, save_exc)
        try:
            disc_log = gd.load_discovery_log()
            existing = disc_log.get(full_name, {})
            disc_log[full_name] = {
                **existing,
                "_last_save_error":    str(save_exc)[:200],
                "_last_save_error_at": _now_iso(),
            }
            gd.save_discovery_log(disc_log)
        except Exception as log_exc:
            log.warning(
                "Could not update discovery log after save failure for %s: %s",
                full_name, log_exc,
            )
        raise RuntimeError(reason) from save_exc


# ── Time helpers ───────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _iso_after_secs(secs: int) -> str:
    from datetime import timedelta
    return (datetime.now(timezone.utc) + timedelta(seconds=secs)).isoformat(timespec="seconds")
