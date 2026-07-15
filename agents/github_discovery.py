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
        return age.days < RECHECK_DAYS
    except Exception:
        return False


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
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="fn-disc") as pool:
        # Use provider_router for automatic quota fallback in both passes
        def _educator_pass():
            base     = _a._build_prompt(transcript, knowledge_ctx, "")
            preamble = (
                "You are Fieldnote's EDUCATOR AI. Your lens is conceptual clarity, "
                "thorough descriptions, and how this skill connects to others in the library.\n\n"
            )
            raw, _prov = provider_router.call_llm_smart(preamble + base, max_tokens=4000, json_mode=True)
            import json as _json
            return _json.loads(raw)

        def _practitioner_pass():
            base     = _a._build_prompt(transcript, knowledge_ctx, "")
            preamble = (
                "You are Fieldnote's PRACTITIONER AI. Your lens is specific actionable steps "
                "a developer can follow immediately, and every concrete tool, command, "
                "and library mentioned in the transcript.\n\n"
            )
            raw, _prov = provider_router.call_llm_smart(preamble + base, max_tokens=4000, json_mode=True)
            import json as _json
            return _json.loads(raw)

        fa = pool.submit(_educator_pass)
        fb = pool.submit(_practitioner_pass)
        try:
            skill_a = fa.result(timeout=90)
        except Exception as e:
            log.warning("Educator extraction failed: %s", e)
        try:
            skill_b = fb.result(timeout=90)
        except Exception as e:
            log.warning("Practitioner extraction failed: %s", e)

    if not skill_a and not skill_b:
        raise ValueError("Both extractions failed for " + repo["full_name"])

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
            raw2, _prov2 = _pr.call_llm_smart(preamble2 + base2, max_tokens=4000, json_mode=True)
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

            # Update log
            disc_log[fn] = {
                "processed_at":   _now_iso(),
                "skill_name":     skill_name,
                "action":         action,
                "stars":          repo["stars"],
                "quality_score":  round(qr.score, 2),
                "quality_decision": qr.decision.value,
            }

            if action == "enhance":
                enhanced += 1
                log.info("Discovery: enhanced '%s' from %s", skill_name, fn)
            else:
                created += 1
                log.info("Discovery: created  '%s' from %s", skill_name, fn)

            results_detail.append({
                "repo":    fn,
                "skill":   skill_name,
                "action":  action,
                "stars":   repo["stars"],
                "quality": round(qr.score, 2),
            })

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
    return summary


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
