from __future__ import annotations

import asyncio
import json
import os
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Any

from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from . import __version__
from .db import aggregate_since, get_metadata, get_runtime_state_fast, initialise, list_transmissions, list_transmissions_since, lookup_callsign, normalise_callsign, normalise_reflector, set_metadata
from .system_state import snapshot
from .settings_api import router as settings_router
from .diagnostics_api import router as diagnostics_router
from .updates_api import router as updates_router
from .network_api import router as network_router
from . import network_db
from .admin import run_admin_helper

app = FastAPI(title="PP5CI Hotspot API", version=__version__)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(settings_router)
app.include_router(diagnostics_router)
app.include_router(updates_router)
app.include_router(network_router)

TZ_NAME = os.getenv("PP5CI_HOTSPOT_TIMEZONE", "UTC")


def _enrich_live_traffic(traffic: dict) -> dict:
    enriched = dict(traffic or {})
    station = str(enriched.get("station") or "").strip().upper()
    enriched["name"] = None
    enriched["location"] = None
    if not station:
        return enriched

    profile = lookup_callsign(station)
    if profile:
        enriched["name"] = profile.get("name") or None
        enriched["location"] = profile.get("location") or None
    return enriched


@app.on_event("startup")
def startup() -> None:
    initialise()
    network_db.initialise()
    network_db.backfill_unassigned_transmission_reflectors()

    # One-time v0.2.12 migration. The release updater installs the new
    # root-owned helper and sudo rule before restarting the API, so the API can
    # safely enable ircDDB without exposing arbitrary root access.
    if get_metadata("migration_v0212_ircddb", "0") != "1":
        try:
            result = run_admin_helper("enable-ircddb", {"hostname": "ircv4.openquad.net"})
            if result.get("ok"):
                set_metadata("migration_v0212_ircddb", "1")
                set_metadata("migration_v0212_ircddb_error", "")
        except Exception as exc:
            set_metadata("migration_v0212_ircddb_error", str(exc)[:500])

    # v0.2.14 additionally enables DStarGateway's native ircDDB USER logging,
    # which exposes the gateway IPv4 chosen for callsign routing.  The same
    # restricted helper performs an idempotent config update and restart.
    if get_metadata("migration_v0214_direct_network", "0") != "1":
        try:
            result = run_admin_helper("enable-ircddb", {"hostname": "ircv4.openquad.net"})
            if result.get("ok"):
                set_metadata("migration_v0214_direct_network", "1")
                set_metadata("migration_v0214_direct_network_error", "")
        except Exception as exc:
            set_metadata("migration_v0214_direct_network_error", str(exc)[:500])


@app.get("/api/v1/health")
def health() -> dict:
    return {"ok": True, "version": __version__}


