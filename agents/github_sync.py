"""
Fieldnote GitHub Sync Agent  (git-CLI edition)
Mirrors skills AND source code to edneycaleb-droid/fieldnote via git push.

Strategy:
  • Keeps a persistent clone at .fieldnote_mirror/ inside the workspace.
  • pull → copy files → commit → push, all via subprocess git.
  • Lock file prevents concurrent pushes.
  • sync_code() copies all workspace source files (*.py, *.html, etc.)
"""
import os, json, re, subprocess, time, fcntl, threading, shutil
from datetime import datetime, timezone
from pathlib import Path

SYNC_REPO  = "edneycaleb-droid/fieldnote"
GH_USER    = "edneycaleb-droid"
GIT_EMAIL  = "60082760-edneycaleb@users.noreply.replit.com"
MIRROR_DIR = Path(__file__).parent.parent / ".fieldnote_mirror"
WORKSPACE  = Path(__file__).parent.parent          # repo root
LOCK_PATH  = Path("/tmp/fn_sync.lock")
_lock      = threading.Lock()

# Files/dirs to copy into the mirror (relative to WORKSPACE)
SOURCE_INCLUDE = [
    "app.py", "main.py", "replit.md", "pyproject.toml", ".gitignore", "PROVIDERS.md",
]
# Never push these — they contain Replit internals / may embed credentials
SOURCE_NEVER  = {".replit", "replit.nix", "replit.toml", ".env", ".env.*"}
SOURCE_DIRS = ["agents", "templates"]

# Never copy these into the mirror
SOURCE_EXCLUDE_DIRS  = {
    "__pycache__", ".fieldnote_mirror", "fieldnote_repos",
    "fieldnote_skills", ".git", "node_modules", ".agents",
    "fieldnote_mcp",
}
SOURCE_EXCLUDE_FILES = {"local_keys.json", ".env"}
SOURCE_EXTENSIONS    = {".py", ".html", ".css", ".js", ".md", ".txt",
                        ".toml", ".nix", ".json", ".replit"}


# ── Token ─────────────────────────────────────────────────────────────────────

def _token() -> str:
    return (os.getenv("GITHUBPAT") or os.getenv("GITHUB_TOKEN") or
            os.getenv("GH_TOKEN") or os.getenv("GITHUB") or "")


def _remote_url() -> str:
    t = _token()
    if t:
        return f"https://{GH_USER}:{t}@github.com/{SYNC_REPO}.git"
    return f"https://github.com/{SYNC_REPO}.git"


# ── Git helpers ───────────────────────────────────────────────────────────────

