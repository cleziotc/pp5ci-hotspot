from __future__ import annotations

import errno
import os
import re
import socket
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import db, network_db

DATA_DIR = Path(os.getenv("PP5CI_HOTSPOT_DSTAR_DATA_DIR", "/usr/local/share/dstargateway.d"))
LINKS_LOG_PATH = Path(os.getenv("PP5CI_HOTSPOT_LINKS_LOG", "/tmp/Links.log"))
PROBE_INTERVAL_SECONDS = max(2.0, float(os.getenv("PP5CI_HOTSPOT_NETWORK_PROBE_INTERVAL", "3")))
PROBE_TIMEOUT_SECONDS = max(0.25, float(os.getenv("PP5CI_HOTSPOT_NETWORK_PROBE_TIMEOUT", "1.2")))
INTERNET_PROBE_HOST = os.getenv("PP5CI_HOTSPOT_INTERNET_PROBE_HOST", "1.1.1.1")
INTERNET_PROBE_PORT = int(os.getenv("PP5CI_HOTSPOT_INTERNET_PROBE_PORT", "443"))
RETENTION_DAYS = max(1, int(os.getenv("PP5CI_HOTSPOT_NETWORK_RETENTION_DAYS", "7")))
DIRECT_HOLD_SECONDS = max(10.0, float(os.getenv("PP5CI_HOTSPOT_DIRECT_NETWORK_HOLD_SECONDS", "60")))
DIRECT_PROBE_TIMEOUT_SECONDS = max(0.25, float(os.getenv("PP5CI_HOTSPOT_DIRECT_PROBE_TIMEOUT", "0.45")))
DIRECT_PROBE_PORTS = tuple(
    int(value)
    for value in os.getenv("PP5CI_HOTSPOT_DIRECT_PROBE_PORTS", "40000,443,80,22").split(",")
    if value.strip().isdigit() and 1 <= int(value.strip()) <= 65535
)

_ircddb_lock = threading.Lock()
_ircddb_users: dict[str, dict[str, Any]] = {}

REFLECTOR_LINK_RE = re.compile(
    r"\bRefl:\s*((?:REF|XRF|DCS|XLX)[A-Z0-9]{3})\s+([A-Z])\b.*\bDir:\s*Outgoing\b",
    re.IGNORECASE,
)
PROTOCOL_RE = re.compile(r"\bProtocol:\s*([A-Za-z0-9+_-]+)", re.IGNORECASE)
IRCDDB_USER_RE = re.compile(
    r"\bUSER:\s+(?P<callsign>[A-Z0-9]+)\s+.*?(?P<address>(?:\d{1,3}\.){3}\d{1,3})\s*$",
    re.IGNORECASE,
)

PROTOCOL_UDP_PORTS = {
    "DPLUS": 20001,
    "DEXTRA": 30001,
    "DCS": 30051,
}

HOST_FILES = {
    "REF": "DPlus_Hosts.txt",
    "XRF": "DExtra_Hosts.txt",
    "DCS": "DCS_Hosts.txt",
    "XLX": "XLXHosts.txt",
}

