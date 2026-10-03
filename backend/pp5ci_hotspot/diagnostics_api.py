from __future__ import annotations

import os
import re
import shutil
import socket
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse

from .admin import require_admin, run_admin_helper
from .config import load_effective_config
from .db import aggregate_since, directory_summary, get_metadata, get_runtime_state, list_transmissions

router = APIRouter(prefix="/api/v1/diagnostics", tags=["diagnostics"])

HOST_TIMER_DROPIN = Path("/etc/systemd/system/pp5ci-hotspot-hosts-update.timer.d/schedule.conf")
SYSTEMD_UNITS = [
    ("MMDVMHost", "pp5ci-hotspot-mmdvmhost.service"),
    ("DStarGateway", "pp5ci-hotspot-dstargateway.service"),
    ("Collector", "pp5ci-hotspot-collector.service"),
    ("API", "pp5ci-hotspot-api.service"),
    ("Mosquitto", "mosquitto.service"),
    ("Nginx", "nginx.service"),
]
LOG_UNITS = [
    "pp5ci-hotspot-mmdvmhost.service",
    "pp5ci-hotspot-dstargateway.service",
    "pp5ci-hotspot-collector.service",
    "pp5ci-hotspot-api.service",
]


def _run(args: list[str], timeout: float = 3.0) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(args, text=True, capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError):
        return None


def _systemctl_properties(unit: str, properties: list[str]) -> dict[str, str]:
    args = ["systemctl", "show", unit]
    for prop in properties:
        args.extend(["-p", prop])
    proc = _run(args)
    if not proc or proc.returncode != 0:
        return {}
    result: dict[str, str] = {}
    for line in proc.stdout.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            result[key] = value
    return result


def _service_info(label: str, unit: str) -> dict[str, Any]:
    props = _systemctl_properties(
        unit,
        ["ActiveState", "SubState", "MainPID", "ExecMainStartTimestamp", "ExecMainStartTimestampMonotonic"],
    )
    active = props.get("ActiveState", "unknown")
    sub = props.get("SubState", "unknown")
    pid = int(props.get("MainPID") or 0)
    uptime: float | None = None
    try:
        started_us = int(props.get("ExecMainStartTimestampMonotonic") or 0)
        boot_seconds = float(Path("/proc/uptime").read_text().split()[0])
        if started_us > 0:
            uptime = max(0.0, boot_seconds - started_us / 1_000_000.0)
    except (OSError, ValueError, IndexError):
        uptime = None
    return {
        "label": label,
        "unit": unit,
        "active": active,
        "sub": sub,
        "pid": pid,
        "uptime_seconds": uptime,
        "since": props.get("ExecMainStartTimestamp") or None,
    }


def _hosts_schedule() -> str:
    try:
        text = HOST_TIMER_DROPIN.read_text(encoding="utf-8")
        match = re.search(r"OnCalendar=\*-\*-\*\s+(\d{2}:\d{2}):\d{2}", text)
        if match:
            return match.group(1)
    except OSError:
        pass
    return "03:00"


def _timer_info() -> dict[str, Any]:
    props = _systemctl_properties(
        "pp5ci-hotspot-hosts-update.timer",
        ["ActiveState", "SubState", "LastTriggerUSec", "NextElapseUSecRealtime"],
    )
    return {
        "active": props.get("ActiveState", "unknown"),
        "sub": props.get("SubState", "unknown"),
        "schedule": _hosts_schedule(),
        "last_trigger": props.get("LastTriggerUSec") or None,
        "next_run": props.get("NextElapseUSecRealtime") or None,
    }


def _usb_properties(device: str) -> dict[str, str]:
    proc = _run(["udevadm", "info", "--query=property", f"--name={device}"])
    if not proc or proc.returncode != 0:
        return {}
    result: dict[str, str] = {}
    for line in proc.stdout.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            result[key] = value
    return result


def _mmdvm_firmware() -> str | None:
    proc = _run(["journalctl", "-u", "pp5ci-hotspot-mmdvmhost.service", "-n", "300", "--no-pager", "-o", "cat"], 4)
    if not proc or proc.returncode != 0:
        return None
    for line in reversed(proc.stdout.splitlines()):
        if "MMDVM_HS" in line:
            match = re.search(r"(MMDVM_HS[^,]*?(?:GitID\s+#[0-9A-Fa-f]+|$))", line)
            return (match.group(1) if match else line.strip())[:240]
        if "description:" in line.lower():
            return line.split(":", 1)[1].strip()[:240]
    return None


