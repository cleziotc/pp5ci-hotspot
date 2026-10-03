from __future__ import annotations

import configparser
import csv
import io
import os
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from starlette.concurrency import run_in_threadpool

from .admin import require_admin, run_admin_helper
from .config import DSTARGATEWAY_CFG, MMDVMHOST_INI, load_effective_config
from .db import (
    directory_summary,
    get_metadata,
    replace_callsign_directory,
    set_metadata,
)

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])

DATA_DIR = Path(os.getenv("PP5CI_HOTSPOT_DSTAR_DATA_DIR", "/usr/local/share/dstargateway.d"))
HOST_TIMER_DROPIN = Path("/etc/systemd/system/pp5ci-hotspot-hosts-update.timer.d/schedule.conf")

HOST_SOURCES = {
    "DPlus": {
        "file": "DPlus_Hosts.txt",
        "url": "https://www.pistar.uk/downloads/DPlus_Hosts.txt",
        "prefix": "REF",
    },
    "DExtra": {
        "file": "DExtra_Hosts.txt",
        "url": "https://www.pistar.uk/downloads/DExtra_Hosts.txt",
        "prefix": "XRF",
    },
    "DCS": {
        "file": "DCS_Hosts.txt",
        "url": "https://www.pistar.uk/downloads/DCS_Hosts.txt",
        "prefix": "DCS",
    },
    "XLX": {
        "file": "XLXHosts.txt",
        "url": "https://www.pistar.uk/downloads/XLXHosts.txt",
        "prefix": "XLX",
    },
}
XLX_GATEWAY_URL = "http://xlxapi.rlx.lu/api.php?do=GetXLXDMRMaster"
MAX_CSV_BYTES = 500 * 1024 * 1024
CSV_SAMPLE_BYTES = 64 * 1024


def _read_ini(path: Path) -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    if path.exists():
        parser.read(path, encoding="utf-8")
    return parser


def _value(parser: configparser.ConfigParser, section: str, key: str, default: str = "") -> str:
    try:
        return parser.get(section, key)
    except (configparser.Error, KeyError):
        return default


