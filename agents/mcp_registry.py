"""
Fieldnote MCP Hub Registry
===========================
Canonical registry of 20+ curated, open-source MCP servers organized by capability.

Lifecycle:
  not_installed → installing → installed (verifying) → connected / failed / degraded
  installed → enabled / disabled
  any → quarantined (bad license or package identity mismatch)

Persistence: fieldnote_mcp/mcp_hub_registry.json
Seed entries are merged on first load — existing runtime state is preserved.
"""
from __future__ import annotations

import difflib
import json
import logging
import os
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

log = logging.getLogger("fieldnote.mcp_registry")

REGISTRY_FILE = os.path.join("fieldnote_mcp", "mcp_hub_registry.json")
STATUS_FILE   = os.path.join("fieldnote_mcp", "status.json")
MIGRATION_FILE = os.path.join("fieldnote_mcp", "migration_report.json")

os.makedirs("fieldnote_mcp", exist_ok=True)

# ── Approved SPDX license identifiers ─────────────────────────────────────────
APPROVED_LICENSES: set[str] = {
    "MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause",
    "ISC", "MPL-2.0", "LGPL-2.1", "LGPL-3.0", "GPL-2.0", "GPL-3.0",
    "LGPL-2.1-only", "LGPL-3.0-only", "GPL-2.0-only", "GPL-3.0-only",
}

# ── Dataclass ──────────────────────────────────────────────────────────────────

@dataclass
class MCPServer:
    id:                  str
    name:                str
    category:            str          # search | browser | media | transcription | local_llm | vector_db | database | git | code | documents | knowledge
    description:         str
    license_spdx:        str
    homepage:            str
    repo_url:            str
    package_name:        str
    install_method:      str          # uvx | pip | npm | local
    runtime_required:    str          # python | node | none
    runtime_check_cmd:   str          # shell command to verify runtime, e.g. "python --version"
    capabilities:        list[str] = field(default_factory=list)  # fieldnote capability names
    credential_env:      str = ""
    credential_optional: bool = True
    quarantine_reason:   str = ""
    health_state:        str = "not_installed"  # not_installed | installing | verifying | connected | degraded | offline | quarantined | runtime_missing | missing_credential
    verified_at:         str = ""
    installed_version:   str = ""
    latest_version:      str = ""
    install_hint:        str = ""
    python_alternative_id: str = ""  # ID of a Python/uvx server with same capability (used when runtime_missing)
    enabled:             bool = True
    write_capable:       bool = False  # write-capable servers disabled by default
    icon:                str = "🔧"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "MCPServer":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})


# ── Seed registry — 20+ curated entries ───────────────────────────────────────