def _serial_info() -> dict[str, Any]:
    cfg = load_effective_config()
    configured = str(cfg.get("uart_port") or "")
    resolved = os.path.realpath(configured) if configured else ""
    present = bool(configured and os.path.exists(configured))
    props = _usb_properties(resolved) if present else {}
    vendor = props.get("ID_VENDOR_FROM_DATABASE") or props.get("ID_VENDOR") or props.get("ID_VENDOR_ID") or "—"
    model = props.get("ID_MODEL_FROM_DATABASE") or props.get("ID_MODEL") or props.get("ID_MODEL_ID") or "—"
    chip = f"{model} ({vendor})" if model != "—" and vendor != "—" else (model if model != "—" else vendor)
    return {
        "configured_device": configured,
        "device": resolved or configured,
        "present": present,
        "usb_chip": chip,
        "vendor_id": props.get("ID_VENDOR_ID"),
        "product_id": props.get("ID_MODEL_ID"),
        "baud": int(cfg.get("uart_speed") or 0),
        "format": "8N1",
        "firmware": _mmdvm_firmware(),
    }


def _ipv4_proc_hex(address: str) -> str | None:
    try:
        packed = socket.inet_aton(address)
    except OSError:
        return None
    return packed[::-1].hex().upper()


def _udp_bound(address: str, port: int) -> bool:
    target_port = f"{int(port):04X}"
    address_hex = _ipv4_proc_hex(address)
    try:
        lines = Path("/proc/net/udp").read_text().splitlines()[1:]
    except OSError:
        return False
    for line in lines:
        parts = line.split()
        if len(parts) < 2 or ":" not in parts[1]:
            continue
        local_address, local_port = parts[1].split(":", 1)
        if local_port.upper() != target_port:
            continue
        if address_hex is None or local_address.upper() in {address_hex, "00000000"}:
            return True
    return False


def _disk_info() -> dict[str, Any]:
    usage = shutil.disk_usage("/")
    percent = round(usage.used * 100.0 / usage.total, 1) if usage.total else 0.0
    return {
        "total_bytes": usage.total,
        "used_bytes": usage.used,
        "free_bytes": usage.free,
        "used_percent": percent,
    }


def _load_info() -> dict[str, Any]:
    try:
        load1, load5, load15 = os.getloadavg()
        cpus = max(1, os.cpu_count() or 1)
        return {
            "load_1m": round(load1, 2),
            "load_5m": round(load5, 2),
            "load_15m": round(load15, 2),
            "cpu_count": cpus,
            "load_percent": round(load1 * 100.0 / cpus, 1),
        }
    except OSError:
        return {
            "load_1m": None,
            "load_5m": None,
            "load_15m": None,
            "cpu_count": os.cpu_count() or 1,
            "load_percent": None,
        }


def _recent_logs(limit: int = 40) -> list[str]:
    args = ["journalctl"]
    for unit in LOG_UNITS:
        args.extend(["-u", unit])
    args.extend(["-n", str(max(1, min(limit, 200))), "--no-pager", "-o", "short-iso"])
    proc = _run(args, 5)
    if not proc or proc.returncode != 0:
        return []
    return [line for line in proc.stdout.splitlines() if line.strip()]


def _seconds_since(value: str | None) -> float | None:
    if not value:
        return None
    try:
        raw = value.strip()
        if re.fullmatch(r"\d+(?:\.\d+)?", raw):
            dt = datetime.fromtimestamp(float(raw), tz=timezone.utc)
        else:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds())
    except (ValueError, OverflowError, OSError):
        return None


def _last_metrics() -> dict[str, Any]:
    runtime = get_runtime_state()
    latest = list_transmissions(1)
    last = latest[0] if latest else {}
    ber = runtime.get("ber_percent")
    if ber is None:
        ber = last.get("ber_percent")
    rssi = runtime.get("rssi_dbm")
    if rssi is None:
        rssi = last.get("rssi_ave_dbm")

    last_transmission_at = last.get("ended_at") or last.get("started_at")
    if runtime.get("state") == "active":
        last_activity_seconds = 0.0
    else:
        last_activity_seconds = _seconds_since(last_transmission_at)
        if last_activity_seconds is None:
            last_activity_seconds = _seconds_since(get_metadata("last_mqtt_event_at"))

    return {
        "ber_percent": ber,
        "rssi_dbm": rssi,
        "last_activity_seconds": last_activity_seconds,
        "last_transmission_at": last_transmission_at,
    }


