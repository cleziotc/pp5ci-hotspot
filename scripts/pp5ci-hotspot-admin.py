#!/usr/bin/env python3
from __future__ import annotations

import configparser
import ipaddress
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CONFIG_DIR = Path("/etc/pp5ci-hotspot")
MMDVMHOST_INI = CONFIG_DIR / "MMDVM-Host.ini"
DSTARGATEWAY_CFG = CONFIG_DIR / "DStarGateway.cfg"
DATA_DIR = Path("/usr/local/share/dstargateway.d")
HOST_STATUS = Path("/var/lib/pp5ci-hotspot/hosts-status.json")
TIMER_DROPIN = Path("/etc/systemd/system/pp5ci-hotspot-hosts-update.timer.d/schedule.conf")
UPDATER = Path("/usr/local/libexec/pp5ci-hotspot-updater")
RELEASES_DIR = Path("/var/lib/pp5ci-hotspot/releases")

XLX_GATEWAY_URL = "http://xlxapi.rlx.lu/api.php?do=GetXLXDMRMaster"
HOST_SOURCES = {
    "DPlus": ("https://www.pistar.uk/downloads/DPlus_Hosts.txt", "DPlus_Hosts.txt", "REF", 20),
    "DExtra": ("https://www.pistar.uk/downloads/DExtra_Hosts.txt", "DExtra_Hosts.txt", "XRF", 20),
    "DCS": ("https://www.pistar.uk/downloads/DCS_Hosts.txt", "DCS_Hosts.txt", "DCS", 20),
    "XLX": ("https://www.pistar.uk/downloads/XLXHosts.txt", "XLXHosts.txt", "", 20),
}

RECONNECT_VALUES = {"never", "fixed", "5", "10", "15", "20", "25", "30", "60", "90", "120", "180"}
LANGUAGES = {
    "english_uk", "deutsch", "dansk", "francais", "italiano", "polski",
    "english_us", "espanol", "svenska", "nederlands_nl", "nederlands_be",
    "norsk", "portugues",
}


def fail(message: str, code: int = 2) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(code)


def payload() -> dict[str, Any]:
    try:
        raw = sys.stdin.read()
        return json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        fail(f"JSON inválido: {exc}")
    return {}


def read_ini(path: Path) -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    if not path.exists():
        fail(f"Configuração não encontrada: {path}")
    parser.read(path, encoding="utf-8")
    return parser


def set_value(parser: configparser.ConfigParser, section: str, key: str, value: Any) -> None:
    if not parser.has_section(section):
        parser.add_section(section)
    parser.set(section, key, str(value))


def backup(path: Path, stamp: str) -> None:
    if path.exists():
        shutil.copy2(path, path.with_name(path.name + f".bak.settings.{stamp}"))


def atomic_write_ini(path: Path, parser: configparser.ConfigParser) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            parser.write(handle, space_around_delimiters=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp_name, 0o644)
        os.replace(tmp_name, path)
    finally:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def number(value: Any, minimum: float, maximum: float, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        fail(f"{label}: valor inválido")
    if not minimum <= result <= maximum:
        fail(f"{label}: deve estar entre {minimum} e {maximum}")
    return result


def integer(value: Any, minimum: int, maximum: int, label: str) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError):
        fail(f"{label}: valor inválido")
    if not minimum <= result <= maximum:
        fail(f"{label}: deve estar entre {minimum} e {maximum}")
    return result


def valid_callsign(value: Any) -> str:
    callsign = str(value or "").strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{3,7}", callsign):
        fail("Indicativo inválido")
    return callsign


def valid_module(value: Any, label: str = "Módulo") -> str:
    module = str(value or "").strip().upper()
    if not re.fullmatch(r"[A-Z]", module):
        fail(f"{label}: use uma letra de A a Z")
    return module


def valid_address(value: Any, label: str) -> str:
    address = str(value or "").strip()
    try:
        ipaddress.ip_address(address)
    except ValueError:
        if not re.fullmatch(r"[A-Za-z0-9.-]{1,253}", address):
            fail(f"{label}: endereço inválido")
    return address


