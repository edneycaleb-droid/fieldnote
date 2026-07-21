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
    """Quarantine discovered MCP candidates; never install, enable, or execute them."""
    from agents import supply_chain_policy

    candidates = [
        item for item in github_results
        if item.get("is_mcp") or item.get("npm_package")
    ]
    receipts = supply_chain_policy.quarantine_github_results(
        candidates, source="mcp_agent.process_repos"
    )
    for item, receipt in zip(candidates, receipts):
        emit(
            f"🛡️  MCP candidate {item.get('full_name', item.get('repo_name', 'unknown'))} "
            f"quarantined; activation authority=false",
            "warning",
        )
        _log(
            f"candidate {receipt['candidate_id']}: state={receipt['state']} "
            f"gaps={','.join(receipt['gaps'])}"
        )
    return []



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


# ── Hub lifecycle helpers ─────────────────────────────────────────────────────

def _run_hub_install(package_name: str, install_method: str, emit) -> bool:
    """Host package execution is disabled; candidates require immutable sandbox evidence."""
    emit(f"🛡️  Quarantined {package_name}; mutable {install_method} execution is blocked", "warning")
    return False


def install_hub_server(
    entry_id: str,
    emit=None,
    force: bool = False,
    _registry_override=None,
) -> dict:
    """Record a curated hub entry as a candidate without installing or accessing secrets."""
    from agents.mcp_registry import load_registry
    from agents import supply_chain_policy

    if emit is None:
        emit = lambda msg, lvl="info": None
    servers = _registry_override if _registry_override is not None else load_registry()
    entry = next((server for server in servers if server.id == entry_id), None)
    if entry is None:
        return {"ok": False, "health_state": "not_installed", "error": f"Unknown server: {entry_id}"}

    repo = entry.repo_url.removeprefix("https://github.com/").rstrip("/")
    result = supply_chain_policy.quarantine([{
        "kind": "mcp",
        "repo": repo,
        "source_commit": "",
        "source_digest": "",
        "license_spdx": entry.license_spdx,
        "package": entry.package_name,
        "install_method": entry.install_method,
        "artifact_sha256": "",
        "credential_env": entry.credential_env,
        "write_capable": entry.write_capable,
        "requested_by": "mcp_agent.install_hub_server",
    }])[0]
    emit(f"🛡️  {entry.name} quarantined pending immutable sandbox evidence", "warning")
    return {
        "ok": False,
        "health_state": "quarantined",
        "candidate_id": result["candidate_id"],
        "gaps": result["gaps"],
        "activation_authority": False,
        "error": "immutable sandbox evidence required",
    }

def uninstall_server(entry_id: str) -> bool:
    """Mark a hub server as not_installed in the registry. Returns True on success."""
    from agents.mcp_registry import update_server
    srv = update_server(
        entry_id,
        health_state="not_installed",
        installed_version="",
        verified_at="",
        enabled=True,
    )
    if srv is None:
        return False
    _log(f"hub uninstall {entry_id}: reset to not_installed")
    return True


def enable_server(entry_id: str) -> bool:
    """Enable a hub server. Returns True on success."""
    from agents.mcp_registry import update_server
    srv = update_server(entry_id, enabled=True)
    if srv is None:
        return False
    _log(f"hub enable {entry_id}")
    return True


def disable_server(entry_id: str) -> bool:
    """Disable a hub server (stops routing, does not uninstall). Returns True on success."""
    from agents.mcp_registry import update_server
    srv = update_server(entry_id, enabled=False)
    if srv is None:
        return False
    _log(f"hub disable {entry_id}")
    return True
