"""
Fieldnote MCP Agent
Manages Model Context Protocol server connections discovered from videos.

Strategy (free-first, never gives up):
  1. Known npm package → register with npx command (works even if npx absent: recorded for user)
  2. Python MCP server → pip install
  3. uvx (uv tool run)  → if uvx available
  4. Local clone        → point to cloned server.py

Config lives in fieldnote_mcp/mcp_config.json  (standard MCP format)
Status lives in fieldnote_mcp/status.json       (Fieldnote metadata)
"""
import os, re, json, subprocess, sys, shutil
from datetime import datetime, timezone

MCP_DIR    = "fieldnote_mcp"
CONFIG_F   = os.path.join(MCP_DIR, "mcp_config.json")
STATUS_F   = os.path.join(MCP_DIR, "status.json")
LOG_F      = os.path.join(MCP_DIR, "install.log")
os.makedirs(MCP_DIR, exist_ok=True)


# ── Persistence ───────────────────────────────────────────────────────────────

def load_config() -> dict:
    if os.path.exists(CONFIG_F):
        try:
            with open(CONFIG_F) as f:
                return json.load(f)
        except Exception:
            pass
    return {"mcpServers": {}}


def save_config(c: dict):
    with open(CONFIG_F, "w") as f:
        json.dump(c, f, indent=2)


def load_status() -> dict:
    if os.path.exists(STATUS_F):
        try:
            with open(STATUS_F) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_status(s: dict):
    with open(STATUS_F, "w") as f:
        json.dump(s, f, indent=2)


def _log(msg: str):
    ts = datetime.now(timezone.utc).isoformat()
    try:
        with open(LOG_F, "a") as f:
            f.write(f"[{ts}] {msg}\n")
    except Exception:
        pass


# ── Installers ────────────────────────────────────────────────────────────────

def _try_npm(npm_package: str, server_name: str, emit) -> dict:
    """Register an npm MCP server. Works even without npx — records it for user."""
    npx_path = shutil.which("npx")
    status   = "ready" if npx_path else "npx_unavailable"
    hint     = None if npx_path else (
        f"Install Node.js then run: npx -y {npm_package}"
    )
    emit(
        f"🔌  MCP npm: {server_name} ({'registered' if npx_path else 'recorded — needs Node.js'})",
        "success" if npx_path else "warning",
    )
    _log(f"npm register {npm_package} -> {status}")
    return {
        "command":      "npx",
        "args":         ["-y", npm_package],
        "source":       "npm",
        "package":      npm_package,
        "status":       status,
        "install_hint": hint,
    }


def _try_pip(package: str, server_name: str, emit) -> dict | None:
    """Install a Python MCP server via pip."""
    emit(f"🔌  MCP pip: {package} …", "info")
    try:
        r = subprocess.run(
            [sys.executable, "-m", "pip", "install", package, "-q",
             "--no-warn-script-location"],
            capture_output=True, text=True, timeout=90,
        )
        if r.returncode == 0:
            emit(f"✅  MCP installed: {server_name}", "success")
            _log(f"pip install {package} -> OK")
            # Derive run command: mcp-server-github → mcp.server.github
            mod = package.replace("-", "_").removeprefix("mcp_server_")
            return {
                "command": sys.executable,
                "args":    ["-m", f"mcp.server.{mod}"],
                "source":  "pip",
                "package": package,
                "status":  "ready",
            }
        _log(f"pip install {package} -> FAIL: {r.stderr[:100]}")
    except Exception as ex:
        _log(f"pip install {package} -> EX: {ex}")
    return None


def _try_uvx(package: str, server_name: str, emit) -> dict | None:
    """Try uvx (uv tool run) — fast Python tool runner."""
    uvx = shutil.which("uvx") or shutil.which("uv")
    if not uvx:
        return None
    try:
        r = subprocess.run(
            [uvx, "run", package, "--help"],
            capture_output=True, timeout=60,
        )
        if r.returncode in (0, 1):
            emit(f"✅  MCP uvx: {server_name}", "success")
            _log(f"uvx {package} -> OK")
            return {
                "command": uvx,
                "args":    ["run", package],
                "source":  "uvx",
                "package": package,
                "status":  "ready",
            }
    except Exception:
        pass
    return None


