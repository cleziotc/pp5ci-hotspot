from __future__ import annotations

import json
import os
import platform
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from . import __version__
from .admin import require_admin, run_admin_helper

router = APIRouter(prefix="/api/v1/updates", tags=["updates"])

DEFAULT_REPOSITORY = "cleziotc/pp5ci-hotspot"
UPDATER_PATH = Path("/usr/local/libexec/pp5ci-hotspot-updater")
UPDATE_STATUS = Path("/var/lib/pp5ci-hotspot/update-status.json")
UPDATE_HISTORY = Path("/var/lib/pp5ci-hotspot/update-history.json")
RELEASES_ROOT = Path("/var/lib/pp5ci-hotspot/releases")
USER_AGENT = "PP5CI-Hotspot-Updates/0.2"


def _repository() -> str:
    return os.getenv("PP5CI_HOTSPOT_GITHUB_REPOSITORY", DEFAULT_REPOSITORY).strip() or DEFAULT_REPOSITORY


def _github_token() -> str | None:
    """Public repository: authentication is not required for release discovery."""
    return None


def _version_key(value: str | None) -> tuple[int, int, int, int]:
    if not value:
        return (0, 0, 0, 0)
    match = re.search(r"(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?", value)
    if not match:
        return (0, 0, 0, 0)
    major, minor, patch = (int(match.group(i)) for i in (1, 2, 3))
    stable = 1 if not match.group(4) else 0
    return (major, minor, patch, stable)


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _operation() -> dict[str, Any]:
    default = {
        "state": "idle",
        "operation": None,
        "step": None,
        "progress": 0,
        "message": "Aguardando uma operação de update",
        "started_at": None,
        "finished_at": None,
        "from_version": None,
        "to_version": None,
        "backup_id": None,
        "error": None,
    }
    value = _read_json(UPDATE_STATUS, default)
    if not isinstance(value, dict):
        return default
    return {**default, **value}


def _github_releases() -> tuple[list[dict[str, Any]], str, str | None]:
    repository = _repository()
    url = f"https://api.github.com/repos/{repository}/releases?per_page=10"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": USER_AGENT,
        "X-GitHub-Api-Version": "2022-11-28",
    }
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.load(response)
        if not isinstance(payload, list):
            return [], "error", "Resposta inválida do GitHub"
        return payload, "online", None
    except urllib.error.HTTPError as exc:
        if exc.code in {401, 403}:
            return [], "error", f"GitHub HTTP {exc.code}"
        if exc.code == 404:
            return [], "not_found", "Repositório público ou endpoint de releases não encontrado"
        return [], "error", f"GitHub HTTP {exc.code}"
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        return [], "offline", str(exc)[:180]


def _asset_info(release: dict[str, Any]) -> dict[str, Any]:
    assets = release.get("assets") if isinstance(release.get("assets"), list) else []
    artifact = None
    checksum = None
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        name = str(asset.get("name") or "")
        item = {
            "name": name,
            "size": int(asset.get("size") or 0),
            "download_url": asset.get("browser_download_url"),
            "api_url": asset.get("url"),
        }
        if name.endswith(".tar.gz") and not name.endswith(".sha256"):
            artifact = item
        elif name.endswith(".sha256"):
            checksum = item
    return {"artifact": artifact, "checksum": checksum}


def _release_record(release: dict[str, Any]) -> dict[str, Any]:
    assets = _asset_info(release)
    return {
        "tag": release.get("tag_name"),
        "name": release.get("name") or release.get("tag_name"),
        "body": release.get("body") or "",
        "published_at": release.get("published_at"),
        "html_url": release.get("html_url"),
        "draft": bool(release.get("draft")),
        "prerelease": bool(release.get("prerelease")),
        "artifact": assets["artifact"],
        "checksum": assets["checksum"],
    }


def _compatibility() -> dict[str, Any]:
    system = platform.system()
    machine = platform.machine()
    compatible = system == "Linux" and machine.lower() in {"x86_64", "amd64", "aarch64", "arm64", "armv7l", "armv6l"}
    return {
        "compatible": compatible,
        "system": system,
        "machine": machine,
        "label": f"{system} {machine}",
    }