def reflector_value(base: Any, module: Any) -> tuple[str, str]:
    name = str(base or "").strip().upper()
    if not name:
        return "", ""
    if not re.fullmatch(r"(?:REF|XRF|DCS|XLX)[0-9A-Z]{3}", name):
        fail("Refletor inválido. Use REFxxx, XRFxxx, DCSxxx ou XLXxxx")
    mod = valid_module(module, "Módulo do refletor")
    return name, f"{name:<7}{mod}"


def restart_services(names: list[str]) -> None:
    order = ["polar-dstargateway.service", "pp5ci-hotspot-host.service"]
    selected = [name for name in order if name in names]
    for name in selected:
        proc = subprocess.run(["systemctl", "restart", name], text=True, capture_output=True, check=False)
        if proc.returncode != 0:
            fail(f"Falha ao reiniciar {name}: {(proc.stderr or proc.stdout).strip()}")


def apply_settings(data: dict[str, Any]) -> dict[str, Any]:
    section = str(data.get("section", ""))
    values = data.get("values") if isinstance(data.get("values"), dict) else {}
    do_restart = as_bool(data.get("restart", False))

    host = read_ini(MMDVMHOST_INI)
    gateway = read_ini(DSTARGATEWAY_CFG)
    host_changed = False
    gateway_changed = False

    if section == "general":
        callsign = valid_callsign(values.get("callsign"))
        set_value(host, "General", "Callsign", callsign)
        set_value(gateway, "Gateway", "callsign", callsign)
        set_value(gateway, "Repeater_1", "callsign", callsign)
        set_value(gateway, "DPlus", "login", callsign)
        set_value(gateway, "ircddb_1", "username", callsign)
        host_changed = gateway_changed = True

    elif section == "mmdvmhost":
        module = valid_module(values.get("module"))
        rx = integer(values.get("rx_frequency_hz"), 100000, 1500000000, "RX Frequency")
        tx = integer(values.get("tx_frequency_hz"), 100000, 1500000000, "TX Frequency")
        rx_offset = integer(values.get("rx_offset_hz", 0), -200000, 200000, "RX Offset")
        tx_offset = integer(values.get("tx_offset_hz", 0), -200000, 200000, "TX Offset")
        rf_level = number(values.get("rf_level_percent"), 0, 100, "RF Level")
        rx_level = number(values.get("rx_level_percent"), 0, 100, "RX Level")
        dstar_tx = number(values.get("dstar_tx_level_percent"), 0, 100, "D-Star TX Level")
        uart_port = str(values.get("uart_port", "")).strip()
        if not uart_port.startswith("/dev/"):
            fail("UART Device deve apontar para /dev/...")
        uart_speed = integer(values.get("uart_speed", 115200), 1200, 1000000, "UART Baudrate")

        for key, value in {
            "RXFrequency": rx,
            "TXFrequency": tx,
            "RXOffset": rx_offset,
            "TXOffset": tx_offset,
            "RFLevel": f"{rf_level:g}",
            "RXLevel": f"{rx_level:g}",
            "D-StarTXLevel": f"{dstar_tx:g}",
            "UARTPort": uart_port,
            "UARTSpeed": uart_speed,
        }.items():
            set_value(host, "Modem", key, value)
        set_value(host, "D-Star", "Module", module)

        # Keep the gateway repeater side consistent with MMDVMHost.
        set_value(gateway, "Repeater_1", "band", module)
        set_value(gateway, "Repeater_1", "frequency", f"{rx / 1_000_000:.6f}")
        host_changed = gateway_changed = True

    elif section == "dstargateway":
        repeater_module = valid_module(values.get("repeater_module"))
        gateway_address = valid_address(values.get("gateway_address", "127.0.0.1"), "Gateway Address")
        gateway_port = integer(values.get("gateway_port", 20010), 1, 65535, "Gateway Port")
        repeater_address = valid_address(values.get("repeater_address", "127.0.0.1"), "Repeater Address")
        repeater_port = integer(values.get("repeater_port", 20011), 1, 65535, "Repeater Port")
        frequency = number(values.get("frequency_mhz", 434.0), 0.1, 1500.0, "Frequency")
        reconnect = str(values.get("reflector_reconnect", "never")).strip()
        if reconnect not in RECONNECT_VALUES:
            fail("Reflector Reconnect inválido")
        language = str(values.get("language", "portugues")).strip().lower()
        if language not in LANGUAGES:
            fail("Idioma do DStarGateway inválido")

        reflector_base, reflector = reflector_value(
            values.get("reflector", ""),
            values.get("reflector_module", "A"),
        )
        at_startup = bool(reflector_base) and as_bool(values.get("reflector_at_startup", False))

        set_value(gateway, "Gateway", "hbAddress", gateway_address)
        set_value(gateway, "Gateway", "hbPort", gateway_port)
        set_value(host, "D-Star Network", "GatewayAddress", gateway_address)
        set_value(host, "D-Star Network", "GatewayPort", gateway_port)
        set_value(host, "D-Star Network", "LocalAddress", repeater_address)
        set_value(host, "D-Star Network", "LocalPort", repeater_port)
        set_value(gateway, "Gateway", "language", language)
        set_value(gateway, "Repeater_1", "address", repeater_address)
        set_value(gateway, "Repeater_1", "port", repeater_port)
        set_value(gateway, "Repeater_1", "band", repeater_module)
        set_value(gateway, "Repeater_1", "frequency", f"{frequency:.6f}")
        set_value(gateway, "Repeater_1", "reflector", reflector)
        set_value(gateway, "Repeater_1", "reflectorAtStartup", str(at_startup).lower())
        set_value(gateway, "Repeater_1", "reflectorReconnect", reconnect)

        ircddb_enabled = as_bool(values.get("ircddb_enabled", True))
        ircddb_hostname = valid_address(values.get("ircddb_hostname", "ircv4.openquad.net"), "ircDDB Hostname")
        ircddb_username = valid_callsign(
            values.get("ircddb_username")
            or gateway.get("Gateway", "callsign", fallback="")
        )
        set_value(gateway, "ircddb_1", "enabled", str(ircddb_enabled).lower())
        set_value(gateway, "ircddb_1", "hostname", ircddb_hostname)
        set_value(gateway, "ircddb_1", "username", ircddb_username)
        set_value(gateway, "ircddb_1", "password", "")

        dextra = as_bool(values.get("dextra_enabled", False))
        dplus = as_bool(values.get("dplus_enabled", False))
        dcs = as_bool(values.get("dcs_enabled", False))
        xlx = as_bool(values.get("xlx_enabled", False))
        if reflector_base.startswith("REF"):
            dplus = True
        elif reflector_base.startswith("XRF"):
            dextra = True
        elif reflector_base.startswith("DCS"):
            dcs = True
        elif reflector_base.startswith("XLX"):
            dcs = True
            xlx = True

        set_value(gateway, "DExtra", "enabled", str(dextra).lower())
        set_value(gateway, "DPlus", "enabled", str(dplus).lower())
        set_value(gateway, "DCS", "enabled", str(dcs).lower())
        set_value(gateway, "XLX", "enabled", str(xlx).lower())
        xlx_url = str(values.get("xlx_hostfile_url", XLX_GATEWAY_URL)).strip() or XLX_GATEWAY_URL
        if not re.match(r"^https?://", xlx_url):
            fail("XLX hostfile URL deve ser http:// ou https://")
        set_value(gateway, "XLX", "hostfileUrl", xlx_url)

        # The local repeater module must match the host module.
        set_value(host, "D-Star", "Module", repeater_module)
        gateway_changed = host_changed = True

    else:
        fail("Seção de configuração desconhecida")

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    if host_changed:
        backup(MMDVMHOST_INI, stamp)
        atomic_write_ini(MMDVMHOST_INI, host)
    if gateway_changed:
        backup(DSTARGATEWAY_CFG, stamp)
        atomic_write_ini(DSTARGATEWAY_CFG, gateway)

    restarted: list[str] = []
    if do_restart:
        if gateway_changed:
            restarted.append("polar-dstargateway.service")
        if host_changed:
            restarted.append("pp5ci-hotspot-host.service")
        restart_services(restarted)

    return {
        "ok": True,
        "section": section,
        "saved": True,
        "restarted": restarted,
        "backup_stamp": stamp,
    }