SEED_ENTRIES: list[dict] = [
    # ── Web Search ─────────────────────────────────────────────────────────────
    {
        "id": "exa-search",
        "name": "Exa Search MCP",
        "category": "search",
        "description": "Neural web search powered by Exa AI. Returns semantically relevant results with full page content. Free tier available.",
        "license_spdx": "MIT",
        "homepage": "https://exa.ai",
        "repo_url": "https://github.com/exa-labs/exa-mcp-server",
        "package_name": "exa-mcp-server",
        "install_method": "uvx",
        "runtime_required": "python",
        "runtime_check_cmd": "python --version",
        "capabilities": ["web_search"],
        "credential_env": "EXA_API_KEY",
        "credential_optional": False,
        "icon": "🔍",
        "health_state": "not_installed",
    },
    {
        "id": "brave-search",
        "name": "Brave Search MCP",
        "category": "search",
        "description": "Privacy-focused web search via Brave Search API. No tracking, free tier with 2000 req/month.",
        "license_spdx": "MIT",
        "homepage": "https://brave.com/search/api/",
        "repo_url": "https://github.com/modelcontextprotocol/servers",
        "package_name": "@modelcontextprotocol/server-brave-search",
        "install_method": "npm",
        "runtime_required": "node",
        "runtime_check_cmd": "node --version",
        "capabilities": ["web_search"],
        "credential_env": "BRAVE_API_KEY",
        "credential_optional": False,
        "icon": "🦁",
        "health_state": "not_installed",
        "python_alternative_id": "exa-search",
    },
    {
        "id": "free-search",
        "name": "Free Search MCP",
        "category": "search",
        "description": "No-key web search using DuckDuckGo. Completely free, no API key required. Lower result quality than Exa.",
        "license_spdx": "MIT",
        "homepage": "https://github.com/jae-jae/fetcher-mcp",
        "repo_url": "https://github.com/jae-jae/fetcher-mcp",
        "package_name": "free-search-mcp",
        "install_method": "uvx",
        "runtime_required": "python",
        "runtime_check_cmd": "python --version",
        "capabilities": ["web_search"],
        "credential_env": "",
        "credential_optional": True,
        "icon": "🌐",
        "health_state": "not_installed",
    },
    # ── Web Browser / Crawl ────────────────────────────────────────────────────
    {
        "id": "firecrawl",
        "name": "Firecrawl MCP",
        "category": "browser",
        "description": "Full-page web scraping and crawling with JS rendering. Returns clean markdown. Free tier available.",
        "license_spdx": "MIT",
        "homepage": "https://firecrawl.dev",
        "repo_url": "https://github.com/mendableai/firecrawl-mcp-server",
        "package_name": "firecrawl-mcp-server",
        "install_method": "uvx",
        "runtime_required": "python",
        "runtime_check_cmd": "python --version",
        "capabilities": ["web_crawl"],
        "credential_env": "FIRECRAWL_API_KEY",
        "credential_optional": False,
        "icon": "🔥",
        "health_state": "not_installed",
    },
    {
        "id": "markdownify",
        "name": "Markdownify MCP",
        "category": "documents",
        "description": "Convert web pages, PDFs, and documents to clean Markdown. Works without an API key for basic use.",
        "license_spdx": "MIT",
        "homepage": "https://github.com/zcaceres/markdownify-mcp",
        "repo_url": "https://github.com/zcaceres/markdownify-mcp",
        "package_name": "markdownify-mcp",
        "install_method": "uvx",
        "runtime_required": "python",
        "runtime_check_cmd": "python --version",
        "capabilities": ["doc_convert", "web_crawl"],
        "credential_env": "",
        "credential_optional": True,
        "icon": "📝",
        "health_state": "not_installed",
    },
    {
        "id": "fetch-mcp",
        "name": "Fetch MCP",
        "category": "browser",
        "description": "Simple HTTP fetch tool — retrieves web page content and converts to text. No API key needed.",
        "license_spdx": "MIT",
        "homepage": "https://github.com/modelcontextprotocol/servers",
        "repo_url": "https://github.com/modelcontextprotocol/servers",
        "package_name": "mcp-server-fetch",
        "install_method": "uvx",
        "runtime_required": "python",
        "runtime_check_cmd": "python --version",
        "capabilities": ["web_crawl", "file_read"],
        "credential_env": "",
        "credential_optional": True,
        "icon": "🌍",
        "health_state": "not_installed",
    },
    # ── Media / Transcription ──────────────────────────────────────────────────
    {
        "id": "youtube-mcp",
        "name": "YouTube MCP",
        "category": "media",
        "description": "Extract YouTube video transcripts, metadata, and chapter markers. No API key required.",
        "license_spdx": "MIT",
        "homepage": "https://github.com/anaisbetts/mcp-youtube",
        "repo_url": "https://github.com/anaisbetts/mcp-youtube",
        "package_name": "mcp-youtube",
        "install_method": "uvx",
        "runtime_required": "python",
        "runtime_check_cmd": "python --version",
        "capabilities": ["transcription", "web_crawl"],
        "credential_env": "",
        "credential_optional": True,
        "icon": "▶️",
        "health_state": "not_installed",
    },
    # ── Git / GitHub ───────────────────────────────────────────────────────────
    {
        "id": "github-mcp",
        "name": "GitHub MCP (Official)",
        "category": "git",
        "description": "Official GitHub MCP server — read repos, issues, PRs, files. Requires a GitHub PAT with repo scope.",
        "license_spdx": "MIT",
        "homepage": "https://github.com/github/github-mcp-server",
        "repo_url": "https://github.com/github/github-mcp-server",
        "package_name": "@modelcontextprotocol/server-github",
        "install_method": "npm",
        "runtime_required": "node",
        "runtime_check_cmd": "node --version",
        "capabilities": ["git_read"],
        "credential_env": "GITHUB_TOKEN",
        "credential_optional": False,
        "icon": "🐙",
        "health_state": "not_installed",
        "python_alternative_id": "git-mcp",
    },
    {
        "id": "git-mcp",
        "name": "Git MCP (filesystem)",
        "category": "git",
        "description": "Read local Git repositories — commits, branches, diffs, blame. Works on any local repo, no API key.",
        "license_spdx": "MIT",
        "homepage": "https://github.com/modelcontextprotocol/servers",
        "repo_url": "https://github.com/modelcontextprotocol/servers",
        "package_name": "mcp-server-git",
        "install_method": "uvx",
        "runtime_required": "python",
        "runtime_check_cmd": "python --version",
        "capabilities": ["git_read"],
        "credential_env": "",
        "credential_optional": True,
        "icon": "🌿",
        "health_state": "not_installed",
    },
    # ── Vector DB ──────────────────────────────────────────────────────────────
    {
        "id": "qdrant-mcp",
        "name": "Qdrant MCP",
        "category": "vector_db",
        "description": "Connect to a Qdrant vector database — semantic search, similarity search, point upsert. Self-hosted or cloud.",
        "license_spdx": "Apache-2.0",
        "homepage": "https://qdrant.tech",
        "repo_url": "https://github.com/qdrant/mcp-server-qdrant",
        "package_name": "mcp-server-qdrant",
        "install_method": "uvx",
        "runtime_required": "python",
        "runtime_check_cmd": "python --version",
        "capabilities": ["vector_search"],
        "credential_env": "QDRANT_URL",
        "credential_optional": False,
        "icon": "📌",
        "health_state": "not_installed",
    },
    # ── Database ───────────────────────────────────────────────────────────────
    {
        "id": "sqlite-mcp",
        "name": "SQLite MCP",
        "category": "database",
        "description": "Read and query SQLite databases. No server, no credentials — just point at a .db file.",
        "license_spdx": "MIT",
        "homepage": "https://github.com/modelcontextprotocol/servers",
        "repo_url": "https://github.com/modelcontextprotocol/servers",
        "package_name": "mcp-server-sqlite",
        "install_method": "uvx",
        "runtime_required": "python",
        "runtime_check_cmd": "python --version",
        "capabilities": ["file_read"],
        "credential_env": "",
        "credential_optional": True,
        "icon": "🗄️",
        "health_state": "not_installed",
    },
    {
        "id": "postgres-mcp",
        "name": "PostgreSQL MCP",
        "category": "database",
        "description": "Query PostgreSQL databases. Read-only by default for safety. Requires a DATABASE_URL connection string.",
        "license_spdx": "MIT",
        "homepage": "https://github.com/modelcontextprotocol/servers",
        "repo_url": "https://github.com/modelcontextprotocol/servers",
        "package_name": "mcp-server-postgres",
        "install_method": "npm",
        "runtime_required": "node",
        "runtime_check_cmd": "node --version",
        "capabilities": ["file_read"],
        "credential_env": "DATABASE_URL",
        "credential_optional": False,
        "icon": "🐘",
        "health_state": "not_installed",
        "python_alternative_id": "sqlite-mcp",
    },
    # ── Code ───────────────────────────────────────────────────────────────────
    {
        "id": "filesystem-mcp",
        "name": "Filesystem MCP",
        "category": "code",
        "description": "Read local files and directories. Sandboxed to approved paths only. No credentials needed.",
        "license_spdx": "MIT",
        "homepage": "https://github.com/modelcontextprotocol/servers",
        "repo_url": "https://github.com/modelcontextprotocol/servers",
        "package_name": "@modelcontextprotocol/server-filesystem",
        "install_method": "npm",
        "runtime_required": "node",
        "runtime_check_cmd": "node --version",
        "capabilities": ["file_read"],
        "credential_env": "",
        "credential_optional": True,
        "icon": "📁",
        "health_state": "not_installed",
        "python_alternative_id": "fetch-mcp",
    },
    {
        "id": "mcp-server-python",
        "name": "Python REPL MCP",
        "category": "code",
        "description": "Execute Python code in a sandboxed environment. Useful for data analysis and prototyping.",
        "license_spdx": "MIT",
        "homepage": "https://github.com/bazinga-tools/mcp-python-repl",
        "repo_url": "https://github.com/bazinga-tools/mcp-python-repl",
        "package_name": "mcp-python-repl",
        "install_method": "uvx",
        "runtime_required": "python",
        "runtime_check_cmd": "python --version",
        "capabilities": ["file_read"],
        "credential_env": "",
        "credential_optional": True,
        "icon": "🐍",
        "health_state": "not_installed",
        "write_capable": True,
        "enabled": False,  # write-capable; disabled by default
    },
    # ── Documents ─────────────────────────────────────────────────────────────
    {
        "id": "mcp-pandoc",
        "name": "Pandoc Document Converter",
        "category": "documents",
        "description": "Convert between document formats (PDF, DOCX, HTML, Markdown) using Pandoc. Requires Pandoc installed.",
        "license_spdx": "MIT",
        "homepage": "https://github.com/vivekVells/mcp-pandoc",
        "repo_url": "https://github.com/vivekVells/mcp-pandoc",
        "package_name": "mcp-pandoc",
        "install_method": "uvx",
        "runtime_required": "python",
        "runtime_check_cmd": "python --version",
        "capabilities": ["doc_convert"],
        "credential_env": "",
        "credential_optional": True,
        "icon": "📄",
        "health_state": "not_installed",
    },
    # ── Knowledge / Memory ─────────────────────────────────────────────────────
    {
        "id": "memory-mcp",
        "name": "Memory MCP (Official)",
        "category": "knowledge",
        "description": "Persistent key-value memory for AI agents using a local SQLite store. No API key needed.",
        "license_spdx": "MIT",
        "homepage": "https://github.com/modelcontextprotocol/servers",
        "repo_url": "https://github.com/modelcontextprotocol/servers",
        "package_name": "@modelcontextprotocol/server-memory",
        "install_method": "npm",
        "runtime_required": "node",
        "runtime_check_cmd": "node --version",
        "capabilities": ["vector_search"],
        "credential_env": "",
        "credential_optional": True,
        "icon": "🧠",
        "health_state": "not_installed",
        "python_alternative_id": "qdrant-mcp",
    },
    # ── Local LLM ─────────────────────────────────────────────────────────────
    {
        "id": "ollama-mcp",
        "name": "Ollama MCP",
        "category": "local_llm",
        "description": "Use Ollama local LLMs (Llama 3, Mistral, Gemma) as MCP tools. Requires Ollama installed locally.",
        "license_spdx": "MIT",
        "homepage": "https://ollama.com",
        "repo_url": "https://github.com/paorazio/mcp-ollama",
        "package_name": "mcp-ollama",
        "install_method": "uvx",
        "runtime_required": "python",
        "runtime_check_cmd": "python --version",
        "capabilities": ["web_search"],
        "credential_env": "OLLAMA_HOST",
        "credential_optional": True,
        "icon": "🦙",
        "health_state": "not_installed",
    },
    # ── All-in-one / Utility ──────────────────────────────────────────────────
    {
        "id": "all-in-one-mcp",
        "name": "All-in-One MCP",
        "category": "search",
        "description": "Multi-capability MCP server covering web search, GitHub, and text tools in one package.",
        "license_spdx": "MIT",
        "homepage": "https://github.com/nguyenvanduocit/all-in-one-model-context-protocol",
        "repo_url": "https://github.com/nguyenvanduocit/all-in-one-model-context-protocol",
        "package_name": "all-in-one-model-context-protocol",
        "install_method": "uvx",
        "runtime_required": "python",
        "runtime_check_cmd": "python --version",
        "capabilities": ["web_search", "git_read"],
        "credential_env": "",
        "credential_optional": True,
        "icon": "🎯",
        "health_state": "not_installed",
    },
    {
        "id": "crawl4ai-mcp",
        "name": "Crawl4AI MCP",
        "category": "browser",
        "description": "AI-optimized web crawler that returns structured data from any page. Uses Playwright internally.",
        "license_spdx": "Apache-2.0",
        "homepage": "https://crawl4ai.com",
        "repo_url": "https://github.com/unclecode/crawl4ai",
        "package_name": "crawl4ai-mcp-server",
        "install_method": "uvx",
        "runtime_required": "python",
        "runtime_check_cmd": "python --version",
        "capabilities": ["web_crawl", "web_search"],
        "credential_env": "",
        "credential_optional": True,
        "icon": "🕷️",
        "health_state": "not_installed",
    },
    {
        "id": "websearch-mcp",
        "name": "WebSearch MCP",
        "category": "search",
        "description": "Free web search tool using multiple search engines as fallback. No API key required.",
        "license_spdx": "MIT",
        "homepage": "https://github.com/mnhlt/WebSearch-MCP",
        "repo_url": "https://github.com/mnhlt/WebSearch-MCP",
        "package_name": "WebSearch-MCP",
        "install_method": "uvx",
        "runtime_required": "python",
        "runtime_check_cmd": "python --version",
        "capabilities": ["web_search"],
        "credential_env": "",
        "credential_optional": True,
        "icon": "🔎",
        "health_state": "not_installed",
    },
    {
        "id": "notion-mcp",
        "name": "Notion MCP",
        "category": "knowledge",
        "description": "Read and write Notion pages, databases, and blocks. Requires a Notion integration token.",
        "license_spdx": "MIT",
        "homepage": "https://notion.so",
        "repo_url": "https://github.com/suekou/mcp-notion-server",
        "package_name": "mcp-notion-server",
        "install_method": "uvx",
        "runtime_required": "python",
        "runtime_check_cmd": "python --version",
        "capabilities": ["file_read"],
        "credential_env": "NOTION_API_KEY",
        "credential_optional": False,
        "icon": "📓",
        "health_state": "not_installed",
        "write_capable": True,
        "enabled": False,  # write-capable; disabled by default
    },
]


