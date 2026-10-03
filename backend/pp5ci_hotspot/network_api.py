from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Query

from . import db, network_db
from .network_monitor import get_active_link, get_active_reflector

router = APIRouter(prefix="/api/v1/network", tags=["network"])


def _iso_before(*, seconds: int = 0, hours: int = 0) -> str:
    value = datetime.now(timezone.utc) - timedelta(seconds=seconds, hours=hours)
    return value.isoformat().replace("+00:00", "Z")


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _decorate_summary(summary: dict[str, Any], latest: dict[str, Any] | None) -> dict[str, Any]:
    latest_at = latest.get("sampled_at") if latest else None
    sampled = _parse_time(latest_at)
    age_seconds = None
    if sampled is not None:
        age_seconds = max(0.0, (datetime.now(timezone.utc) - sampled).total_seconds())

    result = {
        **summary,
        "host": latest.get("host") if latest else None,
        "ip": latest.get("ip") if latest else None,
        "port": latest.get("port") if latest else None,
        "last_sample_at": latest_at,
        "last_sample_age_seconds": None if age_seconds is None else round(age_seconds, 1),
        "fresh": bool(age_seconds is not None and age_seconds <= 20.0),
    }
    if not result["fresh"] and result["state"] != "unavailable":
        result["state"] = "unavailable"
    return result


def _newer_sample(
    first: dict[str, Any] | None,
    second: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if first is None:
        return second
    if second is None:
        return first
    first_at = _parse_time(first.get("sampled_at"))
    second_at = _parse_time(second.get("sampled_at"))
    if first_at is None:
        return second
    if second_at is None:
        return first
    return first if first_at >= second_at else second


def _public_samples(rows: list[dict[str, Any]], limit: int = 24) -> list[dict[str, Any]]:
    values = rows[-limit:]
    return [
        {
            "sampled_at": row.get("sampled_at"),
            "success": bool(row.get("success")),
            "rtt_ms": row.get("rtt_ms"),
        }
        for row in values
    ]


def _latest_dstar_loss() -> dict[str, Any] | None:
    for row in db.list_transmissions(100):
        if row.get("direction") != "NET_TO_RF":
            continue
        if row.get("packet_loss_percent") is None:
            continue
        return {
            "loss_percent": float(row["packet_loss_percent"]),
            "ended_at": row.get("ended_at"),
            "reflector": row.get("reflector"),
        }
    return None


@router.get("")
def current_network_quality() -> dict[str, Any]:
    network_db.initialise()
    link = get_active_link()
    reflector = str(link["reflector"]) if link else None
    since = _iso_before(seconds=60)

    reflector_rows = network_db.list_samples("reflector", since, reflector=reflector) if reflector else []
    internet_rows = network_db.list_samples("internet", since)

    reflector_latest = network_db.latest_sample("reflector", reflector=reflector) if reflector else None
    runtime = db.get_runtime_state_fast()
    live_direct_callsign = (
        str(runtime.get("contact_callsign") or "").strip().upper()
        if runtime.get("state") == "active" and str(runtime.get("route_type") or "").lower() == "callsign"
        else ""
    ) or None
    direct_latest = (
        network_db.latest_sample("direct", callsign=live_direct_callsign)
        if live_direct_callsign
        else network_db.latest_sample("direct")
    )
    internet_latest = network_db.latest_sample("internet")

    direct_callsign = live_direct_callsign or str((direct_latest or {}).get("callsign") or "").strip().upper() or None
    direct_rows = (
        network_db.list_samples("direct", since, callsign=direct_callsign)
        if direct_callsign else []
    )

    reflector_summary = {
        "name": reflector,
        "target_type": "reflector",
        "callsign": None,
        **_decorate_summary(network_db.summarize(reflector_rows), reflector_latest),
        "samples": _public_samples(reflector_rows),
    }
    direct_summary = {
        "name": direct_callsign,
        "target_type": "callsign",
        "callsign": direct_callsign,
        **_decorate_summary(network_db.summarize(direct_rows), direct_latest),
        "samples": _public_samples(direct_rows),
    }

    live_route_type = str(runtime.get("route_type") or "").lower() if runtime.get("state") == "active" else ""
    if live_route_type == "callsign" and direct_callsign:
        active_type = "direct"
    elif runtime.get("state") == "active" and live_route_type != "callsign":
        active_type = "reflector"
    else:
        newest = _newer_sample(reflector_latest, direct_latest)
        direct_sampled = _parse_time((direct_latest or {}).get("sampled_at"))
        direct_recent = bool(
            direct_sampled is not None
            and (datetime.now(timezone.utc) - direct_sampled).total_seconds() <= 10.0
        )
        active_type = (
            "direct"
            if newest and newest.get("target") == "direct" and direct_recent
            else "reflector"
        )
    active_target = direct_summary if active_type == "direct" else reflector_summary

    return {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "window_seconds": 60,
        "probe_method": "TCP connect",
        "icmp_required": False,
        "probe_interval_seconds": 3,
        "direct_hold_seconds": 60,
        "active_target": active_target,
        "reflector": reflector_summary,
        "direct": direct_summary,
        "internet": {
            "name": "Internet baseline",
            **_decorate_summary(network_db.summarize(internet_rows), internet_latest),
            "samples": _public_samples(internet_rows),
        },
        "dstar": {
            "protocol": "G2" if active_type == "direct" else (link.get("protocol") if link else None),
            "udp_port": 40000 if active_type == "direct" else (link.get("udp_port") if link else None),
            "last_network_loss": _latest_dstar_loss(),
        },
    }


@router.get("/history")
def network_history(
    hours: int = Query(default=24, ge=1, le=168),
    reflector: str | None = None,
) -> dict[str, Any]:
    network_db.initialise()
    requested = str(reflector or "").strip().upper() or None
    active = get_active_reflector()
    latest_reflector = network_db.latest_sample("reflector")
    reflector = requested or active or (latest_reflector.get("reflector") if latest_reflector else None)
    since = _iso_before(hours=hours)

    reflector_rows = network_db.list_samples("reflector", since, reflector=reflector, limit=50000) if reflector else []
    internet_rows = network_db.list_samples("internet", since, limit=50000)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "hours": hours,
        "bucket_minutes": 10,
        "probe_method": "TCP connect",
        "icmp_required": False,
        "reflector": {
            "name": reflector,
            **network_db.summarize(reflector_rows),
            "series": network_db.bucketize(reflector_rows, 10),
        },
        "internet": {
            "name": "Internet baseline",
            **network_db.summarize(internet_rows),
            "series": network_db.bucketize(internet_rows, 10),
        },
    }
