"""
Fieldnote GitHub Agent
Discovers repositories for every tool/library mentioned in a video.
  • Free route first: unauthenticated GitHub Search API (60 req/hr)
  • Detects MCP servers via name / topics / description
  • Clones repos and installs Python deps automatically
  • Identifies which services need credentials (OAuth / API key)
Add a GITHUB_TOKEN secret for 5 000 req/hr (optional but recommended).
"""
import os, re, json, subprocess, time
from urllib.request import urlopen, Request
from urllib.parse import quote
from urllib.error import HTTPError, URLError

REPOS_DIR = "fieldnote_repos"
os.makedirs(REPOS_DIR, exist_ok=True)

def _gh_token() -> str:
    """Read GitHub token fresh every call — picks up keys saved via UI without restart."""
    return (os.getenv("GITHUBPAT") or os.getenv("GITHUB_TOKEN") or
            os.getenv("GH_TOKEN") or os.getenv("GITHUB") or "")

# ── Known MCP npm packages ────────────────────────────────────────────────────
KNOWN_MCP_NPM: dict[str, str] = {
    "github":        "@modelcontextprotocol/server-github",
    "filesystem":    "@modelcontextprotocol/server-filesystem",
    "gdrive":        "@modelcontextprotocol/server-gdrive",
    "google-drive":  "@modelcontextprotocol/server-gdrive",
    "googledrive":   "@modelcontextprotocol/server-gdrive",
    "slack":         "@modelcontextprotocol/server-slack",
    "postgres":      "@modelcontextprotocol/server-postgres",
    "postgresql":    "@modelcontextprotocol/server-postgres",
    "sqlite":        "@modelcontextprotocol/server-sqlite",
    "memory":        "@modelcontextprotocol/server-memory",
    "brave":         "@modelcontextprotocol/server-brave-search",
    "brave-search":  "@modelcontextprotocol/server-brave-search",
    "fetch":         "@modelcontextprotocol/server-fetch",
    "puppeteer":     "@modelcontextprotocol/server-puppeteer",
    "everart":       "@modelcontextprotocol/server-everart",
    "sequential-thinking": "@modelcontextprotocol/server-sequential-thinking",
    "aws-kb":        "aws-kb-retrieval-server",
}

