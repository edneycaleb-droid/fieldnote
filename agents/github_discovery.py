"""
Fieldnote GitHub Discovery Agent — autonomous 24/7 learning from GitHub.

discover_and_learn():
  1. Build search queries — fixed trending + dynamic from skill library tags/tools
  2. Search GitHub API for high-quality repos (≥150 stars, recent, not archived)
  3. Filter against discovery log — skip repos processed within RECHECK_DAYS
  4. Fetch full README for each candidate
  5. Run ChatGPT + Groq parallel extraction on the README as content source
  6. Judge synthesises the best-of-both skill
  7. Quality gate — skip weak output
  8. Save: create new skill OR enhance existing matching skill
  9. Update discovery log

Rate budget: ~15 GitHub API calls per cycle.  With GITHUBPAT (5 000/hr) this
is negligible.  Without a token the 60/hr anonymous limit still fits easily.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
import time
from collections import Counter
from concurrent.futures import as_completed
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

log = logging.getLogger("fieldnote.github_discovery")

# ── Config ────────────────────────────────────────────────────────────────────

MIN_STARS     = 150      # minimum stars to consider a repo
BATCH_SIZE    = 5        # repos to process per run (keeps latency bounded)
RECHECK_DAYS  = 21       # re-check a repo after this many days for new content
PER_PAGE      = 8        # results per GitHub search query
README_MAX    = 12_000   # max README characters to send to LLM

DISCOVERY_LOG_NAME = "_discovery_log.json"

# Fixed trending queries — always searched regardless of library content
TRENDING_QUERIES = [
    "AI agent framework python stars:>500 sort:updated",
    "LLM tools workflow python stars:>300 sort:updated",
    "model context protocol MCP stars:>100 sort:updated",
    "RAG retrieval augmented generation stars:>300 sort:stars",
    "autonomous agent language model stars:>200 sort:updated",
    "fine tuning LLM training python stars:>200 sort:stars",
    "vector database embedding search stars:>400 sort:stars",
    "open source AI assistant python stars:>500 sort:updated",
    "machine learning pipeline workflow stars:>300 sort:updated",
    "code generation LLM python stars:>200 sort:updated",
]


# ── GitHub API helpers ────────────────────────────────────────────────────────

def _gh_token() -> str:
    return (os.getenv("GITHUBPAT") or os.getenv("GITHUB_TOKEN")
            or os.getenv("GH_TOKEN") or os.getenv("GITHUB") or "")


def _gh_get(url: str) -> Any:
    """Authenticated GET → parsed JSON.  Raises on non-200."""
    token   = _gh_token()
    headers = {
        "Accept":               "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent":           "fieldnote-discovery/1.0",
    }
    if token:
        headers["Authorization"] = "Bearer " + token
    try:
        req = Request(url, headers=headers)
        with urlopen(req, timeout=12) as resp:
            return json.load(resp)
    except HTTPError as exc:
        if exc.code == 403:
            raise RuntimeError("GitHub rate limit hit — add GITHUBPAT secret for 5 000/hr")
        if exc.code in (404, 422, 451):
            return {}
        raise
    except URLError:
        return {}


def _search_repos(query: str, per_page: int = PER_PAGE) -> list[dict]:
    url  = (f"https://api.github.com/search/repositories"
            f"?q={quote(query)}&per_page={per_page}&sort=stars&order=desc")
    data = _gh_get(url)
    items = data.get("items") or []
    return [
        {
            "full_name":   r["full_name"],
            "html_url":    r["html_url"],
            "description": (r.get("description") or "")[:200],
            "stars":       r.get("stargazers_count", 0),
            "language":    r.get("language", ""),
            "topics":      r.get("topics", []),
            "archived":    r.get("archived", False),
            "pushed_at":   r.get("pushed_at", ""),
            "owner":       r["owner"]["login"],
            "name":        r["name"],
        }
        for r in items
        if not r.get("archived")
        and r.get("stargazers_count", 0) >= MIN_STARS
    ]


def _fetch_readme(owner: str, repo: str) -> str:
    """Return clean plain-text README (≤README_MAX chars).  Empty string on failure."""
    data = _gh_get(f"https://api.github.com/repos/{owner}/{repo}/readme")
    if not data or "content" not in data:
        return ""
    try:
        raw = base64.b64decode(data["content"]).decode("utf-8", errors="ignore")
    except Exception:
        return ""

    # Strip images, badges, HTML comments, keep headings as plain text
    raw = re.sub(r"<!--.*?-->",       "", raw, flags=re.DOTALL)
    raw = re.sub(r"!\[.*?\]\(.*?\)",  "", raw)
    raw = re.sub(r"<[^>]{1,200}>",    "", raw)
    raw = re.sub(r"\[!\[.*?\]\(.*?\)\]\(.*?\)", "", raw)  # badge-links
    raw = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", raw)   # inline links → text
    raw = re.sub(r"\s{3,}", "\n\n", raw)
    return raw.strip()[:README_MAX]


# ── Discovery log ─────────────────────────────────────────────────────────────

def _log_path() -> str:
    import app as _a
    return os.path.join(_a.SKILLS_DIR, DISCOVERY_LOG_NAME)


def load_discovery_log() -> dict:
    path = _log_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


def save_discovery_log(log_data: dict) -> None:
    path = _log_path()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(log_data, f, indent=2)


def _already_processed(full_name: str, log_data: dict) -> bool:
    entry = log_data.get(full_name)
    if not entry:
        return False
    processed_at = entry.get("processed_at", "")
    if not processed_at:
        return False
    try:
        age = datetime.now(timezone.utc) - datetime.fromisoformat(processed_at)
        # Error entries get a much shorter cooldown (1 day) so transient quota
        # failures don't freeze a repo out for 3 weeks.
        recheck = 1 if entry.get("action") == "error" else RECHECK_DAYS
        return age.days < recheck
    except Exception:
        return False


# ── Paid-service detection & free-alternative database ───────────────────────

# Maps paid service keywords → human label + ordered list of free-alternative
# GitHub search queries.  First result with ≥MIN_STARS and a real README wins.
PAID_TO_FREE: dict[str, dict] = {
    "openai": {
        "label": "OpenAI / GPT",
        "alternatives": [
            ("groq python client llm inference free tier stars:>300 sort:stars",  "Groq"),
            ("ollama run llm locally python stars:>2000 sort:stars",               "Ollama"),
            ("vllm fast inference openai compatible python stars:>5000 sort:stars","vLLM"),
            ("litellm openai compatible proxy free stars:>1000 sort:stars",        "LiteLLM"),
        ],
    },
    "gpt-4": {
        "label": "GPT-4",
        "alternatives": [
            ("llama open source llm python stars:>2000 sort:stars",     "Llama"),
            ("mistral open weight model python stars:>1000 sort:stars", "Mistral"),
            ("ollama local model serve python stars:>2000 sort:stars",  "Ollama"),
        ],
    },
    "anthropic": {
        "label": "Anthropic Claude",
        "alternatives": [
            ("groq python llama inference free stars:>300 sort:stars",    "Groq"),
            ("ollama mistral local python stars:>2000 sort:stars",        "Ollama"),
            ("together ai open source llm api python stars:>500 sort:stars","Together AI"),
        ],
    },
    "pinecone": {
        "label": "Pinecone",
        "alternatives": [
            ("chroma vector database open source python stars:>1000 sort:stars",  "Chroma"),
            ("qdrant vector search python self hosted stars:>4000 sort:stars",    "Qdrant"),
            ("faiss facebook vector similarity python stars:>10000 sort:stars",   "FAISS"),
            ("lancedb local vector database python stars:>1000 sort:stars",       "LanceDB"),
        ],
    },
    "weaviate": {
        "label": "Weaviate Cloud",
        "alternatives": [
            ("qdrant vector search python open source stars:>4000 sort:stars", "Qdrant"),
            ("chroma open source embedding database stars:>1000 sort:stars",   "Chroma"),
            ("milvus open source vector database stars:>5000 sort:stars",      "Milvus"),
        ],
    },
    "cohere": {
        "label": "Cohere",
        "alternatives": [
            ("sentence transformers huggingface embedding python stars:>5000 sort:stars",
             "sentence-transformers"),
            ("fastembed fast embedding cpu python stars:>500 sort:stars", "FastEmbed"),
        ],
    },
    "replicate": {
        "label": "Replicate",
        "alternatives": [
            ("ollama local model run python stars:>2000 sort:stars",                  "Ollama"),
            ("diffusers stable diffusion local inference python stars:>5000 sort:stars","Diffusers"),
            ("comfyui stable diffusion workflow python stars:>2000 sort:stars",        "ComfyUI"),
        ],
    },
    "assemblyai": {
        "label": "AssemblyAI",
        "alternatives": [
            ("faster whisper local transcription python stars:>2000 sort:stars", "Faster-Whisper"),
            ("whisper openai speech recognition python stars:>50000 sort:stars", "Whisper"),
            ("insanely fast whisper python stars:>1000 sort:stars",              "insanely-fast-whisper"),
        ],
    },
    "deepgram": {
        "label": "Deepgram",
        "alternatives": [
            ("faster whisper local speech recognition python stars:>2000 sort:stars", "Faster-Whisper"),
            ("whisper speech recognition local python stars:>50000 sort:stars",       "Whisper"),
        ],
    },
    "elevenlabs": {
        "label": "ElevenLabs",
        "alternatives": [
            ("coqui tts open source text speech python stars:>5000 sort:stars", "Coqui TTS"),
            ("piper neural text speech local python stars:>2000 sort:stars",    "Piper TTS"),
            ("bark text speech huggingface python stars:>2000 sort:stars",      "Bark"),
        ],
    },
    "stability ai": {
        "label": "Stability AI API",
        "alternatives": [
            ("diffusers stable diffusion local python huggingface stars:>5000 sort:stars",
             "Diffusers"),
            ("automatic1111 stable diffusion webui python stars:>5000 sort:stars",
             "Automatic1111 WebUI"),
        ],
    },
    "azure openai": {
        "label": "Azure OpenAI",
        "alternatives": [
            ("litellm proxy openai compatible local stars:>1000 sort:stars", "LiteLLM"),
            ("ollama local llm python stars:>2000 sort:stars",               "Ollama"),
        ],
    },
    "mistral api": {
        "label": "Mistral API (paid tier)",
        "alternatives": [
            ("ollama mistral local python stars:>2000 sort:stars",            "Ollama + Mistral"),
            ("mistral inference local python stars:>500 sort:stars",          "Mistral local"),
            ("groq mistral python inference free stars:>300 sort:stars",      "Groq + Mistral"),
        ],
    },
    "voyage ai": {
        "label": "Voyage AI embeddings",
        "alternatives": [
            ("sentence transformers all-minilm embedding python stars:>5000 sort:stars",
             "sentence-transformers"),
            ("nomic embed local embedding python stars:>500 sort:stars", "Nomic Embed"),
        ],
    },
}

# Flat keyword → dict key mapping for fast lookup in detection
_PAID_KEYWORDS: dict[str, str] = {
    "openai":          "openai",
    "gpt-4":           "gpt-4",
    "gpt-3":           "openai",
    "chatgpt":         "openai",
    "anthropic":       "anthropic",
    "claude":          "anthropic",
    "pinecone":        "pinecone",
    "weaviate":        "weaviate",
    "cohere":          "cohere",
    "replicate":       "replicate",
    "assemblyai":      "assemblyai",
    "assembly ai":     "assemblyai",
    "deepgram":        "deepgram",
    "elevenlabs":      "elevenlabs",
    "eleven labs":     "elevenlabs",
    "stability ai":    "stability ai",
    "stabilityai":     "stability ai",
    "azure openai":    "azure openai",
    "mistral api":     "mistral api",
    "voyage ai":       "voyage ai",
    "voyage":          "voyage ai",
}


def _detect_paid_services(repo: dict, skill: dict, readme: str) -> list[str]:
    """Return the PAID_TO_FREE keys for every paid service detected in this repo."""
    haystack = " ".join([
        repo.get("description", ""),
        " ".join(repo.get("topics", [])),
        " ".join(skill.get("tools", [])),
        readme[:4000],
    ]).lower()

    found: list[str] = []
    seen:  set[str]  = set()
    for keyword, key in _PAID_KEYWORDS.items():
        if keyword in haystack and key not in seen:
            found.append(key)
            seen.add(key)
    return found


def _find_best_free_alternative(paid_key: str, disc_log: dict) -> dict | None:
    """
    Search GitHub for the best free alternative for a paid service.
    Tries each query in order, returns the first repo with README ≥ 200 chars
    that hasn't been processed recently.
    Returns the repo dict (with _readme populated) or None.
    """
    entry = PAID_TO_FREE.get(paid_key)
    if not entry:
        return None

    for query, _ in entry["alternatives"]:
        try:
            results = _search_repos(query, per_page=5)
            for repo in results:
                fn = repo["full_name"]
                if _already_processed(fn, disc_log):
                    continue
                readme = _fetch_readme(repo["owner"], repo["name"])
                if readme and len(readme) >= 200:
                    repo["_readme"]       = readme
                    repo["_readme_words"] = readme.split()
                    repo["_alt_for"]      = paid_key
                    log.info("Free alt for '%s': %s (%d ⭐)", paid_key, fn, repo["stars"])
                    return repo
            time.sleep(0.4)
        except Exception as exc:
            log.warning("Alt search '%s' failed: %s", query, exc)

    return None


def _process_free_alternative(
    alt_repo: dict,
    paid_repo: dict,
    paid_key:  str,
    disc_log:  dict,
    index:     dict,
) -> dict | None:
    """
    Run the full extraction + quality gate + save pipeline on a free-alternative repo.
    Returns a result dict on success, or None on failure.
    """
    import agents.skill_quality as sq
    import agents.github_sync   as gs
    import app as _a

    fn     = alt_repo["full_name"]
    readme = alt_repo.get("_readme", "")
    label  = PAID_TO_FREE[paid_key]["label"]

    log.info("Processing free alt %s (for %s)", fn, label)
    try:
        skill  = _extract_from_repo(alt_repo, readme, index)
        qr     = sq.quality_gate(skill)
        log.info("Alt %s quality: %s %.0f%%", fn, qr.decision.value, qr.score * 100)

        if qr.decision == sq.QualityDecision.DENY:
            disc_log[fn] = {
                "processed_at":  _now_iso(),
                "skill_name":    None,
                "action":        "quality_denied",
                "stars":         alt_repo["stars"],
                "quality_score": round(qr.score, 2),
                "alt_for":       paid_repo["full_name"],
            }
            return None

        skill_name, action = _save_discovered_skill(skill, alt_repo, index)
        index = _a.load_index()

        try:
            gs.sync_skill(skill_name, _a._read_existing_markdown(skill_name), index)
        except Exception as exc:
            log.warning("GitHub sync failed for alt skill: %s", exc)

        disc_log[fn] = {
            "processed_at":   _now_iso(),
            "skill_name":     skill_name,
            "action":         action,
            "stars":          alt_repo["stars"],
            "quality_score":  round(qr.score, 2),
            "quality_decision": qr.decision.value,
            "alt_for":        paid_repo["full_name"],
            "free_of":        label,
        }

        # Record the pairing in assistant_knowledge/
        _record_free_alt_pairing(
            paid_repo   = paid_repo,
            alt_repo    = alt_repo,
            paid_label  = label,
            skill_name  = skill_name,
            quality     = qr.score,
        )

        log.info("Free alt saved: '%s' (free of %s)", skill_name, label)
        return {
            "repo":        fn,
            "skill":       skill_name,
            "action":      action,
            "stars":       alt_repo["stars"],
            "quality":     round(qr.score, 2),
            "free_of":     label,
            "paired_with": paid_repo["full_name"],
        }

    except Exception as exc:
        log.warning("Alt AI extraction failed for %s (%s) — saving baseline + queueing enrichment", fn, exc)
        # Never write action:"error" — fall back to deterministic baseline and enqueue
        try:
            import agents.discovery_enrichment as _de
            baseline = _deterministic_baseline(alt_repo, readme)
            baseline_name, _ = _save_discovered_skill(baseline, alt_repo, _a.load_index())
            _de.enqueue(fn, alt_repo.get("stars", 0))
            disc_log[fn] = {
                "processed_at":     _now_iso(),
                "skill_name":       baseline_name,
                "action":           "baseline",
                "enrichment_queued": True,
                "_baseline":        True,
                "_baseline_reason": "alt_ai_failed",
                "error":            str(exc)[:200],
                "stars":            alt_repo.get("stars", 0),
                "alt_for":          paid_repo["full_name"],
            }
        except Exception as inner:
            log.error("Could not save alt baseline for %s: %s", fn, inner)
            disc_log[fn] = {
                "processed_at":     _now_iso(),
                "skill_name":       None,
                "action":           "baseline",
                "enrichment_queued": True,
                "_baseline":        True,
                "_baseline_reason": "alt_ai_failed_no_baseline",
                "stars":            alt_repo.get("stars", 0),
                "alt_for":          paid_repo["full_name"],
            }
        return None


def _record_free_alt_pairing(
    paid_repo:  dict,
    alt_repo:   dict,
    paid_label: str,
    skill_name: str,
    quality:    float,
) -> None:
    """Write a knowledge entry linking the paid repo to its free alternative."""
    try:
        import agents.github_sync as gs
        paid_fn = paid_repo["full_name"]
        alt_fn  = alt_repo["full_name"]
        slug    = re.sub(r"[^a-z0-9-]", "-",
                         f"free-alt-{alt_fn}".lower().replace("/", "--"))[:60]
        content = (
            f"## Free Alternative Pairing\n\n"
            f"**Paid / quota-limited service detected:** {paid_label} "
            f"([{paid_fn}](https://github.com/{paid_fn}))\n\n"
            f"**Free alternative added:** [{alt_fn}](https://github.com/{alt_fn}) "
            f"⭐ {alt_repo['stars']:,}\n\n"
            f"**Skill created:** `{skill_name}` (quality {quality:.0%})\n\n"
            f"### Why this alternative?\n"
            f"{PAID_TO_FREE.get(alt_repo.get('_alt_for',''), {}).get('label', paid_label)} "
            f"requires paid API access or has strict quota limits. "
            f"**{alt_fn.split('/')[-1]}** provides equivalent or similar capability "
            f"with {alt_repo['stars']:,} stars and is fully open-source / free to self-host.\n\n"
            f"These two skills are complementary — use the free alternative when "
            f"cost or quota is a concern."
        )
        gs.sync_knowledge_entry({
            "category":   "discoveries",
            "slug":       slug,
            "title":      f"Free alt: {alt_fn.split('/')[-1]} → replaces {paid_label}",
            "content":    content,
            "sources":    [
                f"https://github.com/{paid_fn}",
                f"https://github.com/{alt_fn}",
            ],
            "confidence": "verified" if quality >= 0.8 else "inferred",
        })
    except Exception as exc:
        log.warning("Could not record alt pairing in knowledge base: %s", exc)


# ── Dynamic query builder ──────────────────────────────────────────────────────

def _build_dynamic_queries(index: dict) -> list[str]:
    """Derive GitHub search queries from the most common tags and tools in the library."""
    if not index:
        return []

    tool_counter = Counter()
    tag_counter  = Counter()
    for meta in index.values():
        for t in meta.get("tools", []):
            tool_counter[t.lower()] += 1
        for t in meta.get("tags", []):
            tag_counter[t.lower()] += 1

    # Top-5 tools and top-3 tags as individual search queries
    queries = []
    for tool, _ in tool_counter.most_common(5):
        if len(tool) > 2:
            queries.append(f"{tool} python stars:>150 sort:updated")
    for tag, _ in tag_counter.most_common(3):
        if len(tag) > 3:
            queries.append(f"{tag} stars:>200 sort:updated")
    return queries


# ── README → skill extraction ─────────────────────────────────────────────────

def _readme_as_transcript(repo: dict, readme: str) -> str:
    """Format a GitHub repo README as a pseudo-transcript for the extraction pipeline."""
    header = (
        f"[SOURCE: GitHub Repository README — not a video transcript]\n"
        f"Repository: {repo['full_name']}\n"
        f"Stars: {repo['stars']:,}\n"
        f"Language: {repo.get('language') or 'unknown'}\n"
        f"Topics: {', '.join(repo.get('topics', [])) or 'none'}\n"
        f"Description: {repo.get('description') or 'no description'}\n"
        f"\n--- README CONTENT ---\n\n"
    )
    return header + readme


def _knowledge_ctx_for_repo(repo: dict, index: dict) -> str:
    """Build knowledge context: existing skills that overlap with this repo's topics."""
    repo_words = set(
        (repo.get("description") or "").lower().split()
        + [t.lower() for t in repo.get("topics", [])]
        + [repo["name"].lower()]
    )
    candidates = []
    for skill_name, meta in index.items():
        skill_words = set(
            " ".join(meta.get("tools", []) + meta.get("tags", [])).lower().split()
        )
        overlap = len(repo_words & skill_words)
        if overlap >= 2:
            candidates.append((overlap, skill_name, meta))

    if not candidates:
        return ""

    candidates.sort(reverse=True)
    lines = []
    for _, skill_name, meta in candidates[:4]:
        lines.append(
            f"[{skill_name}] {meta.get('title','')} — "
            f"tools: {', '.join(meta.get('tools',[])[:5])} — "
            f"tags: {', '.join(meta.get('tags',[])[:4])}"
        )
    return "\n".join(lines)


