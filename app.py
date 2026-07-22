"""
Fieldnote — YouTube → AI Skills Pipeline  (v4 — intelligent self-improvement)

Transcript strategy (never gives up):
  1. YouTube caption API  — instant, no download
  2. Groq Whisper via yt-dlp — works on any public video
  3. Partial audio (first 20 min) — for videos too large for Whisper

Parallel execution (3 phases):
  Phase 1 │ metadata fetch  ║  transcript fetch
  Phase 2 │ AI extraction   ║  GitHub repo search (quick-scan tools)
  Phase 3 │ save skill      ║  install packages  ║  MCP setup
          ║  clone repos    ║  supplemental GitHub search (AI-extracted tools)

Self-improvement principles:
  • Enhance: AI receives FULL existing skill markdown — never overwrites blindly
  • Knowledge context: relevance-scored, includes full markdown for top 5 candidates
  • Sources: every contributing video is permanently recorded in the skill
  • History: metadata index tracks every enhancement with timestamp + source
  • Dedup: tools/tags/concepts/packages merged and deduplicated on enhance
  • Supplemental search: AI-identified tools (not in quick-scan) get their own
    GitHub search pass in Phase 3
"""
import os, re, json, subprocess, sys, tempfile, threading, queue, uuid, shutil, secrets as _secrets, time, random, logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from urllib.request import urlopen, Request as _UReq
from urllib.parse import urlencode as _urlencode

from flask import Flask, render_template, request, jsonify, Response, stream_with_context, redirect

log = logging.getLogger("fieldnote.app")
from groq import Groq
from openai import OpenAI

import agents.github_agent  as github_agent
import agents.mcp_agent     as mcp_agent
import agents.github_sync   as github_sync
import agents.skill_quality as skill_quality
import agents.scheduler       as scheduler_mod
import agents.auto_agent      as auto_agent
import agents.github_discovery as github_discovery
import agents.code_sync        as code_sync
import agents.verify_agent     as verify_agent
import agents.pipeline_guard   as pipeline_guard
import agents.provider_router  as provider_router
import agents.transcript_pipeline as transcript_pipeline
import agents.skill_validator   as skill_validator
import agents.run_checkpoint    as run_checkpoint
import agents.degraded_mode     as degraded_mode

app = Flask(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
SKILLS_DIR    = "fieldnote_skills"
METADATA_FILE = os.path.join(SKILLS_DIR, "_index.json")
os.makedirs(SKILLS_DIR, exist_ok=True)

GROQ_API_KEY   = os.getenv("GROQ_API_KEY") or os.getenv("GROQ")
GROQ_MODELS    = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "llama3-8b-8192"]
OPENAI_API_KEY = os.getenv("CHATGPT") or os.getenv("OPENAI_API_KEY")
OPENAI_MODELS  = ["gpt-4o-mini", "gpt-4o"]
WHISPER_MODEL = "whisper-large-v3"
MAX_AUDIO_MB  = 24
CLIP_SECONDS  = 1200  # 20-min clip when audio too large

_jobs: dict = {}          # {job_id: {"queue": Queue, "done": bool}}
_playlist_jobs: dict = {}  # {pjob_id: {"events": list, "done": bool, "total": int}}
_video_active: dict = {}   # {video_id: job_id} — jobs currently in-flight (dedup guard)
_mcp_sessions: dict = {}   # {session_id: queue.Queue}
_enrich_in_progress: set = set()   # {full_name} — manual enrich threads currently running
_enrich_in_progress_lock = threading.Lock()


# ── Local key store ────────────────────────────────────────────────────────────
# Keys saved here are merged into os.environ at startup and after each save.
# Users never need to open Replit Secrets — paste once in the UI and go.

LOCAL_KEYS_FILE = os.path.join("fieldnote_mcp", "local_keys.json")


def load_local_keys() -> None:
    """Merge local_keys.json into os.environ. Safe to call repeatedly."""
    if not os.path.exists(LOCAL_KEYS_FILE):
        return
    try:
        with open(LOCAL_KEYS_FILE) as f:
            keys: dict = json.load(f)
        for name, value in keys.items():
            if value:  # local store always wins — represents most recent user action
                os.environ[name] = str(value)
        # Refresh module-level API key var
        global GROQ_API_KEY, OPENAI_API_KEY
        GROQ_API_KEY   = os.getenv("GROQ_API_KEY") or os.getenv("GROQ")
        OPENAI_API_KEY = os.getenv("CHATGPT") or os.getenv("OPENAI_API_KEY")
        # Refresh github_agent token attribute
        github_agent._GH_TOKEN = (
            os.getenv("GITHUBPAT") or os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN") or os.getenv("GITHUB") or ""
        )
    except Exception:
        pass


def save_local_key(name: str, value: str) -> None:
    """Persist a key and activate it in the current process immediately."""
    os.makedirs("fieldnote_mcp", exist_ok=True)
    keys: dict = {}
    if os.path.exists(LOCAL_KEYS_FILE):
        try:
            with open(LOCAL_KEYS_FILE) as f:
                keys = json.load(f)
        except Exception:
            pass
    keys[name] = value
    with open(LOCAL_KEYS_FILE, "w") as f:
        json.dump(keys, f, indent=2)
    os.environ[name] = value
    load_local_keys()


# Activate any previously saved keys on startup
os.makedirs("fieldnote_mcp", exist_ok=True)
load_local_keys()
os.makedirs(SKILLS_DIR, exist_ok=True)   # ensure skills dir exists before repair


# ── Metadata index ────────────────────────────────────────────────────────────