# ── Credential requirements registry ─────────────────────────────────────────
# url       = pre-filled page to open (one click to land on the exact form)
# device_flow = True if this service supports GitHub-style device flow via Fieldnote
# paste_hint  = placeholder text for the paste input field
AUTH_REGISTRY: dict[str, dict] = {
    "github":    {
        "type": "token",  "secret": "GITHUB_TOKEN",
        "url":  "https://github.com/settings/tokens/new"
               "?scopes=repo%2Cread%3Aorg&description=Fieldnote+MCP",
        "description": "GitHub Personal Access Token",
        "scopes": "repo, read:org",
        "device_flow": True,
        "paste_hint": "ghp_…",
    },
    "openai":    {
        "type": "token",  "secret": "OPENAI_API_KEY",
        "url":  "https://platform.openai.com/api-keys",
        "description": "OpenAI API Key", "scopes": "",
        "paste_hint": "sk-…",
    },
    "anthropic": {
        "type": "token",  "secret": "ANTHROPIC_API_KEY",
        "url":  "https://console.anthropic.com/settings/keys",
        "description": "Anthropic API Key", "scopes": "",
        "paste_hint": "sk-ant-…",
    },
    "google":    {
        "type": "oauth",  "secret": "GOOGLE_CLIENT_ID",
        "url":  "https://console.cloud.google.com/apis/credentials",
        "description": "Google OAuth Client ID", "scopes": "",
        "paste_hint": "…apps.googleusercontent.com",
    },
    "gdrive":    {
        "type": "oauth",  "secret": "GDRIVE_CLIENT_ID",
        "url":  "https://console.cloud.google.com/apis/credentials",
        "description": "Google Drive OAuth credentials", "scopes": "",
        "paste_hint": "…apps.googleusercontent.com",
    },
    "slack":     {
        "type": "token",  "secret": "SLACK_BOT_TOKEN",
        "url":  "https://api.slack.com/apps?new_app=1",
        "description": "Slack Bot Token", "scopes": "channels:read",
        "paste_hint": "xoxb-…",
    },
    "notion":    {
        "type": "token",  "secret": "NOTION_API_KEY",
        "url":  "https://www.notion.so/my-integrations",
        "description": "Notion Integration Token", "scopes": "",
        "paste_hint": "secret_…",
    },
    "linear":    {
        "type": "token",  "secret": "LINEAR_API_KEY",
        "url":  "https://linear.app/settings/api",
        "description": "Linear API Key", "scopes": "",
        "paste_hint": "lin_api_…",
    },
    "stripe":    {
        "type": "token",  "secret": "STRIPE_SECRET_KEY",
        "url":  "https://dashboard.stripe.com/apikeys",
        "description": "Stripe Secret Key", "scopes": "",
        "paste_hint": "sk_live_… or sk_test_…",
    },
    "brave":     {
        "type": "token",  "secret": "BRAVE_API_KEY",
        "url":  "https://api.search.brave.com/register",
        "description": "Brave Search API Key", "scopes": "",
        "paste_hint": "BSA…",
    },
    "postgres":  {
        "type": "connstr","secret": "POSTGRES_URL",
        "url":  "https://neon.tech/signup",
        "description": "PostgreSQL connection string", "scopes": "",
        "paste_hint": "postgresql://user:pass@host/db",
    },
    "airtable":  {
        "type": "token",  "secret": "AIRTABLE_API_KEY",
        "url":  "https://airtable.com/create/tokens",
        "description": "Airtable Personal Access Token", "scopes": "",
        "paste_hint": "pat…",
    },
    "twitter":   {
        "type": "token",  "secret": "TWITTER_BEARER_TOKEN",
        "url":  "https://developer.twitter.com/en/portal/projects-and-apps",
        "description": "Twitter/X Bearer Token", "scopes": "",
        "paste_hint": "AAAA…",
    },
    "discord":   {
        "type": "token",  "secret": "DISCORD_BOT_TOKEN",
        "url":  "https://discord.com/developers/applications",
        "description": "Discord Bot Token", "scopes": "",
        "paste_hint": "MTI…",
    },
    "jira":      {
        "type": "token",  "secret": "JIRA_API_TOKEN",
        "url":  "https://id.atlassian.com/manage-profile/security/api-tokens",
        "description": "Jira API Token", "scopes": "",
        "paste_hint": "ATATT…",
    },
    "confluence":{"type": "token",  "secret": "CONFLUENCE_API_TOKEN",
                  "url": "https://id.atlassian.com/manage-profile/security/api-tokens",
                  "description": "Confluence API Token", "scopes": "",
                  "paste_hint": "ATATT…"},
    "hubspot":   {
        "type": "token",  "secret": "HUBSPOT_ACCESS_TOKEN",
        "url":  "https://app.hubspot.com/private-apps",
        "description": "HubSpot Private App Token", "scopes": "",
        "paste_hint": "pat-…",
    },
}

# ── Quick transcript scan ─────────────────────────────────────────────────────

_KNOWN_TOOLS_RE = re.compile(
    r'\b(langchain|llamaindex|llama.index|openai|anthropic|groq|ollama|'
    r'huggingface|hugging.face|pinecone|weaviate|chroma|qdrant|milvus|faiss|'
    r'redis|postgres|postgresql|mongodb|supabase|firebase|prisma|drizzle|'
    r'sqlalchemy|fastapi|flask|django|nextjs|react|vue|svelte|astro|vite|'
    r'tailwind|shadcn|langsmith|langgraph|crewai|autogen|dspy|'
    r'llamacpp|llama\.cpp|'
    r'notion|linear|slack|github|stripe|airtable|discord|jira|confluence|'
    r'whisper|elevenlabs|replicate|stability|midjourney|dalle|'
    r'playwright|puppeteer|selenium|scrapy|beautifulsoup|'
    r'tensorflow|pytorch|keras|sklearn|scikit.learn|'
    r'airflow|prefect|dagster|celery|kafka|rabbitmq|'
    r'docker|kubernetes|terraform|ansible|'
    r'browserbase|firecrawl|tavily|exa|perplexity)\b',
    re.IGNORECASE,
)