def count_entries(protocol: str, text: str) -> int:
    count = 0
    for line in text.splitlines():
        clean = line.strip()
        if not clean or clean.startswith("#"):
            continue
        if protocol == "XLX":
            parts = clean.split(";")
            if len(parts) >= 2 and parts[0].strip():
                count += 1
        else:
            parts = clean.split()
            if len(parts) >= 2:
                count += 1
    return count


def update_hosts(data: dict[str, Any]) -> dict[str, Any]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    result: dict[str, Any] = {}
    opener = urllib.request.build_opener()
    opener.addheaders = [("User-Agent", "N0CALL-Hotspot/0.2")]

    for protocol, (url, filename, _prefix, minimum) in HOST_SOURCES.items():
        try:
            with opener.open(url, timeout=20) as response:
                raw = response.read(2 * 1024 * 1024)
            text = raw.decode("utf-8", errors="replace")
            count = count_entries(protocol, text)
            if count < minimum:
                raise RuntimeError(f"arquivo contém somente {count} entradas")
            target = DATA_DIR / filename
            fd, tmp_name = tempfile.mkstemp(prefix=filename + ".", dir=str(DATA_DIR))
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(raw)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.chmod(tmp_name, 0o644)
                os.replace(tmp_name, target)
            finally:
                try:
                    os.unlink(tmp_name)
                except FileNotFoundError:
                    pass
            result[protocol] = {"ok": True, "count": count, "url": url, "path": str(target)}
        except Exception as exc:
            result[protocol] = {"ok": False, "error": str(exc), "url": url}

    updated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    status = {"updated_at": updated_at, "sources": result}
    HOST_STATUS.parent.mkdir(parents=True, exist_ok=True)
    HOST_STATUS.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(HOST_STATUS, 0o644)

    core_ok = all(result.get(name, {}).get("ok") for name in ("DPlus", "DExtra", "DCS"))
    if not core_ok:
        fail("Falha ao atualizar um ou mais host files principais: " + json.dumps(status, ensure_ascii=False), 1)

    restarted = False
    if as_bool(data.get("restart", True)):
        restart_services(["polar-dstargateway.service"])
        restarted = True

    return {"ok": True, "updated_at": updated_at, "sources": result, "gateway_restarted": restarted}


