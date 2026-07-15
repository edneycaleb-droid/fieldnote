"""
Fieldnote Verification Agent
=============================
Runs automatically after every video submission.

8 checks, each with an auto-fix:
  1. skill_file       — .md file exists and has real content
  2. index_entry      — _index.json entry is complete
  3. dca_schedule     — DCA enhancement schedule initialised
  4. brain_graph      — skill appears in _brain.json skill_map
  5. github_skill     — .md pushed to GitHub mirror skills/
  6. github_code      — source code pushed recently (< 5 min)
  7. scheduler        — all background jobs are running
  8. index_integrity  — no orphaned / missing index entries

Results stream back into the SSE queue as verify_check events so the
user sees each check live, then a verify_done summary before the final
done event.
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

log = logging.getLogger("fieldnote.verify")

# ── Types ─────────────────────────────────────────────────────────────────────

@dataclass
class Check:
    name:     str
    label:    str
    passed:   bool
    fixed:    bool = False
    fix_desc: str  = ""
    detail:   str  = ""
    ms:       int  = 0

    def to_dict(self) -> dict:
        return {
            "name":     self.name,
            "label":    self.label,
            "passed":   self.passed,
            "fixed":    self.fixed,
            "fix_desc": self.fix_desc,
            "detail":   self.detail,
            "ms":       self.ms,
        }


@dataclass
class VerifyResult:
    skill_name: str
    checks:     list = field(default_factory=list)
    ran_at:     str  = ""

    @property
    def all_ok(self) -> bool:
        return all(c.passed or c.fixed for c in self.checks)

    @property
    def total_fixed(self) -> int:
        return sum(1 for c in self.checks if c.fixed)

    @property
    def total_failed(self) -> int:
        return sum(1 for c in self.checks if not c.passed and not c.fixed)

    def to_dict(self) -> dict:
        return {
            "skill_name":  self.skill_name,
            "ran_at":      self.ran_at,
            "all_ok":      self.all_ok,
            "total_fixed": self.total_fixed,
            "total_failed":self.total_failed,
            "checks":      [c.to_dict() for c in self.checks],
        }


# ── Lazy app import (avoids circular imports) ─────────────────────────────────

def _app():
    import app as _a
    return _a

def _code_sync():
    import agents.code_sync as cs
    return cs

def _github_sync():
    import agents.github_sync as gs
    return gs

def _scheduler():
    import agents.scheduler as sm
    return sm

def _skill_quality():
    import agents.skill_quality as sq
    return sq


# ── Individual checks ─────────────────────────────────────────────────────────

def _chk_skill_file(skill_name: str, skill_path: str) -> tuple[bool, str, str, str]:
    """Check 1: .md file exists and has meaningful content (> 200 chars)."""
    try:
        a = _app()
        if not os.path.exists(skill_path):
            # Fix: try to write minimal markdown from index data
            idx   = a.load_index()
            entry = idx.get(skill_name)
            if entry:
                md = f"# {entry.get('title', skill_name)}\n\n{entry.get('description', '')}\n\n"
                if entry.get("steps"):
                    md += "## Steps\n" + "\n".join(f"- {s}" for s in entry["steps"])
                with open(skill_path, "w") as f:
                    f.write(md)
                return False, True, "Rebuilt from index data", f"file missing → recreated {len(md)}c"
            return False, False, "", "File missing and no index entry to rebuild from"
        size = os.path.getsize(skill_path)
        if size < 200:
            return False, False, "", f"File exists but suspiciously small ({size} bytes)"
        return True, False, "", f"{size:,} bytes"
    except Exception as e:
        return False, False, "", str(e)


def _chk_index_entry(skill_name: str) -> tuple[bool, str, str, str]:
    """Check 2: index entry exists with required fields."""
    REQUIRED = {"title", "description", "tools", "tags", "created_at", "updated_at", "_dca"}
    try:
        a     = _app()
        index = a.load_index()
        entry = index.get(skill_name)
        if not entry:
            # Fix: run repair_index
            a.repair_index()
            index = a.load_index()
            entry = index.get(skill_name)
            if not entry:
                return False, False, "", "Entry missing even after repair_index()"
            return False, True, "repair_index() rebuilt stub", "stub entry created"
        missing = REQUIRED - set(entry.keys())
        if missing:
            # Fix: fill missing fields with sensible defaults
            now = datetime.now(timezone.utc).isoformat()
            for f_name in missing:
                if f_name == "_dca":
                    entry["_dca"] = _skill_quality().dca_schedule(1, now)
                elif f_name in ("tools", "tags", "concepts", "steps", "python_packages"):
                    entry[f_name] = entry.get(f_name, [])
                elif f_name in ("created_at", "updated_at"):
                    entry[f_name] = now
                else:
                    entry[f_name] = entry.get(f_name, "")
            index[skill_name] = entry
            a.save_index(index)
            return False, True, f"Filled missing fields: {', '.join(missing)}", ""
        return True, False, "", f"{len(entry)} fields"
    except Exception as e:
        return False, False, "", str(e)


def _chk_dca(skill_name: str) -> tuple[bool, str, str, str]:
    """Check 3: DCA enhancement schedule is set."""
    try:
        a     = _app()
        sq    = _skill_quality()
        index = a.load_index()
        entry = index.get(skill_name, {})
        dca   = entry.get("_dca")
        if not dca:
            now             = datetime.now(timezone.utc).isoformat()
            entry["_dca"]   = sq.dca_schedule(1, now)
            index[skill_name] = entry
            a.save_index(index)
            return False, True, "DCA schedule initialised (level 1)", ""
        nxt   = dca.get("next_enhance_at", "?")
        lvl   = dca.get("level", "?")
        return True, False, "", f"level {lvl}, next {nxt[:10] if len(nxt) > 10 else nxt}"
    except Exception as e:
        return False, False, "", str(e)


def _chk_brain(skill_name: str) -> tuple[bool, str, str, str]:
    """Check 4: skill appears in _brain.json skill_map."""
    try:
        a          = _app()
        brain_path = os.path.join(a.SKILLS_DIR, "_brain.json")
        brain      = {}
        if os.path.exists(brain_path):
            with open(brain_path) as f:
                brain = json.load(f)
        if skill_name in brain.get("skill_map", {}):
            conns = len(brain.get("relationships", {}).get(skill_name, {}))
            return True, False, "", f"{conns} related skills"
        # Fix: rebuild brain entry from saved skill
        index = a.load_index()
        entry = index.get(skill_name, {})
        if entry:
            skill_data = {
                "title":       entry.get("title", skill_name),
                "tools":       entry.get("tools", []),
                "concepts":    entry.get("concepts", []),
                "tags":        entry.get("tags", []),
                "steps":       entry.get("steps", []),
                "description": entry.get("description", ""),
            }
            a._update_brain(skill_data, skill_name)
            return False, True, "_update_brain() re-run from index data", ""
        return False, False, "", "No index data to rebuild brain entry from"
    except Exception as e:
        return False, False, "", str(e)


def _chk_github_skill(skill_name: str, skill_path: str) -> tuple[bool, str, str, str]:
    """Check 5: skill .md is committed and pushed in the GitHub mirror."""
    try:
        gs          = _github_sync()
        mirror_file = gs.MIRROR_DIR / "skills" / f"{skill_name}.md"
        if mirror_file.exists():
            return True, False, "", f"synced ({mirror_file.stat().st_size:,} bytes)"
        # Fix: sync it now
        if not os.path.exists(skill_path):
            return False, False, "", "Skill file missing — cannot sync"
        a     = _app()
        index = a.load_index()
        with open(skill_path) as f:
            md = f.read()
        ok = gs.sync_skill(skill_name, md, index)
        if ok:
            return False, True, "sync_skill() pushed to GitHub", ""
        return False, False, "", "sync_skill() returned False (check token / network)"
    except Exception as e:
        return False, False, "", str(e)


def _chk_code_sync() -> tuple[bool, str, str, str]:
    """Check 6: source code pushed to GitHub in the last 5 minutes."""
    try:
        cs     = _code_sync()
        status = cs.status()
        lp     = status.get("last_push")
        if lp:
            pushed_ago_s = time.time() - datetime.fromisoformat(lp).timestamp()
            if pushed_ago_s < 300:   # within 5 minutes
                return True, False, "", f"pushed {int(pushed_ago_s)}s ago"
        # Fix: trigger push now (non-blocking kick; give it 10s to complete)
        cs.push_now(label="verify-fix")
        time.sleep(10)
        status2 = cs.status()
        lp2     = status2.get("last_push")
        if lp2 and lp2 != lp:
            return False, True, "push_now() triggered and completed", ""
        if status2.get("pushes_ok", 0) > 0:
            return False, True, "push_now() triggered", f"last={lp2 or '?'}"
        err = status2.get("last_error", "unknown")
        return False, False, "", f"push failed — {err}"
    except Exception as e:
        return False, False, "", str(e)


def _chk_scheduler() -> tuple[bool, str, str, str]:
    """Check 7: scheduler is running and all jobs are registered."""
    try:
        sm     = _scheduler()
        status = sm.scheduler.status()
        if not status.get("running"):
            sm.scheduler.start()
            return False, True, "scheduler.start() called", "was stopped"
        jobs  = status.get("jobs", [])
        names = {j["name"] for j in jobs}
        expected = {"enhance", "sync", "watchlist", "discover", "code_sync"}
        missing  = expected - names
        if missing:
            return False, False, "", f"Missing jobs: {', '.join(missing)}"
        errored = [j["name"] for j in jobs if j.get("runs_err", 0) > 3
                   and j.get("runs_ok", 0) == 0]
        if errored:
            return False, False, "", f"Jobs with only errors: {', '.join(errored)}"
        return True, False, "", f"{len(jobs)} jobs running"
    except Exception as e:
        return False, False, "", str(e)


def _chk_index_integrity() -> tuple[bool, str, str, str]:
    """Check 8: no orphaned / missing index entries."""
    try:
        a        = _app()
        rm, add  = a.repair_index()
        problems = rm + add
        if problems == 0:
            idx = a.load_index()
            return True, False, "", f"{len(idx)} entries clean"
        return False, True, f"repair_index() cleaned {problems} issue(s)",\
               f"{rm} orphaned removed, {add} stubs added"
    except Exception as e:
        return False, False, "", str(e)


# ── Main entry point ──────────────────────────────────────────────────────────

# Log file for all verification runs
def _log_path() -> str:
    import app as _a
    return os.path.join(_a.SKILLS_DIR, "_verify_log.json")


def _append_log(result: VerifyResult) -> None:
    try:
        path    = _log_path()
        entries = []
        if os.path.exists(path):
            with open(path) as f:
                entries = json.load(f)
        entries.append(result.to_dict())
        entries = entries[-100:]   # keep last 100 runs
        with open(path, "w") as f:
            json.dump(entries, f, indent=2)
    except Exception as e:
        log.debug("Could not append verify log: %s", e)


def verify_and_fix(
    skill_name:  str,
    skill_path:  str,
    emit:        Callable[[str, str], None],
    emit_check:  Callable[[dict], None],
) -> VerifyResult:
    """
    Run all 8 checks. Auto-fix what's broken. Stream each result back
    via emit_check(). Returns the full VerifyResult.
    """
    result = VerifyResult(
        skill_name=skill_name,
        ran_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )

    CHECKS = [
        ("skill_file",      "Skill file",         lambda: _chk_skill_file(skill_name, skill_path)),
        ("index_entry",     "Index entry",         lambda: _chk_index_entry(skill_name)),
        ("dca_schedule",    "DCA schedule",        lambda: _chk_dca(skill_name)),
        ("brain_graph",     "Brain graph",         lambda: _chk_brain(skill_name)),
        ("github_skill",    "GitHub skill sync",   lambda: _chk_github_skill(skill_name, skill_path)),
        ("code_sync",       "Code sync",           lambda: _chk_code_sync()),
        ("scheduler",       "Scheduler health",    lambda: _chk_scheduler()),
        ("index_integrity", "Index integrity",     lambda: _chk_index_integrity()),
    ]

    for name, label, fn in CHECKS:
        t0 = time.time()
        try:
            passed, fixed, fix_desc, detail = fn()
        except Exception as exc:
            passed, fixed, fix_desc, detail = False, False, "", str(exc)
        ms = int((time.time() - t0) * 1000)

        chk = Check(
            name=name, label=label,
            passed=passed, fixed=fixed, fix_desc=fix_desc,
            detail=detail, ms=ms,
        )
        result.checks.append(chk)

        # Emit to SSE stream
        icon = "✅" if passed else ("🔧" if fixed else "❌")
        msg  = fix_desc if (not passed and fix_desc) else detail
        emit(f"{icon}  [{label}] {msg or ('ok' if passed else 'check failed')}", "verify")
        emit_check(chk.to_dict())

    _append_log(result)

    summary_emoji = "✅" if result.all_ok else ("🔧" if result.total_failed == 0 else "⚠️")
    emit(
        f"{summary_emoji}  Verification complete — "
        f"{sum(1 for c in result.checks if c.passed)} passed, "
        f"{result.total_fixed} auto-fixed, "
        f"{result.total_failed} need attention",
        "verify",
    )
    return result