_CAMEL_TECH_RE = re.compile(
    r'\b([A-Z][a-z]{2,}(?:[A-Z][a-z]+){1,3}(?:AI|ML|DB|API|GPT|LLM|SDK)?)\b'
)


def quick_tool_scan(transcript: str) -> list[str]:
    """Regex pre-scan — extracts tool names before the AI prompt finishes."""
    sample = transcript[:8000]
    found: set[str] = set()

    for m in _KNOWN_TOOLS_RE.finditer(sample):
        found.add(m.group(1).lower().replace(".", "-"))

    for m in _CAMEL_TECH_RE.finditer(sample):
        name = m.group(1)
        if len(name) >= 4 and not name.lower() in {
            "this", "that", "with", "from", "have", "what", "they",
            "when", "where", "which", "your", "their", "about", "some",
        }:
            found.add(name.lower())

    return sorted(found)[:12]


# ── GitHub API helpers ────────────────────────────────────────────────────────

def _gh_get(url: str) -> dict:
    headers = {
        "Accept":     "application/vnd.github.v3+json",
        "User-Agent": "Fieldnote/4.0",
    }
    tok = _gh_token()
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    req = Request(url, headers=headers)
    try:
        with urlopen(req, timeout=9) as r:
            return json.loads(r.read())
    except HTTPError as e:
        if e.code == 403:
            raise RuntimeError(
                "GitHub rate limit hit. Add a GITHUB_TOKEN secret for 5 000 req/hr."
            )
        if e.code in (422, 404):
            return {"items": []}
        raise
    except URLError:
        return {"items": []}


def search_repos(query: str, per_page: int = 5) -> list[dict]:
    url = (
        f"https://api.github.com/search/repositories"
        f"?q={quote(query)}&sort=stars&per_page={per_page}&order=desc"
    )
    try:
        d = _gh_get(url)
        return d.get("items", []) if isinstance(d, dict) else []
    except Exception:
        return []


def is_mcp_server(repo: dict) -> bool:
    name   = (repo.get("name")        or "").lower()
    desc   = (repo.get("description") or "").lower()
    topics = [t.lower() for t in (repo.get("topics") or [])]
    return (
        "mcp"                   in name   or
        "model-context-protocol" in name   or
        "mcp server"            in desc   or
        "model context protocol" in desc   or
        "mcp"                   in topics or
        "modelcontextprotocol"  in topics or
        "model-context-protocol" in topics
    )


def get_known_mcp_pkg(tool: str, repo_name: str) -> str | None:
    candidates = [tool.lower(), repo_name.lower()]
    for c in candidates:
        for key, pkg in KNOWN_MCP_NPM.items():
            if key in c or c in key:
                return pkg
    return None


def get_auth_for_tool(tool: str) -> dict | None:
    t = tool.lower()
    for service, info in AUTH_REGISTRY.items():
        if service in t or t.startswith(service[:4]) or service.startswith(t[:4]):
            has_key = bool(os.getenv(info["secret"]))
            return {"service": service, "has_key": has_key, **info}
    return None


# ── Main search entry point ───────────────────────────────────────────────────

