from __future__ import annotations

import configparser
import os
from pathlib import Path
from typing import Any

CONFIG_DIR = Path(os.getenv("PP5CI_HOTSPOT_CONFIG_DIR", "/etc/pp5ci-hotspot"))
MMDVMHOST_INI = CONFIG_DIR / "MMDVM-Host.ini"
DSTARGATEWAY_CFG = CONFIG_DIR / "DStarGateway.cfg"


def _read_ini(path: Path) -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    if path.exists():
        parser.read(path, encoding="utf-8")
    return parser


def _get(parser: configparser.ConfigParser, section: str, key: str, default: str = "") -> str:
    try:
        return parser.get(section, key)
    except (configparser.Error, KeyError):
        return default


def _number(value: str, kind: type[int] | type[float], default: int | float) -> int | float:
    try:
        return kind(value)
    except (TypeError, ValueError):
        return default


def load_effective_config() -> dict[str, Any]:
    host = _read_ini(MMDVMHOST_INI)
    gateway = _read_ini(DSTARGATEWAY_CFG)

    callsign = _get(host, "General", "Callsign", _get(gateway, "Gateway", "callsign", ""))
    module = _get(host, "D-Star", "Module", _get(gateway, "Repeater_1", "band", "A"))
    rx_hz = int(_number(_get(host, "Modem", "RXFrequency", "0"), int, 0))
    tx_hz = int(_number(_get(host, "Modem", "TXFrequency", "0"), int, 0))

    return {
        "callsign": callsign.strip(),
        "module": module.strip() or "A",
        "rx_frequency_hz": rx_hz,
        "tx_frequency_hz": tx_hz,
        "uart_port": _get(host, "Modem", "UARTPort", ""),
        "uart_speed": int(_number(_get(host, "Modem", "UARTSpeed", "115200"), int, 115200)),
        "rf_level_percent": float(_number(_get(host, "Modem", "RFLevel", "0"), float, 0)),
        "rx_level_percent": float(_number(_get(host, "Modem", "RXLevel", "0"), float, 0)),
        "dstar_tx_level_percent": float(_number(_get(host, "Modem", "D-StarTXLevel", _get(host, "Modem", "TXLevel", "0")), float, 0)),
        "gateway_address": _get(host, "D-Star Network", "GatewayAddress", "127.0.0.1"),
        "gateway_port": int(_number(_get(host, "D-Star Network", "GatewayPort", "20010"), int, 20010)),
        "local_address": _get(host, "D-Star Network", "LocalAddress", "127.0.0.1"),
        "local_port": int(_number(_get(host, "D-Star Network", "LocalPort", "20011"), int, 20011)),
        "mqtt_host": _get(host, "MQTT", "Host", "127.0.0.1"),
        "mqtt_port": int(_number(_get(host, "MQTT", "Port", "1883"), int, 1883)),
        "mqtt_name": _get(host, "MQTT", "Name", "mmdvm"),
        "gateway_type": _get(gateway, "Gateway", "type", "hotspot"),
        "ircddb_enabled": _get(gateway, "ircddb_1", "enabled", "false").strip().lower() in {"1", "true", "yes", "on"},
        "ircddb_hostname": _get(gateway, "ircddb_1", "hostname", "ircv4.openquad.net").strip() or "ircv4.openquad.net",
        "ircddb_username": _get(gateway, "ircddb_1", "username", callsign).strip() or callsign.strip(),
    }