def _emit_log(msg: str, kind: str = "info") -> None:
    level = {"info": logging.INFO, "success": logging.INFO,
              "warning": logging.WARNING, "error": logging.ERROR}.get(kind, logging.DEBUG)
    log.log(level, "[discovery] %s", msg)


# ── Badge / noise filter (module-level — reused by baseline and save boundary) ─

_BADGE_STATUS_WORDS: frozenset = frozenset({
    "passing", "failing", "failed", "unknown", "pending",
    "success", "error", "stable", "latest",
})

_BADGE_PATTERNS: list = [
    re.compile(r'^build\s*:?\s*(passing|failing|failed|unknown)$', re.I),
    re.compile(r'^tests?\s*:?\s*(passing|failing|failed)$', re.I),
    re.compile(r'^coverage\s*:?\s*\d+\s*%$', re.I),
    re.compile(r'^\d+\s*%(\s+coverage)?$', re.I),
    re.compile(r'^v?\d+\.\d+[.\d]*(\s*(stable|latest|release))?$', re.I),
    re.compile(r'^(mit|apache|gpl[\s\d.]*|bsd[\s\d.]*|isc)\s*(licen[sc]e)?$', re.I),
    re.compile(r'^licen[sc]e\s*:?\s*(mit|apache|gpl|bsd|isc)[\s\d.]*$', re.I),
    re.compile(r'^python\s+\d+\.\d+\+?$', re.I),
    re.compile(r'^pypi\s+v[\d.]+$', re.I),
    re.compile(r'^npm\s+v[\d.]+$', re.I),
    re.compile(r'^(downloads?|installs?)\s*:?\s*[\d,km]+$', re.I),
    re.compile(r'^(stars?|forks?|watchers?)\s*:?\s*[\d,km]+$', re.I),
]


