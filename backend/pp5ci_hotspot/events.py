from __future__ import annotations

import json
import re
import threading
import time
from datetime import datetime, timezone
from typing import Any

from . import db
from .network_monitor import get_active_reflector, remember_ircddb_user_from_line

RF_HEADER_RE = re.compile(
    r"D-Star, received RF (?:header|late entry) from\s+(?P<station>[A-Z0-9]+)\s*/(?P<ext>[A-Z0-9]*)\s+to\s+(?P<destination>.+?)\s*$",
    re.IGNORECASE,
)
NET_HEADER_RE = re.compile(
    r"D-Star, received network header from\s+(?P<station>[A-Z0-9]+)\s*/(?P<ext>[A-Z0-9]*)\s+to\s+(?P<destination>.+?)\s*$",
    re.IGNORECASE,
)
SLOW_TEXT_RE = re.compile(
    r'D-Star, (?P<source>RF|network) slow data text = "(?P<text>.*)"',
    re.IGNORECASE,
)
G2_CALLSIGN_ROUTE_RE = re.compile(
    r"(?P<user>[A-Z0-9]+)\s+is trying to G2 route to callsign\s+(?P<contact>[A-Z0-9]+)",
    re.IGNORECASE,
)

PENDING_MAX_AGE = 8.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _idle_state(last: dict[str, Any] | None = None) -> dict[str, Any]:
    last = last or {}
    return {
        "state": "idle",
        "direction": None,
        "source": None,
        "started_at": None,
        "station": None,
        "src_ext": None,
        "destination": None,
        "reflector": last.get("reflector"),
        "duration_seconds": 0,
        "ber_percent": None,
        "rssi_dbm": None,
        "rssi": None,
        "slow_text": None,
        "route_type": None,
        "contact_callsign": None,
        "ber_updated_at": None,
        "rssi_updated_at": None,
    }


