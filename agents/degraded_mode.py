"""
degraded_mode.py — deterministic (no-LLM) skill generation and judge fallback.

When all AI providers are exhausted the pipeline calls:
  • build_degraded_skill()         → produce a minimal but valid skill dict from
                                     transcript + metadata using regex patterns
  • deterministic_judge_merge()    → pure Python union of two extraction outputs;
                                     no LLM call, never aborts

Both functions return dicts that pass pipeline_guard.sanitize() and can be
saved directly with _save_skill().  They are marked with:
  _degraded = True
  _pending_enhancement = True
so the scheduler can pick them up for a proper LLM pass later.
"""

from __future__ import annotations

import re
import logging
import uuid
from typing import Optional

log = logging.getLogger("fieldnote.degraded_mode")

# ── Regex patterns for keyword / tool extraction ──────────────────────────────

# Common tools, frameworks, and CLI names
_TOOL_PATTERN = re.compile(
    r'\b(python|pip|node|npm|npx|yarn|pnpm|docker|git|kubectl|terraform|'
    r'aws|gcp|azure|langchain|openai|anthropic|groq|gemini|huggingface|'
    r'pytorch|tensorflow|fastapi|flask|django|react|vue|angular|next\.?js|'
    r'postgres|mysql|mongodb|redis|sqlite|supabase|prisma|'
    r'vite|webpack|babel|eslint|pytest|jest|vitest|'
    r'ollama|llama|mistral|claude|gpt[-\s]?4|'
    r'rag|llm|vector[\s-]?store|embedding|'
    r'curl|wget|ssh|bash|zsh|powershell)\b',
    re.IGNORECASE,
)

# Common Python packages (import statements)
_IMPORT_PATTERN = re.compile(
    r'(?:^|\s)(?:import|from)\s+([a-zA-Z_][a-zA-Z0-9_]*)',
    re.MULTILINE,
)

# Chapter / timestamp markers  →  e.g. "0:30 - Introduction" or "Chapter 1:"
_CHAPTER_PATTERN = re.compile(
    r'(?:^|\n)\s*(?:(\d{1,2}:\d{2}(?::\d{2})?)\s*[-–—:]\s*)(.+)',
    re.MULTILINE,
)

# Sentence-like lines that could be steps (imperative verbs)
_STEP_VERBS = re.compile(
    r'^(?:step\s*\d+[:.]\s*|[-•*]\s*)?'
    r'(?:install|configure|create|run|build|deploy|set\s*up|'
    r'initialize|init|open|use|add|enable|start|make|write|edit|'
    r'update|connect|test|check|import|export|define|call|send|'
    r'copy|paste|navigate|click|select|enter|type|save|push|pull)',
    re.IGNORECASE,
)

# Standard stop-words to filter from tools / concepts
_STOP_WORDS = frozenset({
    "the", "and", "that", "this", "with", "from", "into", "have", "been",
    "will", "would", "could", "should", "their", "there", "where", "when",
    "then", "than", "also", "some", "more", "just", "like", "what", "how",
    "you", "we", "our", "your", "they", "them", "let", "get", "can",
})

_KNOWN_PACKAGES = frozenset({
    "langchain", "openai", "anthropic", "groq", "google", "huggingface",
    "fastapi", "flask", "django", "requests", "httpx", "pydantic",
    "sqlalchemy", "alembic", "psycopg2", "pymongo", "redis", "boto3",
    "torch", "tensorflow", "numpy", "pandas", "sklearn", "matplotlib",
    "tiktoken", "chromadb", "pinecone", "weaviate", "faiss",
    "transformers", "datasets", "accelerate", "diffusers",
    "pytest", "unittest", "click", "typer", "rich",
})


def _extract_tools(transcript: str) -> list[str]:
    matches = _TOOL_PATTERN.findall(transcript)
    seen: dict[str, str] = {}
    for m in matches:
        key = m.lower().replace("-", "").replace(" ", "")
        if key and key not in seen:
            seen[key] = m
    return list(seen.values())[:20]


def _extract_packages(transcript: str) -> list[str]:
    matches = _IMPORT_PATTERN.findall(transcript)
    pkgs: list[str] = []
    for m in matches:
        low = m.lower()
        if low in _KNOWN_PACKAGES or (len(low) > 3 and "_" not in low[:2] and low not in _STOP_WORDS):
            if m not in pkgs:
                pkgs.append(m)
    return pkgs[:15]