def _is_badge_like(s: str) -> bool:
    """Return True if *s* matches a badge alt-text or image-caption pattern.

    Intentionally conservative: only rejects strings that match known badge
    formats (status words, coverage / version / licence / metric patterns).
    Does NOT reject strings merely for being short or lowercase.
    """
    t = s.strip()
    if not t:
        return True
    tl = t.lower()
    if tl in _BADGE_STATUS_WORDS:
        return True
    for pat in _BADGE_PATTERNS:
        if pat.match(t):
            return True
    return False


def _filter_badge_steps(steps: list) -> list:
    """Remove badge-like strings from a steps list.

    Safe to call on any incoming steps list regardless of source (AI or
    baseline).  Returns a new list; never mutates the input.
    """
    if not steps:
        return steps if steps is not None else []
    return [s for s in steps if isinstance(s, str) and not _is_badge_like(s)]


# ── Content fingerprint ────────────────────────────────────────────────────────

def _fingerprint(repo: dict) -> str:
    """Stable 16-char SHA256 fingerprint for deduplication."""
    import hashlib
    key = f"{repo['full_name']}:{repo.get('pushed_at','')}:{repo.get('description','')}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


# ── Deterministic baseline generator ──────────────────────────────────────────

def _deterministic_baseline(repo: dict, readme: str) -> dict:
    """
    Build a skill dict purely from repo metadata and README heuristics — no LLM.
    Always succeeds; never raises.  Marked with _baseline: True.
    """
    import re as _re

    full_name = repo["full_name"]
    name      = repo.get("name", full_name.split("/")[-1])
    desc      = repo.get("description", "") or ""
    stars     = repo.get("stars", 0)
    language  = repo.get("language", "") or ""
    topics    = repo.get("topics", []) or []

    # ── Extract tool names from code blocks and inline code ──────────────────
    code_words: list[str] = []
    # Fenced code blocks
    for block in _re.findall(r'```[\w]*\n(.*?)```', readme, _re.DOTALL):
        code_words.extend(block.split())
    # Inline code
    code_words.extend(_re.findall(r'`([^`]{2,40})`', readme))

    # Known tool keywords to detect
    KNOWN_TOOLS = {
        "langchain", "openai", "groq", "gemini", "anthropic", "huggingface",
        "transformers", "pytorch", "tensorflow", "sklearn", "numpy", "pandas",
        "fastapi", "flask", "django", "uvicorn", "pydantic", "docker",
        "kubernetes", "kubectl", "helm", "terraform", "ansible", "redis",
        "postgresql", "sqlite", "mongodb", "elasticsearch", "qdrant", "chroma",
        "faiss", "milvus", "weaviate", "pinecone", "ollama", "vllm",
        "llamaindex", "llama-index", "llama_index", "autogen", "crewai",
        "langgraph", "streamlit", "gradio", "ray", "celery", "kafka",
        "rabbitmq", "prometheus", "grafana", "duckdb", "polars",
    }
    detected_tools: list[str] = []
    seen_tools: set[str] = set()
    readme_lower = readme.lower()
    for tool in KNOWN_TOOLS:
        if tool in readme_lower and tool not in seen_tools:
            detected_tools.append(tool)
            seen_tools.add(tool)
    # Also add topics as tools if they look like tool names
    for t in topics:
        tl = t.lower()
        if tl not in seen_tools and len(tl) > 2:
            detected_tools.append(t)
            seen_tools.add(tl)
    if language and language.lower() not in seen_tools:
        detected_tools.append(language)

    # (badge filter delegated to module-level _is_badge_like / _filter_badge_steps)
   # ── Extract steps from numbered/bulleted lists ──────────────────────────────────────────
    steps: list[str] = []
    for m in _re.finditer(r'(?:^|\n)(?:\d+\.\s+|\*\s+|-\s+)(.{10,120})', readme):
        step = m.group(1).strip()
        if step and not _is_badge_like(step) and len(steps) < 8:
            steps.append(step)

    # ── Heuristic: extract prose from ## Usage / ## Quickstart sections ───────
    if len(steps) < 3:
        section_pattern = _re.compile(
            r'##\s+(?:Usage|Quickstart|Quick\s+Start|Getting\s+Started|Quick\s+Start\s+Guide)'
            r'(.+?)(?=\n##\s|\Z)',
            _re.IGNORECASE | _re.DOTALL,
        )
        for sec_match in section_pattern.finditer(readme):
            section_text = sec_match.group(1)
            # Try list items inside the section first
            sec_steps: list[str] = []
            for m in _re.finditer(r'(?:^|\n)(?:\d+\.\s+|\*\s+|-\s+)(.{10,120})', section_text):
                candidate = m.group(1).strip()
                if candidate and not _is_badge_like(candidate):
                    sec_steps.append(candidate)
            if not sec_steps:
                # Fall back to prose sentences from the section
                for sent in _re.split(r'(?<=[.!?])\s+', section_text.replace('\n', ' ')):
                    sent = sent.strip()
                    if len(sent) >= 20 and not _is_badge_like(sent):
                        sec_steps.append(sent[:120])
                    if len(sec_steps) >= 5:
                        break
            steps.extend(s for s in sec_steps if s not in steps)
            if len(steps) >= 5:
                break

    # ── Paragraph-extraction fallback: use first 5 meaningful sentences ───────
    if len(steps) < 3:
        prose = readme.replace('\n', ' ')
        for sent in _re.split(r'(?<=[.!?])\s+', prose):
            sent = sent.strip()
            # Skip heading lines, code-like strings, badge noise, and very short fragments
            if (len(sent) >= 25
                    and not sent.startswith('#')
                    and not sent.startswith('```')
                    and not _is_badge_like(sent)
                    and sent not in steps):
                steps.append(sent[:120])
            if len(steps) >= 5:
                break

    # ── Description from first paragraph ─────────────────────────────────────
    paragraphs = [p.strip() for p in _re.split(r'\n{2,}', readme) if p.strip()]
    first_para = ""
    for p in paragraphs[:5]:
        if not p.startswith("#") and len(p) > 30:
            first_para = p[:300]
            break
    description = desc or first_para or f"Skills and patterns from {full_name} ({stars:,} ⭐)"

    # ── Tags from topics + keywords ───────────────────────────────────────────
    tags = list(dict.fromkeys(
        [t.lower()[:30] for t in topics[:5]]
        + ([language.lower()] if language else [])
        + (["ai", "llm"] if any(w in readme_lower for w in ["llm", "language model", "ai"]) else [])
    ))[:8]

    # ── Skill name ────────────────────────────────────────────────────────────
    skill_name = _re.sub(r'[^a-z0-9]+', '_', name.lower())[:50].strip('_')
    if not skill_name:
        skill_name = "github_skill_" + full_name.replace("/", "_").lower()[:30]

    # ── Markdown body ─────────────────────────────────────────────────────────
    steps_md = "\n".join(f"- {s}" for s in steps) if steps else "- See README for detailed steps."
    tools_md = ", ".join(detected_tools[:12]) or "See README"
    readme_excerpt = readme[:2000].strip()
    skill_markdown = (
        f"# {name}\n\n"
        f"## Description\n\n{description}\n\n"
        f"## Steps\n\n{steps_md}\n\n"
        f"## Tools\n\n{tools_md}\n\n"
        f"## Source\n\n"
        f"GitHub: [{full_name}](https://github.com/{full_name}) ⭐ {stars:,}\n\n"
        f"## README Excerpt\n\n{readme_excerpt}\n"
    )

    return {
        "action":          "create",
        "enhance_target":  None,
        "skill_name":      skill_name,
        "title":           name.replace("-", " ").replace("_", " ").title(),
        "description":     description[:400],
        "steps":           steps or [f"Explore the {name} repository", "Follow setup instructions in the README", "Run the examples"],
        "tools":           detected_tools[:15],
        "python_packages": [],
        "concepts":        tags[:5],
        "tags":            tags,
        "related_skills":  [],
        "skill_markdown":  skill_markdown,
        "_baseline":       True,
        "_baseline_reason": "ai_unavailable",
    }