def load_index() -> dict:
    if os.path.exists(METADATA_FILE):
        try:
            with open(METADATA_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_index(index: dict):
    # Atomic write — never leave a half-written index on crash
    _tmp = METADATA_FILE + ".tmp"
    with open(_tmp, "w") as f:
        json.dump(index, f, indent=2, default=str)
    os.replace(_tmp, METADATA_FILE)


def repair_index() -> tuple[int, int]:
    """Remove index entries with no .md file; add stub entries for .md files not in index.
    Returns (removed, added) counts. Safe to call at startup."""
    index   = load_index()
    md_names = {f[:-3] for f in os.listdir(SKILLS_DIR) if f.endswith(".md")}
    removed  = 0
    added    = 0
    for name in list(index.keys()):
        if name not in md_names:
            del index[name]
            removed += 1
    for name in md_names:
        if name not in index:
            index[name] = {"title": name, "created_at": datetime.now(timezone.utc).isoformat()}
            added += 1
    if removed or added:
        save_index(index)
    return removed, added


# Run at startup to fix any index/file mismatches from manual edits or crashes
try:
    _rm, _add = repair_index()
    if _rm or _add:
        print(f"[fieldnote] Index repaired: {_rm} removed, {_add} added", flush=True)
except Exception:
    pass  # non-fatal; best-effort

# Reset stale 'connected' MCP hub badges — servers haven't been verified since the last restart.
# The first _mcp_health_check tick (≤15 min after boot) will resolve each back to
# 'connected' or 'offline'. Until then the UI shows an amber 'Checking…' badge instead of
# a false green 'Connected'.
try:
    from agents.mcp_registry import mark_connected_as_unverified as _mark_unverified
    _reset = _mark_unverified()
    if _reset:
        print(f"[fieldnote] MCP hub: {_reset} server(s) reset to 'unverified' (pending first health check)", flush=True)
except Exception as _mue:
    print(f"[fieldnote] MCP hub unverified reset skipped: {_mue}", flush=True)

# Migrate any action:"error" discovery log entries → enrichment backlog.
# Must run AFTER SKILLS_DIR is guaranteed to exist (i.e. here, not at module import).
try:
    import agents.github_discovery as _gd_boot
    _migrated = _gd_boot._migrate_errors_to_backlog()
    if _migrated:
        print(f"[fieldnote] Discovery migration: {_migrated} error entries → enrichment backlog",
              flush=True)
except Exception as _me:
    print(f"[fieldnote] Discovery migration skipped: {_me}", flush=True)


def list_skills() -> list[dict]:
    index = load_index()
    skills = []
    for fname in os.listdir(SKILLS_DIR):
        if not fname.endswith(".md"):
            continue
        name = fname[:-3]
        meta = index.get(name, {})
        skills.append({
            "file":         fname,
            "name":         name,
            "title":        meta.get("title") or name,
            "description":  meta.get("description", ""),
            "tags":         _nsl(meta.get("tags")),
            "tools":        _nsl(meta.get("tools")),
            "source_title": meta.get("source_title", ""),
            "source_url":   meta.get("source_url", ""),
            "video_id":     meta.get("video_id", ""),
            "method":       meta.get("method", ""),
            "action":       meta.get("action", "create"),
            "created_at":   meta.get("created_at", ""),
            "updated_at":   meta.get("updated_at", ""),
            "_baseline":    meta.get("_baseline", False),
            "_enrich_error": meta.get("_enrich_error", ""),
        })
    return sorted(
        skills,
        key=lambda x: x.get("updated_at") or x.get("created_at") or "",
        reverse=True,
    )


def get_global_stats() -> dict:
    index     = load_index()
    all_tools: set = set()
    all_pkgs:  set = set()
    baseline_count = 0
    for m in index.values():
        all_tools.update(_nsl(m.get("tools")))
        all_pkgs.update(_nsl(m.get("python_packages")))
        if m.get("_baseline"):
            baseline_count += 1

    repos_dir  = "fieldnote_repos"
    repo_count = sum(
        1 for d in os.listdir(repos_dir)
        if os.path.isdir(os.path.join(repos_dir, d))
    ) if os.path.exists(repos_dir) else 0

    try:
        import agents.discovery_enrichment as _de
        enrichment_queue = _de.queue_depth()
    except Exception:
        enrichment_queue = 0

    return {
        "skills":           len(index),
        "tools":            len(all_tools),
        "packages":         len(all_pkgs),
        "repos":            repo_count,
        "mcp":              len(mcp_agent.get_connections()),
        "baseline_count":   baseline_count,
        "enrichment_queue": enrichment_queue,
    }


def get_all_tags() -> list[str]:
    index = load_index()
    tags: set = set()
    for m in index.values():
        tags.update(_nsl(m.get("tags")))
    return sorted(tags)


# ── Knowledge context (self-improvement engine) ───────────────────────────────

def _relevance_score(meta: dict, quick_tools: list[str]) -> int:
    """Score a skill's relevance to the current video's quick-scan tools."""
    if not quick_tools:
        return 0
    skill_tokens = set(
        t.lower()
        for t in _nsl(meta.get("tools")) + _nsl(meta.get("tags")) + _nsl(meta.get("concepts"))
    )
    score = 0
    for qt in quick_tools:
        qt_l = qt.lower()
        for tok in skill_tokens:
            if qt_l in tok or tok in qt_l:
                score += 2
                break
    return score


def get_skills_context(quick_tools: list[str] | None = None) -> str:
    """
    Build the richest possible knowledge context for the AI prompt.

    Structure:
      1. Relevance-scored index of all skills (name, description, tools, tags, steps preview)
      2. Full markdown of the 5 most relevant skills so the AI can enhance intelligently
         instead of guessing what already exists.
    """
    index = load_index()
    if not index:
        return "No existing skills yet — this is the first one."

    # Score and sort skills by relevance to current video
    scored = sorted(
        (((_relevance_score(m, quick_tools or []), name, m) for name, m in index.items())),
        key=lambda x: x[0],
        reverse=True,
    )

    lines: list[str] = ["=== EXISTING SKILL INDEX ===\n"]
    for _, name, m in scored[:30]:
        tools    = ", ".join(_nsl(m.get("tools"))[:6]) or "none"
        tags     = ", ".join(_nsl(m.get("tags"))[:4]) or "none"
        concepts = ", ".join(_nsl(m.get("concepts"))[:4]) or "none"
        pkgs     = ", ".join(_nsl(m.get("python_packages"))[:4]) or "none"
        steps_preview = "; ".join(_nsl(m.get("steps"))[:2])
        sources_count = len(m.get("history", [])) + 1
        lines.append(
            f"SKILL: {name}\n"
            f"  title: {m.get('title','')}\n"
            f"  description: {m.get('description','')[:180]}\n"
            f"  tools: {tools}\n"
            f"  tags: {tags}\n"
            f"  concepts: {concepts}\n"
            f"  packages: {pkgs}\n"
            + (f"  steps preview: {steps_preview[:160]}\n" if steps_preview else "")
            + f"  sources: {sources_count} video(s)\n"
        )

    # Full markdown for top 5 most relevant skills
    top_with_content = [
        (score, name, m) for score, name, m in scored[:5]
        if os.path.exists(os.path.join(SKILLS_DIR, f"{name}.md"))
    ]
    if top_with_content:
        lines.append("\n=== FULL CONTENT OF TOP RELEVANT SKILLS ===\n")
        for _, name, _ in top_with_content:
            md_path = os.path.join(SKILLS_DIR, f"{name}.md")
            try:
                with open(md_path) as f:
                    content = f.read()
                lines.append(f"--- BEGIN: {name} ---\n{content[:2500]}\n--- END: {name} ---\n")
            except Exception:
                pass

    return "\n".join(lines)


# ── Source section helpers ────────────────────────────────────────────────────

def _extract_sources(markdown: str) -> list[dict]:
    """Parse the ## Sources table from existing skill markdown."""
    sources: list[dict] = []
    in_sources = False
    for line in markdown.splitlines():
        stripped = line.strip()
        if re.match(r'^#+\s*sources', stripped, re.IGNORECASE):
            in_sources = True
            continue
        if in_sources:
            if stripped.startswith("#"):
                break
            m = re.search(r'\|\s*(\d{4}-\d{2}-\d{2})\s*\|\s*\[([^\]]+)\]\(([^)]+)\)\s*\|\s*(\w*)', line)
            if m:
                sources.append({
                    "date":   m.group(1),
                    "title":  m.group(2),
                    "url":    m.group(3),
                    "method": m.group(4),
                })
    return sources


def _build_sources_section(sources: list[dict]) -> str:
    """Render a ## Sources markdown table, deduped by URL."""
    seen: set[str] = set()
    unique = []
    for s in sources:
        if s.get("url") and s["url"] not in seen:
            seen.add(s["url"])
            unique.append(s)
    if not unique:
        return ""
    rows = "\n".join(
        f"| {s.get('date','')} "
        f"| [{s.get('title','Source')}]({s.get('url','#')}) "
        f"| {s.get('method','')} |"
        for s in unique
    )
    return (
        "\n\n## Sources\n\n"
        "| Date | Video | Transcript |\n"
        "|------|-------|------------|\n"
        f"{rows}\n"
    )



def _nsl(v) -> list:
    """Null-safe list — returns [] for None; splits comma-strings; passes lists through.
    Safe replacement for dict.get('key', []) when value may be null in LLM/disk JSON:
    dict.get('key', []) returns None if key exists with null value; _nsl(d.get('key')) is safe."""
    if isinstance(v, list): return v
    if v is None:           return []
    if isinstance(v, str):  return [x.strip() for x in v.split(",") if x.strip()]
    return []

def _dedup_list(new_items, old_items) -> list:
    """Merge two lists, deduplicating case-insensitively, preserving order.
    Accepts None for either argument — treated as empty list."""
    seen: set[str] = set()
    result: list   = []
    for item in _nsl(new_items) + _nsl(old_items):
        key = str(item).lower().strip()
        if key not in seen and key:
            seen.add(key)
            result.append(item)
    return result


# ── YouTube helpers ───────────────────────────────────────────────────────────

def normalize_youtube_url(url: str) -> str:
    """Expand short/mobile YouTube URLs to a canonical form."""
    url = url.strip()
    # m.youtube.com → www.youtube.com
    url = re.sub(r"https?://m\.youtube\.com", "https://www.youtube.com", url)
    # music.youtube.com → www.youtube.com
    url = re.sub(r"https?://music\.youtube\.com", "https://www.youtube.com", url)
    # youtu.be/<id> → youtube.com/watch?v=<id>
    m = re.match(r"https?://youtu\.be/([a-zA-Z0-9_-]{11})(.*)", url)
    if m:
        tail = m.group(2)  # may contain ?list=... etc.
        url = f"https://www.youtube.com/watch?v={m.group(1)}{tail.replace('?', '&', 1) if tail.startswith('?') else tail}"
    return url


def extract_video_id(url: str) -> str | None:
    url = normalize_youtube_url(url)
    for p in [
        r"[?&]v=([a-zA-Z0-9_-]{11})",
        r"youtube\.com/embed/([a-zA-Z0-9_-]{11})",
        r"youtube\.com/shorts/([a-zA-Z0-9_-]{11})",
        r"youtube\.com/v/([a-zA-Z0-9_-]{11})",
    ]:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None


def extract_playlist_id(url: str) -> str | None:
    url = normalize_youtube_url(url)
    m = re.search(r"[?&]list=([a-zA-Z0-9_-]+)", url)
    return m.group(1) if m else None


def get_video_metadata(video_id: str) -> dict:
    try:
        oembed = (
            f"https://www.youtube.com/oembed"
            f"?url=https://youtube.com/watch?v={video_id}&format=json"
        )
        with urlopen(oembed, timeout=6) as r:
            d = json.loads(r.read())
        return {
            "title":     d.get("title", ""),
            "author":    d.get("author_name", ""),
            "thumbnail": d.get("thumbnail_url",
                               f"https://img.youtube.com/vi/{video_id}/mqdefault.jpg"),
        }
    except Exception:
        return {
            "title":     "",
            "author":    "",
            "thumbnail": f"https://img.youtube.com/vi/{video_id}/mqdefault.jpg",
        }


def get_playlist_video_ids(playlist_id: str) -> list[str]:
    """
    Return ALL video IDs from a playlist (no cap).
    Robust against yt-dlp deprecation warnings that cause non-zero exit codes:
    we parse stdout regardless of returncode as long as we got at least one ID.
    """
    r = subprocess.run(
        ["yt-dlp", "--flat-playlist", "--print", "id", "--ignore-errors",
         "--no-warnings",
         f"https://www.youtube.com/playlist?list={playlist_id}"],
        capture_output=True, text=True, timeout=120,
    )
    # Extract valid video IDs from stdout (11-char alphanumeric strings)
    id_pat = r'^[a-zA-Z0-9_-]{11}' + '$'
    ids = [l.strip() for l in r.stdout.strip().splitlines()
           if re.match(id_pat, l.strip())]
    if ids:
        return ids
    # No IDs from stdout — surface the real error from stderr
    stderr_clean = r.stderr.strip().split('\n')
    errors = [l for l in stderr_clean
              if l and not l.startswith('WARNING:') and 'Deprecated' not in l]
    msg = errors[0] if errors else (r.stderr[:200] or "yt-dlp returned no video IDs")
    raise RuntimeError(f"Could not read playlist: {msg}")


# ── Transcript helpers ────────────────────────────────────────────────────────

def transcript_from_captions(video_id: str) -> str:
    from youtube_transcript_api import YouTubeTranscriptApi
    entries = YouTubeTranscriptApi.get_transcript(video_id)
    return " ".join(e["text"] for e in entries)


_FW_MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache", "fw_models")


def _transcribe_local(mp3_path: str, emit) -> str:
    """Local CPU transcription via faster-whisper tiny model — no API quota, no billing."""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise RuntimeError("faster-whisper not installed — run: pip install faster-whisper")
    os.makedirs(_FW_MODEL_DIR, exist_ok=True)
    emit("🖥️  Loading local Whisper model (tiny ≈39 MB, cached after first run) …", "warning")
    model = WhisperModel("tiny", device="cpu", compute_type="int8",
                         download_root=_FW_MODEL_DIR)
    emit("📝  Transcribing locally — may take 2–4 min on CPU …", "warning")
    segments, info = model.transcribe(mp3_path, beam_size=1, vad_filter=True)
    text = " ".join(seg.text.strip() for seg in segments)
    emit(f"✅  Local transcription done ({len(text.split()):,} words, lang: {info.language})", "success")
    return text


def transcript_from_whisper(url: str, video_id: str, emit) -> tuple[str, str]:
    client  = Groq(api_key=GROQ_API_KEY)
    tmp_dir = tempfile.mkdtemp()
    raw_out = os.path.join(tmp_dir, f"{video_id}.%(ext)s")
    mp3_out = os.path.join(tmp_dir, f"{video_id}.mp3")

    emit("⬇  No captions — downloading audio via yt-dlp …", "warning")
    dl = subprocess.run(
        ["yt-dlp",
         "-f", "bestaudio[abr<=64]/bestaudio/worst",
         "-x", "--audio-format", "mp3", "--audio-quality", "5",
         "--no-playlist", "-o", raw_out, url],
        capture_output=True, text=True, timeout=300,
    )
    if dl.returncode != 0:
        raise RuntimeError(f"yt-dlp failed: {dl.stderr[-400:]}")

    if not os.path.exists(mp3_out):
        found = [f for f in os.listdir(tmp_dir) if video_id in f]
        if not found:
            raise RuntimeError("Audio file not found after yt-dlp download.")
        src = os.path.join(tmp_dir, found[0])
        subprocess.run(
            ["ffmpeg", "-i", src, "-q:a", "5", "-ar", "16000", "-ac", "1",
             mp3_out, "-y"],
            capture_output=True, timeout=120,
        )

    size_mb = os.path.getsize(mp3_out) / 1024 / 1024
    emit(f"🎵  Audio ready ({size_mb:.1f} MB) — transcribing …", "warning")

    if size_mb > MAX_AUDIO_MB:
        emit(f"✂  Clipping to first {CLIP_SECONDS // 60} min …", "warning")
        clipped = os.path.join(tmp_dir, f"{video_id}_clip.mp3")
        subprocess.run(
            ["ffmpeg", "-i", mp3_out, "-t", str(CLIP_SECONDS),
             "-q:a", "5", "-ar", "16000", "-ac", "1", clipped, "-y"],
            capture_output=True, timeout=60,
        )
        mp3_out = clipped

    try:
        with open(mp3_out, "rb") as f:
            result = client.audio.transcriptions.create(
                file=(os.path.basename(mp3_out), f),
                model=WHISPER_MODEL,
                response_format="text",
            )
    except Exception as _whisper_err:
        _msg      = str(_whisper_err)
        _is_quota = any(k in _msg.lower() for k in
                        ("quota", "billing", "insufficient", "exceeded", "resource_exhausted"))
        _is_auth  = ("401" in _msg or "403" in _msg
                     or "invalid_api_key" in _msg.lower())
        if _is_quota or _is_auth:
            _kind = "quota exhausted" if _is_quota else "auth error"
            emit(f"⚠️  Groq Whisper {_kind} — falling back to local transcription (slower) …",
                 "warning")
            try:
                _local = _transcribe_local(mp3_out, emit)
                shutil.rmtree(tmp_dir, ignore_errors=True)
                return _local, "whisper-local"
            except Exception as _local_err:
                emit(f"⚠️  Local transcription failed: {str(_local_err)[:80]}", "warning")
        shutil.rmtree(tmp_dir, ignore_errors=True)
        if _is_quota:
            raise RuntimeError(
                "Groq Whisper quota exhausted — audio transcription unavailable until quota resets"
            ) from _whisper_err
        if _is_auth:
            raise RuntimeError("Groq Whisper auth error — check GROQ secret") from _whisper_err
        raise

    # Groq SDK 1.5+ always returns Transcription (never raw str).
    # Extract .text safely — raise immediately if None/empty so the caller can fallback.
    raw_text = result.text if (hasattr(result, "text") and isinstance(result.text, str)) else ""
    if not raw_text or len(raw_text.strip()) < 10:
        raise RuntimeError(
            "Groq Whisper returned empty text — audio may be silent, too short, or unsupported."
        )
    shutil.rmtree(tmp_dir, ignore_errors=True)
    return raw_text, "whisper"


def get_transcript(url: str, video_id: str, emit):
    """
    Acquire transcript via the robust multi-stage fallback pipeline.
    Returns (text: str, method: str, result: TranscriptResult).
    text is ALWAYS a str (never None); result.ok=False when all stages failed.
    """
    result = transcript_pipeline.get_transcript_robust(url, video_id, emit)
    return result.text, result.method, result


# ── Groq LLM ─────────────────────────────────────────────────────────────────

def call_groq(prompt: str, max_tokens: int = 4000, emit_fn=None) -> str:
    """Delegate to provider_router (Groq first/free, then Gemini, then OpenAI as last resort).
    emit_fn(msg, kind) is optional; when supplied, provider fallback events reach the job stream."""
    return provider_router.call_llm_smart(prompt, max_tokens=max_tokens, json_mode=True, emit_fn=emit_fn)



def call_openai(prompt: str, max_tokens: int = 4000, json_mode: bool = True, emit_fn=None) -> str:
    """Delegate to provider_router (Groq first/free, then Gemini, then OpenAI as last resort).
    emit_fn(msg, kind) is optional; when supplied, provider fallback events reach the job stream."""
    return provider_router.call_llm_smart(prompt, max_tokens=max_tokens, json_mode=json_mode, emit_fn=emit_fn)


def call_llm(prompt: str, max_tokens: int = 4000, json_mode: bool = True, emit_fn=None) -> str:
    """Route to best available free provider (Groq -> Gemini -> OpenAI as last resort).
    emit_fn(msg, kind) is optional; when supplied, provider fallback events reach the job stream."""
    return provider_router.call_llm_smart(prompt, max_tokens=max_tokens, json_mode=json_mode, emit_fn=emit_fn)


# ── Package auto-installer ────────────────────────────────────────────────────

_PKG_BLOCKLIST = {
    "os", "sys", "flask", "groq", "yt-dlp", "ffmpeg", "python",
    "pip", "setuptools", "wheel", "subprocess", "threading",
    "concurrent", "urllib", "json", "re",
}


def install_packages(packages: list[str]) -> tuple[list, list]:
    installed, failed = [], []
    for pkg in packages[:8]:
        pkg = pkg.strip().lower().split("[")[0]
        if not pkg or not re.match(r'^[a-zA-Z0-9_\-\.]+$', pkg):
            continue
        if pkg in _PKG_BLOCKLIST:
            continue
        try:
            r = subprocess.run(
                [sys.executable, "-m", "pip", "install", pkg, "-q",
                 "--no-warn-script-location"],
                capture_output=True, text=True, timeout=60,
            )
            (installed if r.returncode == 0 else failed).append(pkg)
        except Exception:
            failed.append(pkg)
    return installed, failed


# ── AI skill extraction ───────────────────────────────────────────────────────

def _build_prompt(
    transcript:       str,
    knowledge_ctx:    str,
    existing_content: str = "",   # full markdown of the top enhance candidate
) -> str:

    enhance_block = ""
    if existing_content:
        enhance_block = f"""
EXISTING SKILL CONTENT (if you choose action="enhance", build ON TOP OF THIS — never discard valuable steps, tools, or concepts already here):
{existing_content[:3000]}
"""

    return f"""You are Fieldnote's AI knowledge engine. Your purpose is to build a growing, non-redundant skill library from YouTube videos.

{knowledge_ctx}
{enhance_block}
NEW VIDEO TRANSCRIPT (up to 14 000 chars):
{transcript[:20000]}

═══════════════════════════════════════════════════════════════
TASK — read carefully before deciding:

1. Compare the transcript to the SKILL INDEX above.
2. If the transcript teaches something substantially covered by an existing skill:
   → set action="enhance", set enhance_target to the EXACT skill name from the index.
   → Your skill_markdown MUST include ALL valuable content from the existing skill
     PLUS new knowledge from this video. Merge, don't replace.
   → Deduplicate: remove any step/tool/concept that is already present.
   → Add only genuinely new information.

3. If the transcript teaches something not yet in the library (or only tangentially related):
   → set action="create".
   → Link to related skills via related_skills.

4. Never create a skill that is a shallow duplicate of an existing one.
   If this video is a 95%+ overlap with an existing skill, still enhance it.

Respond with ONLY valid JSON — no markdown fences, no extra text:
{{
  "action": "create",
  "enhance_target": null,
  "skill_name": "short_snake_case_identifier",
  "title": "Clear Human-Readable Title",
  "description": "2-3 sentences: what this teaches and why it matters for AI self-improvement",
  "steps": ["Specific actionable step 1", "step 2", "step 3"],
  "tools": ["ToolName", "APIName", "FrameworkName"],
  "python_packages": ["pip-package-name"],
  "concepts": ["Key Concept 1", "Concept 2"],
  "tags": ["category-tag", "topic-tag"],
  "related_skills": ["existing_skill_name"],
  "skill_markdown": "# Title\\n\\n## Description\\n...\\n\\n## Steps\\n...\\n\\n## Tools\\n...\\n\\n## Concepts\\n...\\n\\n## Related Skills\\n..."
}}

Rules:
- python_packages: only real, installable pip package names. Empty list if none.
- tags: 2-5 short lowercase topic tags.
- related_skills: only names from the SKILL INDEX above.
- skill_markdown: complete, well-structured markdown. When enhancing, this must
  contain the MERGED result — all prior steps/tools/concepts plus new ones.
  Do NOT include a Sources section (that is added automatically).
═══════════════════════════════════════════════════════════════
"""


def _extract_skill_ai(
    transcript:    str,
    knowledge_ctx: str,
    existing_content: str = "",
    emit_fn=None,
) -> dict:
    raw = call_llm(_build_prompt(transcript, knowledge_ctx, existing_content), emit_fn=emit_fn)
    return json.loads(raw)




# ── AI Arena: three providers, one judge ─────────────────────────────────────

def _extract_skill_chatgpt(
    transcript: str, knowledge_ctx: str, existing_content: str = "",
    allow_paid: bool = False, emit=None, notify_fn=None,
) -> dict:
    """Educator-lens extraction — uses lens-aware routing (Groq first for educator lens).
    allow_paid is passed per-job and never mutates global state.
    emit/notify_fn are optional SSE callbacks that surface provider fallback events."""
    base     = _build_prompt(transcript, knowledge_ctx, existing_content)
    preamble = (
        "You are Fieldnote's EDUCATOR AI. Your lens is conceptual clarity, "
        "thorough descriptions, and how this skill connects to others in the library."
        + chr(10) + chr(10)
    )
    raw = provider_router.call_llm_for_lens(
        "educator", preamble + base, max_tokens=4000, json_mode=True,
        allow_paid=allow_paid, emit_fn=emit, status_fn=notify_fn,
    )
    d   = json.loads(raw)
    # Validate immediately — LLM may write "steps": null, "tools": null etc.
    validated = skill_validator.validate_extraction(d, context="chatgpt")
    return _resolve_tools_in_skill(validated, context="chatgpt")


def _extract_skill_groq(
    transcript: str, knowledge_ctx: str, existing_content: str = "",
    allow_paid: bool = False, emit=None, notify_fn=None,
) -> dict:
    """Practitioner-lens extraction — uses lens-aware routing (Gemini first to avoid
    concurrent Groq drain with the educator extractor; replaces fragile time.sleep(4)).
    allow_paid is passed per-job and never mutates global state.
    emit/notify_fn are optional SSE callbacks that surface provider fallback events."""
    base     = _build_prompt(transcript, knowledge_ctx, existing_content)
    preamble = (
        "You are Fieldnote's PRACTITIONER AI. Your lens is specific actionable steps "
        "a developer can follow immediately, and every concrete tool, command, "
        "and library mentioned in the transcript."
        + chr(10) + chr(10)
    )
    raw = provider_router.call_llm_for_lens(
        "practitioner", preamble + base, max_tokens=4000, json_mode=True,
        allow_paid=allow_paid, emit_fn=emit, status_fn=notify_fn,
    )
    d   = json.loads(raw)
    # Validate immediately — same null-field protection as chatgpt extractor
    validated = skill_validator.validate_extraction(d, context="groq")
    return _resolve_tools_in_skill(validated, context="groq")


def _resolve_tools_in_skill(skill: dict, context: str = "") -> dict:
    """
    Run each tool name in skill["tools"] through the MCP registry fuzzy resolver.
    Replaces a tool entry ONLY when confidence >= 0.90 AND the registry entry is
    marked is_taught=True (i.e. it was explicitly confirmed, not just mentioned).
    Logs before/after for any substitution made.
    """
    try:
        from agents.mcp_registry import resolve_tool_name
        tools = skill.get("tools")
        if not isinstance(tools, list) or not tools:
            return skill
        new_tools = []
        for tool in tools:
            raw = tool.strip() if isinstance(tool, str) else str(tool).strip()
            if not raw:
                new_tools.append(tool)
                continue
            match = resolve_tool_name(raw)
            if match and match.get("confidence", 0) >= 0.90:
                canonical = match["canonical_name"]
                if canonical != raw:
                    log.info("mcp_resolve[%s]: %r → %r (conf=%.2f)",
                             context, raw, canonical, match["confidence"])
                new_tools.append(canonical)
            else:
                new_tools.append(tool)
        skill = dict(skill)
        skill["tools"] = new_tools
    except Exception as exc:
        log.debug("_resolve_tools_in_skill: %s", exc)
    return skill


def _github_readme_context(repos: list) -> str:
    """Fetch README snippets for top repos — gives the judge real-world tool context."""
    token   = os.getenv("GITHUBPAT") or os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN") or os.getenv("GITHUB") or ""
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = "Bearer " + token
    lines = []
    import base64 as _b64
    for repo in repos[:5]:
        fn = repo.get("full_name", "")
        if not fn:
            continue
        try:
            req = _UReq("https://api.github.com/repos/" + fn + "/readme", headers=headers)
            with urlopen(req, timeout=7) as resp:
                data = json.load(resp)
            txt = _b64.b64decode(data["content"]).decode("utf-8", errors="ignore")
            txt = re.sub(r"!\[.*?\]\(.*?\)", "", txt)
            txt = re.sub(r"\[.*?\]\(.*?\)", "", txt)
            txt = re.sub(r"#+\s*", "", txt)
            txt = re.sub(r"\s+", " ", txt).strip()[:480]
            lines.append("[" + fn + "] " + txt)
        except Exception:
            lines.append(
                "[" + (fn or "?") + "]"
                + " stars=" + str(repo.get("stars", 0))
                + " lang=" + str(repo.get("language", ""))
            )
    return chr(10).join(lines) if lines else "No README context available."


def _judge_arena(skill_a: dict, skill_b: dict, github_ctx: str, emit, allow_paid: bool = False, notify_fn=None) -> dict:
    """Judge synthesizes ChatGPT + Groq outputs into one superior merged skill."""
    if not skill_a and not skill_b:
        raise ValueError("Both AI extractions failed — nothing to judge")

    # Use `or []` not just default= — LLM may write "steps": null (key present, value None)
    a_steps = len((skill_a or {}).get("steps") or [])
    b_steps = len((skill_b or {}).get("steps") or [])

    # Graceful single-provider fallback
    if not skill_a:
        r = dict(skill_b)
        r["_arena"] = {"title_winner": "groq", "desc_winner": "groq",
                       "steps_a": 0, "steps_b": b_steps, "steps_merged": b_steps,
                       "github_tools_added": 0, "note": "chatgpt_unavailable"}
        emit("🏆  Arena: Groq only (ChatGPT unavailable)", "warning")
        return r
    if not skill_b:
        r = dict(skill_a)
        r["_arena"] = {"title_winner": "chatgpt", "desc_winner": "chatgpt",
                       "steps_a": a_steps, "steps_b": 0, "steps_merged": a_steps,
                       "github_tools_added": 0, "note": "groq_unavailable"}
        emit("🏆  Arena: ChatGPT only (Groq unavailable)", "warning")
        return r

    nl  = chr(10)
    nl2 = chr(10) + chr(10)

    prompt = (
        "You are the Quality Judge for the Fieldnote AI Arena. "
        "Two AI experts analyzed the same YouTube transcript with different lenses. "
        "Your job: synthesize the absolute BEST of both into one superior skill." + nl2

        + "EXTRACTION A — ChatGPT (educator lens):" + nl
        + json.dumps(skill_a, ensure_ascii=False)[:2600] + nl2

        + "EXTRACTION B — Groq (practitioner lens):" + nl
        + json.dumps(skill_b, ensure_ascii=False)[:2600] + nl2

        + "GITHUB INTELLIGENCE (real repos that use these tools):" + nl
        + github_ctx[:700] + nl2

        + "SYNTHESIS RULES — follow every one:" + nl
        + "1. action + enhance_target: if both agree use it; if split, pick the more specific match." + nl
        + "2. title: pick the more specific and descriptive one." + nl
        + "3. description: combine the richest insight from each (2-3 sentences, no repetition)." + nl
        + "4. steps: UNION all unique actionable steps from both lists, reorder for logical flow, max 12." + nl
        + "5. tools: UNION both lists plus any tools clearly named in the GitHub repos above." + nl
        + "6. concepts, tags, python_packages, related_skills: UNION, deduplicated, sorted." + nl
        + "7. skill_markdown: write the definitive merged markdown using ALL the best content." + nl
        + "8. skill_name: pick the cleaner, more descriptive snake_case identifier." + nl
        + "9. _arena: JSON object with: title_winner (chatgpt|groq|merged), desc_winner, "
        + "steps_a=" + str(a_steps) + ", steps_b=" + str(b_steps)
        + ", steps_merged (integer), github_tools_added (integer)." + nl2

        + "Return ONLY valid JSON. No markdown fences. All standard skill fields plus _arena."
    )

    try:
        raw    = provider_router.call_llm_for_lens("judge", prompt, max_tokens=4500, json_mode=True, allow_paid=allow_paid, emit_fn=emit, status_fn=notify_fn)
        result = json.loads(raw)
    except Exception as exc:
        emit("⚠  Judge LLM failed (" + str(exc)[:80] + "), using deterministic merge", "warning")
        # Use the deterministic merge from degraded_mode instead of aborting
        result = degraded_mode.deterministic_judge_merge(skill_a, skill_b)

    arena = result.get("_arena", {})
    sm    = len(result.get("steps") or [])
    emit(
        "🏆  Arena: " + str(a_steps) + " ChatGPT + " + str(b_steps) + " Groq steps"
        + " → " + str(sm) + " merged"
        + " | title: " + str(arena.get("title_winner", "?"))
        + " | desc: " + str(arena.get("desc_winner", "?")),
        "success",
    )
    return result


def _compute_skill_name(
    skill:          dict,
    action:         str,
    enhance_target: str | None,
    existing_index: dict,
) -> str:
    _raw = skill.get("skill_name")
    _sn  = str(_raw).strip() if _raw and not isinstance(_raw, (dict, list)) else ""
    name = re.sub(r"[^a-z0-9_]", "_", (_sn or "unnamed").lower()).strip("_")
    if not name:
        name = f"skill_{uuid.uuid4().hex[:6]}"
    if action == "enhance" and enhance_target and enhance_target in existing_index:
        name = re.sub(r"[^a-z0-9_]", "_", enhance_target.lower()).strip("_")
    return name


def _read_existing_markdown(skill_name: str) -> str:
    """Return existing skill markdown, or empty string if not found."""
    path = os.path.join(SKILLS_DIR, f"{skill_name}.md")
    if os.path.exists(path):
        try:
            with open(path) as f:
                return f.read()
        except Exception:
            pass
    return ""


# ── Smart skill save (merge, dedup, sources, history) ────────────────────────

def _save_skill(
    skill:           dict,
    skill_name:      str,
    url:             str,
    meta:            dict,
    method:          str,
    word_count:      int,
    video_id:        str,
    action:          str,
    github_results:  list,
    mcp_connections: list,
) -> str:
    now       = datetime.now(timezone.utc).isoformat()
    today     = now[:10]
    skill_path = os.path.join(SKILLS_DIR, f"{skill_name}.md")

    # ── Read existing content for merge ──────────────────────────────────────
    existing_markdown = ""
    existing_sources: list[dict] = []
    if action == "enhance" and os.path.exists(skill_path):
        try:
            with open(skill_path) as f:
                existing_markdown = f.read()
            existing_sources = _extract_sources(existing_markdown)
        except Exception:
            pass

    # ── Build new sources list (existing + current, deduped by URL) ──────────
    current_source = {
        "date":   today,
        "title":  meta.get("title") or "Source video",
        "url":    url,
        "method": method,
    }
    all_sources = existing_sources + [current_source]

    # ── Get new markdown from AI output ──────────────────────────────────────
    markdown = skill.get("skill_markdown") or (
        f"# {skill.get('title', 'Skill')}\n\n"
        f"{skill.get('description', '')}\n\n"
        "## Steps\n" +
        "\n".join(f"- {s}" for s in _nsl(skill.get("steps")))
    )

    # Strip any Sources section the AI may have included (we manage it ourselves)
    markdown = re.sub(
        r'\n*##\s*sources.*$', '', markdown,
        flags=re.IGNORECASE | re.DOTALL,
    ).rstrip()

    # Append the authoritative Sources section
    markdown += _build_sources_section(all_sources)

    # ── Write file (atomic: write to .tmp then rename) ───────────────────────
    _tmp_md = skill_path + ".tmp"
    with open(_tmp_md, "w") as f:
        f.write(markdown)
    os.replace(_tmp_md, skill_path)

    # ── Update metadata index ─────────────────────────────────────────────────
    index = load_index()
    prev  = index.get(skill_name, {})

    # Merge and deduplicate all list fields (new AI output wins order, old fills gaps)
    merged_tools    = _dedup_list(_nsl(skill.get("tools")),           _nsl(prev.get("tools")))
    merged_tags     = _dedup_list(_nsl(skill.get("tags")),            _nsl(prev.get("tags")))
    merged_concepts = _dedup_list(_nsl(skill.get("concepts")),        _nsl(prev.get("concepts")))
    merged_packages = _dedup_list(_nsl(skill.get("python_packages")), _nsl(prev.get("python_packages")))
    merged_related  = _dedup_list(_nsl(skill.get("related_skills")),  _nsl(prev.get("related_skills")))

    # History entry for this update
    history_entry = {
        "action":       action,
        "source_url":   url,
        "source_title": meta.get("title", ""),
        "video_id":     video_id,
        "method":       method,
        "updated_at":   now,
    }
    prev_history = prev.get("history", [])
    # Avoid duplicate history entries for the same video
    if not any(h.get("video_id") == video_id for h in prev_history):
        new_history = prev_history + [history_entry]
    else:
        new_history = prev_history

    index[skill_name] = {
        "title":           skill.get("title", skill_name),
        "description":     skill.get("description", ""),
        "tags":            merged_tags,
        "tools":           merged_tools,
        "concepts":        merged_concepts,
        "python_packages": merged_packages,
        "related_skills":  merged_related,
        "steps":           _nsl(skill.get("steps")),
        "source_url":      url,
        "source_title":    meta.get("title", ""),
        "video_id":        video_id,
        "method":          method,
        "word_count":      word_count,
        "action":          action,
        "history":         new_history,
        "github_repos": [
            {
                "full_name": r["full_name"],
                "url":       r["url"],
                "stars":     r["stars"],
                "is_mcp":    r.get("is_mcp", False),
                "language":  r.get("language", ""),
            }
            for r in github_results[:6]
        ],
        "mcp_connections": [c["name"] for c in mcp_connections],
        "created_at":      prev.get("created_at", now),
        "updated_at":      now,
        "_dca":            skill_quality.advance_dca(prev.get("_dca", {}))
                           if action == "enhance"
                           else skill_quality.dca_schedule(1, now),
        # Baseline flag — set by _deterministic_baseline; cleared on AI enrichment
        "_baseline":       skill.get("_baseline", False),
        "_baseline_reason": skill.get("_baseline_reason", ""),
    }
    save_index(index)
    try:
        _update_brain(skill, skill_name)
    except Exception:
        pass
    # ── Auto-sync to GitHub fieldnote repo ────────────────────────────────────
    try:
        with open(skill_path) as _f:
            _md = _f.read()
        github_sync.sync_skill(skill_name, _md, index)
    except Exception:
        pass
    return skill_path


def _install_pkgs(packages: list[str], emit) -> tuple[list, list]:
    if not packages:
        return [], []
    emit(
        f"📦  Installing {len(packages)} package(s): {', '.join(packages[:5])} …",
        "info",
    )
    installed, failed = install_packages(packages)
    if installed:
        emit(f"✅  Installed: {', '.join(installed)}", "success")
    if failed:
        emit(f"⚠  Skipped: {', '.join(failed)}", "warning")
    return installed, failed


# ── Supplemental GitHub search (AI-extracted tools not in quick-scan) ─────────

def _supplemental_github_search(
    ai_tools:     list[str],
    quick_tools:  list[str],
    emit,
) -> list[dict]:
    """Search GitHub for tools the AI identified that weren't in the quick scan."""
    already = {t.lower() for t in quick_tools}
    new_tools = [
        t for t in ai_tools
        if t.lower() not in already
        and not any(t.lower() in a or a in t.lower() for a in already)
    ][:5]
    if not new_tools:
        return []
    emit(
        f"🔍  Supplemental GitHub search: {', '.join(new_tools[:4])} …",
        "info",
    )
    return github_agent.search_tools(new_tools, emit)


# ── Stage-aware error classifier ─────────────────────────────────────────────

_SECRET_RE = re.compile(
    r'(sk-[A-Za-z0-9]{10,}|gsk_[A-Za-z0-9]{10,}|Bearer\s+[A-Za-z0-9._-]{10,}'
    r'|key-[A-Za-z0-9]{10,}|AIza[A-Za-z0-9_-]{30,})',
    re.I,
)

def _classify_stage_error(exc: Exception, stage: str) -> str:
    """Convert a raw exception into a stage-specific, user-readable string.
    Redacts any token or key that might appear in provider error messages."""
    raw = str(exc)
    raw = _SECRET_RE.sub("[redacted]", raw)
    low = raw.lower()

    if "quota" in low or "insufficient_quota" in low:
        return (f"All AI providers are quota-limited ({stage}). "
                "Wait a few minutes and tap Retry.")
    if "429" in raw or "rate_limit" in low or "rate limit" in low:
        return (f"AI providers are rate-limited ({stage}). "
                "Wait 30 s and tap Retry.")
    if "timeout" in low or "timed out" in low:
        return (f"Timed out during {stage}. "
                "The video may be very long or providers are slow. Retry to resume.")
    if "transcript unavailable" in low:
        return raw   # already user-friendly from get_transcript_robust
    if "nonetype" in low and "has no len" in low:
        return (f"An AI provider returned an incomplete response during {stage} "
                "(null list field). Retry usually fixes this.")
    if "json" in low or "jsondecode" in type(exc).__name__.lower():
        return (f"AI provider returned malformed JSON during {stage}. "
                "Retry usually fixes this.")
    if "connection" in low or "network" in low or "timeout" in low:
        return (f"Network error during {stage}. Check your connection and retry.")
    if len(raw) > 220:
        return f"Unexpected error during {stage}: {raw[:200]}…"
    return f"Error during {stage}: {raw}"


# ── Core parallel job runner ──────────────────────────────────────────────────

def run_job(job_id: str, url: str, video_id: str):
    q      = _jobs[job_id]["queue"]
    run_id = _jobs[job_id].get("run_id") or str(uuid.uuid4())[:8]
    _jobs[job_id]["run_id"] = run_id
    _jobs[job_id]["stage"]  = "init"
    provider_attempts: list[dict] = []

    def emit(msg: str, kind: str = "info"):
        q.put({"type": "log", "msg": msg, "kind": kind})

    def set_stage(name: str):
        """Update current stage in job state and broadcast a stage SSE event."""
        _jobs[job_id]["stage"] = name
        q.put({"type": "stage", "stage": name, "run_id": run_id})

    def _notify_status(_status_dict=None):
        """Push a provider_status SSE event so the health bar updates instantly."""
        try:
            q.put({"type": "provider_status",
                   "providers": provider_router.provider_status()})
        except Exception:
            pass

    # Read X-Allow-Paid from job context (set by /process route) — never mutates global
    allow_paid = bool(_jobs[job_id].get("allow_paid", False))

    try:
        set_stage("init")
        emit("🚀  Parallel agents launching …", "info")

        # ── Checkpoint recovery: check if we already have a transcript ────────
        existing_cp = run_checkpoint.checkpoint_for_video(video_id)
        cached_transcript: str = ""
        cached_method: str = ""
        cached_meta: dict = {}
        if existing_cp and existing_cp.get("transcript") and len(existing_cp["transcript"]) > 50:
            cached_transcript = existing_cp["transcript"]
            cached_method     = existing_cp.get("transcript_method", "cached")
            cached_meta       = existing_cp.get("metadata", {})
            emit(f"♻️  Reusing cached transcript from checkpoint (run={existing_cp['run_id']}) …", "info")

        with ThreadPoolExecutor(max_workers=8, thread_name_prefix="fn") as pool:

            # ── Phase 1: metadata + transcript in parallel ────────────────────
            set_stage("transcript")
            emit("⚡  Phase 1: metadata ∥ transcript …", "info")
            meta_f  = pool.submit(get_video_metadata, video_id)

            if cached_transcript:
                # Skip re-download — use checkpoint transcript
                meta = meta_f.result(timeout=30)
                if cached_meta:
                    meta = {**cached_meta, **{k: v for k, v in meta.items() if v}}
                transcript    = cached_transcript
                method        = cached_method
                trans_result  = None
            else:
                trans_f = pool.submit(get_transcript, url, video_id, emit)
                meta    = meta_f.result(timeout=30)
                transcript, method, trans_result = trans_f.result(timeout=300)

            q.put({"type": "meta", "data": meta})
            emit(f"📺  {meta.get('title') or 'Video identified'}", "info")

            # Hard guard — transcript is always str but may be empty when all stages fail
            if not transcript or len(transcript.strip()) < 10:
                stage_summary = (
                    ", ".join(getattr(trans_result, "stage_log", [])) or "none recorded"
                    if trans_result else "none"
                )
                raise RuntimeError(
                    "Transcript unavailable — all acquisition methods failed. "
                    f"Stages tried: {stage_summary}. "
                    "The video may be private, have no audio, or providers are quota-limited. "
                    "Please retry in a few minutes."
                )

            word_count = len(transcript.split())
            if trans_result and getattr(trans_result, "is_degraded", False):
                emit(
                    f"📝  {word_count:,} words via {method} "
                    f"⚡ degraded ({trans_result.degraded_reason or 'lower quality fallback'})",
                    "warning",
                )
            else:
                emit(f"📝  {word_count:,} words via {method}", "success")

            # Save checkpoint after transcript acquisition
            run_checkpoint.save_checkpoint(run_id, {
                "video_id":          video_id,
                "url":               url,
                "stage":             "transcript",
                "transcript":        transcript,
                "transcript_method": method,
                "metadata":          meta,
                "provider_attempts": provider_attempts,
            })

            # Quick regex scan — used for early GitHub search AND relevance scoring
            quick_tools = github_agent.quick_tool_scan(transcript)
            if quick_tools:
                emit(
                    f"🔍  Quick scan: {', '.join(quick_tools[:6])}"
                    f"{'…' if len(quick_tools) > 6 else ''}",
                    "info",
                )

            # ── Phase 2: ChatGPT ∥ Groq ∥ GitHub — AI Arena ─────────────────
            set_stage("extraction")
            emit("⚡  Phase 2: ChatGPT ∥ Groq ∥ GitHub — Arena mode …", "info")

            knowledge_ctx  = get_skills_context(quick_tools)
            existing_index = load_index()

            # Use cached extractions from checkpoint if available
            cached_skill_a = existing_cp.get("skill_a") if existing_cp else None
            cached_skill_b = existing_cp.get("skill_b") if existing_cp else None

            # All three work simultaneously — nobody idles
            # allow_paid is passed explicitly per-job; never mutates global state
            gpt_f    = pool.submit(_extract_skill_chatgpt, transcript, knowledge_ctx, "", allow_paid, emit, _notify_status) \
                       if not cached_skill_a else None
            groq_f   = pool.submit(_extract_skill_groq,   transcript, knowledge_ctx, "", allow_paid, emit, _notify_status) \
                       if not cached_skill_b else None
            github_f = pool.submit(github_agent.search_tools, quick_tools, emit)

            # Collect GitHub first (fastest), then fetch READMEs while LLMs finish
            github_results = github_f.result(timeout=90)
            emit(f"📊  GitHub: {len(github_results)} repos — fetching READMEs …", "info")
            github_ctx = _github_readme_context(github_results)

            # Collect both LLM results (already running in parallel)
            skill_a = cached_skill_a
            skill_b = cached_skill_b
            exc_a_msg: str = ""
            exc_b_msg: str = ""

            if gpt_f is not None:
                try:
                    skill_a = gpt_f.result(timeout=120)
                    emit("✅  Educator extraction done", "info")
                    run_checkpoint.save_checkpoint(run_id, {"skill_a": skill_a})
                except Exception as exc_a:
                    exc_a_msg = str(exc_a)
                    emit(f"⚠  Educator failed ({exc_a_msg[:80]})", "warning")
                    provider_attempts.append({
                        "lens": "educator", "error": exc_a_msg[:200],
                        "error_class": provider_router._classify_error(exc_a_msg),
                    })
            else:
                emit("♻️  Reusing cached educator extraction from checkpoint", "info")

            if groq_f is not None:
                try:
                    skill_b = groq_f.result(timeout=120)
                    emit("✅  Practitioner extraction done", "info")
                    run_checkpoint.save_checkpoint(run_id, {"skill_b": skill_b})
                except Exception as exc_b:
                    exc_b_msg = str(exc_b)
                    emit(f"⚠  Practitioner failed ({exc_b_msg[:80]})", "warning")
                    provider_attempts.append({
                        "lens": "practitioner", "error": exc_b_msg[:200],
                        "error_class": provider_router._classify_error(exc_b_msg),
                    })
            else:
                emit("♻️  Reusing cached practitioner extraction from checkpoint", "info")

            # ── Both lenses failed → degraded mode ────────────────────────────
            if skill_a is None and skill_b is None:
                emit("⚠  Both AI extractions failed — creating degraded skill draft …", "warning")
                set_stage("degraded")

                deg_skill = degraded_mode.build_degraded_skill(transcript, meta, url, video_id)
                deg_skill = pipeline_guard.sanitize(deg_skill, emit)
                deg_name  = deg_skill.get("skill_name", f"skill_{uuid.uuid4().hex[:6]}")

                # Save the degraded skill to disk immediately
                deg_path = _save_skill(
                    deg_skill, deg_name, url, meta, method, word_count,
                    video_id, "create", github_results, [],
                )
                emit(f"💾  Degraded draft saved: {deg_name}.md", "warning")

                # Queue checkpoint for auto-recovery
                run_checkpoint.save_checkpoint(run_id, {
                    "stage":             "queued",
                    "degraded":          True,
                    "skill_name":        deg_name,
                    "provider_attempts": provider_attempts,
                    "queued_at":         datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "recovery_attempts": 0,
                })

                # Emit structured recovery card (not a raw error)
                q.put({
                    "type":         "done",
                    "ok":           True,
                    "degraded":     True,
                    "queued":       True,
                    "run_id":       run_id,
                    "title":        deg_skill.get("title", deg_name),
                    "description":  deg_skill.get("description", ""),
                    "steps":        _nsl(deg_skill.get("steps")),
                    "tools":        _nsl(deg_skill.get("tools")),
                    "concepts":     _nsl(deg_skill.get("concepts")),
                    "tags":         _nsl(deg_skill.get("tags")),
                    "skill_name":   deg_name,
                    "skill_file":   deg_path,
                    "action":       "create",
                    "transcript_words":  word_count,
                    "transcript_method": method,
                    "video_id":     video_id,
                    "thumbnail":    meta.get("thumbnail", ""),
                    "source_title": meta.get("title", ""),
                    "recovery": {
                        "providers_failed":   [a["lens"] for a in provider_attempts],
                        "error_classes":      [a["error_class"] for a in provider_attempts],
                        "skill_preserved":    True,
                        "pending_enhancement": True,
                        "estimated_retry_mins": 5,
                        "auto_resume":        True,
                    },
                    "receipt": {
                        "transcript_words":  word_count,
                        "transcript_method": method,
                        "is_degraded":       True,
                        "degraded_reason":   "all_providers_exhausted",
                        "stage_log":         getattr(trans_result, "stage_log", []) if trans_result else [],
                        "outcome":           "degraded",
                    },
                })
                return  # do not proceed — recovery will handle enhancement

            # Judge synthesizes the winner — allow_paid passed explicitly per-job
            set_stage("judge")
            skill = _judge_arena(skill_a, skill_b, github_ctx, emit, allow_paid=allow_paid, notify_fn=_notify_status)
            skill = pipeline_guard.sanitize(skill, emit)

            action         = skill.get("action", "create")
            enhance_target = skill.get("enhance_target")
            skill_name     = _compute_skill_name(skill, action, enhance_target, existing_index)

            # ── Scheduled enhancement override ────────────────────────────────
            if _jobs[job_id].get("force_enhance"):
                forced     = _jobs[job_id]["force_enhance"]
                action     = "enhance"
                enhance_target = forced
                skill_name = forced
                emit(f"🤖  Scheduler override → enhancing '{forced}'", "info")

            # ── If enhance: re-run ChatGPT with full existing markdown, then re-judge
            existing_md = _read_existing_markdown(skill_name) if action == "enhance" else ""
            if action == "enhance" and existing_md:
                emit(f"🔄  Re-running ChatGPT with existing '{skill_name}' content …", "info")
                try:
                    skill_a2 = _extract_skill_chatgpt(transcript, knowledge_ctx, existing_md, allow_paid, emit, _notify_status)
                    skill    = _judge_arena(skill_a2, skill_b, github_ctx, emit, allow_paid=allow_paid, notify_fn=_notify_status)
                    skill    = pipeline_guard.sanitize(skill, emit)
                    action         = skill.get("action", "enhance")
                    enhance_target = skill.get("enhance_target")
                    skill_name     = _compute_skill_name(skill, action, enhance_target, existing_index)
                except Exception as exc_m:
                    emit(f"⚠  Merge re-run failed ({exc_m}), using first-pass result", "warning")

            # ── Quality Gate (from hermes_live_readiness) ─────────────────────
            qr = skill_quality.quality_gate(skill)
            emit(f"🔬  Quality gate: {qr.summary}", "info")
            if qr.decision == skill_quality.QualityDecision.DENY:
                emit("❌  Skill below minimum quality bar — aborting save. "
                     "Try a longer video with more detail.", "error")
                q.put({"type": "done", "ok": False,
                       "error": "quality_deny", "quality": qr.to_dict()})
                return

            emit(
                f"{'🔄  Enhancing' if action=='enhance' else '✨  New skill'}: "
                f"{skill.get('title','…')}",
                "success",
            )
            emit(f"📊  GitHub: {len(github_results)} repos discovered", "info")
            if action == "enhance":
                emit(f"🔗  Merging into: {skill_name}", "info")

            # ── Phase 3: all heavy work in parallel ───────────────────────────
            set_stage("save")
            emit("⚡  Phase 3: save ∥ packages ∥ MCP ∥ clone ∥ supplemental search …", "info")

            ai_tools    = _nsl(skill.get("tools"))
            mcp_targets = [r for r in github_results
                           if r.get("is_mcp") or r.get("npm_package")]

            pkg_f   = pool.submit(_install_pkgs,
                                  _nsl(skill.get("python_packages")), emit)
            mcp_f   = pool.submit(mcp_agent.process_repos,     mcp_targets,    emit)
            clone_f = pool.submit(github_agent.clone_best_repos, github_results, emit)
            supp_f  = pool.submit(_supplemental_github_search,
                                  ai_tools, quick_tools, emit)

            installed,     failed    = pkg_f.result(timeout=120)
            mcp_connections          = mcp_f.result(timeout=120)
            cloned_repos             = clone_f.result(timeout=180)
            supp_repos               = supp_f.result(timeout=60)

            # Merge supplemental results (dedup by full_name)
            existing_names = {r["full_name"] for r in github_results}
            for r in supp_repos:
                if r["full_name"] not in existing_names:
                    github_results.append(r)
                    existing_names.add(r["full_name"])
            if supp_repos:
                emit(f"📊  Supplemental search added {len(supp_repos)} more repo(s)", "info")

            # Save skill after all results are collected
            skill_path = _save_skill(
                skill, skill_name, url, meta, method, word_count,
                video_id, action, github_results, mcp_connections,
            )
            source_count = len(load_index().get(skill_name, {}).get("history", [])) + 1
            emit(
                f"💾  Skill saved: {skill_name}.md "
                f"(fed by {source_count} video source(s))",
                "success",
            )

            # ── Post-save verification + auto-fix ─────────────────────────────
            emit("🔍  Verifying all systems …", "info")
            set_stage("verify")
            verify_result = verify_agent.verify_and_fix(
                skill_name=skill_name,
                skill_path=skill_path,
                emit=emit,
                emit_check=lambda chk: q.put({"type": "verify_check", "check": chk}),
            )
            q.put({"type": "verify_done", **verify_result.to_dict()})

            if mcp_connections:
                emit(
                    f"🔌  MCP: {len(mcp_connections)} connection(s) configured",
                    "success",
                )
            if cloned_repos:
                emit(f"📁  Repos: {len(cloned_repos)} cloned/updated", "info")

            # Collect auth requirements
            auth_required: list[dict] = []
            seen_svcs: set[str] = set()
            for r in github_results:
                auth = r.get("auth_required")
                if auth and not auth.get("has_key") and auth["service"] not in seen_svcs:
                    auth_required.append(auth)
                    seen_svcs.add(auth["service"])
                    q.put({"type": "oauth_required", "auth": auth})
                    emit(
                        f"🔑  Credential needed: {auth['description']} — see prompt",
                        "warning",
                    )

            total = len(load_index())
            emit(
                f"🎉  Done! {total} skill(s) · "
                f"{len(mcp_connections)} MCP · "
                f"{len(cloned_repos)} repo(s) · "
                f"{len(github_results)} GitHub result(s)",
                "success",
            )

            # Clean up checkpoint on successful completion
            run_checkpoint.delete_checkpoint(run_id)

            q.put({
                "type":              "done",
                "ok":                True,
                "title":             skill.get("title"),
                "description":       skill.get("description"),
                "steps":             _nsl(skill.get("steps")),
                "tools":             _nsl(skill.get("tools")),
                "concepts":          _nsl(skill.get("concepts")),
                "tags":              _nsl(skill.get("tags")),
                "related_skills":    _nsl(skill.get("related_skills")),
                "python_packages":   _nsl(skill.get("python_packages")),
                "installed":         installed,
                "failed":            failed,
                "skill_file":        skill_path,
                "skill_name":        skill_name,
                "transcript_words":  word_count,
                "transcript_method": method,
                "video_id":          video_id,
                "receipt": {
                    "transcript_words":  word_count,
                    "transcript_method": method,
                    "is_degraded":      getattr(trans_result, "is_degraded",     False) if trans_result else False,
                    "degraded_reason":  getattr(trans_result, "degraded_reason", None) if trans_result else None,
                    "stage_log":        getattr(trans_result, "stage_log",        []) if trans_result else [],
                    "content_hash":     getattr(trans_result, "content_hash",     "") if trans_result else "",
                    "fallback_reason":  getattr(trans_result, "fallback_reason",  None) if trans_result else None,
                    "outcome":          "success",
                },
                "action":            action,
                "thumbnail":         meta.get("thumbnail", ""),
                "source_title":      meta.get("title", ""),
                "total_skills":      total,
                "stats":             get_global_stats(),
                "github_repos":      github_results,
                "mcp_connections":   mcp_connections,
                "cloned_repos":      cloned_repos,
                "auth_required":     auth_required,
                "arena":             skill.get("_arena", {}),
                "quality":           qr.to_dict(),
                "dca":               load_index().get(skill_name, {}).get("_dca", {}),
                "sync_repo":         github_sync.repo_url(),
                "verify":            verify_result.to_dict(),
            })

    except Exception as e:
        import traceback as _tb
        log.error("run_job error [stage=%s run_id=%s]: %s",
                  _jobs[job_id].get("stage", "?"), run_id, _tb.format_exc())
        stage   = _jobs[job_id].get("stage", "processing")
        friendly = _classify_stage_error(e, stage)
        emit(f"❌  {friendly}", "error")
        q.put({"type": "done", "ok": False, "error": friendly,
               "stage": stage, "run_id": run_id})
    finally:
        _jobs[job_id]["done"] = True
        _video_active.pop(video_id, None)   # release dedup lock


# ── Server-side playlist queue ────────────────────────────────────────────────

def run_playlist_job(pjob_id: str, ids: list[str]) -> None:
    """Process a full playlist in the background: 2 videos concurrently."""
    pjob      = _playlist_jobs[pjob_id]
    total     = len(ids)
    completed = 0
    failed    = 0
    _lock     = threading.Lock()

    def _process(i: int, video_id: str) -> None:
        nonlocal completed, failed
        url = f"https://www.youtube.com/watch?v={video_id}"
        try:
            meta  = get_video_metadata(video_id)
            title = meta.get("title") or video_id
        except Exception:
            title = video_id

        pjob["events"].append({
            "type": "video_start", "video_id": video_id,
            "index": i, "total": total, "title": title,
        })

        sub_id = str(uuid.uuid4())[:8]
        _jobs[sub_id] = {"queue": queue.Queue(), "done": False}
        try:
            run_job(sub_id, url, video_id)   # synchronous in this worker thread
            # Drain sub-job messages; capture the final done event
            done_msg = None
            sub_q = _jobs[sub_id]["queue"]
            while True:
                try:
                    msg = sub_q.get_nowait()
                    if msg.get("type") == "done":
                        done_msg = msg
                except queue.Empty:
                    break
            if done_msg and done_msg.get("ok"):
                with _lock:
                    completed += 1
                pjob["events"].append({
                    "type": "video_done", "video_id": video_id,
                    "index": i, "skill": done_msg,
                })
            else:
                err = (done_msg or {}).get("error", "quality filtered")
                with _lock:
                    failed += 1
                pjob["events"].append({
                    "type": "video_error", "video_id": video_id,
                    "index": i, "error": str(err)[:120],
                })
        except Exception as exc:
            with _lock:
                failed += 1
            pjob["events"].append({
                "type": "video_error", "video_id": video_id,
                "index": i, "error": str(exc)[:120],
            })
        finally:
            _jobs.pop(sub_id, None)

    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="pq") as pool:
        futs = [pool.submit(_process, i, vid) for i, vid in enumerate(ids)]
        for fut in as_completed(futs):
            try:
                fut.result()
            except Exception:
                pass

    pjob["done"] = True
    pjob["events"].append({
        "type": "playlist_done",
        "total": total, "completed": completed, "failed": failed,
    })