REACHABLE_CONNECT_RESULTS = {
    0,
    errno.ECONNREFUSED,
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def remember_ircddb_user(callsign: str, address: str) -> bool:
    callsign = str(callsign or "").strip().upper()
    address = str(address or "").strip()
    if not callsign or not address:
        return False
    try:
        socket.inet_aton(address)
    except OSError:
        return False
    if address == "0.0.0.0":
        return False

    with _ircddb_lock:
        _ircddb_users[callsign] = {
            "callsign": callsign,
            "address": address,
            "updated_at": time.monotonic(),
        }
    return True


def remember_ircddb_user_from_line(line: str) -> bool:
    match = IRCDDB_USER_RE.search(str(line or ""))
    if not match:
        return False
    return remember_ircddb_user(match.group("callsign"), match.group("address"))


def get_ircddb_user(callsign: str | None) -> dict[str, Any] | None:
    key = str(callsign or "").strip().upper()
    if not key:
        return None
    with _ircddb_lock:
        item = _ircddb_users.get(key)
        return dict(item) if item else None


def get_active_link(path: Path = LINKS_LOG_PATH) -> dict[str, Any] | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    result: dict[str, Any] | None = None
    for line in text.splitlines():
        match = REFLECTOR_LINK_RE.search(line)
        if not match:
            continue
        protocol_match = PROTOCOL_RE.search(line)
        protocol = protocol_match.group(1).upper() if protocol_match else None
        result = {
            "reflector": f"{match.group(1).upper()} {match.group(2).upper()}",
            "protocol": protocol,
            "udp_port": PROTOCOL_UDP_PORTS.get(protocol or ""),
        }
    return result


def get_active_reflector(path: Path = LINKS_LOG_PATH) -> str | None:
    link = get_active_link(path)
    return str(link["reflector"]) if link else None


def _base_reflector(reflector: str) -> str:
    return reflector.strip().upper().split()[0] if reflector.strip() else ""


def _host_from_file(base_reflector: str, data_dir: Path = DATA_DIR) -> str | None:
    prefix = base_reflector[:3]
    filename = HOST_FILES.get(prefix)
    if not filename:
        return None

    path = data_dir / filename
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None

    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue

        if prefix == "XLX":
            parts = [part.strip() for part in line.split(";")]
            if len(parts) < 2:
                continue
            name = parts[0].upper()
            if not name.startswith("XLX"):
                name = f"XLX{name}"
            host = parts[1]
        else:
            parts = line.split()
            if len(parts) < 2:
                continue
            name, host = parts[0].upper(), parts[1]

        if name == base_reflector and host:
            return host
    return None


def resolve_reflector_host(reflector: str, data_dir: Path = DATA_DIR) -> tuple[str | None, str | None]:
    base = _base_reflector(reflector)
    if not base:
        return None, None

    host = _host_from_file(base, data_dir)
    if not host:
        return None, None

    try:
        infos = socket.getaddrinfo(host, None, socket.AF_INET, socket.SOCK_STREAM)
        ip = infos[0][4][0] if infos else None
    except socket.gaierror:
        ip = None
    return host, ip


def _probe_ports() -> list[int]:
    raw = os.getenv("PP5CI_HOTSPOT_REFLECTOR_PROBE_PORTS", "443,80")
    result: list[int] = []
    for value in raw.split(","):
        try:
            port = int(value.strip())
        except ValueError:
            continue
        if 1 <= port <= 65535 and port not in result:
            result.append(port)
    return result or [443, 80]


def probe_host(
    host: str,
    ports: list[int] | tuple[int, ...],
    timeout: float = PROBE_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    last_ip: str | None = None
    last_port: int | None = None

    for port in ports:
        last_port = int(port)
        try:
            infos = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)
        except socket.gaierror:
            continue

        for family, socktype, proto, _canonname, sockaddr in infos:
            last_ip = sockaddr[0]
            sock = socket.socket(family, socktype, proto)
            sock.settimeout(timeout)
            started = time.perf_counter()
            try:
                result = sock.connect_ex(sockaddr)
                elapsed = (time.perf_counter() - started) * 1000.0
            except OSError:
                result = -1
                elapsed = (time.perf_counter() - started) * 1000.0
            finally:
                sock.close()

            if result in REACHABLE_CONNECT_RESULTS:
                return {
                    "success": True,
                    "rtt_ms": round(elapsed, 3),
                    "ip": last_ip,
                    "port": last_port,
                }

    return {
        "success": False,
        "rtt_ms": None,
        "ip": last_ip,
        "port": last_port,
    }


class NetworkMonitor:
    def __init__(self) -> None:
        self._last_prune = 0.0
        self._direct_callsign: str | None = None
        self._direct_until = 0.0

    def _traffic_target(self) -> tuple[str | None, dict[str, Any] | None]:
        state = db.get_runtime_state_fast()
        active = state.get("state") == "active"
        route_type = str(state.get("route_type") or "").lower()
        contact = str(state.get("contact_callsign") or "").strip().upper() or None
        now = time.monotonic()

        if active and route_type == "callsign" and contact:
            self._direct_callsign = contact
            self._direct_until = now + DIRECT_HOLD_SECONDS
            return contact, get_ircddb_user(contact)

        if active and route_type != "callsign":
            self._direct_callsign = None
            self._direct_until = 0.0
            return None, None

        if self._direct_callsign and now < self._direct_until:
            return self._direct_callsign, get_ircddb_user(self._direct_callsign)

        self._direct_callsign = None
        self._direct_until = 0.0
        return None, None

    def _store_probe(
        self,
        target: str,
        host: str,
        ports: list[int] | tuple[int, ...],
        reflector: str | None = None,
        callsign: str | None = None,
        timeout: float = PROBE_TIMEOUT_SECONDS,
    ) -> None:
        result = probe_host(host, ports, timeout=timeout)
        network_db.insert_sample(
            sampled_at=_now_iso(),
            target=target,
            reflector=reflector,
            callsign=callsign,
            host=host,
            ip=result.get("ip"),
            port=result.get("port"),
            success=bool(result.get("success")),
            rtt_ms=result.get("rtt_ms"),
        )

    def sample_once(self) -> None:
        direct_callsign, direct_endpoint = self._traffic_target()
        reflector = get_active_reflector()

        if direct_callsign:
            address = str((direct_endpoint or {}).get("address") or "").strip() or None
            if address:
                self._store_probe(
                    "direct",
                    address,
                    list(DIRECT_PROBE_PORTS) or [40000, 443, 80, 22],
                    callsign=direct_callsign,
                    timeout=DIRECT_PROBE_TIMEOUT_SECONDS,
                )
            else:
                network_db.insert_sample(
                    sampled_at=_now_iso(),
                    target="direct",
                    callsign=direct_callsign,
                    host=None,
                    ip=None,
                    port=None,
                    success=False,
                    rtt_ms=None,
                )
        elif reflector:
            host, resolved_ip = resolve_reflector_host(reflector)
            if host:
                self._store_probe("reflector", host, _probe_ports(), reflector)
            else:
                network_db.insert_sample(
                    sampled_at=_now_iso(),
                    target="reflector",
                    reflector=reflector,
                    host=None,
                    ip=resolved_ip,
                    port=None,
                    success=False,
                    rtt_ms=None,
                )

        self._store_probe("internet", INTERNET_PROBE_HOST, [INTERNET_PROBE_PORT])

        now = time.monotonic()
        if now - self._last_prune >= 3600:
            network_db.prune(RETENTION_DAYS)
            self._last_prune = now

    def run(self, stop_event: threading.Event) -> None:
        network_db.initialise()
        while not stop_event.is_set():
            started = time.monotonic()
            try:
                self.sample_once()
            except Exception:
                # Network telemetry must never interrupt the D-Star collector.
                pass
            elapsed = time.monotonic() - started
            stop_event.wait(max(0.2, PROBE_INTERVAL_SECONDS - elapsed))
