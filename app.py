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

_jobs: dict = {}         # {job_id: {"queue": Queue, "done": bool}}
_mcp_sessions: dict = {}  # {session_id: queue.Queue}


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
    with open(METADATA_FILE, "w") as f:
        json.dump(index, f, indent=2, default=str)


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
            "tags":         meta.get("tags", []),
            "tools":        meta.get("tools", []),
            "source_title": meta.get("source_title", ""),
            "source_url":   meta.get("source_url", ""),
            "video_id":     meta.get("video_id", ""),
            "method":       meta.get("method", ""),
            "action":       meta.get("action", "create"),
            "created_at":   meta.get("created_at", ""),
            "updated_at":   meta.get("updated_at", ""),
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
    for m in index.values():
        all_tools.update(m.get("tools", []))
        all_pkgs.update(m.get("python_packages", []))

    repos_dir  = "fieldnote_repos"
    repo_count = sum(
        1 for d in os.listdir(repos_dir)
        if os.path.isdir(os.path.join(repos_dir, d))
    ) if os.path.exists(repos_dir) else 0

    return {
        "skills":   len(index),
        "tools":    len(all_tools),
        "packages": len(all_pkgs),
        "repos":    repo_count,
        "mcp":      len(mcp_agent.get_connections()),
    }


def get_all_tags() -> list[str]:
    index = load_index()
    tags: set = set()
    for m in index.values():
        tags.update(m.get("tags", []))
    return sorted(tags)


# ── Knowledge context (self-improvement engine) ───────────────────────────────