# ── Flask routes ──────────────────────────────────────────────────────────────

@app.route("/api/enhancement-queue")
def api_skills_due():
    """Return skills whose DCA enhancement schedule shows due=True."""
    index = load_index()
    due   = skill_quality.skills_due_for_enhancement(index)
    rows  = []
    for name in due:
        m = index[name]
        rows.append({
            "skill_name": name,
            "title":      m.get("title", name),
            "dca":        m.get("_dca", {}),
        })
    return jsonify({"due": rows, "total": len(rows)})


@app.route("/api/github/sync", methods=["POST"])
def api_github_sync():
    """Manual full-library sync to the fieldnote GitHub repo."""
    index  = load_index()
    result = github_sync.sync_all(SKILLS_DIR, index)
    return jsonify(result)


@app.route("/api/github/status")
def api_github_status():
    return jsonify({
        "repo":    github_sync.repo_url(),
        "enabled": bool(os.getenv("GITHUBPAT") or os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN") or os.getenv("GITHUB")),
        "skills":  len(load_index()),
    })


@app.route("/")
def index():
    domain   = os.getenv("REPLIT_DEV_DOMAIN", "")
    base_url = f"https://{domain}" if domain else ""
    return render_template(
        "index.html",
        skills=list_skills(),
        stats=get_global_stats(),
        all_tags=get_all_tags(),
        mcp_connections=mcp_agent.get_connections(),
        base_url=base_url,
    )


@app.route("/metadata")
def metadata():
    url         = normalize_youtube_url(request.args.get("url", "").strip())
    video_id    = extract_video_id(url)
    playlist_id = extract_playlist_id(url)

    if not video_id and not playlist_id:
        return jsonify({"error": "No video ID or playlist found"}), 400

    if video_id:
        meta = get_video_metadata(video_id)
    else:
        # Pure playlist URL — no single-video thumbnail, still valid
        meta = {"title": "YouTube Playlist", "author": "", "thumbnail": ""}

    meta["video_id"]    = video_id
    meta["is_playlist"] = bool(playlist_id)
    meta["playlist_id"] = playlist_id
    return jsonify(meta)

@app.route("/process", methods=["POST"])
def process():
    data = request.get_json(silent=True) or {}
    url  = (data.get("url") or "").strip()

    if not url:
        return jsonify({"error": "No URL provided."}), 400
    if not GROQ_API_KEY and not OPENAI_API_KEY and not (os.getenv("Google_API_Key") or os.getenv("Gemini") or os.getenv("GOOGLE_API_KEY")):
        return jsonify({
            "error": "No LLM key — add GROQ or CHATGPT in Tools › Secrets."
        }), 500

    video_id = extract_video_id(url)
    if not video_id:
        return jsonify({
            "error": "Could not find a YouTube video ID in that URL."
        }), 400

    # Dedup: if this video is already in-flight, reattach the caller to its stream
    existing = _video_active.get(video_id)
    if existing and not _jobs.get(existing, {}).get("done", True):
        return jsonify({"job_id": existing, "already_running": True})

    # Read paid-fallback toggle from request header — stored per-job, never touches global
    allow_paid = request.headers.get("X-Allow-Paid", "0") == "1"

    job_id        = str(uuid.uuid4())[:8]
    _jobs[job_id] = {"queue": queue.Queue(), "done": False, "allow_paid": allow_paid}
    _video_active[video_id] = job_id
    threading.Thread(
        target=run_job, args=(job_id, url, video_id), daemon=True
    ).start()
    return jsonify({"job_id": job_id})


@app.route("/stream/<job_id>")
def stream(job_id):
    job = _jobs.get(job_id)
    if not job:
        return "Job not found", 404

    def generate():
        while True:
            try:
                msg = job["queue"].get(timeout=120)
                yield f"data: {json.dumps(msg)}\n\n"
                if msg.get("type") == "done":
                    break
            except Exception:
                if job.get("done"):
                    break
                yield 'data: {"type":"ping"}\n\n'

    return Response(
        stream_with_context(generate()),
        content_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/api/skills")
def api_skills():
    q   = request.args.get("q", "").lower().strip()
    tag = request.args.get("tag", "").strip()
    skills = list_skills()
    if q:
        skills = [s for s in skills
                  if q in s["title"].lower()
                  or q in s["description"].lower()
                  or any(q in t.lower() for t in s["tags"])]
    if tag:
        skills = [s for s in skills if tag in s["tags"]]
    return jsonify(skills)


@app.route("/api/mcp/connections")
def api_mcp_connections():
    return jsonify(mcp_agent.get_connections())


@app.route("/api/mcp/config")
def api_mcp_config():
    return jsonify(mcp_agent.load_config())


@app.route("/api/health")
def api_health():
    """Startup health check — tells the UI which tools are available."""
    def check(cmd):
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=4)
            return r.returncode == 0
        except Exception:
            return False

    return jsonify({
        "groq":    bool(GROQ_API_KEY),
        "chatgpt": bool(OPENAI_API_KEY),
        "github_sync": bool(os.getenv("GITHUBPAT") or os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN") or os.getenv("GITHUB")),
        "sync_repo":   github_sync.repo_url(),
        "ytdlp":   check(["yt-dlp",  "--version"]),
        "ffmpeg":  check(["ffmpeg",   "-version"]),
        "github":  bool(os.getenv("GITHUBPAT") or os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN") or os.getenv("GITHUB")),
        "npx":     check(["npx",      "--version"]),
    })


@app.route("/api/save-key", methods=["POST"])
def api_save_key():
    """Save an API key to local_keys.json and activate it instantly (no restart needed)."""
    data     = request.get_json(silent=True) or {}
    provider = (data.get("provider") or "").strip().lower()
    value    = (data.get("value") or "").strip()
    if not provider or not value:
        return jsonify({"error": "provider and value required"}), 400

    env_map = getattr(provider_router, "KEY_ENV_MAP", {})
    env_var = env_map.get(provider)
    if not env_var:
        return jsonify({"error": f"Unknown provider: {provider}"}), 400

    save_local_key(env_var, value)
    # Reset provider state so it is retried immediately
    provider_router.refresh_provider_key(provider)
    # Re-init provider_router status to pick up the new key
    provider_router._init_status()

    return jsonify({"ok": True, "provider": provider, "env_var": env_var})


@app.route("/api/provider-status")
def api_provider_status():
    """Return live AI provider health (quota / rate-limit / auth state)."""
    return jsonify(provider_router.provider_status())


# ── Failover / recovery API ───────────────────────────────────────────────────

@app.route("/api/jobs/queued")
def api_jobs_queued():
    """List all checkpoints in 'queued' or 'degraded' stage awaiting recovery."""
    pending = run_checkpoint.list_pending_checkpoints()
    stale_count = sum(1 for cp in pending if cp.get("recovery_attempts", 0) >= 3)
    return jsonify({
        "queued":      pending,
        "count":       len(pending),
        "stale_count": stale_count,
    })


@app.route("/api/jobs/<run_id>/resume", methods=["POST"])
def api_job_resume(run_id: str):
    """Resume a queued checkpoint — re-run only the failed stages."""
    cp = run_checkpoint.load_checkpoint(run_id)
    if not cp:
        return jsonify({"ok": False, "error": f"Checkpoint not found: {run_id}"}), 404

    video_id = cp.get("video_id")
    url      = cp.get("url")
    if not video_id or not url:
        return jsonify({"ok": False, "error": "Checkpoint missing video_id or url"}), 400

    # Deduplicate: don't start if already running for this video
    existing = _video_active.get(video_id)
    if existing and not _jobs.get(existing, {}).get("done", True):
        return jsonify({"ok": True, "job_id": existing, "already_running": True})

    # Duplicate-resume protection: if skill file already exists, use enhance
    existing_skill_name = cp.get("skill_name")
    existing_skill_path = None
    if existing_skill_name:
        candidate = os.path.join(SKILLS_DIR, f"{existing_skill_name}.md")
        if os.path.exists(candidate):
            existing_skill_path = candidate

    # Mark that this is a resume (recovery) run with the existing checkpoint run_id
    job_id        = str(uuid.uuid4())[:8]
    _jobs[job_id] = {
        "queue":     queue.Queue(),
        "done":      False,
        "run_id":    run_id,   # reuse existing run_id to continue same checkpoint
        "allow_paid": False,
        "force_enhance": existing_skill_name if existing_skill_path else None,
    }
    _video_active[video_id] = job_id

    # Track recovery attempts
    recovery_attempts = cp.get("recovery_attempts", 0) + 1
    run_checkpoint.save_checkpoint(run_id, {
        "stage":             "resuming",
        "recovery_attempts": recovery_attempts,
        "recovered_at":      datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })

    threading.Thread(
        target=run_job, args=(job_id, url, video_id), daemon=True,
        name=f"fn-resume-{run_id}",
    ).start()

    return jsonify({
        "ok":     True,
        "job_id": job_id,
        "run_id": run_id,
        "video_id": video_id,
        "action":   "enhance" if existing_skill_path else "create",
        "recovery_attempts": recovery_attempts,
    })


@app.route("/api/jobs/<run_id>/delete", methods=["POST"])
def api_job_delete(run_id: str):
    """Manually delete a queued/degraded checkpoint by run_id."""
    cp = run_checkpoint.load_checkpoint(run_id)
    if not cp:
        return jsonify({"ok": False, "error": f"Checkpoint not found: {run_id}"}), 404
    stage = cp.get("stage", "")
    if stage not in ("queued", "degraded", "resuming"):
        return jsonify({"ok": False, "error": f"Checkpoint stage '{stage}' cannot be deleted via this endpoint"}), 400
    run_checkpoint.delete_checkpoint(run_id)
    # Record in purge log as a manual deletion
    run_checkpoint._append_purge_log([{
        "run_id":            run_id,
        "skill_name":        cp.get("skill_name"),
        "video_id":          cp.get("video_id"),
        "queued_at":         cp.get("queued_at"),
        "recovery_attempts": cp.get("recovery_attempts", 0),
        "reason":            "manually_deleted",
        "purged_at":         datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }])
    return jsonify({"ok": True, "run_id": run_id, "skill_name": cp.get("skill_name")})


@app.route("/api/settings/paid-fallback", methods=["POST"])
def api_settings_paid_fallback():
    """Toggle whether OpenAI (billed) is allowed as a fallback provider.
    Body: {"enabled": true|false}
    """
    body    = request.get_json(silent=True) or {}
    enabled = bool(body.get("enabled", False))
    provider_router.set_paid_fallback(enabled)
    return jsonify({"ok": True, "paid_fallback": enabled})


# ── Integrations hub ──────────────────────────────────────────────────────────

@app.route("/api/integrations")
def api_integrations():
    """Return the full integrations registry with live connection status."""
    from fieldnote_mcp.integrations_registry import get_all_statuses
    items = get_all_statuses(local_keys_file=LOCAL_KEYS_FILE)
    pending = sum(1 for i in items if i["status"] == "pending")
    return jsonify({"integrations": items, "pending": pending})


@app.route("/api/integrations/<iid>/save-key", methods=["POST"])
def api_integration_save_key(iid):
    """
    Save + live-verify an integration API key.
    Body: {"key": "<value>"}
    Returns: {"ok", "status", "detail"?, "error"?}
    """
    from fieldnote_mcp.integrations_registry import REGISTRY, verify_integration
    data = request.get_json(silent=True) or {}
    key  = (data.get("key") or "").strip()
    if not key:
        return jsonify({"ok": False, "error": "key is required"}), 400

    # Find registry entry — may be None for dynamic suggestion cards
    entry = next((e for e in REGISTRY if e["id"] == iid), None)

    # For dynamic suggestion cards not in REGISTRY, accept key_env from the request body
    env_var = entry["key_env"] if entry else data.get("key_env", "").strip()
    if not env_var:
        return jsonify({"ok": False, "error": f"Unknown integration: {iid}"}), 404

    # Save locally (persists across restarts)
    save_local_key(env_var, key)

    # Refresh provider router if this env_var maps to a known LLM provider
    if iid in getattr(provider_router, "KEY_ENV_MAP", {}):
        provider_router.refresh_provider_key(iid)
        provider_router._init_status()
    else:
        # Also check by env_var name in case suggestion uses a standard key name
        for pid, penv in getattr(provider_router, "KEY_ENV_MAP", {}).items():
            if penv == env_var:
                provider_router.refresh_provider_key(pid)
                provider_router._init_status()
                break

    # Live verification — only possible for REGISTRY entries with a verify function
    if entry:
        result = verify_integration(iid, key)
    else:
        # Dynamic suggestion: key is saved; we can't verify without a registry entry
        result = {"ok": True, "detail": f"Key saved as {env_var} — active immediately"}

    status = "connected" if result["ok"] else "error"

    return jsonify({
        "ok":     result["ok"],
        "status": status,
        "detail": result.get("detail", ""),
        "error":  result.get("error", ""),
        "iid":    iid,
        "env_var": env_var,
    })


@app.route("/api/integration-agent/status")
def api_integration_agent_status():
    """Live status of the Integration Agent (last run, checks, suggestions, events)."""
    from agents.integration_agent import get_status
    return jsonify(get_status())


@app.route("/api/integration-agent/run", methods=["POST"])
def api_integration_agent_run():
    """Trigger the Integration Agent immediately (runs in background thread)."""
    import threading
    from agents.integration_agent import run_agent
    threading.Thread(target=run_agent, daemon=True, name="fn-integ-agent-manual").start()
    return jsonify({"ok": True, "message": "Integration agent started — refresh in ~15 seconds"})


@app.route("/api/integrations/<iid>/verify", methods=["POST"])
def api_integration_verify(iid):
    """Re-verify an already-saved key without changing it."""
    from fieldnote_mcp.integrations_registry import REGISTRY, verify_integration
    entry = next((e for e in REGISTRY if e["id"] == iid), None)
    if not entry:
        return jsonify({"ok": False, "error": f"Unknown integration: {iid}"}), 404

    env_var = entry["key_env"]
    # Load key from env or local file
    try:
        import json as _json
        with open(LOCAL_KEYS_FILE) as f:
            saved = _json.load(f)
    except Exception:
        saved = {}
    key = (os.environ.get(env_var) or "").strip() or saved.get(env_var, "").strip()

    if not key:
        return jsonify({"ok": False, "error": "No key saved yet", "status": "pending"})

    result = verify_integration(iid, key)
    return jsonify({
        "ok":     result["ok"],
        "status": "connected" if result["ok"] else "error",
        "detail": result.get("detail", ""),
        "error":  result.get("error", ""),
    })



# ── MCP Hub API endpoints ─────────────────────────────────────────────────────

@app.route("/api/mcp-hub/registry")
def api_mcp_hub_registry():
    """Full hub registry with live health states."""
    from agents.mcp_registry import load_registry
    servers = load_registry()
    # Surface the scheduler's last-run time for the mcp_health job so the UI
    # can show a meaningful tooltip on the 'Checking…' badge instead of leaving
    # users wondering whether the health checker has ever fired.
    mcp_health_last_run: str | None = None
    try:
        import agents.scheduler as _sched_mod
        job = next(
            (j for j in _sched_mod.scheduler._jobs if j.name == "mcp_health"),
            None,
        )
        if job:
            mcp_health_last_run = job.last_run  # ISO-8601 UTC or None
    except Exception:
        pass
    return jsonify({
        "servers":              [s.to_dict() for s in servers],
        "count":                len(servers),
        "mcp_health_last_run":  mcp_health_last_run,
    })


@app.route("/api/mcp-hub/health")
def api_mcp_hub_health():
    """Sanitized health summary — safe for Custom GPT."""
    from agents.mcp_registry import health_summary
    return jsonify(health_summary())


@app.route("/api/mcp-hub/capabilities")
def api_mcp_hub_capabilities():
    """Capability → connected server map — safe for Custom GPT."""
    from agents.mcp_registry import capability_map
    return jsonify({"capabilities": capability_map()})


@app.route("/api/mcp-hub/migration-report")
def api_mcp_hub_migration_report():
    """Migration report from existing status.json connections."""
    import json as _json
    rp = os.path.join("fieldnote_mcp", "migration_report.json")
    if not os.path.exists(rp):
        return jsonify({"matched": [], "unmatched": [], "duplicates": [], "note": "not run yet"}), 200
    try:
        with open(rp) as f:
            return jsonify(_json.load(f))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/mcp-hub/install/<entry_id>", methods=["POST"])
def api_mcp_hub_install(entry_id: str):
    """Install + verify a hub server. Returns SSE stream of progress lines."""
    from agents.mcp_registry import get_by_id

    entry = get_by_id(entry_id)
    if entry is None:
        return jsonify({"ok": False, "error": f"Unknown server: {entry_id}"}), 404

    force = (request.get_json(silent=True) or {}).get("force", False)

    def _stream():
        import queue as _queue
        q: _queue.Queue = _queue.Queue()

        def emit(msg: str, level: str = "info"):
            q.put(json.dumps({"msg": msg, "level": level}) + "\n")

        def _run():
            from agents.mcp_agent import install_hub_server
            result = install_hub_server(entry_id, emit=emit, force=force)
            q.put(json.dumps({"done": True, **result}) + "\n")
            q.put(None)

        threading.Thread(target=_run, daemon=True, name=f"fn-hub-install-{entry_id}").start()

        while True:
            item = q.get()
            if item is None:
                break
            yield f"data: {item}\n\n"

    return Response(
        stream_with_context(_stream()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/api/mcp-hub/uninstall/<entry_id>", methods=["POST"])
def api_mcp_hub_uninstall(entry_id: str):
    from agents.mcp_registry import get_by_id
    from agents.mcp_agent import uninstall_server
    if get_by_id(entry_id) is None:
        return jsonify({"ok": False, "error": f"Unknown server: {entry_id}"}), 404
    ok = uninstall_server(entry_id)
    return jsonify({"ok": ok, "entry_id": entry_id, "health_state": "not_installed"})


@app.route("/api/mcp-hub/verify/<entry_id>", methods=["POST"])
def api_mcp_hub_verify(entry_id: str):
    """Re-run the MCP protocol handshake for an installed server."""
    from agents.mcp_registry import get_by_id, update_server
    from agents.mcp_verifier import verify_server
    from datetime import datetime, timezone

    entry = get_by_id(entry_id)
    if entry is None:
        return jsonify({"ok": False, "error": f"Unknown server: {entry_id}"}), 404

    result = verify_server(entry)
    now_iso = datetime.now(timezone.utc).isoformat()
    if result.ok:
        update_server(entry_id, health_state="connected", verified_at=now_iso)
        # Reset circuit breaker on successful verify
        try:
            from agents.mcp_router import _cb_record_success
            _cb_record_success(entry_id)
        except Exception:
            pass
    else:
        update_server(entry_id, health_state="offline" if result.error_code != "runtime_missing" else "runtime_missing")

    return jsonify({
        "ok":          result.ok,
        "error_code":  result.error_code,
        "diagnostics": result.diagnostics,
        "health_state": "connected" if result.ok else "offline",
    })


@app.route("/api/mcp-hub/enable/<entry_id>", methods=["POST"])
def api_mcp_hub_enable(entry_id: str):
    from agents.mcp_registry import get_by_id
    from agents.mcp_agent import enable_server
    if get_by_id(entry_id) is None:
        return jsonify({"ok": False, "error": f"Unknown server: {entry_id}"}), 404
    ok = enable_server(entry_id)
    return jsonify({"ok": ok, "entry_id": entry_id, "enabled": True})


@app.route("/api/mcp-hub/disable/<entry_id>", methods=["POST"])
def api_mcp_hub_disable(entry_id: str):
    from agents.mcp_registry import get_by_id
    from agents.mcp_agent import disable_server
    if get_by_id(entry_id) is None:
        return jsonify({"ok": False, "error": f"Unknown server: {entry_id}"}), 404
    ok = disable_server(entry_id)
    return jsonify({"ok": ok, "entry_id": entry_id, "enabled": False})


@app.route("/api/mcp-router/stats")
def api_mcp_router_stats():
    """Per-server circuit breaker and success/failure stats."""
    try:
        from agents.mcp_router import get_all_stats
        return jsonify(get_all_stats())
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/mcp-hub/import", methods=["POST"])
def api_mcp_hub_import():
    """Import existing MCP connections from status.json into the hub registry."""
    from agents.mcp_registry import import_existing_connections
    report = import_existing_connections()
    return jsonify({"ok": True, **report})


@app.route("/api/mcp-hub/reset-health", methods=["POST"])
def api_mcp_hub_reset_health():
    """Reset all enabled 'connected' servers to 'unverified' so the next health-check
    tick re-validates them.  Useful for external watchdogs or after a container resume
    when the scheduler wake-callback may not have fired (e.g. single-shot invocation).

    Returns JSON: {"ok": true, "reset": <count>}
    """
    try:
        from agents.mcp_registry import mark_connected_as_unverified
        reset = mark_connected_as_unverified()
        log.info("/api/mcp-hub/reset-health: %d server(s) reset to 'unverified'", reset)
        return jsonify({"ok": True, "reset": reset})
    except Exception as exc:
        log.error("/api/mcp-hub/reset-health error: %s", exc)
        return jsonify({"ok": False, "error": str(exc)}), 500


# ── MCP Hub scheduled job helpers ─────────────────────────────────────────────

# Wall-clock deadline (seconds) imposed by the caller on each verify_server call.
# This is a module-level var so tests can override it without monkey-patching internals.
_VERIFIER_DEADLINE_S: int = 30


def _mcp_health_check() -> dict:
    """Verify all enabled hub servers and update their health states.

    Each verify_server call is dispatched into a one-shot ThreadPoolExecutor so
    that a verifier that blocks in the OS (e.g. a hung wait()) is still bounded
    by _VERIFIER_DEADLINE_S.  A deadline breach is treated the same as a crash:
    log a warning and continue to the next server.
    """
    try:
        from agents.mcp_registry import load_registry, update_server
        from agents.mcp_verifier import verify_server
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as _FuturesTimeout
        from datetime import datetime, timezone
        servers  = load_registry()
        checked  = 0
        changed  = 0
        for srv in servers:
            if not srv.enabled or srv.health_state in ("not_installed", "quarantined"):
                continue
            prev_state = srv.health_state
            _pool = ThreadPoolExecutor(max_workers=1)
            try:
                fut = _pool.submit(verify_server, srv)
                result = fut.result(timeout=_VERIFIER_DEADLINE_S)
            except _FuturesTimeout:
                log.warning(
                    "mcp_health: verifier deadline exceeded for %s (%ds); skipping",
                    srv.id, _VERIFIER_DEADLINE_S,
                )
                _pool.shutdown(wait=False, cancel_futures=True)
                continue
            except Exception as srv_exc:
                log.warning("mcp_health: verifier crashed for %s: %s", srv.id, srv_exc)
                _pool.shutdown(wait=False)
                continue
            else:
                _pool.shutdown(wait=False)
            now_iso = datetime.now(timezone.utc).isoformat()
            new_state = "connected" if result.ok else (
                "runtime_missing" if result.error_code == "runtime_missing" else "offline"
            )
            update_server(srv.id, health_state=new_state, verified_at=now_iso)
            checked += 1
            if new_state != prev_state:
                changed += 1
                log.info("mcp_health: %s %s → %s", srv.id, prev_state, new_state)
        return {"checked": checked, "changed": changed}
    except Exception as exc:
        log.warning("mcp_health: error: %s", exc)
        return {"error": str(exc)}


def _mcp_version_refresh() -> dict:
    """Check PyPI/npm for newer package versions."""
    try:
        from agents.mcp_registry import load_registry, update_server
        import urllib.request as _ur
        updated = 0
        for srv in load_registry():
            if not srv.package_name or srv.install_method not in ("uvx", "pip"):
                continue
            try:
                url = f"https://pypi.org/pypi/{srv.package_name}/json"
                req = _ur.Request(url, headers={"User-Agent": "Fieldnote/1.0"})
                with _ur.urlopen(req, timeout=8) as resp:
                    data = json.loads(resp.read(32768))
                latest = data.get("info", {}).get("version", "")
                if latest and latest != srv.latest_version:
                    update_server(srv.id, latest_version=latest)
                    updated += 1
            except Exception:
                pass
        return {"updated": updated}
    except Exception as exc:
        log.warning("mcp_refresh: error: %s", exc)
        return {"error": str(exc)}


@app.route("/run-playlist", methods=["POST"])
def run_playlist_endpoint():
    """Start server-side background processing of an entire playlist."""
    data        = request.get_json(silent=True) or {}
    playlist_id = (data.get("playlist_id") or "").strip()
    if not playlist_id:
        return jsonify({"error": "playlist_id required"}), 400
    try:
        ids = get_playlist_video_ids(playlist_id)
    except Exception as ex:
        return jsonify({"error": str(ex)}), 400
    if not ids:
        return jsonify({"error": "No videos found in playlist"}), 400

    pjob_id = str(uuid.uuid4())[:8]
    _playlist_jobs[pjob_id] = {
        "events": [],
        "done":   False,
        "total":  len(ids),
    }
    threading.Thread(
        target=run_playlist_job, args=(pjob_id, ids), daemon=True
    ).start()
    return jsonify({"pjob_id": pjob_id, "total": len(ids)})


@app.route("/stream-playlist/<pjob_id>")
def stream_playlist(pjob_id):
    """SSE stream of per-video events for a playlist job.
    Uses an index into a growing list so reconnects get caught up from the start."""
    pjob = _playlist_jobs.get(pjob_id)
    if not pjob:
        return "Playlist job not found", 404

    def generate():
        idx = 0
        while True:
            evs = pjob["events"]
            if idx < len(evs):
                for ev in evs[idx:]:
                    yield f"data: {json.dumps(ev)}\n\n"
                idx = len(evs)
            if pjob.get("done") and idx >= len(pjob["events"]):
                break
            time.sleep(0.4)

    return Response(
        stream_with_context(generate()),
        content_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/api/playlist_ids")
def api_playlist_ids():
    """Return all video IDs in a playlist (no limit)."""
    playlist_id = request.args.get("list", "").strip()
    if not playlist_id:
        return jsonify({"error": "list param required"}), 400
    try:
        ids = get_playlist_video_ids(playlist_id)
        return jsonify({"ids": ids, "count": len(ids)})
    except Exception as ex:
        return jsonify({"error": str(ex)}), 500




# ── CORS headers — allows ChatGPT / Claude to call the API ────────────────────

@app.after_request
def add_cors(response):
    """Allow ChatGPT Actions and Claude.ai to call our API from any origin."""
    if request.path.startswith("/api/") or request.path.startswith("/mcp") or request.path == "/openapi.json":
        response.headers["Access-Control-Allow-Origin"]  = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    return response


@app.route("/api/<path:_>", methods=["OPTIONS"])
@app.route("/mcp/<path:_>",  methods=["OPTIONS"])
@app.route("/openapi.json",  methods=["OPTIONS"])
def handle_options(_=""):
    return "", 204


# ── MCP tool definitions (same as fieldnote_server.py) ───────────────────────

_MCP_TOOLS = [
    {
        "name": "list_skills",
        "description": "List all skills in the Fieldnote library with titles, tags, tools, and descriptions.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "tag":   {"type": "string",  "description": "Filter by tag (optional)"},
                "limit": {"type": "integer", "description": "Max results, default 25"},
            },
        },
    },
    {
        "name": "get_skill",
        "description": "Get the full markdown content and metadata of a skill by name.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Skill name (no .md extension)"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "search_skills",
        "description": "Search skills by keyword across titles, descriptions, tags, tools, and concepts.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search terms"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_all_tools",
        "description": "List every tool and library discovered across all skills.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_all_concepts",
        "description": "List every concept accumulated across all skills.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_library_stats",
        "description": "High-level stats: skill count, total tools, concepts, packages.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_recent_activity",
        "description": "Return the most recent skill creations and enhancements, newest first. Useful to understand what was learned lately.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Max results, default 20"},
            },
        },
    },
    {
        "name": "get_all_packages",
        "description": "List every Python package discovered across all skills (pip-installable names).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_mcp_connections",
        "description": "List every MCP (Model Context Protocol) server connection configured in the workspace — name, type, command/URL, and which skills use it.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_brain_map",
        "description": "Return the concept/tool relationship graph — which skills share tools or concepts, the most frequent concepts and tools, and the full skill map.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_system_status",
        "description": "Return AI provider health (Groq, Gemini, OpenAI, HuggingFace, OpenRouter state/quota), system tool availability, and the GitHub sync repo URL.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "list_github_files",
        "description": "List files and directories at a path in the Fieldnote GitHub repository. Leave path empty for the root.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Subdirectory path (optional, default = repo root)"},
            },
        },
    },
    {
        "name": "read_github_file",
        "description": "Read the raw text content of any file in the Fieldnote GitHub repository (skills, code, configs).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path within the repo, e.g. skills/claude_code.md"},
            },
            "required": ["path"],
        },
    },
]