def _run(args: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GCM_INTERACTIVE"]     = "never"
    return subprocess.run(
        args, cwd=str(cwd or MIRROR_DIR),
        capture_output=True, text=True, env=env,
        timeout=30, check=check,
    )


def _ensure_mirror() -> bool:
    """Clone or pull the mirror. Returns True if ready."""
    if not _token():
        return False
    MIRROR_DIR.mkdir(parents=True, exist_ok=True)
    git_dir = MIRROR_DIR / ".git"

    if not git_dir.exists():
        # Directory may exist with stale content but no .git — init in place.
        try:
            _run(["git", "init", "-b", "main"])
            _run(["git", "config", "user.name",  "Fieldnote Sync"])
            _run(["git", "config", "user.email", GIT_EMAIL])
            _run(["git", "remote", "add", "origin", _remote_url()])
            _run(["git", "fetch", "--depth=1", "origin", "main"])
            _run(["git", "reset", "--hard", "origin/main"])
            return True
        except subprocess.CalledProcessError:
            # Fallback: nuke dir and do a proper clone
            try:
                shutil.rmtree(str(MIRROR_DIR))
                MIRROR_DIR.mkdir(parents=True)
                _run(["git", "clone", "--depth=1", _remote_url(), str(MIRROR_DIR)],
                     cwd=MIRROR_DIR.parent, check=True)
                _run(["git", "config", "user.name",  "Fieldnote Sync"])
                _run(["git", "config", "user.email", GIT_EMAIL])
                return True
            except Exception:
                return False
        except Exception:
            return False
    else:
        # Pull latest — autostash so local edits don't block
        try:
            _run(["git", "remote", "set-url", "origin", _remote_url()])
            _run(["git", "pull", "--rebase", "--autostash", "--quiet", "origin", "main"])
            return True
        except Exception:
            return True   # push will work even if pull fails (repo might be ahead)


def _commit_and_push(message: str) -> bool:
    try:
        result = _run(["git", "status", "--porcelain"])
        if not result.stdout.strip():
            return True   # nothing to commit
        _run(["git", "add", "-A"])
        _run(["git", "commit", "-m", message])
        _run(["git", "push", "origin", "main"])
        return True
    except subprocess.CalledProcessError as e:
        # If push rejected (someone pushed ahead), pull-rebase and retry
        if "rejected" in e.stderr or "non-fast-forward" in e.stderr:
            try:
                _run(["git", "pull", "--rebase", "origin", "main"])
                _run(["git", "push", "origin", "main"])
                return True
            except Exception:
                pass
        return False
    except Exception:
        return False


# ── README builder ────────────────────────────────────────────────────────────

def _build_readme(index: dict) -> str:
    skills = sorted(index.items(), key=lambda x: x[1].get("updated_at", ""), reverse=True)
    now    = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    n      = "\n"

    rows = []
    for name, m in skills:
        title = m.get("title", name).replace("|", "\\|")
        desc  = (m.get("description") or "")[:80].replace("|", "\\|")
        tools = " ".join(f"`{t}`" for t in m.get("tools", [])[:4])
        tags  = " ".join(f"`{g}`" for g in m.get("tags",  [])[:3])
        rows.append(f"| [{title}](skills/{name}.md) | {desc} | {tools} | {tags} |")

    table_rows = n.join(rows) if rows else "| *(no skills yet)* | | | |"

    return f"""# ⚡ Fieldnote

> A personal AI skill library — every YouTube video I learn from becomes a structured, searchable skill.
> **{len(skills)} skill{'s' if len(skills) != 1 else ''}** · Last synced: {now}

---

## 📚 Skills

| Skill | Description | Tools | Tags |
|-------|-------------|-------|------|
{table_rows}

---

## 🆓 Free Stack — runs entirely without spending money

Every component has a free path. The system is **free-first by design** — paid providers are optional quality upgrades, never requirements.

### LLM (Language Models)

| Provider | Model | Free Tier | Role in Fieldnote |
|----------|-------|-----------|-------------------|
| **[Groq](https://console.groq.com)** | `llama-3.3-70b-versatile` · `gemma2-9b-it` · `mixtral-8x7b` | 14,400 tokens/min — no card | **Primary** — educator + practitioner extraction |
| **[Gemini AI Studio](https://aistudio.google.com/app/apikey)** | `gemini-2.0-flash` · `gemini-1.5-flash` | 1,500 req/day — no card | Fallback #2 |
| **[HuggingFace](https://huggingface.co/settings/tokens)** | `Qwen/Qwen2.5-72B` · serverless | Anonymous OK, token recommended | Fallback #3 |
| **[OpenRouter](https://openrouter.ai/keys)** | `llama-3.2-3b-instruct:free` + others | Free models, free account | Fallback #4 |

> **To run 100% free:** set only the `GROQ` secret. The router auto-falls-back through all free providers.

### Transcription

| Tool | Type | Cost | Notes |
|------|------|------|-------|
| **YouTube captions** | API | Free | First choice — instant, no compute |
| **[Groq Whisper](https://console.groq.com)** | Cloud API | Free tier (8h audio/day) | Used when captions unavailable |
| **[faster-whisper](https://github.com/guillaumekambham/faster-whisper)** | Local / self-hosted | Free forever | CPU fallback, runs on Replit |

### Infrastructure

| Tool | Cost | Purpose |
|------|------|---------|
| **[yt-dlp](https://github.com/yt-dlp/yt-dlp)** | Free / open source | YouTube download & metadata |
| **[ffmpeg](https://ffmpeg.org)** | Free / open source | Audio extraction & conversion |
| **[GitHub API](https://docs.github.com/en/rest)** | Free (5,000 req/hr with PAT) | Repo sync + discovery |
| **[Flask](https://flask.palletsprojects.com)** | Free / open source | Web server |
| **[Chroma](https://github.com/chroma-core/chroma)** | Free / open source | Free vector DB alternative to Pinecone |
| **[FAISS](https://github.com/facebookresearch/faiss)** | Free / open source | Free vector similarity (Facebook) |
| **[Qdrant](https://qdrant.tech)** | Free self-hosted | Free vector DB alternative to Weaviate |
| **[Ollama](https://github.com/ollama/ollama)** | Free / open source | Free local LLM alternative to OpenAI |
| **[LiteLLM](https://github.com/BerriAI/litellm)** | Free / open source | Free OpenAI-compatible proxy |
| **[sentence-transformers](https://github.com/UKPLab/sentence-transformers)** | Free / open source | Free embeddings alternative to Cohere |

---

## 💳 Paid (optional) — and their free alternatives

Everything paid has a drop-in free replacement already wired into the codebase.

| Paid Service | Used For | Free Alternative | Already Implemented? |
|---|---|---|---|
| **OpenAI GPT-4o-mini** | Educator lens in AI Arena | ✅ **Groq llama-3.3-70b** — same extraction quality, faster, free | ✅ Yes — Groq is provider #1 |
| **OpenAI GPT-4o** | Judge synthesis | ✅ **Groq llama-3.3-70b** via provider router | ✅ Yes — auto-fallback |
| **Pinecone** (if added) | Vector search | ✅ **Chroma** or **FAISS** or **Qdrant** (self-hosted) | ✅ Documented + discovery-paired |
| **AssemblyAI** (if added) | Transcription | ✅ **faster-whisper** (local) + **Groq Whisper** | ✅ Yes — already in stack |
| **ElevenLabs** (if added) | Text-to-speech | ✅ **Coqui TTS** or **Piper TTS** (local) | 🔜 Discoverable |
| **Replicate** (if added) | Image/video AI | ✅ **Diffusers** (local Stable Diffusion) | 🔜 Discoverable |
| **Cohere** (if added) | Embeddings | ✅ **sentence-transformers** (local, CPU) | 🔜 Discoverable |

> **Auto-pairing:** When the GitHub Discovery Agent finds a repo that uses a paid service, it automatically searches for and extracts a free alternative, linking both skills together in the library.

---

## 🤖 How skills are built

Every YouTube URL goes through the **Fieldnote AI Arena**:

| Step | Free Provider | Paid Alternative | Role |
|------|--------------|-----------------|------|
| 1. Transcribe | Groq Whisper · faster-whisper | — | Audio → text |
| 2. Extract A  | Groq llama-3.3-70b | OpenAI GPT-4o-mini | Educator lens — depth & concepts |
| 3. Extract B  | Groq llama-3.3-70b | OpenAI GPT-4o-mini | Practitioner lens — steps & tools |
| 4. Discover   | GitHub API (free) | — | Real repos using these tools |
| 5. Judge      | Groq llama-3.3-70b | OpenAI GPT-4o-mini | Synthesises the best result |
| 6. Sync       | GitHub (free PAT) | — | Pushes here automatically |

Each skill contains: structured steps, tools, concepts, tags, source attribution, related skills, and Python packages.

---

## ⚙️ Autonomous Agents (always free)

| Agent | Schedule | What it does |
|-------|----------|-------------|
| **GitHub Discovery** | Every 2h | Searches GitHub for high-quality repos, extracts skills from READMEs |
| **Free-Alt Pairing** | On discovery | When a paid-tool repo is found, automatically finds + extracts a free alternative |
| **DCA Enhancer** | Every 6h | Re-runs extraction on existing skills to improve quality over time |
| **Watchlist Processor** | Every 1h | Processes queued YouTube URLs |
| **GitHub Sync** | Every 10min | Mirrors all source code + skills to this repo |

---

See [PROVIDERS.md](PROVIDERS.md) for the complete provider reference, rate limits, and setup guide.

*Auto-generated — do not edit directly.*
"""


# ── Source file copy ─────────────────────────────────────────────────────────

def _copy_source_files() -> int:
    """Copy workspace source files into the mirror. Returns count copied."""
    copied = 0

    def _copy_file(src: Path, dst: Path) -> None:
        nonlocal copied
        if src.name in SOURCE_EXCLUDE_FILES or src.name in SOURCE_NEVER:
            return
        if src.suffix not in SOURCE_EXTENSIONS and src.name not in SOURCE_INCLUDE:
            return
        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            if not dst.exists() or src.stat().st_mtime > dst.stat().st_mtime:
                shutil.copy2(src, dst)
                copied += 1
        except Exception:
            pass

    # Top-level files
    for name in SOURCE_INCLUDE:
        src = WORKSPACE / name
        if src.exists():
            _copy_file(src, MIRROR_DIR / name)

    # Source directories (agents/, templates/)
    for dir_name in SOURCE_DIRS:
        src_dir = WORKSPACE / dir_name
        if not src_dir.is_dir():
            continue
        for src in src_dir.rglob("*"):
            if not src.is_file():
                continue
            # Skip excluded subdirs
            parts = src.relative_to(WORKSPACE).parts
            if any(p in SOURCE_EXCLUDE_DIRS for p in parts):
                continue
            rel  = src.relative_to(WORKSPACE)
            _copy_file(src, MIRROR_DIR / rel)

    return copied


# ── Public API ────────────────────────────────────────────────────────────────

def repo_url() -> str:
    return "https://github.com/" + SYNC_REPO


def sync_code(label: str = "auto") -> dict:
    """Copy all workspace source files to the mirror and push.
    Called by the file watcher on every change and by the scheduler as fallback."""
    if not _token():
        return {"ok": False, "error": "No GitHub token configured"}
    with _lock:
        if not _ensure_mirror():
            return {"ok": False, "error": "Could not initialise git mirror"}
        changed = _copy_source_files()
        ok = _commit_and_push(f"sync({label}): {changed} source file(s) updated")
        return {"ok": ok, "changed": changed, "label": label}


def sync_skill(skill_name: str, markdown: str, index: dict) -> bool:
    """Push one skill + refresh README. Called after every _save_skill()."""
    if not _token():
        return False
    with _lock:
        if not _ensure_mirror():
            return False
        # Write skill file
        skills_dir = MIRROR_DIR / "skills"
        skills_dir.mkdir(exist_ok=True)
        (skills_dir / f"{skill_name}.md").write_text(markdown, encoding="utf-8")
        # Refresh README
        (MIRROR_DIR / "README.md").write_text(_build_readme(index), encoding="utf-8")
        return _commit_and_push(f"feat: {'update' if True else 'add'} skill {skill_name}")


def sync_brain(brain: dict) -> bool:
    """Push _brain.json to the repo."""
    if not _token():
        return False
    with _lock:
        if not _ensure_mirror():
            return False
        (MIRROR_DIR / "_brain.json").write_text(
            json.dumps(brain, indent=2), encoding="utf-8"
        )
        return _commit_and_push("chore: update brain graph")


KNOWLEDGE_DIR    = WORKSPACE / "assistant_knowledge"
KNOWLEDGE_CATS   = {"decisions", "discoveries", "session_learnings", "preferences", "architecture"}
KNOWLEDGE_MIRROR = MIRROR_DIR / "assistant_knowledge"


def sync_knowledge_entry(entry: dict) -> dict:
    """Write one knowledge entry to assistant_knowledge/ and push.
    
    entry fields: category, slug, title, content, sources, confidence
    Returns {"ok": bool, "path": str, "error": str|None}
    """
    if not _token():
        return {"ok": False, "error": "No GitHub token configured"}

    category   = (entry.get("category") or "").strip().lower()
    slug       = re.sub(r"[^a-z0-9_-]", "-", (entry.get("slug") or "").strip().lower()).strip("-")
    title      = (entry.get("title") or slug).strip()
    content    = (entry.get("content") or "").strip()
    sources    = entry.get("sources") or []
    confidence = (entry.get("confidence") or "unverified").strip()

    # Whitelist — reject anything outside the approved categories
    if category not in KNOWLEDGE_CATS:
        return {"ok": False, "error": f"Invalid category '{category}'. Allowed: {sorted(KNOWLEDGE_CATS)}"}
    if not slug:
        return {"ok": False, "error": "slug is required"}

    now = datetime.now(timezone.utc).isoformat()

    # Build markdown with YAML frontmatter
    sources_yaml = "\n".join(f'  - "{s}"' for s in sources) if sources else "  []"
    if sources:
        sources_block = "sources:\n" + sources_yaml
    else:
        sources_block = "sources: []"

    # For flat-file categories (preferences, architecture) use root-level file
    if category in {"preferences", "architecture"}:
        rel_path = f"assistant_knowledge/{slug}.md"
    else:
        rel_path = f"assistant_knowledge/{category}/{slug}.md"

    markdown = f"""---
category: {category}
slug: {slug}
title: {title}
confidence: {confidence}
{sources_block}
updated_at: "{now}"
---

{content}
"""

    # Write locally
    local_path = WORKSPACE / rel_path
    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_text(markdown, encoding="utf-8")

    # Rebuild local index.json
    _rebuild_knowledge_index()

    # Sync to mirror and push
    with _lock:
        if not _ensure_mirror():
            return {"ok": False, "error": "Could not initialise git mirror", "path": rel_path}

        # Copy entire assistant_knowledge/ into mirror
        mirror_ak = MIRROR_DIR / "assistant_knowledge"
        if KNOWLEDGE_DIR.exists():
            for src in KNOWLEDGE_DIR.rglob("*"):
                if src.is_file():
                    dst = mirror_ak / src.relative_to(KNOWLEDGE_DIR)
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

        ok = _commit_and_push(f"knowledge({category}): {title[:60]}")
        return {"ok": ok, "path": rel_path, "error": None if ok else "Push failed"}


def _rebuild_knowledge_index() -> None:
    """Scan assistant_knowledge/ and rebuild index.json."""
    entries = []
    if not KNOWLEDGE_DIR.exists():
        return
    for md_file in sorted(KNOWLEDGE_DIR.rglob("*.md")):
        try:
            text = md_file.read_text(encoding="utf-8")
            # Parse simple YAML frontmatter
            meta: dict = {}
            if text.startswith("---"):
                fm_end = text.index("---", 3)
                for line in text[3:fm_end].splitlines():
                    if ":" in line:
                        k, _, v = line.partition(":")
                        meta[k.strip()] = v.strip().strip('"')
            entries.append({
                "slug":       meta.get("slug", md_file.stem),
                "title":      meta.get("title", md_file.stem),
                "category":   meta.get("category", "unknown"),
                "confidence": meta.get("confidence", "unverified"),
                "updated_at": meta.get("updated_at", ""),
                "path":       str(md_file.relative_to(KNOWLEDGE_DIR)),
            })
        except Exception:
            pass
    entries.sort(key=lambda x: x["updated_at"], reverse=True)
    idx_path = KNOWLEDGE_DIR / "index.json"
    idx_path.write_text(
        json.dumps({"entries": entries, "updated_at": datetime.now(timezone.utc).isoformat()},
                   indent=2),
        encoding="utf-8",
    )


def sync_all(skills_dir_path: str, index: dict) -> dict:
    """Full library sync — all skills + README + brain. For manual trigger."""
    if not _token():
        return {"ok": False, "error": "No GitHub token configured"}
    with _lock:
        if not _ensure_mirror():
            return {"ok": False, "error": "Could not initialise git mirror"}

        skills_dir = Path(skills_dir_path)
        mirror_skills = MIRROR_DIR / "skills"
        mirror_skills.mkdir(exist_ok=True)

        pushed, failed = [], []
        for skill_name in index:
            md_path = skills_dir / f"{skill_name}.md"
            if not md_path.exists():
                continue
            try:
                content = md_path.read_text(encoding="utf-8")
                (mirror_skills / f"{skill_name}.md").write_text(content, encoding="utf-8")
                pushed.append(skill_name)
            except Exception as exc:
                failed.append(f"{skill_name} ({str(exc)[:40]})")

        # Brain graph
        brain_path = skills_dir / "_brain.json"
        if brain_path.exists():
            try:
                (MIRROR_DIR / "_brain.json").write_text(
                    brain_path.read_text(encoding="utf-8"), encoding="utf-8"
                )
            except Exception:
                pass

        # README
        (MIRROR_DIR / "README.md").write_text(_build_readme(index), encoding="utf-8")

        ok = _commit_and_push(
            f"chore: full library sync — {len(pushed)} skills"
        )
        return {
            "ok":     ok,
            "pushed": pushed,
            "failed": failed,
            "total":  len(index),
            "repo":   repo_url(),
        }