# ── Persistence ────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_registry() -> list[MCPServer]:
    """Load registry from disk, merging seed entries for any missing IDs."""
    existing: dict[str, dict] = {}
    if os.path.exists(REGISTRY_FILE):
        try:
            with open(REGISTRY_FILE) as f:
                raw = json.load(f)
            for entry in raw:
                existing[entry["id"]] = entry
        except Exception as exc:
            log.warning("mcp_registry: load failed: %s", exc)

    # Merge seed entries — add new IDs and push static metadata into existing entries
    # Runtime state fields are always preserved from the persisted entry.
    _RUNTIME_FIELDS = {"health_state", "verified_at", "installed_version",
                       "latest_version", "enabled", "quarantine_reason"}
    for seed in SEED_ENTRIES:
        sid = seed["id"]
        if sid not in existing:
            existing[sid] = seed
        else:
            # Push static seed fields (e.g. python_alternative_id) that may be absent
            # from older persisted entries, without touching runtime state.
            for k, v in seed.items():
                if k not in _RUNTIME_FIELDS and k not in existing[sid]:
                    existing[sid][k] = v

    servers = []
    for d in existing.values():
        try:
            srv = MCPServer.from_dict(d)
            # Validate license
            if srv.license_spdx not in APPROVED_LICENSES:
                srv.health_state = "quarantined"
                srv.quarantine_reason = "unverified_license"
            servers.append(srv)
        except Exception as exc:
            log.warning("mcp_registry: skipping bad entry: %s", exc)

    return servers