def _mcp_call_tool(name: str, args: dict) -> dict:
    """Shared tool logic — used by both the SSE endpoint and the stdio server."""
    index = load_index()

    if name == "list_skills":
        tag   = (args.get("tag") or "").lower()
        limit = min(int(args.get("limit") or 25), 100)
        skills = []
        for skill_name, meta in index.items():
            if tag and tag not in [t.lower() for t in _nsl(meta.get("tags"))]:
                continue
            skills.append({
                "name":         skill_name,
                "title":        meta.get("title", skill_name),
                "description":  meta.get("description", ""),
                "tags":         _nsl(meta.get("tags")),
                "tools":        _nsl(meta.get("tools"))[:10],
                "concepts":     _nsl(meta.get("concepts"))[:6],
                "updated_at":   meta.get("updated_at", ""),
                "source_count": len(meta.get("history", [])) + 1,
            })
        skills.sort(key=lambda x: x["updated_at"], reverse=True)
        return {"skills": skills[:limit], "total": len(index)}

    elif name == "get_skill":
        skill_name = (args.get("name") or "").strip()
        path = os.path.join(SKILLS_DIR, f"{skill_name}.md")
        if not os.path.exists(path):
            for f in os.listdir(SKILLS_DIR):
                if f.endswith(".md") and f[:-3].lower() == skill_name.lower():
                    skill_name = f[:-3]; path = os.path.join(SKILLS_DIR, f); break
            else:
                avail = [f[:-3] for f in os.listdir(SKILLS_DIR) if f.endswith(".md")][:8]
                return {"error": f"Skill '{skill_name}' not found.", "available": avail}
        meta = index.get(skill_name, {})
        with open(path) as fh:
            content = fh.read()
        return {
            "name": skill_name, "title": meta.get("title", skill_name),
            "description": meta.get("description", ""), "tags": _nsl(meta.get("tags")),
            "tools": _nsl(meta.get("tools")), "concepts": _nsl(meta.get("concepts")),
            "steps": _nsl(meta.get("steps")), "packages": _nsl(meta.get("python_packages")),
            "source_count": len(meta.get("history", [])) + 1,
            "updated_at": meta.get("updated_at", ""), "content": content,
        }

    elif name == "search_skills":
        query = (args.get("query") or "").lower()
        results = []
        for skill_name, meta in index.items():
            hay = " ".join([meta.get("title",""), meta.get("description",""),
                            " ".join(_nsl(meta.get("tags"))), " ".join(_nsl(meta.get("tools"))),
                            " ".join(_nsl(meta.get("concepts"))), " ".join(_nsl(meta.get("steps")))]).lower()
            score = sum(hay.count(w) for w in query.split() if w)
            if score:
                results.append({"name": skill_name, "title": meta.get("title", skill_name),
                                 "description": meta.get("description",""), "score": score,
                                 "tags": _nsl(meta.get("tags")), "tools": _nsl(meta.get("tools"))[:6]})
        results.sort(key=lambda x: x["score"], reverse=True)
        return {"results": results[:12], "query": query}

    elif name == "get_all_tools":
        tools: set = set()
        for m in index.values(): tools.update(_nsl(m.get("tools")))
        return {"tools": sorted(tools), "count": len(tools)}

    elif name == "get_all_concepts":
        concepts: set = set()
        for m in index.values(): concepts.update(_nsl(m.get("concepts")))
        return {"concepts": sorted(concepts), "count": len(concepts)}

    elif name == "get_library_stats":
        tools: set = set(); concepts: set = set(); pkgs: set = set()
        for m in index.values():
            tools.update(_nsl(m.get("tools"))); concepts.update(_nsl(m.get("concepts")))
            pkgs.update(_nsl(m.get("python_packages")))
        return {"skills": len(index), "tools": len(tools), "concepts": len(concepts), "packages": len(pkgs)}


    elif name == "get_recent_activity":
        limit = min(int(args.get("limit") or 20), 100)
        events = []
        for skill_name, meta in index.items():
            for h in meta.get("history", []):
                events.append({
                    "skill": skill_name,
                    "title": meta.get("title", skill_name),
                    "action": h.get("action", "create"),
                    "source_title": h.get("source_title", ""),
                    "source_url": h.get("source_url", ""),
                    "timestamp": h.get("timestamp", ""),
                })
            if not meta.get("history"):
                events.append({
                    "skill": skill_name, "title": meta.get("title", skill_name),
                    "action": "create", "source_title": meta.get("source_title",""),
                    "source_url": meta.get("source_url",""), "timestamp": meta.get("updated_at",""),
                })
        events.sort(key=lambda x: x["timestamp"], reverse=True)
        return {"activity": events[:limit], "total_events": len(events)}

    elif name == "get_all_packages":
        pkgs: set = set()
        for m in index.values(): pkgs.update(_nsl(m.get("python_packages")))
        return {"packages": sorted(pkgs), "count": len(pkgs)}

    elif name == "get_mcp_connections":
        conns = mcp_agent.get_connections()
        # Enrich with which skills use each connection
        usage: dict = {}
        for skill_name, meta in index.items():
            for c in meta.get("mcp_connections", []):
                usage.setdefault(c, []).append(skill_name)
        for conn in conns:
            conn["used_by_skills"] = usage.get(conn.get("name",""), [])
        return {"connections": conns, "count": len(conns)}

    elif name == "get_brain_map":
        brain_path = os.path.join(SKILLS_DIR, "_brain.json")
        if not os.path.exists(brain_path):
            return {"empty": True}
        with open(brain_path) as _f:
            brain = json.load(_f)
        tc = sorted(brain.get("concepts", {}).items(), key=lambda x: x[1]["freq"], reverse=True)[:30]
        tt = sorted(brain.get("tools",    {}).items(), key=lambda x: x[1]["freq"], reverse=True)[:30]
        return {
            "total_skills": brain.get("total_skills", 0),
            "top_concepts": [{"name": k, "freq": v["freq"], "skills": v["skills"]} for k, v in tc],
            "top_tools":    [{"name": k, "freq": v["freq"], "skills": v["skills"]} for k, v in tt],
            "skill_map":    brain.get("skill_map", {}),
            "relationships": brain.get("relationships", {}),
            "updated_at":   brain.get("updated_at", ""),
        }

    elif name == "get_system_status":
        provider_router._init_status()
        prov = provider_router.provider_status()
        return {
            "providers": prov,
            "github_repo": github_sync.repo_url(),
            "github_configured": bool(os.getenv("GITHUBPAT") or os.getenv("GITHUB_TOKEN") or os.getenv("GITHUB")),
            "groq_configured":   bool(os.getenv("GROQ") or os.getenv("GROQ_API_KEY")),
            "openai_configured": bool(os.getenv("CHATGPT") or os.getenv("OPENAI_API_KEY")),
        }

    elif name == "list_github_files":
        path = (args.get("path") or "").strip("/")
        repo_url = github_sync.repo_url()
        if not repo_url:
            return {"error": "No GitHub repo configured"}
        # Parse owner/repo from URL
        parts = repo_url.rstrip("/").split("/")
        if len(parts) < 2:
            return {"error": "Cannot parse repo URL: " + repo_url}
        owner, repo = parts[-2], parts[-1]
        token = os.getenv("GITHUBPAT") or os.getenv("GITHUB_TOKEN") or os.getenv("GITHUB") or ""
        api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
        req = _UReq(api_url, headers={"Accept": "application/vnd.github+json",
                                       "User-Agent": "Fieldnote/2.0"})
        if token: req.add_header("Authorization", "Bearer " + token)
        import urllib.error
        try:
            with urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            if isinstance(data, list):
                return {"path": path, "items": [
                    {"name": i["name"], "type": i["type"], "path": i["path"],
                     "size": i.get("size", 0), "sha": i["sha"]}
                    for i in data
                ]}
            return {"path": path, "item": {"name": data.get("name"), "type": data.get("type"),
                    "size": data.get("size")}}
        except urllib.error.HTTPError as e:
            return {"error": f"GitHub API error {e.code}: {e.reason}"}
        except Exception as exc:
            return {"error": str(exc)}

    elif name == "read_github_file":
        path = (args.get("path") or "").strip("/")
        if not path:
            return {"error": "path is required"}
        repo_url = github_sync.repo_url()
        if not repo_url:
            return {"error": "No GitHub repo configured"}
        parts = repo_url.rstrip("/").split("/")
        if len(parts) < 2:
            return {"error": "Cannot parse repo URL: " + repo_url}
        owner, repo = parts[-2], parts[-1]
        token = os.getenv("GITHUBPAT") or os.getenv("GITHUB_TOKEN") or os.getenv("GITHUB") or ""
        api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
        req = _UReq(api_url, headers={"Accept": "application/vnd.github+json",
                                       "User-Agent": "Fieldnote/2.0"})
        if token: req.add_header("Authorization", "Bearer " + token)
        import urllib.error, base64
        try:
            with urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
            if data.get("encoding") == "base64":
                content = base64.b64decode(data["content"].replace("\n","\n")).decode("utf-8", errors="replace")
            else:
                content = data.get("content", "")
            return {"path": path, "name": data.get("name"), "size": data.get("size"),
                    "content": content, "sha": data.get("sha")}
        except urllib.error.HTTPError as e:
            return {"error": f"GitHub API error {e.code}: {e.reason}"}
        except Exception as exc:
            return {"error": str(exc)}

    return {"error": f"Unknown tool: {name}"}