def _extract_chapters(transcript: str) -> list[str]:
    chapters = []
    for m in _CHAPTER_PATTERN.finditer(transcript):
        label = m.group(2).strip()
        if label and len(label) > 4:
            chapters.append(label[:120])
    return chapters[:12]


def _extract_keywords(transcript: str, n: int = 15) -> list[str]:
    """Simple frequency-based keyword extraction (no stop-words)."""
    words = re.findall(r'\b[a-zA-Z][a-zA-Z_-]{3,}\b', transcript.lower())
    freq: dict[str, int] = {}
    for w in words:
        if w not in _STOP_WORDS:
            freq[w] = freq.get(w, 0) + 1
    sorted_words = sorted(freq.items(), key=lambda x: x[1], reverse=True)
    return [w for w, _ in sorted_words[:n]]


def _derive_title(metadata: dict, transcript: str) -> str:
    title = (metadata.get("title") or "").strip()
    if title:
        return title[:100]
    # Fallback: first non-empty line of transcript
    for line in transcript.splitlines():
        line = line.strip()
        if len(line) > 10:
            return line[:80]
    return "Extracted Skill"


def build_degraded_skill(
    transcript: str,
    metadata: dict,
    url: str,
    video_id: str,
) -> dict:
    """
    Build a minimal but valid skill dict from transcript + metadata
    without any LLM call.  Suitable for saving immediately when all
    providers are exhausted.

    The returned dict:
      • Passes pipeline_guard.sanitize()
      • Is marked _degraded=True and _pending_enhancement=True
      • Has all required fields populated (even if minimal)
    """
    title        = _derive_title(metadata, transcript)
    tools        = _extract_tools(transcript)
    packages     = _extract_packages(transcript)
    keywords     = _extract_keywords(transcript)
    chapters     = _extract_chapters(transcript)
    author       = (metadata.get("author") or "").strip()

    # Derive skill_name from title
    skill_name = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")[:50]
    if not skill_name:
        skill_name = f"skill_{uuid.uuid4().hex[:6]}"

    # Build description
    description_parts = []
    if author:
        description_parts.append(f"By {author}.")
    if tools:
        description_parts.append(f"Key tools: {', '.join(tools[:5])}.")
    description_parts.append("(Auto-extracted — pending AI enhancement.)")
    description = " ".join(description_parts)

    # Build steps from chapters or generic placeholder
    if chapters:
        steps = [f"Review: {c}" for c in chapters[:8]]
    else:
        steps = ["Watch the full video for step-by-step instructions."]

    # Build markdown
    nl = "\n"
    steps_md = nl.join(f"- {s}" for s in steps) or "- See video transcript."
    tools_md = ", ".join(tools[:10]) if tools else "See transcript."
    markdown  = (
        f"# {title}{nl}{nl}"
        f"> ⚠️ **Auto-extracted draft** — pending AI enhancement for full quality.{nl}{nl}"
        f"{description}{nl}{nl}"
        f"## Steps{nl}{nl}{steps_md}{nl}{nl}"
        f"## Tools & Technologies{nl}{nl}{tools_md}{nl}{nl}"
        f"## Source{nl}{nl}"
        f"- **Video**: [{title}]({url}){nl}"
        f"- **Video ID**: `{video_id}`{nl}"
    )

    skill: dict = {
        "action":           "create",
        "enhance_target":   None,
        "skill_name":       skill_name,
        "title":            title,
        "description":      description,
        "steps":            steps,
        "tools":            tools,
        "concepts":         keywords[:10],
        "tags":             keywords[:6],
        "python_packages":  packages,
        "related_skills":   [],
        "skill_markdown":   markdown,
        "_degraded":        True,
        "_pending_enhancement": True,
        "_arena":           {
            "title_winner": "degraded",
            "desc_winner":  "degraded",
            "steps_a":      0, "steps_b": 0, "steps_merged": len(steps),
            "github_tools_added": 0,
            "note":         "all_providers_exhausted",
        },
    }

    log.info(
        "Built degraded skill '%s' for %s (tools=%d steps=%d)",
        skill_name, video_id, len(tools), len(steps),
    )
    return skill


