from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any

from .config import load_effective_config
from .db import get_metadata, get_runtime_state

LINKS_LOG_PATH = Path(os.getenv("PP5CI_HOTSPOT_LINKS_LOG", "/tmp/Links.log"))
REFLECTOR_LINK_RE = re.compile(
    r"\bRefl:\s*((?:REF|XRF|DCS|XLX)[A-Z0-9]{3})\s+([A-Z])\b.*\bDir:\s*Outgoing\b",
    re.IGNORECASE,
)


def _active_reflector_from_links_log(path: Path = LINKS_LOG_PATH) -> tuple[bool, str | None]:
    """Return whether Links.log is available and its current outgoing reflector.

    DStarGateway rewrites Links.log from live link state.  An existing but empty
    file therefore means "currently unlinked" and must not fall back to a stale
    historical reflector.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False, None

    reflector: str | None = None
    for line in text.splitlines():
        match = REFLECTOR_LINK_RE.search(line)
        if match:
            reflector = f"{match.group(1).upper()} {match.group(2).upper()}"
    return True, reflector


def _service_state(name: str) -> dict[str, str]:
    try:
        proc = subprocess.run(
            ["systemctl", "show", name, "--property=ActiveState,SubState", "--value"],
            text=True,
            capture_output=True,
            timeout=2,
            check=False,
        )
        values = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
        active = values[0] if values else "unknown"
        sub = values[1] if len(values) > 1 else "unknown"
        return {"active": active, "sub": sub}
    except (OSError, subprocess.SubprocessError):
        return {"active": "unknown", "sub": "unknown"}


def _memory_percent() -> float | None:
    try:
        values: dict[str, int] = {}
        for line in Path("/proc/meminfo").read_text().splitlines():
            key, value = line.split(":", 1)
            values[key] = int(value.strip().split()[0])
        total = values["MemTotal"]
        available = values["MemAvailable"]
        return round((total - available) * 100.0 / total, 1)
    except (OSError, KeyError, ValueError):
        return None


def _uptime_seconds() -> float | None:
    try:
        return float(Path("/proc/uptime").read_text().split()[0])
    except (OSError, ValueError, IndexError):
        return None


def snapshot() -> dict[str, Any]:
    cfg = load_effective_config()
    runtime = get_runtime_state()
    host_service = _service_state("pp5ci-hotspot-host.service")
    gateway_service = _service_state("polar-dstargateway.service")
    mqtt_service = _service_state("mosquitto.service")
    collector_service = _service_state("pp5ci-hotspot-collector.service")

    uart = cfg.get("uart_port") or ""
    resolved = os.path.realpath(uart) if uart else ""
    serial_exists = bool(uart and os.path.exists(uart))

    try:
        load1, load5, load15 = os.getloadavg()
        load = {"1m": round(load1, 2), "5m": round(load5, 2), "15m": round(load15, 2)}
    except OSError:
        load = {"1m": None, "5m": None, "15m": None}

    links_available, linked_reflector = _active_reflector_from_links_log()
    if gateway_service["active"] != "active":
        reflector = None
    elif links_available:
        reflector = linked_reflector
    else:
        reflector = runtime.get("reflector")
    mqtt_connected = get_metadata("mqtt_connected", "0") == "1"

    return {
        "hotspot": {
            "callsign": cfg["callsign"],
            "name": get_metadata("settings_hotspot_name", os.getenv("PP5CI_HOTSPOT_HOTSPOT_NAME", "PP5CI Hotspot Hotspot")),
            "module": cfg["module"],
            "rx_frequency_hz": cfg["rx_frequency_hz"],
            "tx_frequency_hz": cfg["tx_frequency_hz"],
            "mode": "D-STAR",
        },
        "modem": {
            "online": host_service["active"] == "active" and serial_exists,
            "device": uart,
            "resolved_device": resolved,
            "serial_present": serial_exists,
            "baud": cfg["uart_speed"],
            "rf_level_percent": cfg["rf_level_percent"],
            "rx_level_percent": cfg["rx_level_percent"],
            "dstar_tx_level_percent": cfg["dstar_tx_level_percent"],
            "firmware": None,
        },
        "services": {
            "mmdvmhost": host_service,
            "dstargateway": gateway_service,
            "mosquitto": mqtt_service,
            "collector": collector_service,
        },
        "network": {
            "gateway_address": cfg["gateway_address"],
            "gateway_port": cfg["gateway_port"],
            "local_address": cfg["local_address"],
            "local_port": cfg["local_port"],
        },
        "mqtt": {
            "host": cfg["mqtt_host"],
            "port": cfg["mqtt_port"],
            "name": cfg["mqtt_name"],
            "topic": f"{cfg['mqtt_name']}/json",
            "connected": mqtt_connected,
            "last_event_at": get_metadata("last_mqtt_event_at"),
        },
        "traffic": runtime,
        "link": {
            "reflector": reflector,
            "state": "linked" if reflector else "unlinked",
            "callsign_routing": {
                "enabled": bool(cfg.get("ircddb_enabled")),
                "hostname": cfg.get("ircddb_hostname") or "ircv4.openquad.net",
                "username": cfg.get("ircddb_username") or cfg.get("callsign") or "",
            },
        },
        "system": {
            "load": load,
            "memory_percent": _memory_percent(),
            "uptime_seconds": _uptime_seconds(),
        },
    }