def _handle_mcp_req(req: dict) -> dict | None:
    """Process one MCP JSON-RPC request; return response dict or None for notifications."""
    method = req.get("method", "")
    req_id = req.get("id")
    params = req.get("params", {})

    if method == "initialize":
        return {"jsonrpc":"2.0","id":req_id,"result":{
            "protocolVersion":"2024-11-05","capabilities":{"tools":{}},
            "serverInfo":{"name":"fieldnote","version":"2.0.0"},
        }}
    if method == "initialized":
        return None
    if method == "tools/list":
        return {"jsonrpc":"2.0","id":req_id,"result":{"tools":_MCP_TOOLS}}
    if method == "tools/call":
        tool_name = params.get("name","")
        tool_args = params.get("arguments",{})
        try:
            result = _mcp_call_tool(tool_name, tool_args)
        except Exception as exc:
            result = {"error": str(exc)}
        return {"jsonrpc":"2.0","id":req_id,"result":{
            "content":[{"type":"text","text":json.dumps(result,indent=2)}]
        }}
    if method == "ping":
        return {"jsonrpc":"2.0","id":req_id,"result":{}}
    if req_id is not None:
        return {"jsonrpc":"2.0","id":req_id,"error":{"code":-32601,"message":f"Method not found: {method}"}}
    return None


# ── MCP SSE transport (Claude.ai / Claude Desktop remote) ────────────────────


# ── Project Memory  •  Chat  •  Notes  •  Briefing ──────────────────────────


def _update_brain(skill: dict, skill_name: str) -> None:
    """Update _brain.json after every skill save. Completely free."""
    brain_path = os.path.join(SKILLS_DIR, "_brain.json")
    brain = {}
    if os.path.exists(brain_path):
        try:
            with open(brain_path) as f:
                brain = json.load(f)
        except Exception:
            pass
    brain.setdefault("concepts", {})
    brain.setdefault("tools", {})
    brain.setdefault("skill_map", {})
    brain.setdefault("relationships", {})
    concepts = _nsl(skill.get("concepts"))
    tools    = _nsl(skill.get("tools"))
    for c in concepts:
        brain["concepts"].setdefault(c, {"freq": 0, "skills": []})
        brain["concepts"][c]["freq"] += 1
        if skill_name not in brain["concepts"][c]["skills"]:
            brain["concepts"][c]["skills"].append(skill_name)
    for t in tools:
        brain["tools"].setdefault(t, {"freq": 0, "skills": []})
        brain["tools"][t]["freq"] += 1
        if skill_name not in brain["tools"][t]["skills"]:
            brain["tools"][t]["skills"].append(skill_name)
    brain["skill_map"][skill_name] = {
        "concepts":   concepts,
        "tools":      tools,
        "tags":       _nsl(skill.get("tags")),
        "step_count": len(_nsl(skill.get("steps"))),
    }
    brain["relationships"].setdefault(skill_name, {})
    for other, od in brain["skill_map"].items():
        if other == skill_name:
            continue
        shared = list(
            set(concepts + tools) &
            set(_nsl(od.get("concepts")) + _nsl(od.get("tools")))
        )
        if shared:
            brain["relationships"][skill_name][other] = shared[:6]
            brain["relationships"].setdefault(other, {})[skill_name] = shared[:6]
    brain["updated_at"]   = datetime.now(timezone.utc).isoformat()
    brain["total_skills"] = len(brain["skill_map"])
    with open(brain_path, "w") as f:
        json.dump(brain, f, indent=2)
    try:
        github_sync.sync_brain(brain)
    except Exception:
        pass



@app.route("/api/activity")
def api_activity():
    """Recent skill creation/enhancement history + purge events, newest first."""
    limit = min(int(request.args.get("limit") or 30), 200)
    index = load_index()
    events = []
    for skill_name, meta in index.items():
        for h in meta.get("history", []):
            events.append({
                "skill": skill_name, "title": meta.get("title", skill_name),
                "action": h.get("action","create"), "source_title": h.get("source_title",""),
                "source_url": h.get("source_url",""), "timestamp": h.get("timestamp",""),
            })
        if not meta.get("history"):
            events.append({
                "skill": skill_name, "title": meta.get("title", skill_name),
                "action": "create", "source_title": meta.get("source_title",""),
                "source_url": meta.get("source_url",""), "timestamp": meta.get("updated_at",""),
            })
    # Include purge events from the checkpoint purge log
    for p in run_checkpoint.load_purge_log():
        reason_label = "manually deleted" if p.get("reason") == "manually_deleted" else "auto-purged (stale)"
        events.append({
            "skill":        p.get("skill_name") or p.get("run_id", ""),
            "title":        p.get("skill_name") or "Degraded draft",
            "action":       "purge",
            "source_title": reason_label,
            "source_url":   "",
            "timestamp":    p.get("purged_at", ""),
        })
    events.sort(key=lambda x: x["timestamp"], reverse=True)
    return jsonify({"activity": events[:limit], "total": len(events)})


@app.route("/api/packages")
def api_packages():
    """All Python packages discovered across all skills."""
    index = load_index()
    pkgs: set = set()
    for m in index.values(): pkgs.update(_nsl(m.get("python_packages")))
    return jsonify({"packages": sorted(pkgs), "count": len(pkgs)})


@app.route("/api/snapshot")
def api_snapshot():
    """Complete library snapshot in one call — skills (with full content), tools, concepts,
    packages, MCP connections, brain summary, and provider status. Designed for AI context loading."""
    index  = load_index()
    skills = []
    for skill_name, meta in index.items():
        md_path = os.path.join(SKILLS_DIR, f"{skill_name}.md")
        content = ""
        if os.path.exists(md_path):
            try:
                with open(md_path) as f:
                    content = f.read()
            except Exception:
                pass
        skills.append({
            "name":         skill_name,
            "title":        meta.get("title", skill_name),
            "description":  meta.get("description", ""),
            "tags":         _nsl(meta.get("tags")),
            "tools":        _nsl(meta.get("tools")),
            "concepts":     _nsl(meta.get("concepts")),
            "steps":        _nsl(meta.get("steps")),
            "packages":     _nsl(meta.get("python_packages")),
            "source_count": len(meta.get("history", [])) + 1,
            "updated_at":   meta.get("updated_at", ""),
            "content":      content,
        })
    skills.sort(key=lambda x: x["updated_at"], reverse=True)

    all_tools: set = set(); all_concepts: set = set(); all_pkgs: set = set()
    for m in index.values():
        all_tools.update(_nsl(m.get("tools"))); all_concepts.update(_nsl(m.get("concepts")))
        all_pkgs.update(_nsl(m.get("python_packages")))

    brain_path = os.path.join(SKILLS_DIR, "_brain.json")
    brain_summary = {}
    if os.path.exists(brain_path):
        try:
            with open(brain_path) as f:
                b = json.load(f)
            tc = sorted(b.get("concepts",{}).items(), key=lambda x: x[1]["freq"], reverse=True)[:15]
            tt = sorted(b.get("tools",{}).items(), key=lambda x: x[1]["freq"], reverse=True)[:15]
            brain_summary = {
                "top_concepts": [{"name":k,"freq":v["freq"]} for k,v in tc],
                "top_tools":    [{"name":k,"freq":v["freq"]} for k,v in tt],
                "relationships_count": sum(len(v) for v in b.get("relationships",{}).values()),
            }
        except Exception:
            pass

    return jsonify({
        "skills":       skills,
        "total_skills": len(skills),
        "all_tools":    sorted(all_tools),
        "all_concepts": sorted(all_concepts),
        "all_packages": sorted(all_pkgs),
        "mcp_connections": mcp_agent.get_connections(),
        "brain_summary": brain_summary,
        "provider_status": provider_router.provider_status(),
        "github_repo":  github_sync.repo_url(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    })


@app.route("/api/github/repo")
def api_github_repo():
    """List files in the Fieldnote GitHub repository at an optional path."""
    path      = (request.args.get("path") or "").strip("/")
    repo_url  = github_sync.repo_url()
    if not repo_url:
        return jsonify({"error": "No GitHub repo configured. Set up GitHub sync first."}), 400
    parts = repo_url.rstrip("/").split("/")
    owner, repo = parts[-2], parts[-1]
    token = os.getenv("GITHUBPAT") or os.getenv("GITHUB_TOKEN") or os.getenv("GITHUB") or ""
    api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "Fieldnote/2.0"}
    if token: headers["Authorization"] = "Bearer " + token
    try:
        req = _UReq(api_url, headers=headers)
        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        if isinstance(data, list):
            return jsonify({"repo": repo_url, "path": path, "items": [
                {"name": i["name"], "type": i["type"], "path": i["path"],
                 "size": i.get("size",0)} for i in data
            ]})
        return jsonify({"repo": repo_url, "path": path, "item": data})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/github/repo-file")
def api_github_repo_file():
    """Read the raw content of any file in the Fieldnote GitHub repository."""
    path     = (request.args.get("path") or "").strip("/")
    if not path:
        return jsonify({"error": "path query param required"}), 400
    repo_url = github_sync.repo_url()
    if not repo_url:
        return jsonify({"error": "No GitHub repo configured."}), 400
    parts = repo_url.rstrip("/").split("/")
    owner, repo = parts[-2], parts[-1]
    token = os.getenv("GITHUBPAT") or os.getenv("GITHUB_TOKEN") or os.getenv("GITHUB") or ""
    api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "Fieldnote/2.0"}
    if token: headers["Authorization"] = "Bearer " + token
    try:
        import base64
        req = _UReq(api_url, headers=headers)
        with urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        if data.get("encoding") == "base64":
            content = base64.b64decode(data["content"].replace("\n","")).decode("utf-8", errors="replace")
        else:
            content = data.get("content","")
        return jsonify({"path": path, "name": data.get("name"), "size": data.get("size"),
                        "content": content, "sha": data.get("sha")})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500



@app.route("/api/knowledge")
def api_knowledge():
    """Return the assistant knowledge base index and all entry content."""
    from pathlib import Path
    ak_dir = Path("assistant_knowledge")
    idx_path = ak_dir / "index.json"
    entries = []
    if idx_path.exists():
        try:
            import json as _json
            data = _json.loads(idx_path.read_text())
            # Enrich with full content
            for e in data.get("entries", []):
                fpath = ak_dir / e["path"]
                e["content"] = fpath.read_text() if fpath.exists() else ""
                entries.append(e)
        except Exception:
            pass
    return jsonify({
        "entries": entries,
        "count": len(entries),
        "categories": list(github_sync.KNOWLEDGE_CATS),
    })


@app.route("/api/knowledge/upsert", methods=["POST"])
def api_knowledge_upsert():
    """Write a knowledge entry to assistant_knowledge/ and push to GitHub.

    Body JSON: { category, slug, title, content, sources?, confidence? }
    category must be one of: decisions, discoveries, session_learnings,
                              preferences, architecture
    """
    data = request.get_json(silent=True) or {}

    # Basic validation
    required = {"category", "slug", "title", "content"}
    missing  = required - set(data.keys())
    if missing:
        return jsonify({"ok": False, "error": f"Missing fields: {sorted(missing)}"}), 400

    if data.get("category") not in github_sync.KNOWLEDGE_CATS:
        return jsonify({
            "ok": False,
            "error": f"category must be one of: {sorted(github_sync.KNOWLEDGE_CATS)}"
        }), 400

    result = github_sync.sync_knowledge_entry(data)
    if not result.get("ok"):
        return jsonify(result), 500
    return jsonify(result)