@app.get("/api/v1/status")
def status() -> dict:
    data = snapshot()
    data["traffic"] = _enrich_live_traffic(data.get("traffic") or {})
    data["version"] = __version__
    data["updated_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return data


@app.get("/api/v1/transmissions")
def transmissions(
    limit: int = Query(default=20, ge=1, le=500),
    reflector: str | None = None,
    callsign: str | None = None,
) -> dict:
    selected = normalise_reflector(reflector)
    selected_callsign = normalise_callsign(callsign)
    return {
        "items": list_transmissions(limit, reflector=selected, callsign=selected_callsign),
        "limit": limit,
        "reflector": selected,
        "callsign": selected_callsign,
    }


@app.get("/api/v1/events")
async def events(request: Request) -> StreamingResponse:
    """Stream live traffic state with sub-second latency.

    The collector is a separate process, so this endpoint watches the shared
    SQLite runtime_state row and only emits when its updated_at marker changes.
    """
    async def stream():
        last_updated: str | None = None
        loop = asyncio.get_running_loop()
        last_heartbeat = loop.time()

        yield "retry: 1000\n\n"

        while not await request.is_disconnected():
            try:
                traffic = get_runtime_state_fast()
                marker = str(traffic.get("updated_at") or "")
                if marker and marker != last_updated:
                    last_updated = marker
                    traffic = _enrich_live_traffic(traffic)
                    payload = json.dumps(traffic, ensure_ascii=False, separators=(",", ":"))
                    yield f"event: traffic\ndata: {payload}\n\n"
            except Exception:
                # Keep the stream alive; EventSource will also reconnect if the
                # connection itself is interrupted.
                pass

            now = loop.time()
            if now - last_heartbeat >= 15:
                yield ": keepalive\n\n"
                last_heartbeat = now

            await asyncio.sleep(0.1)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _to_utc_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _hourly_series(rows: list[dict], now_local: datetime, tz) -> list[dict]:
    first = now_local.replace(minute=0, second=0, microsecond=0) - timedelta(hours=23)
    buckets: dict[datetime, dict] = {}
    for i in range(24):
        key = first + timedelta(hours=i)
        buckets[key] = {"label": key.strftime("%H:00"), "rf_to_net": 0, "net_to_rf": 0, "total": 0}

    for row in rows:
        local = _parse_utc(row["started_at"]).astimezone(tz).replace(minute=0, second=0, microsecond=0)
        bucket = buckets.get(local)
        if not bucket:
            continue
        bucket["total"] += 1
        if row["direction"] == "RF_TO_NET":
            bucket["rf_to_net"] += 1
        elif row["direction"] == "NET_TO_RF":
            bucket["net_to_rf"] += 1
    return list(buckets.values())


def _daily_series(rows: list[dict], now_local: datetime, tz, days: int) -> list[dict]:
    first_date = now_local.date() - timedelta(days=days - 1)
    buckets = {
        first_date + timedelta(days=i): {
            "date": (first_date + timedelta(days=i)).isoformat(),
            "transmissions": 0,
            "airtime_seconds": 0.0,
            "rf_to_net": 0,
            "net_to_rf": 0,
        }
        for i in range(days)
    }
    for row in rows:
        local_date = _parse_utc(row["started_at"]).astimezone(tz).date()
        bucket = buckets.get(local_date)
        if not bucket:
            continue
        bucket["transmissions"] += 1
        bucket["airtime_seconds"] += float(row.get("duration_seconds") or 0)
        if row.get("direction") == "RF_TO_NET":
            bucket["rf_to_net"] += 1
        elif row.get("direction") == "NET_TO_RF":
            bucket["net_to_rf"] += 1
    return list(buckets.values())


@app.get("/api/v1/statistics")
def statistics(reflector: str | None = None, callsign: str | None = None) -> dict:
    try:
        tz = ZoneInfo(TZ_NAME)
    except Exception:
        tz = timezone.utc

    now_local = datetime.now(tz)
    start_today = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    start_7d = start_today - timedelta(days=6)
    start_30d = start_today - timedelta(days=29)
    start_24h = now_local - timedelta(hours=24)

    raw_reflector = str(reflector or "").strip().upper()
    selected_reflector = "" if raw_reflector in {"", "ALL", "TODOS", "TODOS OS REFLECTORES"} else (normalise_reflector(raw_reflector) or "")
    selected_callsign = normalise_callsign(callsign) or ""
    if selected_reflector and selected_callsign:
        selected_reflector = ""

    rows_all_30d = list_transmissions_since(_to_utc_iso(start_30d))
    rows_30d = [
        row for row in rows_all_30d
        if (
            (selected_callsign and str(row.get("route_type") or "").lower() == "callsign" and normalise_callsign(row.get("contact_callsign")) == selected_callsign)
            or (selected_reflector and normalise_reflector(row.get("reflector")) == selected_reflector)
            or (not selected_reflector and not selected_callsign)
        )
    ]
    rows_24h = [
        row for row in rows_30d
        if _parse_utc(row["started_at"]) >= start_24h.astimezone(timezone.utc)
    ]
    rows_today = [
        row for row in rows_30d
        if _parse_utc(row["started_at"]).astimezone(tz) >= start_today
    ]

    reflector_usage: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "transmissions": 0,
            "airtime_seconds": 0.0,
            "rf_to_net_seconds": 0.0,
            "net_to_rf_seconds": 0.0,
        }
    )
    for row in rows_all_30d:
        name = normalise_reflector(row.get("reflector"))
        if not name:
            continue
        duration = float(row.get("duration_seconds") or 0)
        usage = reflector_usage[name]
        usage["transmissions"] += 1
        usage["airtime_seconds"] += duration
        if row.get("direction") == "RF_TO_NET":
            usage["rf_to_net_seconds"] += duration
        elif row.get("direction") == "NET_TO_RF":
            usage["net_to_rf_seconds"] += duration

    reflector_usage_30d = [
        {"reflector": name, **values}
        for name, values in sorted(
            reflector_usage.items(),
            key=lambda item: (item[1]["airtime_seconds"], item[1]["transmissions"]),
            reverse=True,
        )
    ]

    callsign_usage: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "transmissions": 0,
            "airtime_seconds": 0.0,
            "rf_to_net_seconds": 0.0,
            "net_to_rf_seconds": 0.0,
        }
    )
    for row in rows_all_30d:
        if str(row.get("route_type") or "").lower() != "callsign":
            continue
        contact = normalise_callsign(row.get("contact_callsign"))
        if not contact:
            continue
        duration = float(row.get("duration_seconds") or 0)
        usage = callsign_usage[contact]
        usage["transmissions"] += 1
        usage["airtime_seconds"] += duration
        if row.get("direction") == "RF_TO_NET":
            usage["rf_to_net_seconds"] += duration
        elif row.get("direction") == "NET_TO_RF":
            usage["net_to_rf_seconds"] += duration

    callsign_usage_30d = []
    for contact, values in sorted(
        callsign_usage.items(),
        key=lambda item: (item[1]["airtime_seconds"], item[1]["transmissions"]),
        reverse=True,
    ):
        profile = lookup_callsign(contact) or {}
        callsign_usage_30d.append({
            "callsign": contact,
            "name": profile.get("name") or None,
            "location": profile.get("location") or None,
            **values,
        })

    direction_counts = Counter(row["direction"] for row in rows_30d)

    station_counts: dict[str, dict] = defaultdict(
        lambda: {
            "transmissions": 0,
            "airtime_seconds": 0.0,
            "name": None,
            "location": None,
        }
    )
    active_callsigns: set[str] = set()
    matched_callsigns: set[str] = set()
    transmissions_with_callsign = 0
    enriched_transmissions = 0

    for row in rows_30d:
        callsign = str(row.get("src_callsign") or "").strip().upper()
        if not callsign:
            continue

        transmissions_with_callsign += 1
        active_callsigns.add(callsign)
        enriched = bool(row.get("name") or row.get("location"))
        if enriched:
            enriched_transmissions += 1
            matched_callsigns.add(callsign)

        station = station_counts[callsign]
        station["transmissions"] += 1
        station["airtime_seconds"] += float(row.get("duration_seconds") or 0)
        if row.get("name"):
            station["name"] = row["name"]
        if row.get("location"):
            station["location"] = row["location"]

    top_stations = [
        {"callsign": callsign, **values}
        for callsign, values in sorted(
            station_counts.items(),
            key=lambda item: (item[1]["transmissions"], item[1]["airtime_seconds"]),
            reverse=True,
        )[:10]
    ]

    hour_counts: Counter[str] = Counter()
    for row in rows_today:
        local = _parse_utc(row["started_at"]).astimezone(tz)
        hour_counts[local.strftime("%H:00")] += 1

    peak_hour = None
    if hour_counts:
        hour, count = max(hour_counts.items(), key=lambda item: (item[1], item[0]))
        start_hour = int(hour[:2])
        peak_hour = {
            "hour": hour,
            "label": f"{start_hour:02d}:00–{(start_hour + 1) % 24:02d}:00",
            "transmissions": int(count),
        }

    scope_reflector = selected_reflector or None
    scope_callsign = selected_callsign or None
    last_30d = aggregate_since(
        _to_utc_iso(start_30d),
        reflector=scope_reflector,
        callsign=scope_callsign,
    )
    total_30d = int(last_30d.get("transmissions") or 0)
    average_qso_seconds = (
        float(last_30d.get("airtime_seconds") or 0) / total_30d
        if total_30d > 0 else 0.0
    )

    active_count = len(active_callsigns)
    matched_count = len(matched_callsigns)
    matched_percent = round(matched_count * 100.0 / active_count, 1) if active_count else 0.0
    enriched_percent = (
        round(enriched_transmissions * 100.0 / transmissions_with_callsign, 1)
        if transmissions_with_callsign else 0.0
    )

    return {
        "timezone": str(tz),
        "scope": {
            "type": "callsign" if scope_callsign else "reflector" if scope_reflector else "all",
            "reflector": scope_reflector,
            "callsign": scope_callsign,
            "label": f"Direto · {scope_callsign}" if scope_callsign else (scope_reflector or "Todos os destinos"),
        },
        "available_reflectors": [row["reflector"] for row in reflector_usage_30d],
        "available_callsigns": [row["callsign"] for row in callsign_usage_30d],
        "reflector_usage_30d": reflector_usage_30d,
        "callsign_usage_30d": callsign_usage_30d,
        "today": aggregate_since(_to_utc_iso(start_today), reflector=scope_reflector, callsign=scope_callsign),
        "last_24h": aggregate_since(_to_utc_iso(start_24h), reflector=scope_reflector, callsign=scope_callsign),
        "last_7d": aggregate_since(_to_utc_iso(start_7d), reflector=scope_reflector, callsign=scope_callsign),
        "last_30d": last_30d,
        "hourly_24h": _hourly_series(rows_24h, now_local, tz),
        "daily_7d": _daily_series(rows_30d, now_local, tz, 7),
        "daily_30d": _daily_series(rows_30d, now_local, tz, 30),
        "direction_30d": {
            "rf_to_net": int(direction_counts.get("RF_TO_NET", 0)),
            "net_to_rf": int(direction_counts.get("NET_TO_RF", 0)),
        },
        "peak_hour_today": peak_hour,
        "average_qso_seconds_30d": round(average_qso_seconds, 2),
        "directory_coverage_30d": {
            "active_callsigns": active_count,
            "matched_callsigns": matched_count,
            "matched_callsigns_percent": matched_percent,
            "transmissions_with_callsign": transmissions_with_callsign,
            "enriched_transmissions": enriched_transmissions,
            "enriched_transmissions_percent": enriched_percent,
        },
        "top_stations": top_stations,
    }