def _extract_from_repo(repo: dict, readme: str, index: dict) -> dict | None:
    """
    Run the full Arena extraction on a README.
    Returns the merged skill dict, or None if both lenses fail.
    Never raises from provider failures — callers check for None.
    """
    import app as _a
    transcript    = _readme_as_transcript(repo, readme)
    knowledge_ctx = _knowledge_ctx_for_repo(repo, index)
    github_ctx    = (
        f"[{repo['full_name']}] stars={repo['stars']} "
        f"lang={repo.get('language','')} "
        f"topics={','.join(repo.get('topics',[]))}"
    )

    import agents.provider_router as provider_router

    skill_a = skill_b = None
    import json as _json

    # Run lenses sequentially (not in parallel) so both don't hammer the same
    # provider simultaneously.  The 5-second gap lets rate-limit backouts clear.
    base_educator = _a._build_prompt(transcript, knowledge_ctx, "")
    preamble_educator = (
        "You are Fieldnote's EDUCATOR AI. Your lens is conceptual clarity, "
        "thorough descriptions, and how this skill connects to others in the library.\n\n"
    )
    try:
        raw_a = provider_router.call_llm_smart(
            preamble_educator + base_educator, max_tokens=4000, json_mode=True,
            emit_fn=_emit_log)
        skill_a = _json.loads(raw_a)
    except Exception as e:
        log.warning("Educator-lens extraction failed (all providers tried): %s", e)

    time.sleep(5)  # allow short-lived rate-limit backouts to expire before second call

    base_practitioner = _a._build_prompt(transcript, knowledge_ctx, "")
    preamble_practitioner = (
        "You are Fieldnote's PRACTITIONER AI. Your lens is specific actionable steps "
        "a developer can follow immediately, and every concrete tool, command, "
        "and library mentioned in the transcript.\n\n"
    )
    try:
        raw_b = provider_router.call_llm_smart(
            preamble_practitioner + base_practitioner, max_tokens=4000, json_mode=True,
            emit_fn=_emit_log)
        skill_b = _json.loads(raw_b)
    except Exception as e:
        log.warning("Practitioner-lens extraction failed (all providers tried): %s", e)

    if not skill_a and not skill_b:
        log.warning("Both lens extractions returned None for %s — will use baseline fallback",
                    repo["full_name"])
        return None   # callers check for None and fall through to baseline

    merged = _a._judge_arena(skill_a, skill_b, github_ctx, _emit_log)
    return merged