def set_hosts_schedule(data: dict[str, Any]) -> dict[str, Any]:
    schedule = str(data.get("schedule", "")).strip()
    match = re.fullmatch(r"([01]\d|2[0-3]):([0-5]\d)", schedule)
    if not match:
        fail("Horário inválido; use HH:MM")

    TIMER_DROPIN.parent.mkdir(parents=True, exist_ok=True)
    TIMER_DROPIN.write_text(
        "[Timer]\n"
        "OnCalendar=\n"
        f"OnCalendar=*-*-* {schedule}:00\n"
        "Persistent=true\n",
        encoding="utf-8",
    )
    os.chmod(TIMER_DROPIN, 0o644)

    subprocess.run(["systemctl", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "enable", "--now", "pp5ci-hotspot-hosts-update.timer"], check=True)
    subprocess.run(["systemctl", "restart", "pp5ci-hotspot-hosts-update.timer"], check=True)
    return {"ok": True, "schedule": schedule}


def restart_service(data: dict[str, Any]) -> dict[str, Any]:
    target = str(data.get("service", "")).strip().lower()
    units = {
        "mmdvmhost": "pp5ci-hotspot-host.service",
        "dstargateway": "polar-dstargateway.service",
    }
    unit = units.get(target)
    if not unit:
        fail("Serviço não permitido")

    proc = subprocess.run(["systemctl", "restart", unit], text=True, capture_output=True, check=False)
    if proc.returncode != 0:
        fail(f"Falha ao reiniciar {unit}: {(proc.stderr or proc.stdout).strip()}")

    show = subprocess.run(
        ["systemctl", "show", unit, "-p", "ActiveState", "-p", "SubState", "-p", "MainPID"],
        text=True,
        capture_output=True,
        check=False,
    )
    status: dict[str, str] = {}
    for line in show.stdout.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            status[key] = value

    return {
        "ok": status.get("ActiveState") == "active",
        "service": target,
        "unit": unit,
        "active": status.get("ActiveState", "unknown"),
        "sub": status.get("SubState", "unknown"),
        "pid": int(status.get("MainPID") or 0),
    }