@app.route("/api/brain")
def api_brain():
    brain_path = os.path.join(SKILLS_DIR, "_brain.json")
    if not os.path.exists(brain_path):
        return jsonify({"empty": True, "total_skills": 0,
                        "top_concepts": [], "top_tools": [], "relationships": []})
    try:
        with open(brain_path) as f:
            brain = json.load(f)
        tc = sorted(brain.get("concepts", {}).items(),
                    key=lambda x: x[1]["freq"], reverse=True)[:20]
        tt = sorted(brain.get("tools", {}).items(),
                    key=lambda x: x[1]["freq"], reverse=True)[:20]
        seen  = set()
        edges = []
        for skill, connected in brain.get("relationships", {}).items():
            for other, shared in connected.items():
                key = tuple(sorted([skill, other]))
                if key not in seen:
                    seen.add(key)
                    edges.append({"a": skill, "b": other, "shared": shared})
        return jsonify({
            "total_skills":  brain.get("total_skills", 0),
            "top_concepts": [{"name": k, "freq": v["freq"],
                              "skills": v["skills"][:3]} for k, v in tc],
            "top_tools":    [{"name": k, "freq": v["freq"],
                              "skills": v["skills"][:3]} for k, v in tt],
            "relationships": edges[:30],
            "updated_at":    brain.get("updated_at", ""),
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/chat", methods=["POST"])
def api_chat():
    data       = request.get_json() or {}
    message    = data.get("message", "").strip()
    skill_name = data.get("skill", "")
    history    = data.get("history", [])
    if not message:
        return jsonify({"error": "No message"}), 400
    if not GROQ_API_KEY and not OPENAI_API_KEY and not (os.getenv("Google_API_Key") or os.getenv("Gemini") or os.getenv("GOOGLE_API_KEY")):
        return jsonify({"error": "No LLM key configured (add GROQ or CHATGPT secret)"}), 503
    index         = load_index()
    context_parts = []
    if skill_name and skill_name in index:
        md_path = os.path.join(SKILLS_DIR, skill_name + ".md")
        if os.path.exists(md_path):
            with open(md_path) as fh:
                context_parts.append(fh.read()[:4500])
    else:
        msg_lower = message.lower()
        scored = []
        for sn, meta in index.items():
            hay = " ".join([
                meta.get("title", ""), meta.get("description", ""),
                " ".join(_nsl(meta.get("tools"))),
                " ".join(_nsl(meta.get("concepts"))),
                " ".join(_nsl(meta.get("tags"))),
            ]).lower()
            score = sum(hay.count(w) for w in msg_lower.split() if len(w) > 2)
            if score:
                scored.append((score, sn))
        scored.sort(reverse=True)
        for _, sn in scored[:3]:
            md_path = os.path.join(SKILLS_DIR, sn + ".md")
            if os.path.exists(md_path):
                with open(md_path) as fh:
                    sep = " --- "
                    context_parts.append("=== " + sn + " ===" + sep + fh.read()[:2500])
    total   = len(index)
    nl2     = chr(10) + chr(10)
    context = nl2.join(context_parts) if context_parts else (
        "No relevant skills found." if total else "Library empty - process a YouTube video first.")
    system_msg = (
        "You are Fieldnote, a helpful AI for a skill library with "
        + str(total) + " skill(s). Answer concisely based on the provided skill content. "
        "Reference specific steps when useful. "
        "If the answer is not in the content, say so."
        + chr(10) + chr(10) + "SKILL CONTENT:" + chr(10) + context
    )
    msgs = [{"role": "system", "content": system_msg}]
    for h in history[-8:]:
        if isinstance(h, dict) and h.get("role") in ("user", "assistant"):
            msgs.append({"role": h["role"], "content": h["content"]})
    msgs.append({"role": "user", "content": message})
    try:
        answer, provider = provider_router.call_chat_smart(msgs, max_tokens=900, temperature=0.7)
        return jsonify({"answer": answer, "skill_used": skill_name, "provider": provider})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


def _load_notes() -> dict:
    p = os.path.join(SKILLS_DIR, "_notes.json")
    if os.path.exists(p):
        try:
            with open(p) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


@app.route("/api/notes/<name>", methods=["GET", "POST"])
def api_notes(name: str):
    name  = re.sub(r"[^a-z0-9_]", "_", name.lower()).strip("_")
    notes = _load_notes()
    if request.method == "GET":
        return jsonify({"note": notes.get(name, "")})
    notes[name] = (request.get_json() or {}).get("note", "")
    with open(os.path.join(SKILLS_DIR, "_notes.json"), "w") as f:
        json.dump(notes, f, indent=2)
    return jsonify({"ok": True})


@app.route("/api/briefing", methods=["POST"])
def api_briefing():
    data       = request.get_json() or {}
    skill_name = data.get("skill", "")
    index      = load_index()
    if not index:
        return jsonify({"error": "No skills in library yet"}), 400
    if not GROQ_API_KEY and not OPENAI_API_KEY and not (os.getenv("Google_API_Key") or os.getenv("Gemini") or os.getenv("GOOGLE_API_KEY")):
        return jsonify({"error": "No LLM key configured"}), 503
    nl = chr(10)
    if skill_name and skill_name in index:
        md_path = os.path.join(SKILLS_DIR, skill_name + ".md")
        ctx = open(md_path).read()[:4000] if os.path.exists(md_path) else ""
        prompt = (
            "Generate a concise study guide:" + nl + nl + ctx + nl + nl
            + "Format:" + nl
            + "**TLDR**: 1-2 sentences" + nl
            + "**Key Takeaways**: 3-5 bullets" + nl
            + "**Quick Reference**: top 3 steps/commands" + nl
            + "**When to use**: 2-3 use cases" + nl
            + "**What to explore next**: 2-3 suggestions"
        )
    else:
        lines = []
        for sn, meta in list(index.items())[:10]:
            tools_str = ", ".join(_nsl(meta.get("tools"))[:3])
            lines.append(
                "- **" + meta.get("title", sn) + "**: "
                + meta.get("description", "")[:80]
                + " (Tools: " + tools_str + ")"
            )
        prompt = (
            "Generate a briefing for this skill library:" + nl + nl
            + nl.join(lines) + nl + nl
            + "Format:" + nl
            + "**Overview**: domains covered" + nl
            + "**Top Skills**: 5 most valuable" + nl
            + "**Learning Paths**: 2-3 sequences" + nl
            + "**Knowledge Gaps**: what to add next" + nl
            + "**Power Tools**: most frequent tools/libraries"
        )
    try:
        briefing, _prov = provider_router.call_chat_smart(
            [{"role": "user", "content": prompt}], max_tokens=1200, temperature=0.5)
        return jsonify({"briefing": briefing})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/mcp/sse")
def mcp_sse():
    """SSE transport endpoint — Claude connects here for a persistent MCP session."""
    sid = str(uuid.uuid4())[:8]
    q   = queue.Queue()
    _mcp_sessions[sid] = q

    domain   = os.getenv("REPLIT_DEV_DOMAIN", "")
    base     = f"https://{domain}" if domain else request.url_root.rstrip("/")
    post_url = f"{base}/mcp/message?sid={sid}"

    def generate():
        # MCP spec: first event must be 'endpoint' with the POST URL
        yield f"event: endpoint\ndata: {json.dumps(post_url)}\n\n"
        while True:
            try:
                msg = q.get(timeout=30)
                if msg is None:
                    break
                yield f"data: {json.dumps(msg)}\n\n"
            except queue.Empty:
                yield ": ping\n\n"
        _mcp_sessions.pop(sid, None)

    return Response(
        stream_with_context(generate()),
        content_type="text/event-stream",
        headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"},
    )


@app.route("/mcp/message", methods=["POST"])
def mcp_message():
    """Receives JSON-RPC from Claude; pushes response to the session's SSE queue."""
    sid = request.args.get("sid","")
    q   = _mcp_sessions.get(sid)
    req = request.get_json(silent=True) or {}
    resp = _handle_mcp_req(req)
    if resp and q:
        q.put(resp)
    return "", 202


# ── OpenAPI spec (ChatGPT Custom GPT Actions) ────────────────────────────────

@app.route("/openapi.json")
def openapi_spec():
    """Full OpenAPI 3.1 spec — one URL gives ChatGPT complete read access to Fieldnote."""
    domain = os.getenv("REPLIT_DEV_DOMAIN","")
    base   = f"https://{domain}" if domain else request.url_root.rstrip("/")
    spec   = {
        "openapi": "3.1.0",
        "info": {
            "title":       "Fieldnote — Complete Knowledge Library API",
            "description": (
                "Full read access to a personal AI skill library built from YouTube videos. "
                "Includes every skill with full markdown, all tools, packages, concepts, "
                "MCP server connections, concept/tool brain map, recent activity, "
                "AI provider health, and direct read access to the Fieldnote GitHub repository. "
                "Start with getFullSnapshot to load all context at once."
            ),
            "version": "3.1.0",
        },
        "servers": [{"url": base}],
        "paths": {


            "/api/discovery/stats": {
                "get": {
                    "operationId": "getDiscoveryStats",
                    "summary": "GitHub discovery agent stats — repos seen, skills created/enhanced, errors",
                    "description": "Returns aggregate counts and the 10 most recent successful discoveries from the autonomous GitHub learning agent.",
                    "parameters": [],
                    "responses": {"200": {"description": "Discovery stats", "content": {"application/json": {"schema": {"type": "object", "additionalProperties": True}}}}},
                }
            },
            "/api/discovery/log": {
                "get": {
                    "operationId": "getDiscoveryLog",
                    "summary": "Full GitHub discovery log — every repo the agent has ever evaluated",
                    "description": "Complete log of every repository the agent has processed: action taken (create/enhance/quality_denied/error), skill name, quality score, and timestamp.",
                    "parameters": [],
                    "responses": {"200": {"description": "Discovery log", "content": {"application/json": {"schema": {"type": "object", "additionalProperties": True}}}}},
                }
            },
            "/api/scheduler/run/{job_name}": {
                "post": {
                    "operationId": "triggerAgentJob",
                    "summary": "Trigger a background agent job immediately",
                    "description": "Run a named scheduler job right now. Use job_name=discover to trigger a GitHub discovery cycle. Other jobs: enhance, sync, watchlist, code_sync.",
                    "parameters": [{"name":"job_name","in":"path","required":True,"schema":{"type":"string"},"description":"Job name: discover | enhance | sync | watchlist | code_sync"}],
                    "responses": {"200": {"description": "Job triggered", "content": {"application/json": {"schema": {"type": "object", "additionalProperties": True}}}}},
                }
            },
            "/api/knowledge": {
                "get": {
                    "operationId": "getKnowledgeBase",
                    "summary": "Read the full assistant knowledge base",
                    "description": "Returns every entry the assistant has written to assistant_knowledge/ — decisions, discoveries, session learnings, preferences, and architecture notes — with full content.",
                    "parameters": [],
                    "responses": {"200": {"description": "Knowledge base entries", "content": {"application/json": {"schema": {"type": "object", "additionalProperties": True}}}}},
                }
            },
            "/api/knowledge/upsert": {
                "post": {
                    "operationId": "upsertKnowledgeEntry",
                    "summary": "Write or update a knowledge entry in the Fieldnote repo",
                    "description": "Write or update a knowledge entry in assistant_knowledge/ and push to GitHub. Records decisions, discoveries, session learnings, preferences, or architecture notes. confidence: verified | inferred | speculative.",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["category", "slug", "title", "content"],
                                    "properties": {
                                        "category":   {"type": "string", "enum": ["decisions", "discoveries", "session_learnings", "preferences", "architecture"]},
                                        "slug":       {"type": "string", "description": "URL-safe identifier, e.g. gpt-actions-openapi-compatibility"},
                                        "title":      {"type": "string", "description": "Human-readable title"},
                                        "content":    {"type": "string", "description": "Full markdown content of the entry"},
                                        "sources":    {"type": "array",  "items": {"type": "string"}, "description": "URLs or references supporting this entry"},
                                        "confidence": {"type": "string", "enum": ["verified", "inferred", "speculative"], "description": "How certain this entry is"},
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": {"description": "Entry written and pushed", "content": {"application/json": {"schema": {"type": "object", "additionalProperties": True}}}},
                        "400": {"description": "Validation error"},
                        "500": {"description": "Push failed"},
                    },
                }
            },
            "/api/snapshot": {
                "get": {
                    "operationId": "getFullSnapshot",
                    "summary": "Complete library snapshot — everything in one call",
                    "description": "Returns all skills with full markdown content, every tool, concept, and package, all MCP connections, the brain summary, AI provider status, and the GitHub repo URL. Call this first to load full context.",
                    "parameters": [],
                    "responses": {"200": {"description": "Full snapshot", "content": {"application/json": {"schema": {"type": "object", "additionalProperties": True}}}}},
                }
            },
            "/api/skills": {
                "get": {
                    "operationId": "listSkills",
                    "summary": "List all skills with metadata",
                    "description": "Returns every skill with title, description, tags, tools, concepts, and update date. Filter by keyword or tag.",
                    "parameters": [
                        {"name":"q",     "in":"query","schema":{"type":"string"},"description":"Keyword filter"},
                        {"name":"tag",   "in":"query","schema":{"type":"string"},"description":"Tag filter"},
                        {"name":"limit", "in":"query","schema":{"type":"integer"},"description":"Max results"},
                    ],
                    "responses": {"200": {"description": "Skill summaries", "content": {"application/json": {"schema": {"type": "array", "items": {"type": "object", "additionalProperties": True}}}}}},
                }
            },
            "/api/skills/{name}/content": {
                "get": {
                    "operationId": "getSkillContent",
                    "summary": "Full skill — complete markdown and all metadata",
                    "description": "Returns the entire skill markdown with steps, tools, code, and source references plus all metadata.",
                    "parameters": [{"name":"name","in":"path","required":True,"schema":{"type":"string"},"description":"Skill name without .md extension"}],
                    "responses": {
                        "200": {"description": "Full skill", "content": {"application/json": {"schema": {"type": "object", "additionalProperties": True}}}},
                        "404": {"description": "Not found"},
                    },
                }
            },
            "/api/brain": {
                "get": {
                    "operationId": "getBrainMap",
                    "summary": "Concept and tool relationship graph",
                    "description": "Shows which concepts and tools appear most often across skills, which skills share them, and how skills relate to each other.",
                    "parameters": [],
                    "responses": {"200": {"description": "Brain map", "content": {"application/json": {"schema": {"type": "object", "additionalProperties": True}}}}},
                }
            },
            "/api/activity": {
                "get": {
                    "operationId": "getRecentActivity",
                    "summary": "Recent skill creation and enhancement history",
                    "description": "Shows the most recently created or enhanced skills, which video they came from, and when.",
                    "parameters": [{"name":"limit","in":"query","schema":{"type":"integer"},"description":"Max events, default 30"}],
                    "responses": {"200": {"description": "Activity log", "content": {"application/json": {"schema": {"type": "object", "additionalProperties": True}}}}},
                }
            },
            "/api/packages": {
                "get": {
                    "operationId": "getAllPackages",
                    "summary": "All Python packages discovered across skills",
                    "description": "Returns every pip-installable package name mentioned across all skills.",
                    "parameters": [],
                    "responses": {"200": {"description": "Package list", "content": {"application/json": {"schema": {"type": "object", "additionalProperties": True}}}}},
                }
            },
            "/api/mcp/connections": {
                "get": {
                    "operationId": "getMcpConnections",
                    "summary": "All MCP server connections configured in the workspace",
                    "description": "Lists every Model Context Protocol server — name, type, transport, command or URL, and which skills reference it.",
                    "parameters": [],
                    "responses": {"200": {"description": "MCP connections", "content": {"application/json": {"schema": {"type": "array", "items": {"type": "object", "additionalProperties": True}}}}}},
                }
            },
            "/api/provider-status": {
                "get": {
                    "operationId": "getProviderStatus",
                    "summary": "AI provider health — Groq, Gemini, OpenAI, HuggingFace, OpenRouter",
                    "description": "Returns live state for each AI provider: healthy, rate_limited, quota_exhausted, auth_error, or no_key.",
                    "parameters": [],
                    "responses": {"200": {"description": "Provider states", "content": {"application/json": {"schema": {"type": "object", "additionalProperties": True}}}}},
                }
            },
            "/api/github/repo": {
                "get": {
                    "operationId": "listGithubFiles",
                    "summary": "List files in the Fieldnote GitHub repository",
                    "description": "Browse any directory of the Fieldnote GitHub repo. Leave path empty for the root listing.",
                    "parameters": [{"name":"path","in":"query","schema":{"type":"string"},"description":"Directory path, empty for root"}],
                    "responses": {
                        "200": {"description": "File listing", "content": {"application/json": {"schema": {"type": "object", "additionalProperties": True}}}},
                        "400": {"description": "No GitHub repo configured"},
                    },
                }
            },
            "/api/github/repo-file": {
                "get": {
                    "operationId": "readGithubFile",
                    "summary": "Read any file from the Fieldnote GitHub repository",
                    "description": "Fetches and returns the decoded text content of any file in the repo — skills, code, configs.",
                    "parameters": [{"name":"path","in":"query","required":True,"schema":{"type":"string"},"description":"File path in the repo, e.g. skills/claude_code.md"}],
                    "responses": {
                        "200": {"description": "File content", "content": {"application/json": {"schema": {"type": "object", "additionalProperties": True}}}},
                        "500": {"description": "File not found or GitHub error"},
                    },
                }
            },
            "/api/health": {
                "get": {
                    "operationId": "getHealth",
                    "summary": "System health — tool availability, AI keys, GitHub sync",
                    "parameters": [],
                    "responses": {"200": {"description": "Health check", "content": {"application/json": {"schema": {"type": "object", "additionalProperties": True}}}}},
                }
            },
        },
    }
    return jsonify(spec)


# ── OpenAPI 3.0.0 — ChatGPT Custom GPT Actions (validated, full property schemas) ──

def _build_gpt_spec(base: str) -> dict:
    """Return a ChatGPT-compatible OpenAPI 3.0.0 spec with every response object
    property explicitly declared. ChatGPT's action importer rejects schemas that
    use {"type":"object","additionalProperties":true} without properties.

    Key differences from /openapi.json (3.1.0):
    • openapi: "3.0.0"  — ChatGPT importer accepts 3.0.x most reliably
    • All response objects have declared 'properties'
    • $ref components keep the document DRY
    • additionalProperties uses a typed sub-schema, never plain True
    """

    # ── Reusable component schemas ────────────────────────────────────────────
    schemas = {

        "Error": {
            "type": "object",
            "description": "Standard error envelope",
            "properties": {
                "error": {"type": "string", "description": "Human-readable error message"},
                "ok":    {"type": "boolean", "description": "Always false for errors", "default": False}
            },
            "required": ["error"]
        },

        "SkillSummary": {
            "type": "object",
            "description": "Skill metadata (no full markdown content)",
            "properties": {
                "name":         {"type": "string",  "description": "Skill slug/identifier"},
                "title":        {"type": "string",  "description": "Human-readable title"},
                "description":  {"type": "string",  "description": "Short summary"},
                "tags":         {"type": "array",   "items": {"type": "string"}, "description": "Category tags"},
                "tools":        {"type": "array",   "items": {"type": "string"}, "description": "Tools and libraries"},
                "source_title": {"type": "string",  "description": "Source video title"},
                "source_url":   {"type": "string",  "description": "Source video URL"},
                "video_id":     {"type": "string",  "description": "YouTube video ID"},
                "method":       {"type": "string",  "description": "Transcript method: captions | whisper | yt_dlp_subs | whisper_local"},
                "action":       {"type": "string",  "enum": ["create", "enhance"], "description": "Last action"},
                "created_at":   {"type": "string",  "description": "ISO 8601 creation timestamp"},
                "updated_at":   {"type": "string",  "description": "ISO 8601 last-updated timestamp"}
            },
            "required": ["name", "title", "description"]
        },

        "SkillContent": {
            "type": "object",
            "description": "Full skill with all metadata and markdown content",
            "properties": {
                "name":            {"type": "string",  "description": "Skill slug"},
                "title":           {"type": "string",  "description": "Human-readable title"},
                "description":     {"type": "string",  "description": "Short summary"},
                "tags":            {"type": "array",   "items": {"type": "string"}},
                "tools":           {"type": "array",   "items": {"type": "string"}},
                "concepts":        {"type": "array",   "items": {"type": "string"}},
                "steps":           {"type": "array",   "items": {"type": "string"}, "description": "Ordered step list"},
                "python_packages": {"type": "array",   "items": {"type": "string"}, "description": "Required pip packages"},
                "source_count":    {"type": "integer", "description": "Number of source videos"},
                "updated_at":      {"type": "string",  "description": "ISO 8601 timestamp"},
                "content":         {"type": "string",  "description": "Full markdown content with all sections"}
            },
            "required": ["name", "title", "content"]
        },

        "BrainNode": {
            "type": "object",
            "description": "A concept or tool node in the knowledge graph",
            "properties": {
                "name":   {"type": "string",  "description": "Concept or tool name"},
                "freq":   {"type": "integer", "description": "Number of skills that mention this"},
                "skills": {"type": "array",   "items": {"type": "string"}, "description": "Top skill slugs that use this"}
            },
            "required": ["name", "freq", "skills"]
        },

        "BrainRelationship": {
            "type": "object",
            "description": "Relationship edge between two skills sharing concepts/tools",
            "properties": {
                "a":      {"type": "string", "description": "First skill slug"},
                "b":      {"type": "string", "description": "Second skill slug"},
                "shared": {"type": "array",  "items": {"type": "string"}, "description": "Shared concept/tool names"}
            },
            "required": ["a", "b", "shared"]
        },

        "ActivityEvent": {
            "type": "object",
            "description": "A skill creation or enhancement event",
            "properties": {
                "skill":        {"type": "string", "description": "Skill slug"},
                "title":        {"type": "string", "description": "Skill title"},
                "action":       {"type": "string", "enum": ["create", "enhance"]},
                "source_title": {"type": "string", "description": "Source video title"},
                "source_url":   {"type": "string", "description": "Source video URL"},
                "timestamp":    {"type": "string", "description": "ISO 8601 timestamp"}
            },
            "required": ["skill", "title", "action", "timestamp"]
        },

        "McpConnection": {
            "type": "object",
            "description": "MCP server connection configured in the workspace",
            "properties": {
                "name":         {"type": "string",  "description": "Connection name"},
                "tool":         {"type": "string",  "description": "Tool/package name"},
                "source":       {"type": "string",  "description": "How it was discovered: skill | manual | agent"},
                "repo_url":     {"type": "string",  "description": "GitHub repository URL"},
                "full_name":    {"type": "string",  "description": "GitHub owner/repo"},
                "needs_auth":   {"type": "boolean", "description": "Requires an API key"},
                "installed_at": {"type": "string",  "description": "ISO 8601 timestamp"},
                "status":       {"type": "string",  "enum": ["ready", "pending", "error"]},
                "install_hint": {"type": "string",  "description": "Setup instructions if auth is needed"}
            },
            "required": ["name", "tool", "source"]
        },

        "ProviderState": {
            "type": "object",
            "description": "Health state of a single AI provider",
            "properties": {
                "state": {
                    "type": "string",
                    "enum": ["healthy", "rate_limited", "quota_exhausted", "auth_error", "no_key", ""],
                    "description": "Current availability state"
                },
                "model":           {"type": "string",  "description": "Active model name"},
                "blackout_until":  {"type": "number",  "description": "Unix timestamp when blackout expires (0 = none)"},
                "calls":           {"type": "integer", "description": "Total calls this session"},
                "has_key":         {"type": "boolean", "description": "API key is configured"}
            },
            "required": ["state"]
        },

        "GithubFileItem": {
            "type": "object",
            "description": "File or directory entry in the GitHub repo",
            "properties": {
                "name": {"type": "string",  "description": "File or directory name"},
                "type": {"type": "string",  "enum": ["file", "dir"], "description": "Entry type"},
                "path": {"type": "string",  "description": "Full path from repo root"},
                "size": {"type": "integer", "description": "File size in bytes (0 for directories)"}
            },
            "required": ["name", "type", "path"]
        },

        "KnowledgeEntry": {
            "type": "object",
            "description": "Entry in the assistant knowledge base",
            "properties": {
                "category":   {
                    "type": "string",
                    "enum": ["decisions", "discoveries", "session_learnings", "preferences", "architecture"]
                },
                "slug":       {"type": "string", "description": "URL-safe identifier"},
                "title":      {"type": "string", "description": "Human-readable title"},
                "content":    {"type": "string", "description": "Full markdown content"},
                "path":       {"type": "string", "description": "File path in the repository"},
                "sources":    {"type": "array",  "items": {"type": "string"}, "description": "Supporting references"},
                "confidence": {"type": "string", "enum": ["verified", "inferred", "speculative"]}
            },
            "required": ["category", "slug", "title", "content"]
        },

        "SnapshotSkill": {
            "type": "object",
            "description": "Full skill within a snapshot (includes content)",
            "properties": {
                "name":         {"type": "string"},
                "title":        {"type": "string"},
                "description":  {"type": "string"},
                "tags":         {"type": "array", "items": {"type": "string"}},
                "tools":        {"type": "array", "items": {"type": "string"}},
                "concepts":     {"type": "array", "items": {"type": "string"}},
                "steps":        {"type": "array", "items": {"type": "string"}},
                "packages":     {"type": "array", "items": {"type": "string"}},
                "source_count": {"type": "integer"},
                "updated_at":   {"type": "string"},
                "content":      {"type": "string", "description": "Full markdown"}
            },
            "required": ["name", "title"]
        },

        "BrainSummary": {
            "type": "object",
            "description": "Abbreviated brain graph for snapshot responses",
            "properties": {
                "top_concepts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "freq": {"type": "integer"}
                        },
                        "required": ["name", "freq"]
                    }
                },
                "top_tools": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "freq": {"type": "integer"}
                        },
                        "required": ["name", "freq"]
                    }
                },
                "relationships_count": {"type": "integer"}
            }
        },

        "DiscoveryRecentItem": {
            "type": "object",
            "description": "One recent GitHub discovery result",
            "properties": {
                "repo":         {"type": "string", "description": "Repository full_name (owner/repo)"},
                "action":       {"type": "string", "enum": ["create", "enhance", "quality_denied", "error", "skip"]},
                "skill_name":   {"type": "string", "description": "Skill created or enhanced"},
                "processed_at": {"type": "string", "description": "ISO 8601 timestamp"},
                "quality_score":{"type": "number", "description": "Quality gate score 0–1"},
                "error":        {"type": "string", "description": "Error message when action=error"}
            },
            "required": ["repo", "action", "processed_at"]
        },

        "DiscoveryLogEntry": {
            "type": "object",
            "description": "Discovery log entry for one repository",
            "properties": {
                "action":        {"type": "string", "enum": ["create", "enhance", "quality_denied", "error", "skip"]},
                "skill_name":    {"type": "string"},
                "processed_at":  {"type": "string"},
                "quality_score": {"type": "number"},
                "error":         {"type": "string"}
            },
            "required": ["action", "processed_at"]
        },

    }

    # ── Helper: build a $ref ──────────────────────────────────────────────────
    def ref(name: str) -> dict:
        return {"$ref": f"#/components/schemas/{name}"}

    # ── Path definitions ──────────────────────────────────────────────────────
    paths = {

        "/api/health": {"get": {
            "operationId": "getHealth",
            "summary": "System health — tool availability, AI keys, GitHub sync",
            "description": "Returns availability of yt-dlp, ffmpeg, npx and whether each AI provider key is configured. Safe to poll frequently.",
            "parameters": [],
            "responses": {
                "200": {"description": "Health check", "content": {"application/json": {"schema": {
                    "type": "object",
                    "description": "Health status for every system component",
                    "properties": {
                        "groq":        {"type": "boolean", "description": "Groq API key configured"},
                        "chatgpt":     {"type": "boolean", "description": "OpenAI API key configured"},
                        "github_sync": {"type": "boolean", "description": "GitHub sync PAT configured"},
                        "sync_repo":   {"type": "string",  "description": "GitHub repository URL"},
                        "ytdlp":       {"type": "boolean", "description": "yt-dlp installed"},
                        "ffmpeg":      {"type": "boolean", "description": "ffmpeg installed"},
                        "github":      {"type": "boolean", "description": "Any GitHub token available"},
                        "npx":         {"type": "boolean", "description": "npx installed"}
                    },
                    "required": ["groq", "chatgpt", "ytdlp", "ffmpeg", "github", "npx"]
                }}}}
            }
        }},

        "/api/provider-status": {"get": {
            "operationId": "getProviderStatus",
            "summary": "AI provider health — Groq, Gemini, OpenAI, HuggingFace, OpenRouter",
            "description": "Returns live state for each AI provider: healthy, rate_limited, quota_exhausted, auth_error, or no_key.",
            "parameters": [],
            "responses": {
                "200": {"description": "Provider states keyed by provider name", "content": {"application/json": {"schema": {
                    "type": "object",
                    "description": "Map of provider name to health state",
                    "properties": {
                        "groq":        ref("ProviderState"),
                        "gemini":      ref("ProviderState"),
                        "openai":      ref("ProviderState"),
                        "huggingface": ref("ProviderState"),
                        "openrouter":  ref("ProviderState")
                    }
                }}}}
            }
        }},

        "/api/snapshot": {"get": {
            "operationId": "getFullSnapshot",
            "summary": "Complete library snapshot — everything in one call",
            "description": "All skills with full markdown, every tool/concept/package, all MCP connections, brain summary, AI provider status, and GitHub repo URL. Call this first to load full context. Response can be large (>100KB for large libraries).",
            "parameters": [],
            "responses": {
                "200": {"description": "Full snapshot", "content": {"application/json": {"schema": {
                    "type": "object",
                    "description": "Complete library state",
                    "properties": {
                        "skills":          {"type": "array",   "items": ref("SnapshotSkill"), "description": "All skills with content"},
                        "total_skills":    {"type": "integer", "description": "Total skill count"},
                        "all_tools":       {"type": "array",   "items": {"type": "string"}, "description": "Every tool mentioned across all skills"},
                        "all_concepts":    {"type": "array",   "items": {"type": "string"}, "description": "Every concept mentioned"},
                        "all_packages":    {"type": "array",   "items": {"type": "string"}, "description": "Every pip package mentioned"},
                        "mcp_connections": {"type": "array",   "items": ref("McpConnection")},
                        "brain_summary":   ref("BrainSummary"),
                        "provider_status": {
                            "type": "object",
                            "description": "Current AI provider states",
                            "properties": {
                                "groq":        ref("ProviderState"),
                                "gemini":      ref("ProviderState"),
                                "openai":      ref("ProviderState"),
                                "huggingface": ref("ProviderState"),
                                "openrouter":  ref("ProviderState")
                            }
                        },
                        "github_repo":  {"type": "string",  "description": "GitHub repository URL"},
                        "generated_at": {"type": "string",  "description": "ISO 8601 snapshot timestamp"}
                    },
                    "required": ["skills", "total_skills", "generated_at"]
                }}}}
            }
        }},

        "/api/skills": {"get": {
            "operationId": "listSkills",
            "summary": "List all skills with metadata",
            "description": "Returns every skill with title, description, tags, tools, and update date. Filter by keyword (q) or tag. Does not include full markdown — use getSkillContent for that.",
            "parameters": [
                {"name": "q",     "in": "query", "schema": {"type": "string"},  "description": "Keyword search across title, description, tags"},
                {"name": "tag",   "in": "query", "schema": {"type": "string"},  "description": "Filter by exact tag value"},
                {"name": "limit", "in": "query", "schema": {"type": "integer"}, "description": "Max number of results"},
            ],
            "responses": {
                "200": {"description": "Array of skill summaries", "content": {"application/json": {"schema": {
                    "type": "array",
                    "items": ref("SkillSummary"),
                    "description": "Skills matching the filter, newest first"
                }}}}
            }
        }},

        "/api/skills/{name}/content": {"get": {
            "operationId": "getSkillContent",
            "summary": "Full skill — complete markdown and all metadata",
            "description": "Returns the entire skill markdown with steps, tools, code, and source references plus all metadata. Always fetch full content rather than relying on summaries.",
            "parameters": [
                {"name": "name", "in": "path", "required": True,
                 "schema": {"type": "string"}, "description": "Skill slug (no .md extension), e.g. langchain_rag_pipeline"}
            ],
            "responses": {
                "200": {"description": "Full skill with content", "content": {"application/json": {"schema": ref("SkillContent")}}},
                "404": {"description": "Skill not found",         "content": {"application/json": {"schema": ref("Error")}}}
            }
        }},

        "/api/brain": {"get": {
            "operationId": "getBrainMap",
            "summary": "Concept and tool relationship graph",
            "description": "Shows which concepts/tools appear most often across skills, which skills share them, and how skills relate to each other through shared concepts.",
            "parameters": [],
            "responses": {
                "200": {"description": "Brain map", "content": {"application/json": {"schema": {
                    "type": "object",
                    "description": "Full knowledge graph",
                    "properties": {
                        "total_skills":   {"type": "integer"},
                        "top_concepts":   {"type": "array", "items": ref("BrainNode"), "description": "Top 20 concepts by frequency"},
                        "top_tools":      {"type": "array", "items": ref("BrainNode"), "description": "Top 20 tools by frequency"},
                        "relationships":  {"type": "array", "items": ref("BrainRelationship"), "description": "Top 30 skill-to-skill edges"},
                        "updated_at":     {"type": "string", "description": "ISO 8601 timestamp"}
                    },
                    "required": ["total_skills", "top_concepts", "top_tools", "relationships"]
                }}}}
            }
        }},

        "/api/activity": {"get": {
            "operationId": "getRecentActivity",
            "summary": "Recent skill creation and enhancement history",
            "description": "Shows the most recently created or enhanced skills, which video they came from, and when. Useful for 'what have I been learning lately?' queries.",
            "parameters": [
                {"name": "limit", "in": "query", "schema": {"type": "integer"}, "description": "Max events to return (default 30, max 200)"}
            ],
            "responses": {
                "200": {"description": "Activity log", "content": {"application/json": {"schema": {
                    "type": "object",
                    "description": "Paginated activity events",
                    "properties": {
                        "activity": {"type": "array",   "items": ref("ActivityEvent"), "description": "Events, newest first"},
                        "total":    {"type": "integer", "description": "Total number of events available"}
                    },
                    "required": ["activity", "total"]
                }}}}
            }
        }},

        "/api/packages": {"get": {
            "operationId": "getAllPackages",
            "summary": "All Python packages discovered across skills",
            "description": "Returns every pip-installable package mentioned across all skills. Useful for generating requirements.txt or checking what packages the library covers.",
            "parameters": [],
            "responses": {
                "200": {"description": "Package list", "content": {"application/json": {"schema": {
                    "type": "object",
                    "description": "Aggregated packages",
                    "properties": {
                        "packages": {"type": "array",   "items": {"type": "string"}, "description": "Sorted list of package names"},
                        "count":    {"type": "integer", "description": "Total count"}
                    },
                    "required": ["packages", "count"]
                }}}}
            }
        }},

        "/api/mcp/connections": {"get": {
            "operationId": "getMcpConnections",
            "summary": "All MCP server connections configured in the workspace",
            "description": "Lists every Model Context Protocol server — name, source, repo, auth status, and installation hint.",
            "parameters": [],
            "responses": {
                "200": {"description": "MCP connections", "content": {"application/json": {"schema": {
                    "type": "array",
                    "items": ref("McpConnection"),
                    "description": "All registered MCP connections"
                }}}}
            }
        }},

        "/api/knowledge": {"get": {
            "operationId": "getKnowledgeBase",
            "summary": "Read the full assistant knowledge base",
            "description": "Returns every entry the assistant has written to assistant_knowledge/ — decisions, discoveries, session learnings, preferences, architecture notes — with full content.",
            "parameters": [],
            "responses": {
                "200": {"description": "Knowledge base", "content": {"application/json": {"schema": {
                    "type": "object",
                    "description": "Full knowledge base",
                    "properties": {
                        "entries":    {"type": "array",   "items": ref("KnowledgeEntry"), "description": "All knowledge entries"},
                        "count":      {"type": "integer", "description": "Total entry count"},
                        "categories": {"type": "array",   "items": {"type": "string"},    "description": "Valid category names"}
                    },
                    "required": ["entries", "count", "categories"]
                }}}}
            }
        }},

        "/api/knowledge/upsert": {"post": {
            "operationId": "upsertKnowledgeEntry",
            "summary": "Write or update a knowledge entry",
            "description": "Write or update a knowledge entry in assistant_knowledge/ and push to GitHub. Records decisions, discoveries, session learnings, preferences, or architecture notes.",
            "requestBody": {
                "required": True,
                "content": {"application/json": {"schema": {
                    "type": "object",
                    "description": "Knowledge entry to write",
                    "properties": {
                        "category":   {"type": "string", "enum": ["decisions", "discoveries", "session_learnings", "preferences", "architecture"], "description": "Knowledge category"},
                        "slug":       {"type": "string", "description": "URL-safe identifier, e.g. gpt-actions-schema-fix"},
                        "title":      {"type": "string", "description": "Human-readable title"},
                        "content":    {"type": "string", "description": "Full markdown content"},
                        "sources":    {"type": "array",  "items": {"type": "string"}, "description": "URLs or references"},
                        "confidence": {"type": "string", "enum": ["verified", "inferred", "speculative"]}
                    },
                    "required": ["category", "slug", "title", "content"]
                }}}
            },
            "responses": {
                "200": {"description": "Entry written and pushed", "content": {"application/json": {"schema": {
                    "type": "object",
                    "description": "Write result",
                    "properties": {
                        "ok":      {"type": "boolean"},
                        "path":    {"type": "string",  "description": "File path written"},
                        "pushed":  {"type": "boolean", "description": "Whether GitHub push succeeded"},
                        "message": {"type": "string",  "description": "Status message"}
                    },
                    "required": ["ok"]
                }}}},
                "400": {"description": "Validation error", "content": {"application/json": {"schema": ref("Error")}}},
                "500": {"description": "Push failed",       "content": {"application/json": {"schema": ref("Error")}}}
            }
        }},

        "/api/github/repo": {"get": {
            "operationId": "listGithubFiles",
            "summary": "List files in the Fieldnote GitHub repository",
            "description": "Browse any directory of the Fieldnote GitHub repo. Leave path empty for the root listing.",
            "parameters": [
                {"name": "path", "in": "query", "schema": {"type": "string"}, "description": "Directory path from repo root, empty for root"}
            ],
            "responses": {
                "200": {"description": "File listing", "content": {"application/json": {"schema": {
                    "type": "object",
                    "description": "Directory listing",
                    "properties": {
                        "repo":  {"type": "string", "description": "Repository URL"},
                        "path":  {"type": "string", "description": "Requested path"},
                        "items": {"type": "array",  "items": ref("GithubFileItem"), "description": "Files and directories"}
                    },
                    "required": ["repo", "path", "items"]
                }}}},
                "400": {"description": "No GitHub repo configured", "content": {"application/json": {"schema": ref("Error")}}},
                "500": {"description": "GitHub API error",           "content": {"application/json": {"schema": ref("Error")}}}
            }
        }},

        "/api/github/repo-file": {"get": {
            "operationId": "readGithubFile",
            "summary": "Read any file from the Fieldnote GitHub repository",
            "description": "Fetches and returns the decoded text content of any file in the repo — skills, code, configs.",
            "parameters": [
                {"name": "path", "in": "query", "required": True,
                 "schema": {"type": "string"}, "description": "File path, e.g. skills/claude_code.md or README.md"}
            ],
            "responses": {
                "200": {"description": "File content", "content": {"application/json": {"schema": {
                    "type": "object",
                    "description": "File metadata and decoded content",
                    "properties": {
                        "path":    {"type": "string",  "description": "File path"},
                        "name":    {"type": "string",  "description": "Filename"},
                        "size":    {"type": "integer", "description": "File size in bytes"},
                        "content": {"type": "string",  "description": "Decoded UTF-8 file content"},
                        "sha":     {"type": "string",  "description": "Git blob SHA"}
                    },
                    "required": ["path", "name", "content"]
                }}}},
                "500": {"description": "File not found or GitHub error", "content": {"application/json": {"schema": ref("Error")}}}
            }
        }},

        "/api/discovery/stats": {"get": {
            "operationId": "getDiscoveryStats",
            "summary": "GitHub discovery agent stats — repos seen, skills created, errors",
            "description": "Returns aggregate counts and the 10 most recent successful discoveries from the autonomous GitHub learning agent.",
            "parameters": [],
            "responses": {
                "200": {"description": "Discovery statistics", "content": {"application/json": {"schema": {
                    "type": "object",
                    "description": "Discovery agent statistics",
                    "properties": {
                        "total_repos_seen":   {"type": "integer", "description": "Total repos the agent has evaluated"},
                        "skills_created":     {"type": "integer", "description": "Skills created from GitHub READMEs"},
                        "skills_enhanced":    {"type": "integer", "description": "Existing skills updated"},
                        "quality_denied":     {"type": "integer", "description": "Repos rejected by quality gate"},
                        "errors":             {"type": "integer", "description": "Processing errors"},
                        "recent_discoveries": {"type": "array",   "items": ref("DiscoveryRecentItem"), "description": "10 most recent successes"}
                    },
                    "required": ["total_repos_seen", "skills_created", "skills_enhanced", "errors", "recent_discoveries"]
                }}}}
            }
        }},

        "/api/discovery/log": {"get": {
            "operationId": "getDiscoveryLog",
            "summary": "Full GitHub discovery log — every repo the agent has evaluated",
            "description": "Complete log of every repository the agent has processed: action taken (create/enhance/quality_denied/error), skill name, quality score, and timestamp. Keys are repo full_names (owner/repo).",
            "parameters": [],
            "responses": {
                "200": {"description": "Discovery log", "content": {"application/json": {"schema": {
                    "type": "object",
                    "description": "Map of repository full_name to discovery result",
                    "additionalProperties": ref("DiscoveryLogEntry")
                }}}}
            }
        }},

        "/api/scheduler/run/{job_name}": {"post": {
            "operationId": "triggerSchedulerJob",
            "summary": "Trigger a background agent job immediately",
            "description": "Run a named scheduler job right now without waiting for its schedule. Use job_name=discover to run a GitHub discovery cycle, enhance for DCA enhancement, sync for GitHub push, watchlist to process queued URLs.",
            "parameters": [
                {"name": "job_name", "in": "path", "required": True,
                 "schema": {"type": "string", "enum": ["discover", "enhance", "sync", "watchlist", "code_sync", "integrations", "mcp_health", "mcp_refresh"]},
                 "description": "Job to trigger immediately"}
            ],
            "responses": {
                "200": {"description": "Job triggered", "content": {"application/json": {"schema": {
                    "type": "object",
                    "description": "Job trigger result",
                    "properties": {
                        "ok":      {"type": "boolean"},
                        "job":     {"type": "string",  "description": "Job name that was triggered"},
                        "message": {"type": "string",  "description": "Status message"},
                        "ran_at":  {"type": "string",  "description": "ISO 8601 execution timestamp"}
                    },
                    "required": ["ok"]
                }}}},
                "404": {"description": "Unknown job name", "content": {"application/json": {"schema": ref("Error")}}}
            }
        }},

        "/api/mcp-hub/health": {"get": {
            "operationId": "getMcpHubHealth",
            "summary": "MCP Hub health summary — counts by state",
            "description": "Returns sanitized health counts for all hub servers: connected, degraded, offline, quarantined, not_installed, runtime_missing, missing_credential.",
            "parameters": [],
            "responses": {
                "200": {"description": "Health summary", "content": {"application/json": {"schema": {
                    "type": "object",
                    "properties": {
                        "total":          {"type": "integer"},
                        "connected":      {"type": "integer"},
                        "degraded":       {"type": "integer"},
                        "offline":        {"type": "integer"},
                        "quarantined":    {"type": "integer"},
                        "not_installed":  {"type": "integer"},
                    },
                }}}}
            }
        }},

        "/api/mcp-hub/capabilities": {"get": {
            "operationId": "getMcpHubCapabilities",
            "summary": "MCP capability map — which servers handle which tasks",
            "description": "Returns a map of capability name (e.g. web_search, transcription) to list of connected server names that handle it.",
            "parameters": [],
            "responses": {
                "200": {"description": "Capability map", "content": {"application/json": {"schema": {
                    "type": "object",
                    "properties": {
                        "capabilities": {"type": "object", "description": "capability → list of server names",
                                         "additionalProperties": {"type": "array", "items": {"type": "string"}}},
                    },
                }}}}
            }
        }},

    }  # end paths

    return {
        "openapi": "3.0.0",
        "info": {
            "title": "Fieldnote — Personal AI Knowledge Library",
            "description": (
                "Complete read and write access to a personal AI skill library built from YouTube videos. "
                "Every skill has full markdown content, steps, tools, concepts, and source references. "
                "Start with getFullSnapshot to load all context at once, or listSkills + getSkillContent "
                "for targeted queries. Record discoveries and decisions with upsertKnowledgeEntry."
            ),
            "version": "4.0.0",
        },
        "servers": [{"url": base, "description": "Fieldnote live instance"}],
        "paths": paths,
        "components": {"schemas": schemas},
    }