def _checks(
    services: list[dict[str, Any]],
    serial: dict[str, Any],
    ports: list[dict[str, Any]],
    timer: dict[str, Any],
    disk: dict[str, Any],
    load: dict[str, Any],
    directory: dict[str, Any],
) -> list[dict[str, Any]]:
    service_map = {item["unit"]: item for item in services}
    host_ok = service_map.get("pp5ci-hotspot-mmdvmhost.service", {}).get("active") == "active"
    gateway_ok = service_map.get("pp5ci-hotspot-dstargateway.service", {}).get("active") == "active"
    ports_ok = all(item["listening"] for item in ports)
    disk_ok = disk["used_percent"] < 90
    load_percent = load.get("load_percent")
    load_ok = load_percent is None or load_percent < 100
    return [
        {"name": "Serial link", "ok": host_ok and serial["present"], "detail": serial["device"] or "não encontrado"},
        {"name": "MMDVMHost", "ok": host_ok, "detail": service_map.get("pp5ci-hotspot-mmdvmhost.service", {}).get("sub", "unknown")},
        {"name": "DStarGateway", "ok": gateway_ok, "detail": service_map.get("pp5ci-hotspot-dstargateway.service", {}).get("sub", "unknown")},
        {"name": "CSV users loaded", "ok": int(directory.get("count") or 0) > 0, "detail": f'{int(directory.get("count") or 0)} registros'},
        {"name": "Hosts update timer", "ok": timer.get("active") == "active", "detail": f'diário {timer.get("schedule", "—")}'},
        {"name": "Network / UDP ports", "ok": ports_ok, "detail": "20010 / 20011" if ports_ok else "porta indisponível"},
        {"name": "Disk space", "ok": disk_ok, "detail": f'{disk["used_percent"]:.1f}% usado'},
        {"name": "System load", "ok": load_ok, "detail": f'{load.get("load_1m") if load.get("load_1m") is not None else "—"} / {load.get("cpu_count")} CPU'},
    ]


@router.get("")
def diagnostics() -> dict[str, Any]:
    cfg = load_effective_config()
    services = [_service_info(label, unit) for label, unit in SYSTEMD_UNITS]
    timer = _timer_info()
    serial = _serial_info()
    disk = _disk_info()
    load = _load_info()
    directory = directory_summary()
    ports = [
        {
            "port": int(cfg["gateway_port"]),
            "protocol": "D-Star Gateway",
            "address": str(cfg["gateway_address"]),
            "listening": _udp_bound(str(cfg["gateway_address"]), int(cfg["gateway_port"])),
        },
        {
            "port": int(cfg["local_port"]),
            "protocol": "MMDVMHost",
            "address": str(cfg["local_address"]),
            "listening": _udp_bound(str(cfg["local_address"]), int(cfg["local_port"])),
        },
    ]
    total = aggregate_since("1970-01-01T00:00:00Z")
    metrics = _last_metrics()
    runtime = get_runtime_state()
    return {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "services": services,
        "timer": timer,
        "serial": serial,
        "ports": ports,
        "metrics": {
            **metrics,
            "rf_level_percent": float(cfg.get("rf_level_percent") or 0),
            "rx_level_percent": float(cfg.get("rx_level_percent") or 0),
            "dstar_tx_level_percent": float(cfg.get("dstar_tx_level_percent") or 0),
            "traffic_state": runtime.get("state"),
            "total_transmissions": int(total.get("transmissions") or 0),
        },
        "system": {"disk": disk, "load": load},
        "directory": directory,
        "checks": _checks(services, serial, ports, timer, disk, load, directory),
        "logs": _recent_logs(40),
    }


@router.post("/serial-check")
def serial_check() -> dict[str, Any]:
    serial = _serial_info()
    return {
        "ok": bool(serial["present"]),
        "message": "Dispositivo serial presente e configuração carregada" if serial["present"] else "Dispositivo serial não encontrado",
        "serial": serial,
    }


@router.post("/dstar-check")
def dstar_check() -> dict[str, Any]:
    cfg = load_effective_config()
    host = _service_info("MMDVMHost", "pp5ci-hotspot-mmdvmhost.service")
    gateway = _service_info("DStarGateway", "pp5ci-hotspot-dstargateway.service")
    ports = [
        _udp_bound(str(cfg["gateway_address"]), int(cfg["gateway_port"])),
        _udp_bound(str(cfg["local_address"]), int(cfg["local_port"])),
    ]
    ok = host["active"] == "active" and gateway["active"] == "active" and all(ports)
    return {
        "ok": ok,
        "message": "Caminho local D-Star operacional; o teste não injeta áudio RF" if ok else "Falha em um ou mais componentes do caminho local D-Star",
        "host": host["active"],
        "gateway": gateway["active"],
        "ports": ports,
    }


@router.post("/restart/{target}", dependencies=[Depends(require_admin)])
def restart_service(target: str) -> dict[str, Any]:
    if target not in {"mmdvmhost", "dstargateway"}:
        raise HTTPException(status_code=400, detail="Serviço não permitido")
    return run_admin_helper("restart-service", {"service": target}, timeout=45)


@router.get("/logs/export", dependencies=[Depends(require_admin)])
def export_logs() -> PlainTextResponse:
    lines = _recent_logs(200)
    generated = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    content = "PP5CI Hotspot diagnostics log\nGenerated: " + generated + "\n\n" + "\n".join(lines) + "\n"
    return PlainTextResponse(content, headers={"Content-Disposition": 'attachment; filename="pp5ci-hotspot-diagnostics.log"'})