def _upgrade_baseline_to_ai(skill_dict: dict, repo: dict, index: dict,
                             skill_name: str) -> None:
    """
    Overlay AI-enriched fields on top of an existing baseline skill file.
    Updates the file and the discovery log entry.
    """
    import app as _a
    try:
        # Strip badge-noise steps before writing so that AI responses that echo
        # badge strings (e.g. "Build passing", "Coverage 92%") do not pollute
        # the enriched skill.  We work on a shallow copy to avoid mutating the
        # caller's dict.
        skill_dict = dict(skill_dict)
        if "steps" in skill_dict:
            skill_dict["steps"] = _filter_badge_steps(skill_dict.get("steps") or [])

        # Re-save with the AI-enriched content
        _a._save_skill(
            skill          = skill_dict,
            skill_name     = skill_name,
            url            = repo["html_url"],
            meta           = {"title": repo["full_name"], "channel": "GitHub", "duration": 0},
            method         = "github_readme_ai_enriched",
            word_count     = len(repo.get("_readme_words", [])),
            video_id       = repo["full_name"],
            action         = skill_dict.get("action", "enhance"),
            github_results = [],
            mcp_connections = [],
        )
        log.info("Baseline upgraded to AI for %s → skill '%s'", repo["full_name"], skill_name)
    except Exception as exc:
        log.warning("_upgrade_baseline_to_ai failed for %s: %s", repo["full_name"], exc)


# ── Save wrapper ───────────────────────────────────────────────────────────────

