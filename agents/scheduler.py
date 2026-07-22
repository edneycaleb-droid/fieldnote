"""
Fieldnote Scheduler — autonomous 24/7 background agents.

Three built-in jobs:
  enhance   — every 6 h: DCA enhancement queue, re-run due skills
  sync      — every 24 h: full GitHub push
  watchlist — every 1 h: process any new URLs in watchlist.json

The scheduler runs as a daemon thread inside the Flask process.
Use start() at app startup, stop() on shutdown, status() for the API.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Callable, Optional

log = logging.getLogger("fieldnote.scheduler")


# ── Job record ────────────────────────────────────────────────────────────────

@dataclass
class Job:
    name:          str
    description:   str
    interval_secs: int
    fn:            Callable
    enabled:       bool = True
    # runtime state (not serialised to disk)
    running:       bool = False
    last_run:      Optional[str] = None   # ISO-8601 UTC
    next_run:      Optional[str] = None   # ISO-8601 UTC
    runs_ok:       int = 0
    runs_err:      int = 0
    last_error:    Optional[str] = None
    last_result:   Optional[dict] = None

    def to_dict(self) -> dict:
        return {
            "name":          self.name,
            "description":   self.description,
            "interval_secs": self.interval_secs,
            "enabled":       self.enabled,
            "running":       self.running,
            "last_run":      self.last_run,
            "next_run":      self.next_run,
            "runs_ok":       self.runs_ok,
            "runs_err":      self.runs_err,
            "last_error":    self.last_error,
            "last_result":   self.last_result,
        }


# ── Scheduler ─────────────────────────────────────────────────────────────────

class SchedulerAgent:
    def __init__(self):
        self._jobs: list[Job] = []
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._started_at: Optional[str] = None
        self._wake_callbacks: list[Callable] = []

    # ── Wake callbacks ────────────────────────────────────────────────────────

    def register_wake_callback(self, fn: Callable) -> None:
        """Register *fn* to be called when the scheduler detects a clock jump
        (i.e. the container was paused/resumed without a full restart).

        All wake callbacks are fired from the scheduler thread before the next
        job tick is processed, so they should be fast and non-blocking.
        """
        with self._lock:
            self._wake_callbacks.append(fn)

    # ── Registration ──────────────────────────────────────────────────────────

    def register(self, name: str, description: str, interval_hours: float,
                 fn: Callable, enabled: bool = True) -> None:
        secs = int(interval_hours * 3600)
        with self._lock:
            if any(j.name == name for j in self._jobs):
                log.debug("Scheduler: job '%s' already registered — skipping", name)
                return
            job = Job(
                name=name, description=description, interval_secs=secs,
                fn=fn, enabled=enabled,
                next_run=_iso_after_secs(secs // 4),   # first run after 25% of interval
            )
            self._jobs.append(job)
        log.info("Scheduler: registered job '%s' every %.1f h", name, interval_hours)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            log.debug("Scheduler: already running — ignoring duplicate start()")
            return
        self._stop_event.clear()
        self._started_at = _now_iso()
        self._thread = threading.Thread(target=self._loop, daemon=True,
                                        name="fieldnote-scheduler")
        self._thread.start()
        log.info("Scheduler started — %d jobs registered", len(self._jobs))

    def stop(self) -> None:
        self._stop_event.set()

    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    # ── Status / manual trigger ───────────────────────────────────────────────

    def status(self) -> dict:
        with self._lock:
            jobs = [j.to_dict() for j in self._jobs]
        return {
            "running":    self.is_running(),
            "started_at": self._started_at,
            "jobs":       jobs,
        }

    def run_now(self, job_name: str) -> dict:
        """Trigger a job immediately (non-blocking — spawns a thread)."""
        with self._lock:
            job = next((j for j in self._jobs if j.name == job_name), None)
        if not job:
            return {"ok": False, "error": f"Unknown job: {job_name}"}
        if job.running:
            return {"ok": False, "error": "Already running"}
        threading.Thread(target=self._run_job, args=(job,),
                         daemon=True, name=f"fn-job-{job_name}").start()
        return {"ok": True, "job": job_name}

    def set_enabled(self, job_name: str, enabled: bool) -> dict:
        with self._lock:
            job = next((j for j in self._jobs if j.name == job_name), None)
        if not job:
            return {"ok": False, "error": f"Unknown job: {job_name}"}
        job.enabled = enabled
        return {"ok": True, "job": job_name, "enabled": enabled}

    # ── Internal loop ─────────────────────────────────────────────────────────

    def _loop(self) -> None:
        TICK = 30  # seconds between scheduler wakeups
        # Clock-drift threshold: if a tick takes more than 2× TICK the process
        # was almost certainly paused (Replit sleep / container freeze).
        DRIFT_THRESHOLD = TICK * 2
        last_tick = time.time()

        while not self._stop_event.is_set():
            now = time.time()
            elapsed = now - last_tick
            last_tick = now

            # Detect container pause / Replit sleep: wall-clock jumped forward
            # by far more than the expected tick interval.
            if elapsed > DRIFT_THRESHOLD:
                log.warning(
                    "Scheduler: clock drift detected (%.0f s gap) — "
                    "container was likely paused; firing %d wake callback(s)",
                    elapsed, len(self._wake_callbacks),
                )
                with self._lock:
                    cbs = list(self._wake_callbacks)
                for cb in cbs:
                    try:
                        cb()
                    except Exception as exc:
                        log.error("Scheduler: wake callback %r raised: %s", cb, exc)

            with self._lock:
                due = [j for j in self._jobs
                       if j.enabled
                       and not j.running
                       and j.next_run is not None
                       and _iso_to_ts(j.next_run) <= now]
            for job in due:
                threading.Thread(target=self._run_job, args=(job,),
                                 daemon=True, name=f"fn-job-{job.name}").start()
            self._stop_event.wait(timeout=TICK)

    def _run_job(self, job: Job) -> None:
        job.running  = True
        job.last_run = _now_iso()
        log.info("Scheduler: running job '%s'", job.name)
        try:
            result        = job.fn()
            job.runs_ok  += 1
            job.last_result = result
            job.last_error  = None
            log.info("Scheduler: job '%s' OK → %s", job.name, result)
        except Exception as exc:
            job.runs_err += 1
            job.last_error  = str(exc)
            job.last_result = None
            log.error("Scheduler: job '%s' ERROR → %s", job.name, exc)
        finally:
            job.running  = False
            job.next_run = _iso_after_secs(job.interval_secs)


# ── Time helpers ──────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def _iso_after_secs(secs: int) -> str:
    return datetime.fromtimestamp(time.time() + secs, tz=timezone.utc).isoformat(timespec="seconds")

def _iso_to_ts(iso: str) -> float:
    try:
        return datetime.fromisoformat(iso).timestamp()
    except Exception:
        return 0.0


# ── Singleton ─────────────────────────────────────────────────────────────────

scheduler = SchedulerAgent()