def _bool(parser: configparser.ConfigParser, section: str, key: str, default: bool = False) -> bool:
    value = _value(parser, section, key, "true" if default else "false").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _int(value: str, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _float(value: str, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _iso_mtime(path: Path) -> str | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat().replace("+00:00", "Z")
    except OSError:
        return None


def _parse_host_line(protocol: str, line: str) -> tuple[str, str] | None:
    text = line.strip()
    if not text or text.startswith("#"):
        return None

    if protocol == "XLX":
        parts = [part.strip() for part in text.split(";")]
        if len(parts) < 2 or not parts[0]:
            return None
        return f"XLX{parts[0].upper()}", parts[1]

    parts = text.split()
    if len(parts) < 2:
        return None
    return parts[0].upper(), parts[1]


def _read_hosts(protocol: str) -> list[dict[str, str]]:
    source = HOST_SOURCES[protocol]
    path = DATA_DIR / source["file"]
    items: dict[str, dict[str, str]] = {}
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            parsed = _parse_host_line(protocol, line)
            if not parsed:
                continue
            name, host = parsed
            if not name.startswith(source["prefix"]):
                continue
            items.setdefault(name, {"name": name, "host": host, "protocol": protocol})
    except OSError:
        return []
    return list(items.values())


def _host_status() -> list[dict[str, Any]]:
    result = []
    for protocol, source in HOST_SOURCES.items():
        path = DATA_DIR / source["file"]
        result.append({
            "protocol": protocol,
            "path": str(path),
            "url": source["url"],
            "count": len(_read_hosts(protocol)),
            "updated_at": _iso_mtime(path),
            "available": path.exists(),
        })
    return result


def _reflector_parts(raw: str) -> tuple[str, str]:
    clean = raw.strip().upper()
    if not clean:
        return "", "A"
    match = re.match(r"^((?:REF|XRF|DCS|XLX)[0-9A-Z]{3})\s*([A-Z])?$", clean)
    if not match:
        return clean, "A"
    return match.group(1), match.group(2) or "A"


def _hosts_schedule() -> str:
    try:
        text = HOST_TIMER_DROPIN.read_text(encoding="utf-8")
        match = re.search(r"OnCalendar=\*-\*-\*\s+(\d{2}:\d{2}):\d{2}", text)
        if match:
            return match.group(1)
    except OSError:
        pass
    return "03:00"


def _metadata_bool(key: str, default: bool) -> bool:
    value = get_metadata(key)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


@router.get("")
def settings() -> dict[str, Any]:
    host_cfg = _read_ini(MMDVMHOST_INI)
    gateway_cfg = _read_ini(DSTARGATEWAY_CFG)
    effective = load_effective_config()

    reflector, reflector_module = _reflector_parts(_value(gateway_cfg, "Repeater_1", "reflector", ""))

    return {
        "admin_required": True,
        "general": {
            "callsign": effective["callsign"],
            "hotspot_name": get_metadata("settings_hotspot_name", "PP5CI Hotspot Hotspot"),
            "city": get_metadata("settings_city", ""),
            "grid": get_metadata("settings_grid", ""),
        },
        "mmdvmhost": {
            "module": effective["module"],
            "rx_frequency_hz": effective["rx_frequency_hz"],
            "tx_frequency_hz": effective["tx_frequency_hz"],
            "rx_offset_hz": _int(_value(host_cfg, "Modem", "RXOffset", "0")),
            "tx_offset_hz": _int(_value(host_cfg, "Modem", "TXOffset", "0")),
            "rf_level_percent": effective["rf_level_percent"],
            "rx_level_percent": effective["rx_level_percent"],
            "dstar_tx_level_percent": effective["dstar_tx_level_percent"],
            "uart_port": effective["uart_port"],
            "uart_speed": effective["uart_speed"],
            "rssi_mapping_file": _value(host_cfg, "Modem", "RSSIMappingFile", ""),
            "mqtt_host": effective["mqtt_host"],
            "mqtt_port": effective["mqtt_port"],
            "mqtt_name": effective["mqtt_name"],
        },
        "dstargateway": {
            "gateway_address": _value(gateway_cfg, "Gateway", "hbAddress", "127.0.0.1"),
            "gateway_port": _int(_value(gateway_cfg, "Gateway", "hbPort", "20010"), 20010),
            "repeater_address": _value(gateway_cfg, "Repeater_1", "address", "127.0.0.1"),
            "repeater_port": _int(_value(gateway_cfg, "Repeater_1", "port", "20011"), 20011),
            "repeater_module": _value(gateway_cfg, "Repeater_1", "band", effective["module"]),
            "frequency_mhz": _float(_value(gateway_cfg, "Repeater_1", "frequency", "0"), 0.0),
            "reflector": reflector,
            "reflector_module": reflector_module,
            "reflector_at_startup": _bool(gateway_cfg, "Repeater_1", "reflectorAtStartup", False),
            "reflector_reconnect": _value(gateway_cfg, "Repeater_1", "reflectorReconnect", "never"),
            "language": _value(gateway_cfg, "Gateway", "language", "portugues"),
            "ircddb_enabled": _bool(gateway_cfg, "ircddb_1", "enabled", True),
            "ircddb_hostname": _value(gateway_cfg, "ircddb_1", "hostname", "ircv4.openquad.net") or "ircv4.openquad.net",
            "ircddb_username": _value(gateway_cfg, "ircddb_1", "username", effective["callsign"]) or effective["callsign"],
            "dextra_enabled": _bool(gateway_cfg, "DExtra", "enabled", False),
            "dplus_enabled": _bool(gateway_cfg, "DPlus", "enabled", False),
            "dcs_enabled": _bool(gateway_cfg, "DCS", "enabled", False),
            "xlx_enabled": _bool(gateway_cfg, "XLX", "enabled", False),
            "xlx_hostfile_url": _value(gateway_cfg, "XLX", "hostfileUrl", XLX_GATEWAY_URL) or XLX_GATEWAY_URL,
        },
        "hosts": {
            "schedule": _hosts_schedule(),
            "files": _host_status(),
            "xlx_gateway_url": XLX_GATEWAY_URL,
        },
        "users": directory_summary(),
        "dashboard": {
            "refresh_seconds": _int(get_metadata("settings_dashboard_refresh", "5"), 5),
            "last_heard_limit": _int(get_metadata("settings_dashboard_last_heard", "8"), 8),
            "theme": get_metadata("settings_dashboard_theme", "dark"),
            "language": get_metadata("settings_dashboard_language", "pt-BR"),
            "show_diagnostics": _metadata_bool("settings_dashboard_show_diagnostics", True),
            "show_activity": _metadata_bool("settings_dashboard_show_activity", True),
            "show_uptime": _metadata_bool("settings_dashboard_show_uptime", True),
        },
    }


@router.post("/admin/check", dependencies=[Depends(require_admin)])
def admin_check() -> dict[str, bool]:
    return {"ok": True}


@router.get("/reflectors")
def reflectors(
    q: str = Query(default="", max_length=32),
    protocol: str = Query(default="all", pattern="^(all|DPlus|DExtra|DCS|XLX)$"),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    query = q.strip().upper()
    protocols = list(HOST_SOURCES) if protocol == "all" else [protocol]
    items: list[dict[str, str]] = []
    for name in protocols:
        for item in _read_hosts(name):
            if query and query not in item["name"] and query.lower() not in item["host"].lower():
                continue
            items.append(item)
    items.sort(key=lambda item: (item["name"], item["protocol"]))
    return {"items": items[:limit], "total": len(items)}


def _save_general(values: dict[str, Any], restart: bool) -> dict[str, Any]:
    name = str(values.get("hotspot_name", "")).strip()[:80]
    city = str(values.get("city", "")).strip()[:120]
    grid = str(values.get("grid", "")).strip().upper()[:12]
    set_metadata("settings_hotspot_name", name or "PP5CI Hotspot Hotspot")
    set_metadata("settings_city", city)
    set_metadata("settings_grid", grid)

    callsign = str(values.get("callsign", "")).strip().upper()
    return run_admin_helper("apply", {
        "section": "general",
        "restart": restart,
        "values": {"callsign": callsign},
    })


def _save_dashboard(values: dict[str, Any]) -> dict[str, Any]:
    refresh = max(1, min(_int(str(values.get("refresh_seconds", 5)), 5), 60))
    last_heard = max(4, min(_int(str(values.get("last_heard_limit", 8)), 8), 30))
    theme = str(values.get("theme", "dark"))
    language = str(values.get("language", "pt-BR"))
    if theme != "dark":
        raise HTTPException(status_code=400, detail="Only the dark theme is available in this release")
    if language != "pt-BR":
        raise HTTPException(status_code=400, detail="Only pt-BR is available in this release")

    set_metadata("settings_dashboard_refresh", str(refresh))
    set_metadata("settings_dashboard_last_heard", str(last_heard))
    set_metadata("settings_dashboard_theme", theme)
    set_metadata("settings_dashboard_language", language)
    for key in ("show_diagnostics", "show_activity", "show_uptime"):
        set_metadata(f"settings_dashboard_{key}", "1" if bool(values.get(key, True)) else "0")
    return {"ok": True, "restart": False}


@router.post("/apply/{section}", dependencies=[Depends(require_admin)])
def apply_settings(section: str, payload: dict[str, Any]) -> dict[str, Any]:
    values = payload.get("values") if isinstance(payload.get("values"), dict) else payload
    restart = bool(payload.get("restart", False))

    if section == "general":
        return _save_general(values, restart)
    if section in {"mmdvmhost", "dstargateway"}:
        return run_admin_helper("apply", {
            "section": section,
            "restart": restart,
            "values": values,
        })
    if section == "hosts":
        schedule = str(values.get("schedule", "03:00")).strip()
        return run_admin_helper("set-hosts-schedule", {"schedule": schedule})
    if section == "dashboard":
        return _save_dashboard(values)
    raise HTTPException(status_code=404, detail="Unknown settings section")


@router.post("/hosts/update", dependencies=[Depends(require_admin)])
def update_hosts() -> dict[str, Any]:
    return run_admin_helper("update-hosts", {"restart": True}, timeout=90)


CALLSIGN_ALIASES = ("callsign", "call", "indicativo")
NAME_ALIASES = ("name", "nome")
LOCATION_ALIASES = ("location", "local", "qth", "city", "cidade")
STATE_ALIASES = ("state", "estado", "uf", "province", "provincia", "state_province")


def _normalize_column(name: str) -> str:
    value = unicodedata.normalize("NFKD", name)
    value = "".join(char for char in value if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def _column_map(fieldnames: list[str]) -> dict[str, str]:
    normalized = {_normalize_column(name): name for name in fieldnames if name}
    result: dict[str, str] = {}
    for target, aliases in (
        ("callsign", CALLSIGN_ALIASES),
        ("name", NAME_ALIASES),
        ("location", LOCATION_ALIASES),
        ("state", STATE_ALIASES),
    ):
        for alias in aliases:
            if alias in normalized:
                result[target] = normalized[alias]
                break
    return result


def _format_location(location: str, state: str) -> str:
    location = location.strip()
    state = state.strip()

    if not location:
        return state[:160]
    if not state:
        return location[:160]

    # Do not duplicate the state when a Location/QTH field already contains it.
    tokens = [token for token in re.split(r"[\s,;/\-]+", location.upper()) if token]
    if state.upper() in tokens:
        return location[:160]

    return f"{location} - {state}"[:160]


def _import_csv_file(binary_file: Any, filename: str) -> dict[str, Any]:
    binary_file.seek(0, os.SEEK_END)
    size = binary_file.tell()
    binary_file.seek(0)
    if size > MAX_CSV_BYTES:
        raise HTTPException(status_code=413, detail="CSV maior que 500 MB")

    imported_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    # UTF-8 is preferred.  If a later row proves the file is Latin-1, the
    # SQLite staging transaction rolls back and the import is retried safely.
    last_error: UnicodeDecodeError | None = None
    for encoding in ("utf-8-sig", "latin-1"):
        binary_file.seek(0)
        wrapper: io.TextIOWrapper | None = None
        try:
            wrapper = io.TextIOWrapper(binary_file, encoding=encoding, errors="strict", newline="")
            sample = wrapper.read(CSV_SAMPLE_BYTES)
            wrapper.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
            except csv.Error:
                dialect = csv.excel

            reader = csv.DictReader(wrapper, dialect=dialect)
            if not reader.fieldnames:
                raise HTTPException(status_code=400, detail="CSV sem cabeçalho")

            columns = _column_map(reader.fieldnames)
            if "callsign" not in columns:
                raise HTTPException(status_code=400, detail="CSV precisa ter uma coluna Callsign/Call/Indicativo")

            def records():
                for row in reader:
                    callsign = str(row.get(columns["callsign"], "") or "").strip().upper()
                    if not re.fullmatch(r"[A-Z0-9/\-]{3,16}", callsign):
                        continue
                    location = str(row.get(columns.get("location", ""), "") or "")
                    state = str(row.get(columns.get("state", ""), "") or "")
                    yield {
                        "callsign": callsign,
                        "name": str(row.get(columns.get("name", ""), "") or "").strip()[:120],
                        "location": _format_location(location, state),
                    }

            try:
                count = replace_callsign_directory(records(), imported_at, filename)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

            detected = sorted(columns)
            return {
                "ok": True,
                "count": count,
                "imported_at": imported_at,
                "source_file": filename,
                "detected_columns": detected,
            }
        except UnicodeDecodeError as exc:
            last_error = exc
            continue
        finally:
            if wrapper is not None:
                try:
                    wrapper.detach()
                except Exception:
                    pass
            binary_file.seek(0)

    raise HTTPException(status_code=400, detail=f"Não foi possível decodificar o CSV: {last_error}")


@router.post("/users/import", dependencies=[Depends(require_admin)])
async def import_users(file: UploadFile = File(...)) -> dict[str, Any]:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Selecione um arquivo .csv")

    return await run_in_threadpool(_import_csv_file, file.file, file.filename)