def _save_discovered_skill(skill: dict, repo: dict, index: dict) -> tuple[str, str]:
    """Persist the extracted skill and return (skill_name, action)."""
    import app as _a

    # Strip badge noise from steps before any further processing so that
    # AI responses that echo baseline badge strings are cleaned at the boundary.
    _STEPS_MIN = 3  # must match _gate_steps minimum in skill_quality.py
    if "steps" in skill:
        raw_steps = skill.get("steps") or []
        filtered = _filter_badge_steps(raw_steps)
        if raw_steps and not filtered:
            log.warning(
                "_save_discovered_skill: all %d step(s) were badge strings and "
                "were stripped for '%s' — post-filter steps is empty; "
                "quality gate will flag this skill as too_few_steps",
                len(raw_steps),
                skill.get("skill_name") or repo.get("full_name", "?"),
            )
        # Post-filter quality gate enforcement: if badge filtering caused the step
        # count to drop from gate-passing (≥ minimum) to below the minimum, raise
        # so the caller can preserve the baseline rather than writing a skill that
        # would have been DENY'd if quality_gate had seen the post-filter list.
        if len(raw_steps) >= _STEPS_MIN and len(filtered) < _STEPS_MIN:
            raise ValueError(
                f"Post-badge-filter steps gate failed for "
                f"'{skill.get('skill_name') or repo.get('full_name', '?')}': "
                f"badge filtering reduced {len(raw_steps)} steps to {len(filtered)} "
                f"(minimum is {_STEPS_MIN}); caller should preserve the baseline"
            )
        skill = {**skill, "steps": filtered}

    action         = skill.get("action", "create")
    enhance_target = skill.get("enhance_target")
    skill_name     = _a._compute_skill_name(skill, action, enhance_target, index)

    # For enhance: load existing markdown so the pipeline can merge properly
    existing_md = _a._read_existing_markdown(skill_name) if action == "enhance" else ""
    if action == "enhance" and existing_md:
        # Re-run ChatGPT with existing content as context, then re-judge
        transcript    = _readme_as_transcript(repo, "")  # blank readme for re-run (already merged)
        knowledge_ctx = _knowledge_ctx_for_repo(repo, index)
        github_ctx    = f"[{repo['full_name']}] stars={repo['stars']}"
        try:
            import app as _a2
            import agents.provider_router as _pr
            base2    = _a2._build_prompt(transcript, knowledge_ctx, existing_md)
            preamble2 = (
                "You are Fieldnote's EDUCATOR AI. Your lens is conceptual clarity, "
                "thorough descriptions, and how this skill connects to others in the library.\n\n"
            )
            import json as _json2
            raw2 = _pr.call_llm_smart(preamble2 + base2, max_tokens=4000, json_mode=True,
                                       emit_fn=_emit_log)
            skill_a2 = _json2.loads(raw2)
            skill_b2 = skill  # use the original merged as the "B" candidate
            skill    = _a2._judge_arena(skill_a2, skill_b2, github_ctx, _emit_log)
            action   = skill.get("action", "enhance")
            skill_name = _a2._compute_skill_name(skill, action,
                                                  skill.get("enhance_target"), index)
        except Exception as e:
            log.warning("Enhance re-run failed (%s) — using first-pass result", e)

    # Re-apply badge filter immediately before writing: the enhance re-judge
    # path above may have reassigned `skill` from _judge_arena, which can
    # reintroduce badge-like strings.  A second pass here guarantees every
    # ingestion path (create, enhance first-pass, enhance re-judge) is clean.
    if "steps" in skill:
        raw_steps2 = skill.get("steps") or []
        filtered2  = _filter_badge_steps(raw_steps2)
        if raw_steps2 and not filtered2:
            log.warning(
                "_save_discovered_skill (post-rejudge): all %d step(s) were badge "
                "strings and were stripped for '%s' — post-filter steps is empty; "
                "quality gate will flag this skill as too_few_steps",
                len(raw_steps2),
                skill.get("skill_name") or repo.get("full_name", "?"),
            )
        # Second enforcement pass: the enhance re-judge path may have introduced
        # a new badge-dominated steps list.  Enforce again so the rejudge path
        # cannot bypass the gate either.
        if len(raw_steps2) >= _STEPS_MIN and len(filtered2) < _STEPS_MIN:
            raise ValueError(
                f"Post-rejudge badge-filter steps gate failed for "
                f"'{skill.get('skill_name') or repo.get('full_name', '?')}': "
                f"badge filtering reduced {len(raw_steps2)} steps to {len(filtered2)} "
                f"(minimum is {_STEPS_MIN}); caller should preserve the baseline"
            )
        skill = {**skill, "steps": filtered2}

    synthetic_meta = {
        "title":    repo["full_name"],
        "channel":  "GitHub",
        "duration": 0,
    }
    _a._save_skill(
        skill          = skill,
        skill_name     = skill_name,
        url            = repo["html_url"],
        meta           = synthetic_meta,
        method         = "github_readme",
        word_count     = len(repo.get("_readme_words", [])),
        video_id       = repo["full_name"],    # unique ID in history
        action         = action,
        github_results = [
            {
                "full_name": repo["full_name"],
                "url":       repo["html_url"],
                "stars":     repo["stars"],
                "is_mcp":    "mcp" in " ".join(repo.get("topics", [])).lower()
                              or "model-context-protocol" in repo.get("description","").lower(),
                "language":  repo.get("language", ""),
            }
        ],
        mcp_connections = [],
    )
    return skill_name, action


# ── Error→backlog migration (runs once per app restart) ───────────────────────

_migration_ran = False

def _migrate_errors_to_backlog() -> int:
    """
    Convert all action:"error" discovery log entries into enrichment backlog entries.
    Runs once per app restart (guarded by migration_done flag in enrichment state).
    Returns the number of entries migrated.
    """
    global _migration_ran
    if _migration_ran:
        return 0
    _migration_ran = True

    try:
        import agents.discovery_enrichment as de
        if de.migration_done():
            return 0

        disc_log = load_discovery_log()
        errors = [
            (fn, v) for fn, v in disc_log.items()
            if v.get("action") == "error"
        ]
        if not errors:
            de.set_migration_done()
            return 0

        # Sort by stars descending (highest-value repos get priority)
        errors.sort(key=lambda x: x[1].get("stars", 0), reverse=True)
        migrated = 0
        for fn, v in errors:
            de.enqueue(fn, v.get("stars", 0))
            # Update log entry to show it's in the recovery backlog
            disc_log[fn] = {
                **v,
                "action":           "baseline",
                "enrichment_queued": True,
                "_baseline":         True,
                "_baseline_reason":  "migrated_from_error",
                "skill_name":        v.get("skill_name"),  # may be None
            }
            migrated += 1

        save_discovery_log(disc_log)
        de.set_migration_done()
        log.info("Discovery: migrated %d error entries → enrichment backlog", migrated)
        return migrated
    except Exception as exc:
        log.warning("Error-to-backlog migration failed: %s", exc)
        return 0


# Migration is triggered by app.py after full bootstrap (SKILLS_DIR guaranteed).
# Do NOT call _migrate_errors_to_backlog() here — app may not be initialised yet.


# ── Main job ───────────────────────────────────────────────────────────────────

