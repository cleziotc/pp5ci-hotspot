from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import subprocess
from pathlib import Path
from typing import Any

from fastapi import Header, HTTPException

ADMIN_PASSWORD_FILE = Path(os.getenv("PP5CI_HOTSPOT_ADMIN_PASSWORD_FILE", "/etc/pp5ci-hotspot/admin-password.json"))
ADMIN_HELPER = os.getenv("PP5CI_HOTSPOT_ADMIN_HELPER", "/usr/local/sbin/pp5ci-hotspot-admin")
PBKDF2_ITERATIONS = 310_000


def _read_password_record() -> dict[str, Any]:
    try:
        value = json.loads(ADMIN_PASSWORD_FILE.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def verify_admin_password(password: str) -> bool:
    record = _read_password_record()
    try:
        salt = base64.b64decode(str(record["salt"]), validate=True)
        expected = base64.b64decode(str(record["hash"]), validate=True)
        iterations = int(record.get("iterations") or PBKDF2_ITERATIONS)
    except (KeyError, ValueError, TypeError):
        return False
    if iterations < 100_000 or not salt or not expected:
        return False
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(candidate, expected)


def require_admin(
    x_pp5ci_hotspot_admin_password: str | None = Header(
        default=None,
        alias="X-PP5CI-Hotspot-Admin-Password",
    )
) -> None:
    supplied = x_pp5ci_hotspot_admin_password or ""
    if not _read_password_record():
        raise HTTPException(status_code=503, detail="Senha de administrador ainda não foi configurada")
    if not supplied or not verify_admin_password(supplied):
        raise HTTPException(status_code=401, detail="Senha de administrador inválida")


def run_admin_helper(command: str, payload: dict[str, Any] | None = None, timeout: int = 30) -> dict[str, Any]:
    if command not in {"apply", "update-hosts", "set-hosts-schedule", "restart-service", "enable-ircddb", "start-update", "start-rollback"}:
        raise ValueError("Unsupported admin helper command")

    proc = subprocess.run(
        ["sudo", ADMIN_HELPER, command],
        input=json.dumps(payload or {}, ensure_ascii=False),
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "Admin helper failed").strip()
        raise HTTPException(status_code=500, detail=detail[-2000:])

    output = proc.stdout.strip()
    if not output:
        return {"ok": True}
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        return {"ok": True, "output": output}
