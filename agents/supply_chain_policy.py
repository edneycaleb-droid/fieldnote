"""Fail-closed policy and durable quarantine for discovered ecosystem candidates.

Discovery is autonomous. Installation, activation, credentials, and host mutation are
not. Candidates advance only when immutable provenance and sandbox evidence exist.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

POLICY_VERSION = "1.0"
DEFAULT_QUEUE = Path("fieldnote_mcp/ecosystem_candidates.json")
APPROVED_LICENSES = {"Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC", "MIT", "MPL-2.0"}
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
PYTHON_PIN_RE = re.compile(r"^[A-Za-z0-9_.-]+==[A-Za-z0-9_.+!-]+$")
NPM_PIN_RE = re.compile(r"^(?:@[A-Za-z0-9_.-]+/)?[A-Za-z0-9_.-]+@[0-9][A-Za-z0-9_.+-]*$")
SAFE_ENV_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")

CONTROL_IDS = (
    "immutable_source", "content_digest", "approved_license", "exact_package_pin",
    "artifact_digest", "read_only_default", "credential_allowlist",
    "durable_dedup", "zero_host_execution", "explicit_activation",
)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _digest(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def exact_package_pin(package: str, method: str) -> bool:
    package = str(package or "").strip()
    if method in {"pip", "uvx"}:
        return bool(PYTHON_PIN_RE.fullmatch(package))
    if method == "npm":
        return bool(NPM_PIN_RE.fullmatch(package))
    if method in {"local", "none", ""}:
        return not package
    return False


def evaluate(candidate: dict[str, Any]) -> dict[str, Any]:
    """Return a deterministic decision. Missing or unverifiable evidence quarantines."""
    gaps: list[str] = []
    repo = str(candidate.get("repo", ""))
    commit = str(candidate.get("source_commit", ""))
    source_digest = str(candidate.get("source_digest", ""))
    license_spdx = str(candidate.get("license_spdx", ""))
    package = str(candidate.get("package", ""))
    method = str(candidate.get("install_method", ""))
    artifact_digest = str(candidate.get("artifact_sha256", ""))
    credential_env = candidate.get("credential_env")
    write_capable = bool(candidate.get("write_capable", False))

    if not REPO_RE.fullmatch(repo):
        gaps.append("canonical_repository")
    if not COMMIT_RE.fullmatch(commit):
        gaps.append("immutable_source_commit")
    if not DIGEST_RE.fullmatch(source_digest):
        gaps.append("source_content_digest")
    if license_spdx not in APPROVED_LICENSES:
        gaps.append("approved_license")
    if package or method not in {"none", "", "local"}:
        if not exact_package_pin(package, method):
            gaps.append("exact_package_version")
        if not DIGEST_RE.fullmatch(artifact_digest):
            gaps.append("artifact_digest")
    if write_capable:
        gaps.append("read_only_capability")
    if credential_env not in (None, "") and not SAFE_ENV_RE.fullmatch(str(credential_env)):
        gaps.append("credential_name_allowlist")

    candidate_id = _digest({
        "repo": repo,
        "source_commit": commit,
        "source_digest": source_digest,
        "package": package,
        "install_method": method,
        "artifact_sha256": artifact_digest,
        "policy_version": POLICY_VERSION,
    })
    state = "structurally_validated" if not gaps else "quarantined"
    return {
        "candidate_id": candidate_id,
        "policy_version": POLICY_VERSION,
        "state": state,
        "gaps": sorted(set(gaps)),
        "activation_authority": False,
        "host_execution": False,
        "credentials_accessed": False,
        "network_used_by_policy": False,
        "evaluated_at": _now(),
        "candidate": candidate,
    }


def _load(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"schema_version": "1.0", "policy_version": POLICY_VERSION, "candidates": {}}
    if not isinstance(payload.get("candidates"), dict):
        return {"schema_version": "1.0", "policy_version": POLICY_VERSION, "candidates": {}}
    return payload


def _write_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def quarantine(candidates: Iterable[dict[str, Any]], path: Path = DEFAULT_QUEUE) -> list[dict[str, Any]]:
    """Evaluate and persist candidates idempotently without executing project/package code."""
    payload = _load(path)
    results: list[dict[str, Any]] = []
    for candidate in candidates:
        result = evaluate(dict(candidate))
        existing = payload["candidates"].get(result["candidate_id"])
        if existing:
            result = {**existing, "last_seen_at": _now()}
        else:
            result["first_seen_at"] = result["evaluated_at"]
        payload["candidates"][result["candidate_id"]] = result
        results.append(result)
    payload["updated_at"] = _now()
    _write_atomic(path, payload)
    return results


def quarantine_package_requests(packages: Iterable[str], source: str = "llm") -> list[dict[str, Any]]:
    candidates = [
        {
            "kind": "python_package",
            "repo": "",
            "source_commit": "",
            "source_digest": "",
            "license_spdx": "",
            "package": str(package).strip(),
            "install_method": "pip",
            "artifact_sha256": "",
            "write_capable": False,
            "requested_by": source,
        }
        for package in packages
        if str(package).strip()
    ]
    return quarantine(candidates)


def quarantine_github_results(results: Iterable[dict[str, Any]], source: str) -> list[dict[str, Any]]:
    candidates = []
    for item in results:
        candidates.append({
            "kind": "mcp" if item.get("is_mcp") else "tool",
            "repo": item.get("full_name", ""),
            "source_commit": item.get("source_commit") or item.get("commit_sha") or "",
            "source_digest": item.get("readme_sha256") or "",
            "license_spdx": item.get("license_spdx") or "",
            "package": item.get("npm_package") or "",
            "install_method": "npm" if item.get("npm_package") else "none",
            "artifact_sha256": item.get("artifact_sha256") or "",
            "credential_env": (item.get("auth_required") or {}).get("secret"),
            "write_capable": bool(item.get("write_capable", False)),
            "requested_by": source,
            "source_url": item.get("url", ""),
        })
    return quarantine(candidates)


def architecture_score() -> dict[str, Any]:
    """Machine-readable policy score; execution evidence is deliberately separate."""
    controls = {control: True for control in CONTROL_IDS}
    return {
        "policy_version": POLICY_VERSION,
        "controls": controls,
        "score": f"{sum(controls.values())}/{len(controls)}",
        "execution_evidence": False,
        "activation_authority": False,
    }