def _relevance_score(meta: dict, quick_tools: list[str]) -> int:
    """Score a skill's relevance to the current video's quick-scan tools."""
    if not quick_tools:
        return 0
    skill_tokens = set(
        t.lower()
        for t in meta.get("tools", []) + meta.get("tags", []) + meta.get("concepts", [])
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
        tools    = ", ".join(m.get("tools",    [])[:6]) or "none"
        tags     = ", ".join(m.get("tags",     [])[:4]) or "none"
        concepts = ", ".join(m.get("concepts", [])[:4]) or "none"
        pkgs     = ", ".join(m.get("python_packages", [])[:4]) or "none"
        steps_preview = "; ".join(m.get("steps", [])[:2])
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


def _dedup_list(new_items: list, old_items: list) -> list:
    """Merge two lists, deduplicating case-insensitively, preserving order."""
    seen: set[str] = set()
    result: list   = []
    for item in new_items + old_items:
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
    Return up to 20 video IDs from a playlist.
    Robust against yt-dlp deprecation warnings that cause non-zero exit codes:
    we parse stdout regardless of returncode as long as we got at least one ID.
    """
    r = subprocess.run(
        ["yt-dlp", "--flat-playlist", "--print", "id", "--ignore-errors",
         "--no-warnings",
         f"https://www.youtube.com/playlist?list={playlist_id}"],
        capture_output=True, text=True, timeout=60,
    )
    # Extract valid video IDs from stdout (11-char alphanumeric strings)
    id_pat = r'^[a-zA-Z0-9_-]{11}' + '$'
    ids = [l.strip() for l in r.stdout.strip().splitlines()
           if re.match(id_pat, l.strip())][:20]
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


def transcript_from_whisper(url: str, video_id: str, emit) -> str:
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

    with open(mp3_out, "rb") as f:
        result = client.audio.transcriptions.create(
            file=(os.path.basename(mp3_out), f),
            model=WHISPER_MODEL,
            response_format="text",
        )

    shutil.rmtree(tmp_dir, ignore_errors=True)
    return result if isinstance(result, str) else result.text


def get_transcript(url: str, video_id: str, emit) -> tuple[str, str]:
    try:
        text = transcript_from_captions(video_id)
        emit("✅  Captions found — transcript ready.", "success")
        return text, "captions"
    except Exception as e:
        emit(f"⚠  No captions ({type(e).__name__}) — switching to Whisper …", "warning")
    text = transcript_from_whisper(url, video_id, emit)
    return text, "whisper"


# ── Groq LLM ─────────────────────────────────────────────────────────────────

def call_groq(prompt: str, max_tokens: int = 4000) -> str:
    """Call Groq with per-model fallback and exponential backoff on 429 rate limits."""
    client = Groq(api_key=GROQ_API_KEY)
    last_err = None
    for model in GROQ_MODELS:
        for attempt in range(3):
            try:
                resp = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=max_tokens,
                    response_format={"type": "json_object"},
                )
                return resp.choices[0].message.content
            except Exception as e:
                err = str(e)
                last_err = e
                if any(k in err for k in ("decommissioned", "404", "model_not_found")):
                    break  # try next model immediately
                if "429" in err or "rate_limit" in err.lower() or "rate limit" in err.lower():
                    wait = (2 ** attempt) + random.uniform(0, 1)
                    time.sleep(wait)
                    continue
                raise  # non-retryable error
    raise RuntimeError(f"All Groq models failed. Last error: {last_err}")



def call_openai(prompt: str, max_tokens: int = 4000, json_mode: bool = True) -> str:
    """Call OpenAI (GPT-4o-mini default) with JSON or plain-text output."""
    client   = OpenAI(api_key=OPENAI_API_KEY)
    messages = [{"role": "user", "content": prompt}]
    kwargs: dict = dict(messages=messages, max_tokens=max_tokens, temperature=0.2)
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    last_err = None
    for model in OPENAI_MODELS:
        try:
            resp = client.chat.completions.create(model=model, **kwargs)
            return resp.choices[0].message.content
        except Exception as e:
            last_err = e
            err = str(e)
            if "404" in err or "model_not_found" in err:
                continue   # try next model
            raise          # non-retryable (auth, rate-limit, etc.)
    raise RuntimeError(f"All OpenAI models failed. Last: {last_err}")


def call_llm(prompt: str, max_tokens: int = 4000, json_mode: bool = True) -> str:
    """Try OpenAI first (higher quality), fall back to Groq."""
    if OPENAI_API_KEY:
        try:
            return call_openai(prompt, max_tokens=max_tokens, json_mode=json_mode)
        except Exception as e:
            if "401" in str(e) or "invalid_api_key" in str(e).lower():
                raise   # bad key — don't silently fall through
            # transient / quota error — fall back to Groq
    return call_groq(prompt, max_tokens=max_tokens)


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
) -> dict:
    raw = call_llm(_build_prompt(transcript, knowledge_ctx, existing_content))
    return json.loads(raw)




# ── AI Arena: three providers, one judge ─────────────────────────────────────

def _extract_skill_chatgpt(transcript: str, knowledge_ctx: str, existing_content: str = "") -> dict:
    """ChatGPT pass — educator lens: depth, clarity, concept relationships."""
    base     = _build_prompt(transcript, knowledge_ctx, existing_content)
    preamble = (
        "You are Fieldnote's EDUCATOR AI. Your lens is conceptual clarity, "
        "thorough descriptions, and how this skill connects to others in the library."
        + chr(10) + chr(10)
    )
    raw = call_openai(preamble + base, max_tokens=4000, json_mode=True)
    return json.loads(raw)


def _extract_skill_groq(transcript: str, knowledge_ctx: str, existing_content: str = "") -> dict:
    """Groq pass — practitioner lens: actionable steps, every tool and command."""
    base     = _build_prompt(transcript, knowledge_ctx, existing_content)
    preamble = (
        "You are Fieldnote's PRACTITIONER AI. Your lens is specific actionable steps "
        "a developer can follow immediately, and every concrete tool, command, "
        "and library mentioned in the transcript."
        + chr(10) + chr(10)
    )
    raw = call_groq(preamble + base, max_tokens=4000)
    return json.loads(raw)


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


def _judge_arena(skill_a: dict, skill_b: dict, github_ctx: str, emit) -> dict:
    """Judge synthesizes ChatGPT + Groq outputs into one superior merged skill."""
    if not skill_a and not skill_b:
        raise ValueError("Both AI extractions failed — nothing to judge")

    a_steps = len((skill_a or {}).get("steps", []))
    b_steps = len((skill_b or {}).get("steps", []))

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
        raw    = call_llm(prompt, max_tokens=4500, json_mode=True)
        result = json.loads(raw)
    except Exception as exc:
        emit("⚠  Judge LLM failed (" + str(exc)[:80] + "), falling back to ChatGPT result", "warning")
        result = dict(skill_a)
        result["tools"]    = list(dict.fromkeys((skill_a.get("tools", []) + skill_b.get("tools", []))))
        result["concepts"] = list(dict.fromkeys((skill_a.get("concepts", []) + skill_b.get("concepts", []))))
        result["steps"]    = list(dict.fromkeys((skill_a.get("steps", []) + skill_b.get("steps", []))))[:12]
        result["_arena"]   = {"title_winner": "chatgpt", "desc_winner": "chatgpt",
                              "steps_a": a_steps, "steps_b": b_steps,
                              "steps_merged": len(result["steps"]),
                              "github_tools_added": 0, "note": "manual_merge"}

    arena = result.get("_arena", {})
    sm    = len(result.get("steps", []))
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
        "\n".join(f"- {s}" for s in skill.get("steps", []))
    )

    # Strip any Sources section the AI may have included (we manage it ourselves)
    markdown = re.sub(
        r'\n*##\s*sources.*$', '', markdown,
        flags=re.IGNORECASE | re.DOTALL,
    ).rstrip()

    # Append the authoritative Sources section
    markdown += _build_sources_section(all_sources)

    # ── Write file ────────────────────────────────────────────────────────────
    with open(skill_path, "w") as f:
        f.write(markdown)

    # ── Update metadata index ─────────────────────────────────────────────────
    index = load_index()
    prev  = index.get(skill_name, {})

    # Merge and deduplicate all list fields (new AI output wins order, old fills gaps)
    merged_tools    = _dedup_list(skill.get("tools", []),           prev.get("tools", []))
    merged_tags     = _dedup_list(skill.get("tags", []),            prev.get("tags", []))
    merged_concepts = _dedup_list(skill.get("concepts", []),        prev.get("concepts", []))
    merged_packages = _dedup_list(skill.get("python_packages", []), prev.get("python_packages", []))
    merged_related  = _dedup_list(skill.get("related_skills", []),  prev.get("related_skills", []))

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
        "steps":           skill.get("steps", []),
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


# ── Core parallel job runner ──────────────────────────────────────────────────

def run_job(job_id: str, url: str, video_id: str):
    q = _jobs[job_id]["queue"]

    def emit(msg: str, kind: str = "info"):
        q.put({"type": "log", "msg": msg, "kind": kind})

    try:
        emit("🚀  Parallel agents launching …", "info")

        with ThreadPoolExecutor(max_workers=8, thread_name_prefix="fn") as pool:

            # ── Phase 1: metadata + transcript in parallel ────────────────────
            emit("⚡  Phase 1: metadata ∥ transcript …", "info")
            meta_f  = pool.submit(get_video_metadata, video_id)
            trans_f = pool.submit(get_transcript, url, video_id, emit)

            meta = meta_f.result(timeout=30)
            q.put({"type": "meta", "data": meta})
            emit(f"📺  {meta['title'] or 'Video identified'}", "info")

            transcript, method = trans_f.result(timeout=300)
            word_count = len(transcript.split())
            emit(f"📝  {word_count:,} words via {method}", "success")

            # Quick regex scan — used for early GitHub search AND relevance scoring
            quick_tools = github_agent.quick_tool_scan(transcript)
            if quick_tools:
                emit(
                    f"🔍  Quick scan: {', '.join(quick_tools[:6])}"
                    f"{'…' if len(quick_tools) > 6 else ''}",
                    "info",
                )

            # ── Phase 2: ChatGPT ∥ Groq ∥ GitHub — AI Arena ─────────────────
            emit("⚡  Phase 2: ChatGPT ∥ Groq ∥ GitHub — Arena mode …", "info")

            knowledge_ctx  = get_skills_context(quick_tools)
            existing_index = load_index()

            # All three work simultaneously — nobody idles
            gpt_f    = pool.submit(_extract_skill_chatgpt, transcript, knowledge_ctx, "")
            groq_f   = pool.submit(_extract_skill_groq,   transcript, knowledge_ctx, "")
            github_f = pool.submit(github_agent.search_tools, quick_tools, emit)

            # Collect GitHub first (fastest), then fetch READMEs while LLMs finish
            github_results = github_f.result(timeout=90)
            emit(f"📊  GitHub: {len(github_results)} repos — fetching READMEs …", "info")
            github_ctx = _github_readme_context(github_results)

            # Collect both LLM results (already running in parallel)
            skill_a = None
            skill_b = None
            try:
                skill_a = gpt_f.result(timeout=120)
                emit("✅  ChatGPT extraction done", "info")
            except Exception as exc_a:
                emit(f"⚠  ChatGPT failed ({exc_a})", "warning")
            try:
                skill_b = groq_f.result(timeout=120)
                emit("✅  Groq extraction done", "info")
            except Exception as exc_b:
                emit(f"⚠  Groq failed ({exc_b})", "warning")

            # Judge synthesizes the winner
            skill = _judge_arena(skill_a, skill_b, github_ctx, emit)
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
                    skill_a2 = _extract_skill_chatgpt(transcript, knowledge_ctx, existing_md)
                    skill    = _judge_arena(skill_a2, skill_b, github_ctx, emit)
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
            emit("⚡  Phase 3: save ∥ packages ∥ MCP ∥ clone ∥ supplemental search …", "info")

            ai_tools    = skill.get("tools", [])
            mcp_targets = [r for r in github_results
                           if r.get("is_mcp") or r.get("npm_package")]

            pkg_f   = pool.submit(_install_pkgs,
                                  skill.get("python_packages", []), emit)
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

            q.put({
                "type":              "done",
                "ok":                True,
                "title":             skill.get("title"),
                "description":       skill.get("description"),
                "steps":             skill.get("steps", []),
                "tools":             skill.get("tools", []),
                "concepts":          skill.get("concepts", []),
                "tags":              skill.get("tags", []),
                "related_skills":    skill.get("related_skills", []),
                "python_packages":   skill.get("python_packages", []),
                "installed":         installed,
                "failed":            failed,
                "skill_file":        skill_path,
                "skill_name":        skill_name,
                "transcript_words":  word_count,
                "transcript_method": method,
                "video_id":          video_id,
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
        import traceback
        tb = traceback.format_exc()
        emit(f"❌  {e}", "error")
        if len(tb) > 100:
            emit(tb[:600], "error")
        q.put({"type": "done", "ok": False, "error": str(e)})
    finally:
        _jobs[job_id]["done"] = True


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
    if not GROQ_API_KEY and not OPENAI_API_KEY:
        return jsonify({
            "error": "No LLM key — add GROQ or CHATGPT in Tools › Secrets."
        }), 500

    video_id = extract_video_id(url)
    if not video_id:
        return jsonify({
            "error": "Could not find a YouTube video ID in that URL."
        }), 400

    job_id        = str(uuid.uuid4())[:8]
    _jobs[job_id] = {"queue": queue.Queue(), "done": False}
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


@app.route("/api/playlist_ids")
def api_playlist_ids():
    """Return all video IDs in a playlist (up to 20)."""
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
]


def _mcp_call_tool(name: str, args: dict) -> dict:
    """Shared tool logic — used by both the SSE endpoint and the stdio server."""
    index = load_index()

    if name == "list_skills":
        tag   = (args.get("tag") or "").lower()
        limit = min(int(args.get("limit") or 25), 100)
        skills = []
        for skill_name, meta in index.items():
            if tag and tag not in [t.lower() for t in meta.get("tags", [])]:
                continue
            skills.append({
                "name":         skill_name,
                "title":        meta.get("title", skill_name),
                "description":  meta.get("description", ""),
                "tags":         meta.get("tags", []),
                "tools":        meta.get("tools", [])[:10],
                "concepts":     meta.get("concepts", [])[:6],
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
            "description": meta.get("description", ""), "tags": meta.get("tags", []),
            "tools": meta.get("tools", []), "concepts": meta.get("concepts", []),
            "steps": meta.get("steps", []), "packages": meta.get("python_packages", []),
            "source_count": len(meta.get("history", [])) + 1,
            "updated_at": meta.get("updated_at", ""), "content": content,
        }

    elif name == "search_skills":
        query = (args.get("query") or "").lower()
        results = []
        for skill_name, meta in index.items():
            hay = " ".join([meta.get("title",""), meta.get("description",""),
                            " ".join(meta.get("tags",[])), " ".join(meta.get("tools",[])),
                            " ".join(meta.get("concepts",[])), " ".join(meta.get("steps",[]))]).lower()
            score = sum(hay.count(w) for w in query.split() if w)
            if score:
                results.append({"name": skill_name, "title": meta.get("title", skill_name),
                                 "description": meta.get("description",""), "score": score,
                                 "tags": meta.get("tags",[]), "tools": meta.get("tools",[])[:6]})
        results.sort(key=lambda x: x["score"], reverse=True)
        return {"results": results[:12], "query": query}

    elif name == "get_all_tools":
        tools: set = set()
        for m in index.values(): tools.update(m.get("tools",[]))
        return {"tools": sorted(tools), "count": len(tools)}

    elif name == "get_all_concepts":
        concepts: set = set()
        for m in index.values(): concepts.update(m.get("concepts",[]))
        return {"concepts": sorted(concepts), "count": len(concepts)}

    elif name == "get_library_stats":
        tools: set = set(); concepts: set = set(); pkgs: set = set()
        for m in index.values():
            tools.update(m.get("tools",[])); concepts.update(m.get("concepts",[]))
            pkgs.update(m.get("python_packages",[]))
        return {"skills": len(index), "tools": len(tools), "concepts": len(concepts), "packages": len(pkgs)}

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
    concepts = skill.get("concepts", [])
    tools    = skill.get("tools", [])
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
        "tags":       skill.get("tags", []),
        "step_count": len(skill.get("steps", [])),
    }
    brain["relationships"].setdefault(skill_name, {})
    for other, od in brain["skill_map"].items():
        if other == skill_name:
            continue
        shared = list(
            set(concepts + tools) &
            set(od.get("concepts", []) + od.get("tools", []))
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
    if not GROQ_API_KEY and not OPENAI_API_KEY:
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
                " ".join(meta.get("tools", [])),
                " ".join(meta.get("concepts", [])),
                " ".join(meta.get("tags", [])),
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
        if OPENAI_API_KEY:
            resp     = OpenAI(api_key=OPENAI_API_KEY).chat.completions.create(
                model=OPENAI_MODELS[0], messages=msgs, max_tokens=900, temperature=0.7)
            provider = OPENAI_MODELS[0]
        else:
            resp     = Groq(api_key=GROQ_API_KEY).chat.completions.create(
                model=GROQ_MODELS[0], messages=msgs, max_tokens=900, temperature=0.7)
            provider = GROQ_MODELS[0]
        return jsonify({"answer": resp.choices[0].message.content,
                        "skill_used": skill_name, "provider": provider})
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
    if not GROQ_API_KEY and not OPENAI_API_KEY:
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
            tools_str = ", ".join(meta.get("tools", [])[:3])
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
        if OPENAI_API_KEY:
            resp = OpenAI(api_key=OPENAI_API_KEY).chat.completions.create(
                model=OPENAI_MODELS[0],
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1200, temperature=0.5)
        else:
            resp = Groq(api_key=GROQ_API_KEY).chat.completions.create(
                model=GROQ_MODELS[0],
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1200, temperature=0.5)
        return jsonify({"briefing": resp.choices[0].message.content})
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
    """Full OpenAPI 3.0 spec — paste the URL into a ChatGPT Custom GPT Action."""
    domain = os.getenv("REPLIT_DEV_DOMAIN","")
    base   = f"https://{domain}" if domain else request.url_root.rstrip("/")
    spec   = {
        "openapi": "3.0.0",
        "info": {
            "title":       "Fieldnote Skill Library",
            "description": "Search and retrieve AI skills extracted from YouTube videos. Each skill contains steps, tools, concepts, and code references.",
            "version":     "2.0.0",
        },
        "servers": [{"url": base}],
        "paths": {
            "/api/skills": {
                "get": {
                    "operationId": "listSkills",
                    "summary":     "List all skills",
                    "description": "Returns every skill in the library with title, description, tags, tools, and concepts.",
                    "parameters": [
                        {"name":"q",   "in":"query","schema":{"type":"string"},"description":"Keyword filter"},
                        {"name":"tag", "in":"query","schema":{"type":"string"},"description":"Tag filter"},
                    ],
                    "responses": {"200":{"description":"Array of skill summaries","content":{"application/json":{"schema":{"type":"array","items":{"type":"object"}}}}}},
                }
            },
            "/api/skills/{name}/content": {
                "get": {
                    "operationId": "getSkillContent",
                    "summary":     "Get a skill's full markdown content",
                    "description": "Returns the complete skill markdown with all steps, tools, concepts, and source references.",
                    "parameters": [{"name":"name","in":"path","required":True,"schema":{"type":"string"},"description":"Skill name (no .md)"}],
                    "responses": {"200":{"description":"Skill with full content","content":{"application/json":{"schema":{"type":"object"}}}},
                                  "404":{"description":"Skill not found"}},
                }
            },
            "/api/health": {
                "get": {
                    "operationId": "getHealth",
                    "summary":     "System health status",
                    "responses":   {"200":{"description":"Health check results"}},
                }
            },
        },
    }
    return jsonify(spec)


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
        "tags":         meta.get("tags",[]),
        "tools":        meta.get("tools",[]),
        "concepts":     meta.get("concepts",[]),
        "steps":        meta.get("steps",[]),
        "python_packages": meta.get("python_packages",[]),
        "source_count": len(meta.get("history",[])) + 1,
        "updated_at":   meta.get("updated_at",""),
        "content":      content,
    })


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

    s.start()

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
# ── Groq LLM ─────────────────────────────────────────────────────────────────

def call_groq(prompt: str, max_tokens: int = 4000) -> str:
    """Call Groq with per-model fallback and exponential backoff on 429 rate limits."""
    client = Groq(api_key=GROQ_API_KEY)
    last_err = None
    for model in GROQ_MODELS:
        for attempt in range(3):
            try:
                resp = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=max_tokens,
                    response_format={"type": "json_object"},
                )
                return resp.choices[0].message.content
            except Exception as e:
                err = str(e)
                last_err = e
                if any(k in err for k in ("decommissioned", "404", "model_not_found")):
                    break  # try next model immediately
                if "429" in err or "rate_limit" in err.lower() or "rate limit" in err.lower():
                    wait = (2 ** attempt) + random.uniform(0, 1)
                    time.sleep(wait)
                    continue
                raise  # non-retryable error
    raise RuntimeError(f"All Groq models failed. Last error: {last_err}")



def call_openai(prompt: str, max_tokens: int = 4000, json_mode: bool = True) -> str:
    """Call OpenAI (GPT-4o-mini default) with JSON or plain-text output."""
    client   = OpenAI(api_key=OPENAI_API_KEY)
    messages = [{"role": "user", "content": prompt}]
    kwargs: dict = dict(messages=messages, max_tokens=max_tokens, temperature=0.2)
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    last_err = None
    for model in OPENAI_MODELS:
        try:
            resp = client.chat.completions.create(model=model, **kwargs)
            return resp.choices[0].message.content
        except Exception as e:
            last_err = e
            err = str(e)
            if "404" in err or "model_not_found" in err:
                continue   # try next model
            raise          # non-retryable (auth, rate-limit, etc.)
    raise RuntimeError(f"All OpenAI models failed. Last: {last_err}")


def call_llm(prompt: str, max_tokens: int = 4000, json_mode: bool = True) -> str:
    """Try OpenAI first (higher quality), fall back to Groq."""
    if OPENAI_API_KEY:
        try:
            return call_openai(prompt, max_tokens=max_tokens, json_mode=json_mode)
        except Exception as e:
            if "401" in str(e) or "invalid_api_key" in str(e).lower():
                raise   # bad key — don't silently fall through
            # transient / quota error — fall back to Groq
    return call_groq(prompt, max_tokens=max_tokens)


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
) -> dict:
    raw = call_llm(_build_prompt(transcript, knowledge_ctx, existing_content))
    return json.loads(raw)




# ── AI Arena: three providers, one judge ─────────────────────────────────────

def _extract_skill_chatgpt(transcript: str, knowledge_ctx: str, existing_content: str = "") -> dict:
    """ChatGPT pass — educator lens: depth, clarity, concept relationships."""
    base     = _build_prompt(transcript, knowledge_ctx, existing_content)
    preamble = (
        "You are Fieldnote's EDUCATOR AI. Your lens is conceptual clarity, "
        "thorough descriptions, and how this skill connects to others in the library."
        + chr(10) + chr(10)
    )
    raw = call_openai(preamble + base, max_tokens=4000, json_mode=True)
    return json.loads(raw)


def _extract_skill_groq(transcript: str, knowledge_ctx: str, existing_content: str = "") -> dict:
    """Groq pass — practitioner lens: actionable steps, every tool and command."""
    base     = _build_prompt(transcript, knowledge_ctx, existing_content)
    preamble = (
        "You are Fieldnote's PRACTITIONER AI. Your lens is specific actionable steps "
        "a developer can follow immediately, and every concrete tool, command, "
        "and library mentioned in the transcript."
        + chr(10) + chr(10)
    )
    raw = call_groq(preamble + base, max_tokens=4000)
    return json.loads(raw)


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


def _judge_arena(skill_a: dict, skill_b: dict, github_ctx: str, emit) -> dict:
    """Judge synthesizes ChatGPT + Groq outputs into one superior merged skill."""
    if not skill_a and not skill_b:
        raise ValueError("Both AI extractions failed — nothing to judge")

    a_steps = len((skill_a or {}).get("steps", []))
    b_steps = len((skill_b or {}).get("steps", []))

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
        raw    = call_llm(prompt, max_tokens=4500, json_mode=True)
        result = json.loads(raw)
    except Exception as exc:
        emit("⚠  Judge LLM failed (" + str(exc)[:80] + "), falling back to ChatGPT result", "warning")
        result = dict(skill_a)
        result["tools"]    = list(dict.fromkeys((skill_a.get("tools", []) + skill_b.get("tools", []))))
        result["concepts"] = list(dict.fromkeys((skill_a.get("concepts", []) + skill_b.get("concepts", []))))
        result["steps"]    = list(dict.fromkeys((skill_a.get("steps", []) + skill_b.get("steps", []))))[:12]
        result["_arena"]   = {"title_winner": "chatgpt", "desc_winner": "chatgpt",
                              "steps_a": a_steps, "steps_b": b_steps,
                              "steps_merged": len(result["steps"]),
                              "github_tools_added": 0, "note": "manual_merge"}

    arena = result.get("_arena", {})
    sm    = len(result.get("steps", []))
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
        "\n".join(f"- {s}" for s in skill.get("steps", []))
    )

    # Strip any Sources section the AI may have included (we manage it ourselves)
    markdown = re.sub(
        r'\n*##\s*sources.*$', '', markdown,
        flags=re.IGNORECASE | re.DOTALL,
    ).rstrip()

    # Append the authoritative Sources section
    markdown += _build_sources_section(all_sources)

    # ── Write file ────────────────────────────────────────────────────────────
    with open(skill_path, "w") as f:
        f.write(markdown)

    # ── Update metadata index ─────────────────────────────────────────────────
    index = load_index()
    prev  = index.get(skill_name, {})

    # Merge and deduplicate all list fields (new AI output wins order, old fills gaps)
    merged_tools    = _dedup_list(skill.get("tools", []),           prev.get("tools", []))
    merged_tags     = _dedup_list(skill.get("tags", []),            prev.get("tags", []))
    merged_concepts = _dedup_list(skill.get("concepts", []),        prev.get("concepts", []))
    merged_packages = _dedup_list(skill.get("python_packages", []), prev.get("python_packages", []))
    merged_related  = _dedup_list(skill.get("related_skills", []),  prev.get("related_skills", []))

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
        "steps":           skill.get("steps", []),
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


# ── Core parallel job runner ──────────────────────────────────────────────────

def run_job(job_id: str, url: str, video_id: str):
    q = _jobs[job_id]["queue"]

    def emit(msg: str, kind: str = "info"):
        q.put({"type": "log", "msg": msg, "kind": kind})

    try:
        emit("🚀  Parallel agents launching …", "info")

        with ThreadPoolExecutor(max_workers=8, thread_name_prefix="fn") as pool:

            # ── Phase 1: metadata + transcript in parallel ────────────────────
            emit("⚡  Phase 1: metadata ∥ transcript …", "info")
            meta_f  = pool.submit(get_video_metadata, video_id)
            trans_f = pool.submit(get_transcript, url, video_id, emit)

            meta = meta_f.result(timeout=30)
            q.put({"type": "meta", "data": meta})
            emit(f"📺  {meta['title'] or 'Video identified'}", "info")

            transcript, method = trans_f.result(timeout=300)
            word_count = len(transcript.split())
            emit(f"📝  {word_count:,} words via {method}", "success")

            # Quick regex scan — used for early GitHub search AND relevance scoring
            quick_tools = github_agent.quick_tool_scan(transcript)
            if quick_tools:
                emit(
                    f"🔍  Quick scan: {', '.join(quick_tools[:6])}"
                    f"{'…' if len(quick_tools) > 6 else ''}",
                    "info",
                )

            # ── Phase 2: ChatGPT ∥ Groq ∥ GitHub — AI Arena ─────────────────
            emit("⚡  Phase 2: ChatGPT ∥ Groq ∥ GitHub — Arena mode …", "info")

            knowledge_ctx  = get_skills_context(quick_tools)
            existing_index = load_index()

            # All three work simultaneously — nobody idles
            gpt_f    = pool.submit(_extract_skill_chatgpt, transcript, knowledge_ctx, "")
            groq_f   = pool.submit(_extract_skill_groq,   transcript, knowledge_ctx, "")
            github_f = pool.submit(github_agent.search_tools, quick_tools, emit)

            # Collect GitHub first (fastest), then fetch READMEs while LLMs finish
            github_results = github_f.result(timeout=90)
            emit(f"📊  GitHub: {len(github_results)} repos — fetching READMEs …", "info")
            github_ctx = _github_readme_context(github_results)

            # Collect both LLM results (already running in parallel)
            skill_a = None
            skill_b = None
            try:
                skill_a = gpt_f.result(timeout=120)
                emit("✅  ChatGPT extraction done", "info")
            except Exception as exc_a:
                emit(f"⚠  ChatGPT failed ({exc_a})", "warning")
            try:
                skill_b = groq_f.result(timeout=120)
                emit("✅  Groq extraction done", "info")
            except Exception as exc_b:
                emit(f"⚠  Groq failed ({exc_b})", "warning")

            # Judge synthesizes the winner
            skill = _judge_arena(skill_a, skill_b, github_ctx, emit)
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
                    skill_a2 = _extract_skill_chatgpt(transcript, knowledge_ctx, existing_md)
                    skill    = _judge_arena(skill_a2, skill_b, github_ctx, emit)
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
            emit("⚡  Phase 3: save ∥ packages ∥ MCP ∥ clone ∥ supplemental search …", "info")

            ai_tools    = skill.get("tools", [])
            mcp_targets = [r for r in github_results
                           if r.get("is_mcp") or r.get("npm_package")]

            pkg_f   = pool.submit(_install_pkgs,
                                  skill.get("python_packages", []), emit)
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

            q.put({
                "type":              "done",
                "ok":                True,
                "title":             skill.get("title"),
                "description":       skill.get("description"),
                "steps":             skill.get("steps", []),
                "tools":             skill.get("tools", []),
                "concepts":          skill.get("concepts", []),
                "tags":              skill.get("tags", []),
                "related_skills":    skill.get("related_skills", []),
                "python_packages":   skill.get("python_packages", []),
                "installed":         installed,
                "failed":            failed,
                "skill_file":        skill_path,
                "skill_name":        skill_name,
                "transcript_words":  word_count,
                "transcript_method": method,
                "video_id":          video_id,
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
        import traceback
        tb = traceback.format_exc()
        emit(f"❌  {e}", "error")
        if len(tb) > 100:
            emit(tb[:600], "error")
        q.put({"type": "done", "ok": False, "error": str(e)})
    finally:
        _jobs[job_id]["done"] = True


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


@app.route("/process", methods=["POST"])
def process():
    data = request.get_json(silent=True) or {}
    url  = (data.get("url") or "").strip()

    if not url:
        return jsonify({"error": "No URL provided."}), 400
    if not GROQ_API_KEY and not OPENAI_API_KEY:
        return jsonify({
            "error": "No LLM key — add GROQ or CHATGPT in Tools › Secrets."
        }), 500

    video_id = extract_video_id(url)
    if not video_id:
        return jsonify({
            "error": "Could not find a YouTube video ID in that URL."
        }), 400

    job_id        = str(uuid.uuid4())[:8]
    _jobs[job_id] = {"queue": queue.Queue(), "done": False}
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


@app.route("/api/playlist_ids")
def api_playlist_ids():
    """Return all video IDs in a playlist (up to 20)."""
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
]


def _mcp_call_tool(name: str, args: dict) -> dict:
    """Shared tool logic — used by both the SSE endpoint and the stdio server."""
    index = load_index()

    if name == "list_skills":
        tag   = (args.get("tag") or "").lower()
        limit = min(int(args.get("limit") or 25), 100)
        skills = []
        for skill_name, meta in index.items():
            if tag and tag not in [t.lower() for t in meta.get("tags", [])]:
                continue
            skills.append({
                "name":         skill_name,
                "title":        meta.get("title", skill_name),
                "description":  meta.get("description", ""),
                "tags":         meta.get("tags", []),
                "tools":        meta.get("tools", [])[:10],
                "concepts":     meta.get("concepts", [])[:6],
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
            "description": meta.get("description", ""), "tags": meta.get("tags", []),
            "tools": meta.get("tools", []), "concepts": meta.get("concepts", []),
            "steps": meta.get("steps", []), "packages": meta.get("python_packages", []),
            "source_count": len(meta.get("history", [])) + 1,
            "updated_at": meta.get("updated_at", ""), "content": content,
        }

    elif name == "search_skills":
        query = (args.get("query") or "").lower()
        results = []
        for skill_name, meta in index.items():
            hay = " ".join([meta.get("title",""), meta.get("description",""),
                            " ".join(meta.get("tags",[])), " ".join(meta.get("tools",[])),
                            " ".join(meta.get("concepts",[])), " ".join(meta.get("steps",[]))]).lower()
            score = sum(hay.count(w) for w in query.split() if w)
            if score:
                results.append({"name": skill_name, "title": meta.get("title", skill_name),
                                 "description": meta.get("description",""), "score": score,
                                 "tags": meta.get("tags",[]), "tools": meta.get("tools",[])[:6]})
        results.sort(key=lambda x: x["score"], reverse=True)
        return {"results": results[:12], "query": query}

    elif name == "get_all_tools":
        tools: set = set()
        for m in index.values(): tools.update(m.get("tools",[]))
        return {"tools": sorted(tools), "count": len(tools)}

    elif name == "get_all_concepts":
        concepts: set = set()
        for m in index.values(): concepts.update(m.get("concepts",[]))
        return {"concepts": sorted(concepts), "count": len(concepts)}

    elif name == "get_library_stats":
        tools: set = set(); concepts: set = set(); pkgs: set = set()
        for m in index.values():
            tools.update(m.get("tools",[])); concepts.update(m.get("concepts",[]))
            pkgs.update(m.get("python_packages",[]))
        return {"skills": len(index), "tools": len(tools), "concepts": len(concepts), "packages": len(pkgs)}

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
    concepts = skill.get("concepts", [])
    tools    = skill.get("tools", [])
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
        "tags":       skill.get("tags", []),
        "step_count": len(skill.get("steps", [])),
    }
    brain["relationships"].setdefault(skill_name, {})
    for other, od in brain["skill_map"].items():
        if other == skill_name:
            continue
        shared = list(
            set(concepts + tools) &
            set(od.get("concepts", []) + od.get("tools", []))
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
    if not GROQ_API_KEY and not OPENAI_API_KEY:
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
                " ".join(meta.get("tools", [])),
                " ".join(meta.get("concepts", [])),
                " ".join(meta.get("tags", [])),
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
        if OPENAI_API_KEY:
            resp     = OpenAI(api_key=OPENAI_API_KEY).chat.completions.create(
                model=OPENAI_MODELS[0], messages=msgs, max_tokens=900, temperature=0.7)
            provider = OPENAI_MODELS[0]
        else:
            resp     = Groq(api_key=GROQ_API_KEY).chat.completions.create(
                model=GROQ_MODELS[0], messages=msgs, max_tokens=900, temperature=0.7)
            provider = GROQ_MODELS[0]
        return jsonify({"answer": resp.choices[0].message.content,
                        "skill_used": skill_name, "provider": provider})
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
    if not GROQ_API_KEY and not OPENAI_API_KEY:
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
            tools_str = ", ".join(meta.get("tools", [])[:3])
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
        if OPENAI_API_KEY:
            resp = OpenAI(api_key=OPENAI_API_KEY).chat.completions.create(
                model=OPENAI_MODELS[0],
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1200, temperature=0.5)
        else:
            resp = Groq(api_key=GROQ_API_KEY).chat.completions.create(
                model=GROQ_MODELS[0],
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1200, temperature=0.5)
        return jsonify({"briefing": resp.choices[0].message.content})
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
    """Full OpenAPI 3.0 spec — paste the URL into a ChatGPT Custom GPT Action."""
    domain = os.getenv("REPLIT_DEV_DOMAIN","")
    base   = f"https://{domain}" if domain else request.url_root.rstrip("/")
    spec   = {
        "openapi": "3.0.0",
        "info": {
            "title":       "Fieldnote Skill Library",
            "description": "Search and retrieve AI skills extracted from YouTube videos. Each skill contains steps, tools, concepts, and code references.",
            "version":     "2.0.0",
        },
        "servers": [{"url": base}],
        "paths": {
            "/api/skills": {
                "get": {
                    "operationId": "listSkills",
                    "summary":     "List all skills",
                    "description": "Returns every skill in the library with title, description, tags, tools, and concepts.",
                    "parameters": [
                        {"name":"q",   "in":"query","schema":{"type":"string"},"description":"Keyword filter"},
                        {"name":"tag", "in":"query","schema":{"type":"string"},"description":"Tag filter"},
                    ],
                    "responses": {"200":{"description":"Array of skill summaries","content":{"application/json":{"schema":{"type":"array","items":{"type":"object"}}}}}},
                }
            },
            "/api/skills/{name}/content": {
                "get": {
                    "operationId": "getSkillContent",
                    "summary":     "Get a skill's full markdown content",
                    "description": "Returns the complete skill markdown with all steps, tools, concepts, and source references.",
                    "parameters": [{"name":"name","in":"path","required":True,"schema":{"type":"string"},"description":"Skill name (no .md)"}],
                    "responses": {"200":{"description":"Skill with full content","content":{"application/json":{"schema":{"type":"object"}}}},
                                  "404":{"description":"Skill not found"}},
                }
            },
            "/api/health": {
                "get": {
                    "operationId": "getHealth",
                    "summary":     "System health status",
                    "responses":   {"200":{"description":"Health check results"}},
                }
            },
        },
    }
    return jsonify(spec)


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
        "tags":         meta.get("tags",[]),
        "tools":        meta.get("tools",[]),
        "concepts":     meta.get("concepts",[]),
        "steps":        meta.get("steps",[]),
        "python_packages": meta.get("python_packages",[]),
        "source_count": len(meta.get("history",[])) + 1,
        "updated_at":   meta.get("updated_at",""),
        "content":      content,
    })


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

    s.start()

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