def save_registry(servers: list[MCPServer]) -> None:
    os.makedirs("fieldnote_mcp", exist_ok=True)
    with open(REGISTRY_FILE, "w") as f:
        json.dump([s.to_dict() for s in servers], f, indent=2)


def get_by_id(entry_id: str) -> Optional[MCPServer]:
    for s in load_registry():
        if s.id == entry_id:
            return s
    return None


def update_server(entry_id: str, **kwargs) -> Optional[MCPServer]:
    """Atomically update fields on a registry entry and persist."""
    servers = load_registry()
    target = None
    for s in servers:
        if s.id == entry_id:
            for k, v in kwargs.items():
                if hasattr(s, k):
                    setattr(s, k, v)
            target = s
            break
    if target is not None:
        save_registry(servers)
    return target


def mark_connected_as_unverified() -> int:
    """On startup, reset enabled health_state='connected' entries to 'unverified'.

    Only enabled servers are reset because the health-check scheduler skips disabled
    ones (``if not srv.enabled: continue``). Resetting a disabled+connected server
    would leave it stuck as 'unverified' indefinitely with no way for the health
    check to resolve it. Disabled servers keep their 'connected' state so the UI
    still shows the enable/disable toggle rather than a locked spinner.

    The first _mcp_health_check tick resolves each reset entry to 'connected' or
    'offline' as normal.

    Returns the number of entries that were reset.
    """
    servers = load_registry()
    reset = 0
    for srv in servers:
        if srv.health_state == "connected" and srv.enabled:
            srv.health_state = "unverified"
            reset += 1
    if reset:
        save_registry(servers)
        log.info("mcp_registry: %d server(s) marked 'unverified' at startup (pending first health check)", reset)
    return reset