@app.route("/openapi-gpt.json")
def openapi_gpt_spec():
    """OpenAPI 3.0.0 schema validated for ChatGPT Custom GPT Actions import.

    Uses explicit property definitions on every response object schema.
    ChatGPT's action importer rejects {'type':'object','additionalProperties':true}
    schemas without 'properties'. This endpoint fixes that across all 16 operations.
    """
    domain = os.getenv("REPLIT_DEV_DOMAIN", "")
    base   = f"https://{domain}" if domain else request.url_root.rstrip("/")
    resp   = jsonify(_build_gpt_spec(base))
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Cache-Control"] = "no-cache"
    return resp


@app.route("/api/schema/health")
def api_schema_health():
    """Return validation metadata about the GPT-compatible OpenAPI schema.
    Used by the Integrations page to show schema health indicator."""
    domain = os.getenv("REPLIT_DEV_DOMAIN", "")
    base   = f"https://{domain}" if domain else request.url_root.rstrip("/")
    spec   = _build_gpt_spec(base)

    paths      = spec.get("paths", {})
    operations = sum(len(v) for v in paths.values())  # count HTTP methods
    schemas    = spec.get("components", {}).get("schemas", {})

    # Validate: count operations whose 200 responses have no properties on object schemas
    errors = []
    for path, methods in paths.items():
        for method, op in methods.items():
            op_id = op.get("operationId", f"{method} {path}")
            for status, resp_def in op.get("responses", {}).items():
                if status != "200":
                    continue
                content = resp_def.get("content", {})
                for ct, ct_def in content.items():
                    s = ct_def.get("schema", {})
                    if s.get("type") == "object" and not s.get("properties") and not s.get("$ref") and s.get("additionalProperties") is True:
                        errors.append(f"{op_id}: object response missing properties")

    return jsonify({
        "schema_url":       f"{base}/openapi-gpt.json",
        "standard_url":     f"{base}/openapi.json",
        "openapi_version":  spec["openapi"],
        "info_version":     spec["info"]["version"],
        "endpoint_count":   len(paths),
        "operation_count":  operations,
        "schema_count":     len(schemas),
        "errors":           errors,
        "error_count":      len(errors),
        "chatgpt_compatible": len(errors) == 0,
        "validated_at":     datetime.now(timezone.utc).isoformat(),
    })