class EventProcessor:
    @staticmethod
    def _apply_route_context(state: dict[str, Any]) -> None:
        contact = db.direct_contact_callsign(
            state.get("source"),
            state.get("station"),
            state.get("destination"),
        )
        if contact:
            state["route_type"] = "callsign"
            state["contact_callsign"] = contact
            state["reflector"] = None
            return

        state["contact_callsign"] = None
        if not state.get("reflector"):
            state["reflector"] = db.normalise_reflector(get_active_reflector())
        state["route_type"] = db.route_type_for(state.get("reflector"), None)

    def __init__(self) -> None:
        db.initialise()
        self._lock = threading.RLock()
        self._pending: dict[str, dict[str, Any]] = {}

    def reset_runtime(self) -> None:
        with self._lock:
            db.set_runtime_state(_idle_state(db.get_runtime_state()), _now_iso())
            self._pending.clear()

    def process(self, payload: bytes | str) -> bool:
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8", errors="replace")
        try:
            event = json.loads(payload)
        except json.JSONDecodeError:
            return False

        with self._lock:
            if "D-Star" in event and isinstance(event["D-Star"], dict):
                return self._process_dstar(event["D-Star"])
            if "BER" in event and isinstance(event["BER"], dict):
                return self._process_metric("ber_percent", event["BER"])
            if "RSSI" in event and isinstance(event["RSSI"], dict):
                return self._process_metric("rssi_dbm", event["RSSI"])
            if "Text" in event and isinstance(event["Text"], dict):
                return self._process_metric("slow_text", event["Text"])
        return False

    def process_journal_line(self, line: str) -> bool:
        """Enrich structured MQTT events with fields published only in journald.

        Besides MMDVMHost header/slow-text enrichment, DStarGateway can publish
        ircDDB USER records with the gateway IPv4 address used for G2 routing.
        These records feed the network target cache used by direct-call telemetry.
        """
        if remember_ircddb_user_from_line(line):
            return True

        with self._lock:
            match = G2_CALLSIGN_ROUTE_RE.search(line)
            if match:
                return self._apply_or_queue(
                    "rf",
                    {
                        "station": match.group("user").strip().upper(),
                        "destination": match.group("contact").strip().upper(),
                    },
                )

            match = RF_HEADER_RE.search(line)
            if match:
                return self._apply_or_queue(
                    "rf",
                    {
                        "station": match.group("station").strip(),
                        "src_ext": match.group("ext").strip() or None,
                        "destination": match.group("destination").strip() or None,
                    },
                )

            match = NET_HEADER_RE.search(line)
            if match:
                return self._apply_or_queue(
                    "network",
                    {
                        "station": match.group("station").strip(),
                        "src_ext": match.group("ext").strip() or None,
                        "destination": match.group("destination").strip() or None,
                    },
                )

            match = SLOW_TEXT_RE.search(line)
            if match:
                source = "rf" if match.group("source").lower() == "rf" else "network"
                return self._apply_or_queue(source, {"slow_text": match.group("text")})

        return False

    def _apply_or_queue(self, source: str, fields: dict[str, Any]) -> bool:
        state = db.get_runtime_state()
        if state.get("state") == "active" and state.get("source") == source:
            for key, value in fields.items():
                if value is not None:
                    state[key] = value
            if "destination" in fields or "station" in fields:
                self._apply_route_context(state)
            db.set_runtime_state(state, _now_iso())
            return True

        pending = self._pending.get(source, {})
        pending.update(fields)
        pending["_seen_monotonic"] = time.monotonic()
        self._pending[source] = pending
        return True

    def _consume_pending(self, source: str, station: str | None) -> dict[str, Any]:
        pending = self._pending.pop(source, None)
        if not pending:
            return {}
        if time.monotonic() - float(pending.get("_seen_monotonic", 0)) > PENDING_MAX_AGE:
            return {}
        pending_station = pending.get("station")
        if station and pending_station and station != pending_station:
            return {}
        pending.pop("_seen_monotonic", None)
        return pending

    def _process_metric(self, field: str, data: dict[str, Any]) -> bool:
        if data.get("mode") != "D-Star":
            return False
        state = db.get_runtime_state()
        if state.get("state") != "active":
            return False
        state[field] = data.get("value")
        timestamp = data.get("timestamp") or _now_iso()
        if field == "ber_percent":
            state["ber_updated_at"] = timestamp
        elif field == "rssi_dbm":
            state["rssi_updated_at"] = timestamp
        db.set_runtime_state(state, timestamp)
        return True

    def _process_dstar(self, data: dict[str, Any]) -> bool:
        action = str(data.get("action", "")).lower()
        timestamp = data.get("timestamp") or _now_iso()

        if action in {"start", "late_entry"} and data.get("src_callsign"):
            source = data.get("source") or "unknown"
            direction = "RF_TO_NET" if source == "rf" else "NET_TO_RF" if source == "network" else "UNKNOWN"
            event_reflector = db.normalise_reflector(data.get("reflector"))
            active_reflector = db.normalise_reflector(get_active_reflector())
            reflector = active_reflector or event_reflector
            state = {
                "state": "active",
                "direction": direction,
                "source": source,
                "started_at": timestamp,
                "station": data.get("src_callsign") or None,
                "src_ext": data.get("src_ext") or None,
                "destination": data.get("dst_callsign") or None,
                "reflector": reflector,
                "duration_seconds": 0,
                "ber_percent": None,
                "rssi_dbm": None,
                "rssi": None,
                "packet_loss_percent": None,
                "slow_text": None,
                "route_type": None,
                "contact_callsign": None,
                "ber_updated_at": None,
                "rssi_updated_at": None,
            }

            pending = self._consume_pending(source, state["station"])
            for key in ("station", "src_ext", "destination", "slow_text"):
                if pending.get(key) is not None and (key in {"destination", "slow_text"} or not state.get(key)):
                    state[key] = pending[key]

            self._apply_route_context(state)
            db.set_runtime_state(state, timestamp)
            if state["reflector"]:
                db.set_metadata("last_reflector", str(state["reflector"]))
            return True

        if action in {"end", "lost"}:
            state = db.get_runtime_state()
            if state.get("state") != "active":
                return False

            rssi = data.get("rssi") if isinstance(data.get("rssi"), dict) else {}
            duration = data.get("duration", state.get("duration_seconds"))
            ber = data.get("ber", state.get("ber_percent"))
            loss = data.get("loss", state.get("packet_loss_percent"))

            self._apply_route_context(state)

            record = {
                "started_at": state.get("started_at") or timestamp,
                "ended_at": timestamp,
                "direction": state.get("direction") or "UNKNOWN",
                "source": state.get("source") or "unknown",
                "src_callsign": state.get("station"),
                "src_ext": state.get("src_ext"),
                "dst_callsign": state.get("destination"),
                "reflector": state.get("reflector"),
                "duration_seconds": duration,
                "ber_percent": ber,
                "rssi_min_dbm": rssi.get("min"),
                "rssi_max_dbm": rssi.get("max"),
                "rssi_ave_dbm": rssi.get("ave", state.get("rssi_dbm")),
                "packet_loss_percent": loss,
                "slow_text": state.get("slow_text"),
                "route_type": state.get("route_type"),
                "contact_callsign": state.get("contact_callsign"),
            }
            db.insert_transmission(record)
            idle = _idle_state(state)
            if not idle.get("reflector"):
                idle["reflector"] = db.get_metadata("last_reflector")
            db.set_runtime_state(idle, timestamp)
            return True

        return False