def get_python_alternative(entry_id: str) -> Optional[MCPServer]:
    """Return the recorded Python/uvx alternative for an npm-only server, or None.

    Returns None if the alternative's runtime is also absent on this system,
    preventing the UI from showing a 'Try X instead' link that would immediately
    fail with runtime_missing again.
    """
    import shutil as _shutil
    srv = get_by_id(entry_id)
    if srv is None or not srv.python_alternative_id:
        return None
    alt = get_by_id(srv.python_alternative_id)
    if alt is None:
        return None
    # Check that the alternative's runtime is actually present before surfacing it
    if alt.runtime_required and alt.runtime_required not in ("none", ""):
        if alt.runtime_required == "node":
            runtime_bin = _shutil.which("node")
        else:
            runtime_bin = _shutil.which("python3") or _shutil.which("python")
        if runtime_bin is None:
            return None
    return alt


def get_by_capability(capability: str) -> list[MCPServer]:
    """Return all servers that support the given capability, healthiest first."""
    state_order = {
        "connected": 0, "degraded": 1, "offline": 2,
        "missing_credential": 3, "not_installed": 4,
        "quarantined": 99, "runtime_missing": 5,
    }
    servers = [
        s for s in load_registry()
        if capability in s.capabilities and s.health_state not in ("quarantined",)
    ]
    servers.sort(key=lambda s: state_order.get(s.health_state, 50))
    return servers


