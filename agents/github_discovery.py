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
from concurrent.futures import ThreadPoolExecutor, as_completed
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
            gs.sync_skill(skill_name, _a.SKILLS_DIR, index)
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
        log.error("Alt extraction failed for %s: %s", fn, exc)
        disc_log[fn] = {
            "processed_at": _now_iso(),
            "skill_name":   None,
            "action":       "error",
            "error":        str(exc)[:200],
            "stars":        alt_repo.get("stars", 0),
            "alt_for":      paid_repo["full_name"],
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


def _extract_from_repo(repo: dict, readme: str, index: dict) -> dict:
    """Run the full Arena extraction on a README and return the merged skill dict."""
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
            preamble_educator + base_educator, max_tokens=4000, json_mode=True)
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
            preamble_practitioner + base_practitioner, max_tokens=4000, json_mode=True)
        skill_b = _json.loads(raw_b)
    except Exception as e:
        log.warning("Practitioner-lens extraction failed (all providers tried): %s", e)

    if not skill_a and not skill_b:
        raise ValueError("Both lens extractions failed for " + repo["full_name"]
                         + " — all AI providers may be quota-exhausted")

    merged = _a._judge_arena(skill_a, skill_b, github_ctx, _emit_log)
    return merged


# ── Save wrapper ───────────────────────────────────────────────────────────────

def _save_discovered_skill(skill: dict, repo: dict, index: dict) -> tuple[str, str]:
    """Persist the extracted skill and return (skill_name, action)."""
    import app as _a

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
            raw2 = _pr.call_llm_smart(preamble2 + base2, max_tokens=4000, json_mode=True)
            skill_a2 = _json2.loads(raw2)
            skill_b2 = skill  # use the original merged as the "B" candidate
            skill    = _a2._judge_arena(skill_a2, skill_b2, github_ctx, _emit_log)
            action   = skill.get("action", "enhance")
            skill_name = _a2._compute_skill_name(skill, action,
                                                  skill.get("enhance_target"), index)
        except Exception as e:
            log.warning("Enhance re-run failed (%s) — using first-pass result", e)

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


# ── Main job ───────────────────────────────────────────────────────────────────

def discover_and_learn() -> dict:
    """
    Search GitHub, extract skills from READMEs, and save them to Fieldnote.
    Called by the scheduler every 2 hours.
    Returns a result summary dict.
    """
    import app as _a
    import agents.skill_quality as sq

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
                "errors": 0, "message": "No new repos to process"}

    # 3. Sort by stars descending, take top BATCH_SIZE
    candidates.sort(key=lambda r: r["stars"], reverse=True)
    batch = candidates[:BATCH_SIZE]

    created = enhanced = errors = 0
    results_detail = []

    for repo in batch:
        fn = repo["full_name"]
        log.info("Discovery: processing %s (%d ⭐)", fn, repo["stars"])

        try:
            # Fetch README
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

            # Extract skill
            skill = _extract_from_repo(repo, readme, index)

            # Quality gate
            qr = sq.quality_gate(skill)
            log.info("Discovery: %s → quality %s %.0f%%", fn,
                     qr.decision.value, qr.score * 100)

            if qr.decision == sq.QualityDecision.DENY:
                disc_log[fn] = {
                    "processed_at":   _now_iso(),
                    "skill_name":     None,
                    "action":         "quality_denied",
                    "stars":          repo["stars"],
                    "quality_score":  round(qr.score, 2),
                }
                results_detail.append({"repo": fn, "result": "quality_denied",
                                       "score": round(qr.score, 2)})
                continue

            # Save
            skill_name, action = _save_discovered_skill(skill, repo, index)
            index = _a.load_index()  # refresh after save

            # Sync to GitHub
            try:
                import agents.github_sync as gs
                gs.sync_skill(skill_name, _a.SKILLS_DIR, index)
            except Exception as e:
                log.warning("GitHub sync failed after discovery save: %s", e)

            # ── Paid-service detection → free alternative ────────────────────
            readme_text = " ".join(repo.get("_readme_words", []))
            paid_keys   = _detect_paid_services(repo, skill, readme_text)
            alt_results : list[dict] = []

            if paid_keys:
                log.info("Discovery: %s uses paid services: %s — finding free alts",
                         fn, paid_keys)
                for paid_key in paid_keys[:2]:   # max 2 paid services per repo
                    alt_repo = _find_best_free_alternative(paid_key, disc_log)
                    if alt_repo:
                        seen.add(alt_repo["full_name"])  # don't re-process in main loop
                        alt_result = _process_free_alternative(
                            alt_repo, repo, paid_key, disc_log, index
                        )
                        if alt_result:
                            alt_results.append(alt_result)
                            index = _a.load_index()       # keep index fresh
                            if alt_result.get("action") == "enhance":
                                enhanced += 1
                            else:
                                created += 1
                        time.sleep(2)

            # Update log
            disc_log[fn] = {
                "processed_at":      _now_iso(),
                "skill_name":        skill_name,
                "action":            action,
                "stars":             repo["stars"],
                "quality_score":     round(qr.score, 2),
                "quality_decision":  qr.decision.value,
                "paid_services":     paid_keys,
                "free_alts_added":   [r["skill"] for r in alt_results],
            }

            if action == "enhance":
                enhanced += 1
                log.info("Discovery: enhanced '%s' from %s", skill_name, fn)
            else:
                created += 1
                log.info("Discovery: created  '%s' from %s", skill_name, fn)

            result_entry = {
                "repo":      fn,
                "skill":     skill_name,
                "action":    action,
                "stars":     repo["stars"],
                "quality":   round(qr.score, 2),
            }
            if paid_keys:
                result_entry["paid_services"]  = paid_keys
                result_entry["free_alts_added"] = [r["skill"] for r in alt_results]
            results_detail.append(result_entry)
            results_detail.extend(alt_results)

        except Exception as exc:
            errors += 1
            log.error("Discovery: failed on %s → %s", fn, exc)
            disc_log[fn] = {
                "processed_at": _now_iso(),
                "skill_name":   None,
                "action":       "error",
                "error":        str(exc)[:200],
                "stars":        repo.get("stars", 0),
            }
            results_detail.append({"repo": fn, "result": "error", "error": str(exc)[:120]})

        time.sleep(3)   # pause between repos to be a polite API citizen

    save_discovery_log(disc_log)

    summary = {
        "repos_searched":  len(candidates),
        "repos_processed": len(batch),
        "skills_created":  created,
        "skills_enhanced": enhanced,
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
    recent   = sorted(
        [{"repo": k, **v} for k, v in disc_log.items() if v.get("skill_name")],
        key=lambda x: x.get("processed_at", ""),
        reverse=True,
    )[:10]
    return {
        "total_repos_seen":  total,
        "skills_created":    by_action.get("create", 0),
        "skills_enhanced":   by_action.get("enhance", 0),
        "quality_denied":    by_action.get("quality_denied", 0),
        "errors":            by_action.get("error", 0),
        "recent_discoveries": recent,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