def discover_and_learn() -> dict:
    """
    Search GitHub, extract skills from READMEs, and save them to Fieldnote.
    Persist-first: every repo gets a baseline skill immediately, even if AI fails.
    Called by the scheduler every 2 hours.
    Returns a result summary dict.
    """
    import app as _a
    import agents.skill_quality as sq
    import agents.discovery_enrichment as de

    log.info("GitHub discovery starting …")
    index     = _a.load_index()
    disc_log  = load_discovery_log()

    # 1. Build queries
    queries = list(TRENDING_QUERIES) + _build_dynamic_queries(index)
    log.info("Discovery: %d queries", len(queries))

    # 2. Search + collect candidates (dedup by full_name)
    seen:       set[str]   = set()
    candidates: list[dict] = []

    for query in queries:
        if len(candidates) >= BATCH_SIZE * 3:  # generous buffer before filtering
            break
        try:
            repos = _search_repos(query)
            for repo in repos:
                fn = repo["full_name"]
                if fn not in seen and not _already_processed(fn, disc_log):
                    seen.add(fn)
                    candidates.append(repo)
        except RuntimeError as e:
            log.error("Search failed (%s) — stopping", e)
            break
        except Exception as e:
            log.warning("Query '%s' failed: %s", query, e)
        time.sleep(0.5)  # gentle rate limiting

    log.info("Discovery: %d new candidates after dedup/filter", len(candidates))

    if not candidates:
        return {"repos_found": 0, "skills_created": 0, "skills_enhanced": 0,
                "baseline": 0, "errors": 0, "message": "No new repos to process"}

    # 3. Sort by stars descending, take top BATCH_SIZE
    candidates.sort(key=lambda r: r["stars"], reverse=True)
    batch = candidates[:BATCH_SIZE]

    created = enhanced = baseline_count = errors = 0
    results_detail = []

    # Check if any free provider is available before trying AI
    ai_available = de.any_free_provider_available()
    if not ai_available:
        log.warning("Discovery: no free providers available — all repos will get baseline skills")

    for repo in batch:
        fn = repo["full_name"]
        log.info("Discovery: processing %s (%d ⭐)", fn, repo["stars"])

        try:
            # ── Fetch README ─────────────────────────────────────────────────
            readme = _fetch_readme(repo["owner"], repo["name"])
            if not readme or len(readme) < 100:
                log.info("Discovery: %s has no/tiny README — skipping", fn)
                disc_log[fn] = {
                    "processed_at": _now_iso(),
                    "skill_name":   None,
                    "action":       "skipped_no_readme",
                    "stars":        repo["stars"],
                }
                continue

            repo["_readme_words"] = readme.split()

            # ── Fingerprint deduplication ────────────────────────────────────
            fp = _fingerprint(repo)
            existing_entry = disc_log.get(fn, {})
            if existing_entry.get("fingerprint") == fp and existing_entry.get("skill_name"):
                log.info("Discovery: %s fingerprint unchanged — skipped duplicate", fn)
                disc_log[fn] = {**existing_entry, "action": "skipped_duplicate",
                                 "processed_at": _now_iso()}
                results_detail.append({"repo": fn, "result": "skipped_duplicate"})
                continue

            # ── Step 1: Save baseline skill IMMEDIATELY (persist-first) ──────
            baseline = _deterministic_baseline(repo, readme)
            baseline_skill_name, baseline_action = _save_discovered_skill(
                baseline, repo, _a.load_index()
            )
            index = _a.load_index()

            # Write baseline entry to discovery log
            disc_log[fn] = {
                "processed_at":     _now_iso(),
                "skill_name":       baseline_skill_name,
                "action":           "baseline",
                "stars":            repo["stars"],
                "fingerprint":      fp,
                "enrichment_queued": True,
                "_baseline":        True,
                "_baseline_reason": "ai_unavailable" if not ai_available else "persist_first",
            }
            save_discovery_log(disc_log)   # persist immediately — guaranteed

            # Enqueue for AI enrichment
            de.enqueue(fn, repo["stars"], fingerprint=fp)
            log.info("Discovery: baseline saved for %s → '%s', queued for enrichment",
                     fn, baseline_skill_name)

            # ── Step 2: Attempt AI enrichment now (if providers available) ───
            ai_skill = None
            if ai_available:
                ai_skill = _extract_from_repo(repo, readme, index)

            if ai_skill is not None:
                # AI succeeded — quality gate on AI result
                qr = sq.quality_gate(ai_skill)
                log.info("Discovery: %s → quality %s %.0f%%", fn,
                         qr.decision.value, qr.score * 100)

                if qr.decision == sq.QualityDecision.DENY:
                    disc_log[fn] = {
                        **disc_log.get(fn, {}),
                        "processed_at":      _now_iso(),
                        "action":            "quality_denied",
                        "quality_score":     round(qr.score, 2),
                        "enrichment_queued": False,
                    }
                    de.mark_succeeded({"full_name": fn})
                    results_detail.append({"repo": fn, "result": "quality_denied",
                                           "score": round(qr.score, 2)})
                    continue

                # Overlay AI result (may change skill_name)
                skill_name, action = _save_discovered_skill(ai_skill, repo, index)
                index = _a.load_index()

                # Sync to GitHub
                try:
                    import agents.github_sync as gs
                    gs.sync_skill(skill_name, _a._read_existing_markdown(skill_name), index)
                except Exception as e:
                    log.warning("GitHub sync failed after AI save: %s", e)

                # ── Paid-service detection → free alternative ────────────────
                readme_text = " ".join(repo.get("_readme_words", []))
                paid_keys   = _detect_paid_services(repo, ai_skill, readme_text)
                alt_results: list[dict] = []

                if paid_keys:
                    log.info("Discovery: %s uses paid services: %s", fn, paid_keys)
                    for paid_key in paid_keys[:2]:
                        alt_repo = _find_best_free_alternative(paid_key, disc_log)
                        if alt_repo:
                            seen.add(alt_repo["full_name"])
                            alt_result = _process_free_alternative(
                                alt_repo, repo, paid_key, disc_log, index
                            )
                            if alt_result:
                                alt_results.append(alt_result)
                                index = _a.load_index()
                                if alt_result.get("action") == "enhance":
                                    enhanced += 1
                                else:
                                    created += 1
                            time.sleep(2)

                # Update log with AI-enriched state
                disc_log[fn] = {
                    "processed_at":      _now_iso(),
                    "skill_name":        skill_name,
                    "action":            action,
                    "stars":             repo["stars"],
                    "fingerprint":       fp,
                    "quality_score":     round(qr.score, 2),
                    "quality_decision":  qr.decision.value,
                    "paid_services":     paid_keys,
                    "free_alts_added":   [r["skill"] for r in alt_results],
                    "enrichment_queued": False,
                    "_baseline":         False,
                }
                de.mark_succeeded({"full_name": fn})

                if action == "enhance":
                    enhanced += 1
                    log.info("Discovery: enhanced '%s' from %s", skill_name, fn)
                else:
                    created += 1
                    log.info("Discovery: created  '%s' from %s", skill_name, fn)

                result_entry = {
                    "repo":    fn,
                    "skill":   skill_name,
                    "action":  action,
                    "stars":   repo["stars"],
                    "quality": round(qr.score, 2),
                }
                if paid_keys:
                    result_entry["paid_services"]   = paid_keys
                    result_entry["free_alts_added"] = [r["skill"] for r in alt_results]
                results_detail.append(result_entry)
                results_detail.extend(alt_results)

            else:
                # AI failed — baseline already saved; leave enrichment_queued: True
                baseline_count += 1
                results_detail.append({
                    "repo":   fn,
                    "skill":  baseline_skill_name,
                    "action": "baseline",
                    "stars":  repo["stars"],
                })
                log.info("Discovery: baseline-only for %s (AI unavailable)", fn)

        except Exception as exc:
            # This should rarely happen now — even AI failure doesn't raise
            errors += 1
            log.error("Discovery: unexpected failure on %s → %s", fn, exc)
            # If we somehow got here without a baseline, try to write one
            if not disc_log.get(fn, {}).get("skill_name"):
                disc_log[fn] = {
                    "processed_at":     _now_iso(),
                    "skill_name":       None,
                    "action":           "baseline",
                    "enrichment_queued": True,
                    "error":            str(exc)[:200],
                    "stars":            repo.get("stars", 0),
                    "_baseline":        True,
                    "_baseline_reason": "exception_fallback",
                }
                try:
                    de.enqueue(fn, repo.get("stars", 0))
                except Exception:
                    pass
            results_detail.append({"repo": fn, "result": "error", "error": str(exc)[:120]})

        save_discovery_log(disc_log)   # save after each repo
        time.sleep(3)   # pause between repos to be a polite API citizen

    save_discovery_log(disc_log)

    summary = {
        "repos_searched":  len(candidates),
        "repos_processed": len(batch),
        "skills_created":  created,
        "skills_enhanced": enhanced,
        "baseline":        baseline_count,
        "errors":          errors,
        "detail":          results_detail,
    }
    log.info("Discovery complete: %s", summary)

    # Write a summary discovery entry to assistant_knowledge/ so ChatGPT sees it
    if created + enhanced > 0:
        _record_cycle_to_knowledge(summary, results_detail)

    return summary