@router.get("/status")
def updates_status() -> dict[str, Any]:
    releases, github_state, github_error = _github_releases()
    stable = [
        item for item in releases
        if isinstance(item, dict) and not item.get("draft") and not item.get("prerelease")
    ]
    latest_raw = stable[0] if stable else None
    latest = _release_record(latest_raw) if latest_raw else None
    installed = __version__
    available = str(latest.get("tag") or "") if latest else None
    update_available = bool(latest and _version_key(available) > _version_key(installed))
    compatibility = _compatibility()
    operation = _operation()

    release_ready = bool(
        latest
        and latest.get("artifact")
        and latest.get("checksum")
        and not latest.get("draft")
        and not latest.get("prerelease")
        and compatibility["compatible"]
    )
    installer_ready = UPDATER_PATH.is_file()
    busy = operation.get("state") == "running"
    can_install = bool(update_available and release_ready and installer_ready and not busy)

    if busy:
        install_reason = "Há uma operação de update/rollback em andamento."
    elif not latest:
        install_reason = "Nenhuma release oficial publicada."
    elif not update_available:
        install_reason = "A versão instalada já está atualizada."
    elif not release_ready:
        install_reason = "A release precisa de artefato, SHA-256 e compatibilidade válida."
    elif not installer_ready:
        install_reason = "Motor transacional de atualização não está instalado."
    else:
        install_reason = "Release pronta para instalação transacional."

    return {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "installed_version": installed,
        "available_version": available,
        "update_available": update_available,
        "github": {
            "state": github_state,
            "error": github_error,
            "repository": _repository(),
            "repository_url": f"https://github.com/{_repository()}",
            "authenticated": False,
        },
        "channel": "stable",
        "compatibility": compatibility,
        "release": latest,
        "release_ready": release_ready,
        "installer_ready": installer_ready,
        "can_install": can_install,
        "install_reason": install_reason,
        "operation": operation,
    }


@router.get("/operation")
def update_operation() -> dict[str, Any]:
    return _operation()


@router.get("/history")
def updates_history() -> dict[str, Any]:
    items = _read_json(UPDATE_HISTORY, [])
    if not isinstance(items, list):
        items = []
    return {"items": [item for item in items[:100] if isinstance(item, dict)]}


def _rollback_items() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    try:
        candidates = sorted(RELEASES_ROOT.glob("*/metadata.json"), reverse=True)
    except OSError:
        candidates = []
    for metadata in candidates[:5]:
        try:
            item = json.loads(metadata.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(item, dict) or not item.get("version"):
            continue
        items.append({
            "id": str(item.get("id") or metadata.parent.name),
            "version": str(item.get("version")),
            "created_at": item.get("created_at"),
            "sha256": item.get("sha256"),
        })
    return items


@router.get("/rollback-options")
def rollback_options() -> dict[str, Any]:
    return {"items": _rollback_items()}


@router.post("/install", dependencies=[Depends(require_admin)])
def install_update() -> dict[str, Any]:
    current = updates_status()
    if not current["can_install"]:
        raise HTTPException(status_code=409, detail=current["install_reason"])
    tag = str(current.get("available_version") or "")
    if not re.fullmatch(r"v\d+\.\d+\.\d+", tag):
        raise HTTPException(status_code=409, detail="Release disponível possui tag inválida")
    return run_admin_helper("start-update", {"tag": tag}, timeout=15)


@router.post("/rollback", dependencies=[Depends(require_admin)])
def rollback_update(payload: dict[str, Any]) -> dict[str, Any]:
    if _operation().get("state") == "running":
        raise HTTPException(status_code=409, detail="Há uma operação de update/rollback em andamento")
    backup_id = str(payload.get("backup_id") or "").strip()
    allowed = {item["id"] for item in _rollback_items()}
    if backup_id not in allowed:
        raise HTTPException(status_code=404, detail="Backup de rollback não encontrado")
    return run_admin_helper("start-rollback", {"backup_id": backup_id}, timeout=15)