def _try_local(repo_path: str, server_name: str, emit) -> dict | None:
    """Point to a locally cloned server.py."""
    candidates = [
        os.path.join(repo_path, "server.py"),
        os.path.join(repo_path, "src", "server.py"),
        os.path.join(repo_path, "main.py"),
    ]
    for path in candidates:
        if os.path.exists(path):
            emit(f"✅  MCP local: {server_name} → {os.path.basename(path)}", "success")
            return {
                "command": sys.executable,
                "args":    [path],
                "source":  "local",
                "path":    path,
                "status":  "ready",
            }
    return None


# ── Main processor ────────────────────────────────────────────────────────────

def process_repos(github_results: list[dict], emit) -> list[dict]:
    """
    For each GitHub result, attempt to install/register an MCP server.
    Returns list of successfully registered connection dicts.
    Called in a background thread — emit is thread-safe.
    """
    installed: list[dict] = []
    config = load_config()
    status = load_status()
    now    = datetime.now(timezone.utc).isoformat()

    for repo in github_results:
        is_mcp  = repo.get("is_mcp", False)
        npm_pkg = repo.get("npm_package")
        lang    = repo.get("language_lower", "")
        tool    = repo.get("tool", repo.get("repo_name", ""))
        sname   = re.sub(r"[^a-z0-9_]", "_", repo["repo_name"].lower()).strip("_")
        auth    = repo.get("auth_required")

        # Skip already-registered entries
        if sname in status and status[sname].get("installed"):
            continue

        # Only register if it looks like an MCP server or has a known npm package
        if not is_mcp and not npm_pkg:
            continue

        entry: dict | None = None

        # Priority 1: known npm package (always register regardless of npx)
        if npm_pkg:
            entry = _try_npm(npm_pkg, sname, emit)

        # Priority 2: Python pip (for Python MCP servers)
        if entry is None and is_mcp and lang == "python":
            for guess in [
                f"mcp-server-{tool}",
                f"mcp-{tool}",
                repo["repo_name"],
            ]:
                entry = _try_pip(guess, sname, emit)
                if entry:
                    break

        # Priority 3: uvx
        if entry is None and is_mcp:
            entry = _try_uvx(repo["repo_name"], sname, emit)

        # Priority 4: local clone
        if entry is None:
            local_path = os.path.join("fieldnote_repos", repo["repo_name"])
            entry = _try_local(local_path, sname, emit)

        if entry:
            # Inject auth env placeholder
            if auth:
                entry["env"]        = {auth["secret"]: f"${{{auth['secret']}}}"}
                entry["needs_auth"] = not auth.get("has_key", False)
            else:
                entry["needs_auth"] = False

            # Write to standard MCP config (omit Fieldnote-only keys)
            config_entry = {k: v for k, v in entry.items()
                            if k in ("command", "args", "env")}
            config["mcpServers"][sname] = config_entry

            # Write rich status
            status[sname] = {
                **entry,
                "tool":        tool,
                "repo_url":    repo.get("url", ""),
                "full_name":   repo.get("full_name", ""),
                "is_mcp":      is_mcp,
                "auth_info":   auth,
                "installed_at": now,
                "installed":   True,
            }

            installed.append({
                "name":        sname,
                "tool":        tool,
                "source":      entry.get("source", "unknown"),
                "status":      entry.get("status", "ready"),
                "repo_url":    repo.get("url", ""),
                "needs_auth":  entry.get("needs_auth", False),
                "install_hint": entry.get("install_hint"),
                "auth_info":   auth,
            })

    save_config(config)
    save_status(status)
    return installed


# ── Query helpers ─────────────────────────────────────────────────────────────

def get_connections() -> list[dict]:
    """Return all registered MCP connections with live status."""
    status = load_status()
    return [
        {
            "name":         name,
            "tool":         info.get("tool", name),
            "source":       info.get("source", "unknown"),
            "repo_url":     info.get("repo_url", ""),
            "full_name":    info.get("full_name", ""),
            "needs_auth":   info.get("needs_auth", False),
            "auth_info":    info.get("auth_info"),
            "installed_at": info.get("installed_at", ""),
            "status":       info.get("status", "ready"),
            "install_hint": info.get("install_hint"),
        }
        for name, info in status.items()
    ]


def get_config_path() -> str:
    return os.path.abspath(CONFIG_F)
