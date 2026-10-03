from __future__ import annotations

import hmac
import json
import os
import subprocess
from pathlib import Path
from typing import Any

from fastapi import Header, HTTPException

ADMIN_TOKEN_FILE = Path(os.getenv("PP5CI_HOTSPOT_ADMIN_TOKEN_FILE", "/etc/pp5ci-hotspot/admin-token"))
ADMIN_HELPER = os.getenv("PP5CI_HOTSPOT_ADMIN_HELPER", "/usr/local/sbin/pp5ci-hotspot-admin")


def _read_token() -> str:
    try:
        return ADMIN_TOKEN_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def require_admin(x_polar_admin_token: str | None = Header(default=None)) -> None:
    expected = _read_token()
    if not expected:
        raise HTTPException(status_code=503, detail="Admin token is not configured")
    supplied = (x_polar_admin_token or "").strip()
    if not supplied or not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Invalid admin token")


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