def enable_ircddb(data: dict[str, Any]) -> dict[str, Any]:
    gateway = read_ini(DSTARGATEWAY_CFG)
    callsign = valid_callsign(gateway.get("Gateway", "callsign", fallback=""))
    hostname = str(data.get("hostname") or "ircv4.openquad.net").strip().lower()
    hostname = valid_address(hostname, "ircDDB Hostname")

    current = {
        "enabled": gateway.get("ircddb_1", "enabled", fallback="false").strip().lower(),
        "hostname": gateway.get("ircddb_1", "hostname", fallback="").strip().lower(),
        "username": gateway.get("ircddb_1", "username", fallback="").strip().upper(),
        "password": gateway.get("ircddb_1", "password", fallback=""),
        "log_ircddb": gateway.get("Log", "logIRCDDBTraffic", fallback="false").strip().lower(),
    }
    desired = {
        "enabled": "true",
        "hostname": hostname,
        "username": callsign,
        "password": "",
        "log_ircddb": "true",
    }

    changed = current != desired
    if changed:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup(DSTARGATEWAY_CFG, stamp)
        for key in ("enabled", "hostname", "username", "password"):
            set_value(gateway, "ircddb_1", key, desired[key])
        set_value(gateway, "Log", "logIRCDDBTraffic", "true")
        atomic_write_ini(DSTARGATEWAY_CFG, gateway)
        restart_services(["polar-dstargateway.service"])
    return {
        "ok": True,
        "changed": changed,
        "enabled": True,
        "hostname": hostname,
        "username": callsign,
        "logIRCDDBTraffic": True,
        "restarted": ["polar-dstargateway.service"] if changed else [],
    }


def _start_update_process(operation: str, argument: str) -> dict[str, Any]:
    if not UPDATER.exists():
        fail("Updater transacional não está instalado")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    unit = f"pp5ci-hotspot-update-{stamp}"
    proc = subprocess.run(
        [
            "systemd-run",
            f"--unit={unit}",
            "--collect",
            "--quiet",
            "--property=Type=exec",
            str(UPDATER),
            operation,
            argument,
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        fail(f"Falha ao iniciar operação: {(proc.stderr or proc.stdout).strip()}")
    return {"ok": True, "accepted": True, "operation": operation, "argument": argument, "unit": unit}


def start_update(data: dict[str, Any]) -> dict[str, Any]:
    tag = str(data.get("tag", "")).strip()
    if not re.fullmatch(r"v\d+\.\d+\.\d+", tag):
        fail("Tag de update inválida")
    return _start_update_process("install", tag)


def start_rollback(data: dict[str, Any]) -> dict[str, Any]:
    backup_id = str(data.get("backup_id", "")).strip()
    if not re.fullmatch(r"[0-9A-Za-z._-]+", backup_id):
        fail("Identificador de rollback inválido")
    if not (RELEASES_DIR / backup_id / "metadata.json").exists():
        fail("Backup de rollback não encontrado")
    return _start_update_process("rollback", backup_id)

def main() -> None:
    if os.geteuid() != 0:
        fail("pp5ci-hotspot-admin precisa executar como root")
    if len(sys.argv) != 2:
        fail("Uso: pp5ci-hotspot-admin {apply|update-hosts|set-hosts-schedule|restart-service|enable-ircddb|start-update|start-rollback}")

    command = sys.argv[1]
    data = payload()
    if command == "apply":
        result = apply_settings(data)
    elif command == "update-hosts":
        result = update_hosts(data)
    elif command == "set-hosts-schedule":
        result = set_hosts_schedule(data)
    elif command == "restart-service":
        result = restart_service(data)
    elif command == "enable-ircddb":
        result = enable_ircddb(data)
    elif command == "start-update":
        result = start_update(data)
    elif command == "start-rollback":
        result = start_rollback(data)
    else:
        fail("Comando não suportado")

    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
