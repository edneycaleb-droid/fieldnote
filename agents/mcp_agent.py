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


# ── Hub lifecycle helpers ─────────────────────────────────────────────────────

def _run_hub_install(package_name: str, install_method: str, emit) -> bool:
    """Run the actual install command for a hub registry entry. Returns True on success."""
    if install_method in ("uvx", "pip"):
        uvx = shutil.which("uvx") or shutil.which("uv")
        if uvx:
            emit(f"📦  Installing {package_name} via uvx…", "info")
            try:
                r = subprocess.run(
                    [uvx, "run", package_name, "--help"],
                    capture_output=True, timeout=90,
                )
                if r.returncode in (0, 1):
                    return True
            except Exception as ex:
                _log(f"uvx install {package_name}: {ex}")
        # Fallback: pip
        emit(f"📦  Installing {package_name} via pip…", "info")
        try:
            r = subprocess.run(
                [sys.executable, "-m", "pip", "install", package_name, "-q",
                 "--no-warn-script-location"],
                capture_output=True, text=True, timeout=120,
            )
            if r.returncode == 0:
                return True
            _log(f"pip install {package_name}: {r.stderr[:200]}")
        except Exception as ex:
            _log(f"pip install {package_name}: {ex}")
        return False

    if install_method == "npm":
        npx = shutil.which("npx")
        if not npx:
            emit(f"⚠  npx not found — Node.js is required for {package_name}", "warning")
            return False
        emit(f"📦  Installing {package_name} via npx…", "info")
        try:
            r = subprocess.run(
                ["npx", "-y", "--prefix", "/tmp/fieldnote_npm", package_name, "--help"],
                capture_output=True, timeout=90,
            )
            return r.returncode in (0, 1)
        except Exception as ex:
            _log(f"npm install {package_name}: {ex}")
            return False

    return False


def install_hub_server(
    entry_id: str,
    emit=None,
    force: bool = False,
    _registry_override=None,
) -> dict:
    """
    Install and verify a hub registry server. Returns a dict with at least
    {"health_state": ...}. Idempotent — second call with force=False is a no-op
    if the server is already connected.

    emit: callable(msg: str, level: str) for progress reporting.
    """
    from agents.mcp_registry import load_registry, save_registry, update_server, MCPServer
    from agents import mcp_verifier

    if emit is None:
        emit = lambda msg, lvl="info": None

    servers = _registry_override if _registry_override is not None else load_registry()
    entry   = next((s for s in servers if s.id == entry_id), None)

    if entry is None:
        return {"ok": False, "health_state": "not_installed", "error": f"Unknown server: {entry_id}"}

    # Idempotent check
    if not force and entry.health_state in ("connected",):
        return {"ok": True, "health_state": "connected"}

    # Check runtime
    import shutil as _shutil
    if entry.runtime_required and entry.runtime_required not in ("none", ""):
        runtime_bin = (
            _shutil.which("node") if entry.runtime_required == "node"
            else _shutil.which("python3") or _shutil.which("python")
        )
        if runtime_bin is None:
            update_server(entry_id, health_state="runtime_missing")
            emit(f"⚠  Runtime {entry.runtime_required!r} not found", "warning")
            result: dict = {"ok": False, "health_state": "runtime_missing",
                            "missing_runtime": entry.runtime_required}
            # Surface a Python/uvx alternative so the UI can offer a one-click fallback
            from agents.mcp_registry import get_python_alternative
            alt = get_python_alternative(entry_id)
            if alt:
                result["alternative_id"]   = alt.id
                result["alternative_name"] = alt.name
                emit(f"💡  Try '{alt.name}' (Python) as an alternative", "info")
            return result

    # Check required credential
    if entry.credential_env and not entry.credential_optional:
        key_val = os.environ.get(entry.credential_env, "").strip()
        if not key_val:
            # Try local_keys.json
            try:
                import json as _json
                with open(os.path.join("fieldnote_mcp", "local_keys.json")) as f:
                    key_val = _json.load(f).get(entry.credential_env, "").strip()
            except Exception:
                pass
        if not key_val:
            update_server(entry_id, health_state="missing_credential")
            emit(f"⚠  Required credential {entry.credential_env} not configured", "warning")
            return {"ok": False, "health_state": "missing_credential",
                    "credential_env": entry.credential_env}

    # Install
    update_server(entry_id, health_state="installing")
    emit(f"⏳  Installing {entry.name}…", "info")
    ok = _run_hub_install(entry.package_name, entry.install_method, emit)

    if not ok:
        update_server(entry_id, health_state="offline")
        emit(f"❌  Install failed for {entry.name}", "error")
        return {"ok": False, "health_state": "offline", "error": "install failed"}

    # Verify protocol
    update_server(entry_id, health_state="verifying")
    emit(f"🔍  Verifying MCP protocol for {entry.name}…", "info")
    result = mcp_verifier.verify_server(entry)

    from datetime import datetime, timezone
    now_iso = datetime.now(timezone.utc).isoformat()

    if result.ok:
        update_server(entry_id, health_state="connected", verified_at=now_iso)
        emit(f"✅  {entry.name} connected — protocol verified", "success")
        _log(f"hub install {entry_id}: connected, tools={result.diagnostics.get('tools_count', '?')}")
        return {"ok": True, "health_state": "connected", "diagnostics": result.diagnostics}
    else:
        if result.error_code == "runtime_missing":
            update_server(entry_id, health_state="runtime_missing")
        else:
            update_server(entry_id, health_state="offline")
        emit(f"⚠  Verification failed: {result.error_code}", "warning")
        _log(f"hub install {entry_id}: verify failed: {result.error_code}")
        ret: dict = {
            "ok": False,
            "health_state": "runtime_missing" if result.error_code == "runtime_missing" else "offline",
            "error": result.error_code,
            "diagnostics": result.diagnostics,
        }
        if result.error_code == "runtime_missing":
            from agents.mcp_registry import get_python_alternative
            alt = get_python_alternative(entry_id)
            if alt:
                ret["alternative_id"]   = alt.id
                ret["alternative_name"] = alt.name
                emit(f"💡  Try '{alt.name}' (Python) as an alternative", "info")
        return ret


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