# ── License & identity validation ─────────────────────────────────────────────

def validate_license(srv: MCPServer) -> bool:
    """Return True if license is approved; quarantine otherwise."""
    if srv.license_spdx in APPROVED_LICENSES:
        return True
    log.warning("mcp_registry: %s quarantined — license %r not in allowlist", srv.id, srv.license_spdx)
    return False


def check_package_identity(entry: MCPServer) -> dict:
    """
    Verify the PyPI/npm package name matches the expected repo owner.
    Quarantine on mismatch. Returns {ok, detail}.
    Never logs credentials.
    """
    pkg = entry.package_name
    if not pkg or entry.install_method not in ("uvx", "pip"):
        return {"ok": True, "detail": "identity check not applicable"}

    try:
        url = f"https://pypi.org/pypi/{pkg}/json"
        req = urllib.request.Request(url, headers={"User-Agent": "Fieldnote/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read(65536))
        info = data.get("info", {})
        project_urls = info.get("project_urls") or {}
        source_url = (project_urls.get("Source") or project_urls.get("Homepage")
                      or info.get("home_page") or "").lower()
        repo_owner = entry.repo_url.split("/")[3].lower() if entry.repo_url.count("/") >= 3 else ""
        if repo_owner and repo_owner not in source_url:
            log.warning("mcp_registry: %s — package identity mismatch (expected owner %r in %r)",
                        entry.id, repo_owner, source_url)
            return {"ok": False, "detail": f"owner mismatch: expected {repo_owner!r}"}
        return {"ok": True, "detail": "identity verified"}
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return {"ok": True, "detail": "package not on PyPI — skipping identity check"}
        return {"ok": True, "detail": f"PyPI returned {exc.code} — skipping"}
    except Exception as exc:
        return {"ok": True, "detail": f"identity check skipped: {exc}"}


# ── Migration from status.json ─────────────────────────────────────────────────

def import_existing_connections() -> dict:
    """
    Read fieldnote_mcp/status.json and import known servers into the registry.
    Returns a migration report dict.
    Never removes existing registry entries.
    """
    if not os.path.exists(STATUS_FILE):
        return {"matched": [], "unmatched": [], "duplicates": []}

    try:
        with open(STATUS_FILE) as f:
            status = json.load(f)
    except Exception as exc:
        log.warning("mcp_registry: could not read status.json: %s", exc)
        return {"matched": [], "unmatched": [], "duplicates": []}

    servers = load_registry()
    reg_by_pkg = {s.package_name: s for s in servers}
    reg_by_id  = {s.id: s for s in servers}

    matched:   list[str] = []
    unmatched: list[str] = []
    duplicates: list[str] = []

    for sname, info in status.items():
        pkg = info.get("package", "")
        if not pkg:
            unmatched.append(sname)
            continue

        srv = reg_by_pkg.get(pkg)
        if srv is None:
            # Try fuzzy match by package name
            close = difflib.get_close_matches(pkg, reg_by_pkg.keys(), n=1, cutoff=0.7)
            if close:
                srv = reg_by_pkg[close[0]]
            else:
                unmatched.append(sname)
                continue

        if srv.health_state in ("connected", "installed"):
            duplicates.append(sname)
        else:
            srv.health_state = "connected"
            srv.verified_at  = info.get("installed_at", _now_iso())
            matched.append(sname)

    save_registry(servers)
    report = {
        "matched":    matched,
        "unmatched":  unmatched,
        "duplicates": duplicates,
        "timestamp":  _now_iso(),
    }
    try:
        with open(MIGRATION_FILE, "w") as f:
            json.dump(report, f, indent=2)
        log.info("mcp_registry: migration report written — %d matched, %d unmatched",
                 len(matched), len(unmatched))
    except Exception as exc:
        log.warning("mcp_registry: could not write migration report: %s", exc)

    return report


# ── Tool name resolver ─────────────────────────────────────────────────────────

def resolve_tool_name(raw: str, min_confidence: float = 0.90) -> Optional[dict]:
    """
    Fuzzy-match a raw tool mention against registry names and package names.
    Returns {canonical_name, entry_id, confidence} only if confidence >= min_confidence.
    Returns None otherwise. Never matches on empty string.
    """
    if not raw or len(raw.strip()) < 2:
        return None

    raw_lower = raw.lower().strip()
    servers   = load_registry()

    best_score = 0.0
    best_srv   = None

    for srv in servers:
        for candidate in [srv.name.lower(), srv.package_name.lower()]:
            if not candidate:
                continue
            score = difflib.SequenceMatcher(None, raw_lower, candidate).ratio()
            if score > best_score:
                best_score = score
                best_srv   = srv

    if best_srv is not None and best_score >= min_confidence:
        return {
            "canonical_name": best_srv.name,
            "entry_id":       best_srv.id,
            "confidence":     best_score,
        }
    return None


# ── Health summary ─────────────────────────────────────────────────────────────

def health_summary() -> dict:
    """Return a sanitized summary safe for public-facing API endpoints."""
    servers = load_registry()
    counts: dict[str, int] = {}
    for s in servers:
        counts[s.health_state] = counts.get(s.health_state, 0) + 1
    return {
        "total":          len(servers),
        "connected":      counts.get("connected", 0),
        "degraded":       counts.get("degraded", 0),
        "offline":        counts.get("offline", 0),
        "quarantined":    counts.get("quarantined", 0),
        "not_installed":  counts.get("not_installed", 0),
        "runtime_missing": counts.get("runtime_missing", 0),
        "missing_credential": counts.get("missing_credential", 0),
    }


def capability_map() -> dict:
    """Return capability → list of server names for the capabilities endpoint."""
    cap_map: dict[str, list[str]] = {}
    for srv in load_registry():
        if srv.health_state not in ("connected", "degraded"):
            continue
        for cap in srv.capabilities:
            cap_map.setdefault(cap, []).append(srv.name)
    return cap_map