# ── Per-skill content API ────────────────────────────────────────────────────

@app.route("/api/skills/<name>/content")
def api_skill_content(name: str):
    """Return a skill's full markdown + metadata — used by ChatGPT and Claude."""
    name     = re.sub(r"[^a-z0-9_]","_", name.lower()).strip("_")
    md_path  = os.path.join(SKILLS_DIR, f"{name}.md")
    if not os.path.exists(md_path):
        # case-insensitive search
        for f in os.listdir(SKILLS_DIR):
            if f.endswith(".md") and f[:-3].lower() == name.lower():
                name = f[:-3]; md_path = os.path.join(SKILLS_DIR, f); break
        else:
            return jsonify({"error": f"Skill '{name}' not found"}), 404
    index = load_index()
    meta  = index.get(name, {})
    with open(md_path) as fh:
        content = fh.read()
    return jsonify({
        "name":         name,
        "title":        meta.get("title", name),
        "description":  meta.get("description",""),
        "tags":         _nsl(meta.get("tags")),
        "tools":        _nsl(meta.get("tools")),
        "concepts":     _nsl(meta.get("concepts")),
        "steps":        _nsl(meta.get("steps")),
        "python_packages": _nsl(meta.get("python_packages")),
        "source_count": len(meta.get("history",[])) + 1,
        "updated_at":   meta.get("updated_at",""),
        "content":      content,
    })


@app.route("/api/skills/<name>/meta")
def api_skill_meta(name: str):
    """Lightweight endpoint returning index metadata for a single skill (includes _baseline flag)."""
    name = re.sub(r"[^a-z0-9_]", "_", name.lower()).strip("_")
    index = load_index()
    meta = index.get(name)
    if meta is None:
        return jsonify({"error": f"Skill '{name}' not found"}), 404
    return jsonify({
        "name":        name,
        "title":       meta.get("title", name),
        "description": meta.get("description", ""),
        "tags":        _nsl(meta.get("tags")),
        "tools":       _nsl(meta.get("tools")),
        "_baseline":   meta.get("_baseline", False),
        "updated_at":  meta.get("updated_at", ""),
    })


@app.route("/api/skills/<name>/enrich", methods=["POST"])
def api_skill_enrich(name: str):
    """Push a baseline skill to the front of the enrichment queue and trigger an
    immediate attempt in a background thread."""
    try:
        import agents.discovery_enrichment as de
        import agents.github_discovery as gd

        name = re.sub(r"[^a-z0-9_]", "_", name.lower()).strip("_")
        index = load_index()
        meta = index.get(name)
        if meta is None:
            return jsonify({"ok": False, "error": f"Skill '{name}' not found"}), 404
        if not meta.get("_baseline"):
            return jsonify({"ok": False, "error": "Skill is not a baseline — nothing to enrich"}), 400

        # Find the full_name (owner/repo) via the discovery log
        disc_log = gd.load_discovery_log()
        full_name = None
        stars = 0
        fingerprint = ""
        for fn, v in disc_log.items():
            if v.get("skill_name") == name:
                full_name = fn
                stars = v.get("stars", 0)
                fingerprint = v.get("fingerprint", "")
                break

        if not full_name:
            return jsonify({"ok": False, "error": "Could not find GitHub repo for this baseline skill"}), 400

        # Push to the very front of the enrichment queue
        de.enqueue_priority(full_name, stars, fingerprint)

        # Clear any stale error from a prior attempt so the poll doesn't
        # immediately terminate with a false failure on the new run.
        _idx_pre = load_index()
        if name in _idx_pre:
            _idx_pre[name].pop("_enrich_error", None)
            save_index(_idx_pre)

        # De-duplicate: reject if a thread for the same repo is already running
        with _enrich_in_progress_lock:
            if full_name in _enrich_in_progress:
                return jsonify({"ok": False, "error": "enrichment already in progress"}), 409
            _enrich_in_progress.add(full_name)

        # Fire an immediate enrichment attempt in a background thread
        queue_item = {
            "full_name":   full_name,
            "stars":       stars,
            "retry_count": 0,
            "fingerprint": fingerprint,
        }

        _ENRICH_TIMEOUT = 120  # seconds

        def _bg_enrich():
            _skill_name = re.sub(r"[^a-z0-9_]", "_", full_name.split("/")[-1].lower()).strip("_")
            exc_holder: list = []

            def _run():
                try:
                    de._enrich_one(queue_item)
                except Exception as e:
                    exc_holder.append(e)

            worker = threading.Thread(target=_run, daemon=True)
            worker.start()
            worker.join(timeout=_ENRICH_TIMEOUT)

            try:
                if worker.is_alive():
                    # Thread is still running after the timeout — treat as failure
                    err_msg = f"enrichment timed out after {_ENRICH_TIMEOUT}s"
                    log.warning("Manual enrich timed out for %s", full_name)
                    de.mark_failed(queue_item, err_msg)
                    _idx = load_index()
                    if _skill_name in _idx:
                        _idx[_skill_name]["_enrich_error"] = err_msg
                        save_index(_idx)
                    return

                if exc_holder:
                    exc = exc_holder[0]
                    log.warning("Manual enrich failed for %s: %s", full_name, exc)
                    de.mark_failed(queue_item, str(exc))
                    _idx = load_index()
                    if _skill_name in _idx:
                        _idx[_skill_name]["_enrich_error"] = str(exc)[:200]
                        save_index(_idx)
                else:
                    de.mark_succeeded(queue_item)
                    # Clear any previous error flag on success
                    _idx = load_index()
                    if _skill_name in _idx:
                        _idx[_skill_name].pop("_enrich_error", None)
                        save_index(_idx)
            finally:
                with _enrich_in_progress_lock:
                    _enrich_in_progress.discard(full_name)

        t = threading.Thread(target=_bg_enrich, daemon=True)
        t.start()

        return jsonify({"ok": True, "status": "triggered", "full_name": full_name})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/skills/<filename>")
def view_skill(filename):
    filename = os.path.basename(filename)
    if not filename.endswith(".md"):
        return "Not found", 404
    path = os.path.join(SKILLS_DIR, filename)
    if not os.path.exists(path):
        return "Skill not found", 404
    with open(path) as f:
        content = f.read()
    name  = filename[:-3]
    index = load_index()
    meta  = index.get(name, {})
    # Resolve full MCP connection objects for connections this skill uses
    all_conns   = {c["name"]: c for c in mcp_agent.get_connections()}
    skill_conns = [all_conns[n] for n in meta.get("mcp_connections", []) if n in all_conns]
    return render_template(
        "skill.html",
        filename=filename,
        content=content,
        meta=meta,
        name=name,
        history=meta.get("history", []),
        mcp_connections=skill_conns,
    )


@app.route("/skills/<filename>/delete", methods=["POST"])
def delete_skill(filename):
    filename = os.path.basename(filename)
    path = os.path.join(SKILLS_DIR, filename)
    if os.path.exists(path):
        os.remove(path)
    name  = filename[:-3]
    index = load_index()
    index.pop(name, None)
    save_index(index)
    return jsonify({"ok": True})


@app.route("/skills/<filename>/raw")
def raw_skill(filename):
    filename = os.path.basename(filename)
    path = os.path.join(SKILLS_DIR, filename)
    if not os.path.exists(path):
        return "Not found", 404
    with open(path) as f:
        content = f.read()
    return Response(
        content,
        content_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.route("/favicon.ico")
def favicon():
    return Response(status=204)


# ── One-click OAuth & secret management routes ────────────────────────────────

_GH_DEVICE_CODE_URL = "https://github.com/login/device/code"
_GH_DEVICE_TOKEN_URL = "https://github.com/login/oauth/access_token"


def _gh_post(url: str, params: dict) -> dict:
    """POST to a GitHub URL with form-encoded body, returns parsed JSON."""
    data = _urlencode(params).encode()
    req  = _UReq(url, data=data,
                 headers={"Accept": "application/json",
                          "User-Agent": "Fieldnote/4.0"})
    with urlopen(req, timeout=12) as r:
        return json.loads(r.read())


@app.route("/oauth/github/device/start")
def github_device_start():
    """
    Kick off the GitHub Device Flow.

    Requires GITHUB_OAUTH_CLIENT_ID — a one-time setup (register any OAuth App
    at github.com/settings/developers; homepage + callback can both be this
    Replit URL).  Once the client ID is saved via /api/secrets/set or Replit
    Secrets, every future GitHub auth is truly one-click.
    """
    client_id = os.getenv("GITHUB_OAUTH_CLIENT_ID")
    if not client_id:
        return jsonify({
            "error":   "no_client_id",
            "setup_url": "https://github.com/settings/applications/new",
            "message": (
                "One-time setup: register a GitHub OAuth App at "
                "github.com/settings/developers. Set Homepage URL + Callback "
                "URL to this app's URL. Then save the Client ID here as "
                "GITHUB_OAUTH_CLIENT_ID via the Activate button below."
            ),
        }), 400
    try:
        result = _gh_post(_GH_DEVICE_CODE_URL,
                          {"client_id": client_id, "scope": "repo read:org"})
        return jsonify(result)
    except Exception as ex:
        return jsonify({"error": str(ex)}), 500


@app.route("/oauth/github/device/poll", methods=["POST"])
def github_device_poll():
    """
    Poll GitHub to see if the user approved the device code.
    Returns {ok, activated} on success, or the GitHub error code so the
    frontend can implement correct back-off.
    """
    body        = request.get_json() or {}
    device_code = body.get("device_code", "")
    client_id   = os.getenv("GITHUB_OAUTH_CLIENT_ID")
    if not client_id or not device_code:
        return jsonify({"error": "missing_params"}), 400
    try:
        result = _gh_post(_GH_DEVICE_TOKEN_URL, {
            "client_id":   client_id,
            "device_code": device_code,
            "grant_type":  "urn:ietf:params:oauth:grant-type:device_code",
        })
        if "access_token" in result:
            save_local_key("GITHUB_TOKEN", result["access_token"])
            return jsonify({"ok": True, "activated": True,
                            "scope": result.get("scope", "")})
        # Relay GitHub's own error codes (authorization_pending, slow_down, etc.)
        return jsonify(result)
    except Exception as ex:
        return jsonify({"error": str(ex)}), 500


@app.route("/api/secrets/set", methods=["POST"])
def api_secrets_set():
    """
    Save an API key/token to the local store and activate it immediately.
    Takes effect for all subsequent job runs without any restart.
    """
    body  = request.get_json() or {}
    name  = (body.get("name")  or "").strip().upper().replace("-", "_")
    value = (body.get("value") or "").strip()
    if not name or not value:
        return jsonify({"error": "name and value required"}), 400
    if not re.match(r'^[A-Z][A-Z0-9_]{1,80}$', name):
        return jsonify({"error": "Invalid secret name"}), 400
    save_local_key(name, value)
    return jsonify({"ok": True, "name": name, "activated": True})


@app.route("/api/secrets/check", methods=["POST"])
def api_secrets_check():
    """Return which of the requested secret names are currently set."""
    body  = request.get_json() or {}
    names = [n for n in (body.get("names") or [])
             if re.match(r'^[A-Z][A-Z0-9_]{1,80}$', n)]
    return jsonify({n: bool(os.getenv(n)) for n in names})


# ── Scheduler API ─────────────────────────────────────────────────────────────

@app.route("/api/scheduler/status")
def api_scheduler_status():
    return jsonify(scheduler_mod.scheduler.status())


@app.route("/api/scheduler/run/<job_name>", methods=["POST"])
def api_scheduler_run(job_name: str):
    result = scheduler_mod.scheduler.run_now(job_name)
    return jsonify(result)


@app.route("/api/scheduler/toggle/<job_name>", methods=["POST"])
def api_scheduler_toggle(job_name: str):
    body    = request.get_json(silent=True) or {}
    enabled = bool(body.get("enabled", True))
    return jsonify(scheduler_mod.scheduler.set_enabled(job_name, enabled))


# ── Watchlist API ─────────────────────────────────────────────────────────────

@app.route("/api/watchlist")
def api_watchlist_get():
    return jsonify({"entries": auto_agent.load_watchlist()})


@app.route("/api/watchlist", methods=["POST"])
def api_watchlist_add():
    body  = request.get_json(silent=True) or {}
    url   = (body.get("url") or "").strip()
    label = (body.get("label") or "").strip()
    if not url:
        return jsonify({"ok": False, "error": "url required"}), 400
    if not extract_video_id(url):
        return jsonify({"ok": False, "error": "Invalid YouTube URL"}), 400
    return jsonify(auto_agent.add_to_watchlist(url, label))


@app.route("/api/watchlist/remove", methods=["POST"])
def api_watchlist_remove():
    body = request.get_json(silent=True) or {}
    url  = (body.get("url") or "").strip()
    return jsonify(auto_agent.remove_from_watchlist(url))


@app.route("/api/verify/log")
def api_verify_log():
    """Last 100 post-save verification runs."""
    import agents.verify_agent as va
    path = va._log_path()
    if not os.path.exists(path):
        return jsonify([])
    try:
        with open(path) as f:
            return jsonify(json.load(f))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/sync/status")
def api_sync_status():
    """Live status of the code-sync watcher."""
    return jsonify({
        "watcher": code_sync.status(),
        "repo":    github_sync.repo_url(),
    })


@app.route("/api/sync/push", methods=["POST"])
def api_sync_push():
    """Trigger an immediate code + skills push."""
    result = code_sync.push_now(label="manual")
    return jsonify(result)


@app.route("/api/discovery/stats")
def api_discovery_stats():
    return jsonify(github_discovery.discovery_stats())


@app.route("/api/discovery/log")
def api_discovery_log():
    return jsonify(github_discovery.load_discovery_log())


@app.route("/api/discovery/reliability")
def api_discovery_reliability():
    """Provider availability + cooldown timers + enrichment queue stats."""
    return jsonify(github_discovery.discovery_reliability())


@app.route("/api/discovery/recover-all", methods=["POST"])
def api_discovery_recover_all():
    """Re-enqueue all discovery log entries that have no skill or are baseline."""
    try:
        import agents.discovery_enrichment as de
        disc_log = github_discovery.load_discovery_log()
        enqueued = 0
        for fn, v in disc_log.items():
            if v.get("action") in ("error", "baseline") or v.get("enrichment_queued"):
                de.enqueue(fn, v.get("stars", 0))
                enqueued += 1
        return jsonify({"ok": True, "enqueued": enqueued})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/discovery/enqueue", methods=["POST"])
def api_discovery_enqueue():
    """Enqueue a specific repo for AI enrichment."""
    try:
        import agents.discovery_enrichment as de
        data = request.get_json(force=True, silent=True) or {}
        full_name = data.get("full_name", "")
        if not full_name:
            return jsonify({"ok": False, "error": "full_name required"}), 400
        disc_log = github_discovery.load_discovery_log()
        stars = disc_log.get(full_name, {}).get("stars", 0)
        de.enqueue(full_name, stars)
        return jsonify({"ok": True, "full_name": full_name})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/discovery/enrichment/pause", methods=["POST"])
def api_discovery_enrichment_pause():
    """Pause the enrichment scheduler."""
    try:
        import agents.discovery_enrichment as de
        de.set_paused(True)
        return jsonify({"ok": True, "paused": True})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/discovery/enrichment/resume", methods=["POST"])
def api_discovery_enrichment_resume():
    """Resume the enrichment scheduler."""
    try:
        import agents.discovery_enrichment as de
        de.set_paused(False)
        return jsonify({"ok": True, "paused": False})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/watchlist/run-now", methods=["POST"])
def api_watchlist_run_now():
    """Immediately process the next pending watchlist entry."""
    result = scheduler_mod.scheduler.run_now("watchlist")
    return jsonify(result)


# ── Scheduler boot ────────────────────────────────────────────────────────────

def _boot_scheduler():
    """Register jobs and start the scheduler daemon."""
    s = scheduler_mod.scheduler

    s.register(
        name="enhance",
        description="Re-run extraction on skills due for DCA enhancement",
        interval_hours=6,
        fn=auto_agent.enhance_due_skills,
    )
    s.register(
        name="sync",
        description="Full push of all skills to the GitHub mirror",
        interval_hours=24,
        fn=auto_agent.sync_github,
    )
    s.register(
        name="watchlist",
        description="Process the next pending URL in the watchlist queue",
        interval_hours=1,
        fn=auto_agent.process_watchlist,
    )
    s.register(
        name="discover",
        description="Search GitHub for high-quality repos and learn new skills from READMEs",
        interval_hours=2,
        fn=github_discovery.discover_and_learn,
    )
    s.register(
        name="code_sync",
        description="Fallback: push any source-code changes not yet caught by the file watcher",
        interval_hours=0.167,   # every 10 minutes
        fn=lambda: github_sync.sync_code(label="scheduler"),
    )

    import agents.discovery_enrichment as _disc_enrich
    s.register(
        name="enrich_backlog",
        description="AI-enrich baseline skills queued during provider outages (up to 3 per run)",
        interval_hours=0.167,   # every 10 minutes
        fn=_disc_enrich.enrich_backlog,
    )

    import agents.integration_agent as _integ_agent
    s.register(
        name="integrations",
        description="Health-check all integrations, auto-detect new Replit Secrets, suggest missing ones",
        interval_hours=0.5,     # every 30 minutes
        fn=_integ_agent.run_agent,
    )

    s.register(
        name="mcp_health",
        description="Re-verify all enabled MCP hub servers; update health states",
        interval_hours=0.25,    # every 15 minutes
        fn=_mcp_health_check,
    )

    s.register(
        name="mcp_refresh",
        description="Check PyPI/npm for newer MCP package versions",
        interval_hours=24,
        fn=_mcp_version_refresh,
    )

    def _recover_queued_jobs() -> dict:
        """
        Auto-recovery: find queued checkpoints and resume any that can run now.
        Called every 5 minutes by the scheduler.
        Also purges checkpoints older than 7 days that exceeded the retry limit.
        """
        # ── Step 1: purge stale checkpoints (max retries + older than 7 days) ──
        try:
            purged = run_checkpoint.purge_stale_checkpoints()
            for p in purged:
                log.info(
                    "recover_queued_jobs: auto-purged stale checkpoint %s "
                    "(skill=%s, attempts=%d, reason=%s)",
                    p.get("run_id"), p.get("skill_name"),
                    p.get("recovery_attempts", 0), p.get("reason"),
                )
        except Exception as exc:
            log.error("recover_queued_jobs: purge step failed: %s", exc)
            purged = []

        pending = run_checkpoint.list_pending_checkpoints()
        if not pending:
            return {"recovered": 0, "skipped": 0, "purged": len(purged)}

        # Check if any free provider is healthy
        statuses = provider_router.provider_status()
        free_ok  = any(
            v.get("state") == "healthy"
            for p, v in statuses.items()
            if p != "openai"
        )
        if not free_ok:
            log.info("recover_queued_jobs: no free provider healthy — deferring")
            return {"recovered": 0, "skipped": len(pending)}

        recovered = 0
        skipped   = 0
        for cp in pending:
            run_id   = cp.get("run_id")
            video_id = cp.get("video_id")
            url      = cp.get("url")

            if not run_id or not video_id or not url:
                skipped += 1
                continue

            # Don't launch if already in-flight
            if video_id in _video_active and not _jobs.get(_video_active[video_id], {}).get("done", True):
                skipped += 1
                continue

            # Max 3 auto-recovery attempts to avoid infinite loops
            if cp.get("recovery_attempts", 0) >= 3:
                log.info("recover_queued_jobs: %s exceeded max attempts — skipping", run_id)
                skipped += 1
                continue

            try:
                # Use the resume endpoint logic inline
                existing_skill = cp.get("skill_name")
                existing_path  = None
                if existing_skill:
                    ep = os.path.join(SKILLS_DIR, f"{existing_skill}.md")
                    if os.path.exists(ep):
                        existing_path = ep

                job_id        = str(uuid.uuid4())[:8]
                _jobs[job_id] = {
                    "queue":        queue.Queue(),
                    "done":         False,
                    "run_id":       run_id,
                    "allow_paid":   False,
                    "force_enhance": existing_skill if existing_path else None,
                }
                _video_active[video_id] = job_id

                recovery_attempts = cp.get("recovery_attempts", 0) + 1
                run_checkpoint.save_checkpoint(run_id, {
                    "stage":             "resuming",
                    "recovery_attempts": recovery_attempts,
                    "recovered_at":      datetime.now(timezone.utc).isoformat(timespec="seconds"),
                })

                threading.Thread(
                    target=run_job, args=(job_id, url, video_id), daemon=True,
                    name=f"fn-auto-resume-{run_id[:6]}",
                ).start()
                recovered += 1
                log.info("recover_queued_jobs: resumed %s (video=%s)", run_id, video_id)

            except Exception as exc:
                log.error("recover_queued_jobs: error resuming %s: %s", run_id, exc)
                skipped += 1

        return {"recovered": recovered, "skipped": skipped, "pending": len(pending)}

    s.register(
        name="recover_queued",
        description="Auto-resume queued degraded-skill checkpoints when a free provider recovers",
        interval_hours=1 / 12,  # every 5 minutes
        fn=_recover_queued_jobs,
    )

    s.start()

    # Wake-from-sleep guard: if the container is paused and resumed without a
    # full restart the registry may still hold stale 'connected' entries that
    # were never reset this session.  The scheduler detects the resulting clock
    # drift and fires this callback so the first health-check tick after wake
    # resolves every badge back to the true state.
    try:
        from agents.mcp_registry import mark_connected_as_unverified as _mark_unverified_wake
        def _on_scheduler_wake():
            reset = _mark_unverified_wake()
            if reset:
                log.info(
                    "_boot_scheduler: wake detected — %d MCP server(s) reset to "
                    "'unverified' (pending next health-check tick)", reset,
                )
        s.register_wake_callback(_on_scheduler_wake)
    except Exception as _wce:
        log.warning("_boot_scheduler: could not register wake callback: %s", _wce)

    # File watcher: push within seconds of any file change
    code_sync.start()

    # Immediate startup push so the repo is current right now
    threading.Thread(
        target=lambda: github_sync.sync_code(label="startup"),
        daemon=True, name="fn-startup-sync"
    ).start()

    logging.getLogger("fieldnote.scheduler").info(
        "Fieldnote booted — scheduler + file watcher running"
    )


_boot_scheduler()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