def deterministic_judge_merge(skill_a: Optional[dict], skill_b: Optional[dict]) -> dict:
    """
    Pure-Python union of two extraction dicts — no LLM call, never aborts.
    Used when the judge provider fails and both extractions succeeded.

    Merge rules:
      • title / description / skill_name: prefer skill_a (educator lens) if present
      • lists (steps, tools, etc.): union + deduplicate, preserve order
      • skill_markdown: prefer whichever is longer
      • action / enhance_target: prefer skill_a
    """
    if not skill_a and not skill_b:
        return _empty_skill()
    if not skill_a:
        result = dict(skill_b)  # type: ignore[arg-type]
        result["_arena"] = {"note": "deterministic_merge_a_missing", "title_winner": "groq"}
        return result
    if not skill_b:
        result = dict(skill_a)
        result["_arena"] = {"note": "deterministic_merge_b_missing", "title_winner": "chatgpt"}
        return result

    def safe_list(d: dict, key: str) -> list:
        v = (d or {}).get(key)
        if isinstance(v, list):
            return v
        return []

    def union_dedup(a: list, b: list) -> list:
        seen: dict[str, str] = {}
        for item in a + b:
            if isinstance(item, str):
                key = item.strip().lower()
                if key and key not in seen:
                    seen[key] = item.strip()
        return list(seen.values())

    # Prefer skill_a for scalar fields (educator lens = better descriptions)
    title       = (skill_a.get("title") or skill_b.get("title") or "").strip()
    description = (skill_a.get("description") or skill_b.get("description") or "").strip()
    skill_name  = (skill_a.get("skill_name") or skill_b.get("skill_name") or "").strip()
    action      = skill_a.get("action") or skill_b.get("action") or "create"
    enhance_target = skill_a.get("enhance_target") or skill_b.get("enhance_target")

    # Merge lists
    steps   = union_dedup(safe_list(skill_a, "steps"),   safe_list(skill_b, "steps"))[:12]
    tools   = union_dedup(safe_list(skill_a, "tools"),   safe_list(skill_b, "tools"))
    concepts = union_dedup(safe_list(skill_a, "concepts"), safe_list(skill_b, "concepts"))
    tags     = union_dedup(safe_list(skill_a, "tags"),    safe_list(skill_b, "tags"))
    packages = union_dedup(safe_list(skill_a, "python_packages"), safe_list(skill_b, "python_packages"))
    related  = union_dedup(safe_list(skill_a, "related_skills"), safe_list(skill_b, "related_skills"))

    # Prefer longer markdown
    md_a = (skill_a.get("skill_markdown") or "").strip()
    md_b = (skill_b.get("skill_markdown") or "").strip()
    skill_markdown = md_a if len(md_a) >= len(md_b) else md_b

    a_steps = len(safe_list(skill_a, "steps"))
    b_steps = len(safe_list(skill_b, "steps"))

    result: dict = {
        "action":           action,
        "enhance_target":   enhance_target,
        "skill_name":       skill_name,
        "title":            title,
        "description":      description,
        "steps":            steps,
        "tools":            tools,
        "concepts":         concepts,
        "tags":             tags,
        "python_packages":  packages,
        "related_skills":   related,
        "skill_markdown":   skill_markdown,
        "_arena": {
            "title_winner":      "chatgpt",
            "desc_winner":       "chatgpt",
            "steps_a":           a_steps,
            "steps_b":           b_steps,
            "steps_merged":      len(steps),
            "github_tools_added": 0,
            "note":              "deterministic_merge_judge_failed",
        },
    }

    log.info(
        "deterministic_judge_merge: %d+%d steps → %d merged, %d tools",
        a_steps, b_steps, len(steps), len(tools),
    )
    return result


def _empty_skill() -> dict:
    return {
        "action": "create", "enhance_target": None,
        "skill_name": f"skill_{uuid.uuid4().hex[:6]}",
        "title": "Extracted Skill", "description": "Pending AI enhancement.",
        "steps": [], "tools": [], "concepts": [], "tags": [],
        "python_packages": [], "related_skills": [],
        "skill_markdown": "# Extracted Skill\n\nPending AI enhancement.\n",
        "_degraded": True, "_pending_enhancement": True,
        "_arena": {"note": "both_extractions_failed"},
    }