def search_tools(tools: list[str], emit) -> list[dict]:
    """
    Search GitHub for each tool. Returns an enriched list of repo dicts.
    Called in a background thread — emit is thread-safe (Queue-backed).
    """
    results: list[dict] = []
    seen_ids: set[int]  = set()

    for i, tool in enumerate(tools[:10]):
        try:
            if i > 0:
                time.sleep(0.4)   # respect unauthenticated rate limit

            # MCP-specific search first, fall back to general
            mcp_repos = search_repos(f"{tool} mcp server model-context-protocol", 3)
            gen_repos = search_repos(f"{tool}", 4)

            for repo in (mcp_repos + gen_repos)[:5]:
                if repo["id"] in seen_ids:
                    continue
                seen_ids.add(repo["id"])

                mcp_flag = is_mcp_server(repo)
                npm_pkg  = get_known_mcp_pkg(tool, repo["name"])
                auth     = get_auth_for_tool(tool)
                lang     = (repo.get("language") or "").lower()
                stars    = repo.get("stargazers_count", 0)

                entry = {
                    "tool":        tool,
                    "repo_name":   repo["name"],
                    "full_name":   repo["full_name"],
                    "description": repo.get("description") or "",
                    "stars":       stars,
                    "url":         repo.get("html_url", ""),
                    "clone_url":   repo.get("clone_url", ""),
                    "language":    repo.get("language") or "",
                    "language_lower": lang,
                    "is_mcp":      mcp_flag,
                    "npm_package": npm_pkg,
                    "auth_required": auth,
                }
                results.append(entry)

                badge = "🔌 MCP" if mcp_flag else "📦"
                auth_flag = " 🔑" if auth and not auth.get("has_key") else ""
                emit(
                    f"{badge}  {repo['full_name']} ⭐{stars}{auth_flag}",
                    "info",
                )

        except Exception as ex:
            emit(f"⚠  GitHub '{tool}': {ex}", "warning")

    return results


# ── Repo cloning ──────────────────────────────────────────────────────────────

def clone_best_repos(github_results: list[dict], emit) -> list[dict]:
    """
    Clone the most valuable repos:
      • All detected MCP servers
      • Python repos with >50 stars
      • Any repo with >500 stars
    Cap at 4 clones per video to avoid timeouts.
    """
    cloned: list[dict] = []

    candidates = [
        r for r in github_results
        if r.get("is_mcp")
        or (r.get("language_lower") == "python" and r.get("stars", 0) > 50)
        or r.get("stars", 0) > 500
    ]

    for r in candidates[:4]:
        full_name = r["full_name"]
        repo_name = r["repo_name"]
        clone_url = r["clone_url"]
        dest      = os.path.join(REPOS_DIR, repo_name)

        try:
            if os.path.exists(dest):
                proc = subprocess.run(
                    ["git", "-C", dest, "pull", "--ff-only", "-q"],
                    capture_output=True, timeout=30,
                )
                if proc.returncode == 0:
                    emit(f"🔄  Updated {repo_name}", "success")
                    cloned.append({"repo": full_name, "path": dest,
                                   "action": "updated", "repo_name": repo_name})
                    continue

            emit(f"⬇  Cloning {full_name} …", "info")
            proc = subprocess.run(
                ["git", "clone", "--depth=1", "-q", clone_url, dest],
                capture_output=True, text=True, timeout=90,
            )
            if proc.returncode == 0:
                emit(f"✅  Cloned {repo_name}", "success")
                cloned.append({"repo": full_name, "path": dest,
                               "action": "cloned", "repo_name": repo_name})
                _install_python_deps(dest, repo_name, emit)
            else:
                emit(f"⚠  Clone failed ({repo_name}): {proc.stderr[:80]}", "warning")

        except Exception as ex:
            emit(f"⚠  Clone {repo_name}: {ex}", "warning")

    return cloned


def _install_python_deps(repo_path: str, repo_name: str, emit):
    """Install requirements.txt or pip-installable pyproject.toml."""
    import sys
    req   = os.path.join(repo_path, "requirements.txt")
    pypj  = os.path.join(repo_path, "pyproject.toml")

    try:
        if os.path.exists(req):
            r = subprocess.run(
                [sys.executable, "-m", "pip", "install", "-r", req,
                 "-q", "--no-warn-script-location"],
                capture_output=True, timeout=120,
            )
            if r.returncode == 0:
                emit(f"📦  pip deps → {repo_name}", "success")
        elif os.path.exists(pypj):
            r = subprocess.run(
                [sys.executable, "-m", "pip", "install", "-e", repo_path,
                 "-q", "--no-warn-script-location"],
                capture_output=True, timeout=120,
            )
            if r.returncode == 0:
                emit(f"📦  pip -e → {repo_name}", "success")
    except Exception:
        pass