def _record_cycle_to_knowledge(summary: dict, detail: list) -> None:
    """Persist each successfully discovered skill into assistant_knowledge/discoveries/."""
    try:
        import agents.github_sync as gs
        for item in detail:
            if "skill" not in item:
                continue
            repo  = item["repo"]
            skill = item["skill"]
            action = item.get("action", "create")
            stars  = item.get("stars", 0)
            quality = item.get("quality", 0)
            slug   = re.sub(r"[^a-z0-9-]", "-", repo.lower().replace("/", "--"))[:60]
            content = (
                f"## GitHub Discovery\n\n"
                f"**Repository:** [{repo}](https://github.com/{repo})\n"
                f"**Stars:** {stars:,}\n"
                f"**Action:** {action}\n"
                f"**Skill created:** `{skill}`\n"
                f"**Quality score:** {quality:.0%}\n\n"
                f"This skill was autonomously discovered and extracted from the repository README "
                f"by Fieldnote's GitHub Discovery Agent."
            )
            gs.sync_knowledge_entry({
                "category":   "discoveries",
                "slug":       slug,
                "title":      f"Discovered: {repo}",
                "content":    content,
                "sources":    [f"https://github.com/{repo}"],
                "confidence": "verified" if quality >= 0.8 else "inferred",
            })
            log.info("Discovery: recorded knowledge entry for %s", repo)
    except Exception as exc:
        log.warning("Could not write discovery to knowledge base: %s", exc)


# ── Discovery log API helpers ─────────────────────────────────────────────────

def discovery_stats() -> dict:
    """Return a summary suitable for the /api/discovery/stats endpoint."""
    disc_log = load_discovery_log()
    total    = len(disc_log)
    by_action: Counter = Counter(v.get("action", "unknown") for v in disc_log.values())

    # New state tracking
    baseline_count         = by_action.get("baseline", 0)
    enrichment_queued_count = sum(
        1 for v in disc_log.values() if v.get("enrichment_queued", False)
    )
    enriched_count         = by_action.get("enriched", 0) + by_action.get("enhanced_from_baseline", 0)
    skipped_dup_count      = by_action.get("skipped_duplicate", 0)

    # Timestamps
    last_baseline_at  = None
    last_enrichment_at = None
    for v in disc_log.values():
        if v.get("action") == "baseline" and v.get("processed_at"):
            if not last_baseline_at or v["processed_at"] > last_baseline_at:
                last_baseline_at = v["processed_at"]
        if v.get("enriched_at"):
            if not last_enrichment_at or v["enriched_at"] > last_enrichment_at:
                last_enrichment_at = v["enriched_at"]

    # Backlog depth
    try:
        import agents.discovery_enrichment as de
        backlog_depth = de.queue_depth()
        enrichment_paused = de.is_paused()
    except Exception:
        backlog_depth = 0
        enrichment_paused = False

    # Recent discoveries — include all non-skipped entries with or without skill_name
    recent = sorted(
        [{"repo": k, **v} for k, v in disc_log.items()
         if v.get("action") not in ("skipped_no_readme", "skipped_duplicate")],
        key=lambda x: x.get("processed_at", ""),
        reverse=True,
    )[:15]

    return {
        "total_repos_seen":      total,
        "skills_created":        by_action.get("create", 0),
        "skills_enhanced":       by_action.get("enhance", 0),
        "quality_denied":        by_action.get("quality_denied", 0),
        "errors":                by_action.get("error", 0),   # legacy — should be 0 after migration
        "baseline_count":        baseline_count,
        "enrichment_queued_count": enrichment_queued_count,
        "enriched_count":        enriched_count,
        "skipped_duplicate_count": skipped_dup_count,
        "backlog_depth":         backlog_depth,
        "enrichment_paused":     enrichment_paused,
        "last_baseline_at":      last_baseline_at,
        "last_enrichment_at":    last_enrichment_at,
        "recent_discoveries":    recent,
    }


def discovery_reliability() -> dict:
    """Return provider availability + queue stats for the reliability panel."""
    try:
        import agents.provider_router as pr
        import agents.discovery_enrichment as de
        providers = {}
        for name in ("groq", "gemini", "openai", "huggingface"):
            with pr._lock:
                s = pr._status.get(name, {})
                state = s.get("state", "no_key")
                until = s.get("until", 0.0)
            cooldown_secs = max(0, int(until - pr._now())) if until > 0 else 0
            providers[name] = {
                "state":        state,
                "available":    pr._is_available(name),
                "cooldown_secs": cooldown_secs,
            }
        items = de.load_queue()
        return {
            "providers":        providers,
            "backlog_depth":    len(items),
            "enrichment_paused": de.is_paused(),
            "queue_items":      [
                {
                    "full_name":     q["full_name"],
                    "stars":         q.get("stars", 0),
                    "retry_count":   q.get("retry_count", 0),
                    "next_attempt_at": q.get("next_attempt_at", ""),
                }
                for q in sorted(items, key=lambda x: x.get("stars", 0), reverse=True)[:20]
            ],
        }
    except Exception as exc:
        return {"error": str(exc)}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
