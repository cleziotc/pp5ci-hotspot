from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from statistics import median
from typing import Any, Iterator

from . import db

NETWORK_SCHEMA = """
CREATE TABLE IF NOT EXISTS network_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sampled_at TEXT NOT NULL,
    target TEXT NOT NULL,
    reflector TEXT,
    callsign TEXT,
    host TEXT,
    ip TEXT,
    port INTEGER,
    success INTEGER NOT NULL,
    rtt_ms REAL
);

CREATE INDEX IF NOT EXISTS idx_network_samples_target_time
ON network_samples(target, sampled_at DESC);

CREATE INDEX IF NOT EXISTS idx_network_samples_reflector_time
ON network_samples(reflector, sampled_at DESC);
"""


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    db.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db.DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=10000")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def initialise() -> None:
    db.initialise()
    with connect() as conn:
        conn.executescript(NETWORK_SCHEMA)
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(network_samples)").fetchall()}
        if "callsign" not in columns:
            conn.execute("ALTER TABLE network_samples ADD COLUMN callsign TEXT")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_network_samples_callsign_time "
            "ON network_samples(callsign, sampled_at DESC)"
        )


def insert_sample(
    *,
    sampled_at: str,
    target: str,
    success: bool,
    reflector: str | None = None,
    callsign: str | None = None,
    host: str | None = None,
    ip: str | None = None,
    port: int | None = None,
    rtt_ms: float | None = None,
) -> int:
    initialise()
    with connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO network_samples(
                sampled_at, target, reflector, callsign, host, ip, port, success, rtt_ms
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sampled_at,
                target,
                reflector,
                callsign,
                host,
                ip,
                port,
                1 if success else 0,
                None if rtt_ms is None else round(float(rtt_ms), 3),
            ),
        )
        return int(cur.lastrowid)


def list_samples(
    target: str,
    since_utc: str,
    *,
    reflector: str | None = None,
    callsign: str | None = None,
    limit: int = 20000,
) -> list[dict[str, Any]]:
    initialise()
    limit = max(1, min(int(limit), 50000))
    sql = """
        SELECT sampled_at, target, reflector, callsign, host, ip, port, success, rtt_ms
        FROM network_samples
        WHERE target=? AND sampled_at>=?
    """
    params: list[Any] = [target, since_utc]
    if reflector:
        sql += " AND reflector=?"
        params.append(reflector)
    if callsign:
        sql += " AND UPPER(TRIM(COALESCE(callsign, ''))) = ?"
        params.append(str(callsign).strip().upper())
    sql += " ORDER BY sampled_at ASC LIMIT ?"
    params.append(limit)

    with connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def latest_sample(
    target: str,
    reflector: str | None = None,
    callsign: str | None = None,
) -> dict[str, Any] | None:
    initialise()
    sql = """
        SELECT sampled_at, target, reflector, callsign, host, ip, port, success, rtt_ms
        FROM network_samples
        WHERE target=?
    """
    params: list[Any] = [target]
    if reflector:
        sql += " AND reflector=?"
        params.append(reflector)
    if callsign:
        sql += " AND UPPER(TRIM(COALESCE(callsign, ''))) = ?"
        params.append(str(callsign).strip().upper())
    sql += " ORDER BY sampled_at DESC LIMIT 1"
    with connect() as conn:
        row = conn.execute(sql, params).fetchone()
    return dict(row) if row else None


def prune(retention_days: int = 7) -> int:
    initialise()
    cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, retention_days))
    cutoff_iso = cutoff.isoformat().replace("+00:00", "Z")
    with connect() as conn:
        cur = conn.execute("DELETE FROM network_samples WHERE sampled_at < ?", (cutoff_iso,))
        return int(cur.rowcount or 0)


def backfill_unassigned_transmission_reflectors(max_distance_seconds: int = 15) -> int:
    """Recover missing transmission reflector labels from nearby network samples.

    Network samples are collected every few seconds and already store the active
    reflector from Links.log. Only transmissions with an empty reflector are
    considered, and only a nearby sample inside the requested time window can
    assign one.
    """
    initialise()
    distance = max(1, int(max_distance_seconds))
    changed = 0

    with connect() as conn:
        transmissions = conn.execute(
            """
            SELECT id, started_at
            FROM transmissions
            WHERE TRIM(COALESCE(reflector, '')) = ''
              AND LOWER(COALESCE(route_type, '')) <> 'callsign'
            ORDER BY started_at ASC
            """
        ).fetchall()

        for transmission in transmissions:
            sample = conn.execute(
                """
                SELECT reflector
                FROM network_samples
                WHERE target = 'reflector'
                  AND TRIM(COALESCE(reflector, '')) <> ''
                  AND ABS((julianday(sampled_at) - julianday(?)) * 86400.0) <= ?
                ORDER BY ABS((julianday(sampled_at) - julianday(?)) * 86400.0) ASC
                LIMIT 1
                """,
                (transmission["started_at"], distance, transmission["started_at"]),
            ).fetchone()

            if not sample:
                continue

            canonical = db.normalise_reflector(sample["reflector"])
            if not canonical:
                continue

            conn.execute(
                "UPDATE transmissions SET reflector=? WHERE id=? AND TRIM(COALESCE(reflector, '')) = '' AND LOWER(COALESCE(route_type, '')) <> 'callsign'",
                (canonical, transmission["id"]),
            )
            changed += 1

        rows = conn.execute(
            """
            SELECT id, reflector
            FROM transmissions
            WHERE TRIM(COALESCE(reflector, '')) <> ''
            """
        ).fetchall()
        for row in rows:
            canonical = db.normalise_reflector(row["reflector"])
            if canonical and canonical != row["reflector"]:
                conn.execute("UPDATE transmissions SET reflector=? WHERE id=?", (canonical, row["id"]))

    return changed


def summarize(samples: list[dict[str, Any]]) -> dict[str, Any]:
    if not samples:
        return {
            "latency_ms": None,
            "jitter_ms": None,
            "loss_percent": None,
            "max_rtt_ms": None,
            "sample_count": 0,
            "successful_samples": 0,
            "state": "unavailable",
        }

    successful = [
        float(row["rtt_ms"])
        for row in samples
        if bool(row.get("success")) and row.get("rtt_ms") is not None
    ]
    total = len(samples)
    ok_count = len(successful)
    loss = round((total - ok_count) * 100.0 / total, 1)

    if not successful:
        return {
            "latency_ms": None,
            "jitter_ms": None,
            "loss_percent": loss,
            "max_rtt_ms": None,
            "sample_count": total,
            "successful_samples": 0,
            "state": "unavailable",
        }

    latency = round(float(median(successful)), 1)
    deltas = [abs(successful[index] - successful[index - 1]) for index in range(1, len(successful))]
    jitter = round(sum(deltas) / len(deltas), 1) if deltas else 0.0
    max_rtt = round(max(successful), 1)

    # RTT bands requested for the dashboard:
    #   0-100 ms   -> good
    #   101-260 ms -> degraded (can be normal for an overseas reflector)
    #   >260 ms    -> poor
    #
    # Packet loss and jitter can still worsen the state even when RTT is low.
    if loss >= 5.0 or jitter >= 100.0 or latency > 260.0:
        state = "poor"
    elif loss >= 1.0 or jitter >= 40.0 or latency > 100.0:
        state = "degraded"
    else:
        state = "good"

    return {
        "latency_ms": latency,
        "jitter_ms": jitter,
        "loss_percent": loss,
        "max_rtt_ms": max_rtt,
        "sample_count": total,
        "successful_samples": ok_count,
        "state": state,
    }


def bucketize(samples: list[dict[str, Any]], bucket_minutes: int = 10) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = {}
    minutes = max(1, int(bucket_minutes))

    for row in samples:
        try:
            dt = datetime.fromisoformat(str(row["sampled_at"]).replace("Z", "+00:00")).astimezone(timezone.utc)
        except (KeyError, TypeError, ValueError):
            continue
        minute = (dt.minute // minutes) * minutes
        start = dt.replace(minute=minute, second=0, microsecond=0)
        key = start.isoformat().replace("+00:00", "Z")
        buckets.setdefault(key, []).append(row)

    result = []
    for key in sorted(buckets):
        summary = summarize(buckets[key])
        result.append({
            "sampled_at": key,
            "latency_ms": summary["latency_ms"],
            "jitter_ms": summary["jitter_ms"],
            "loss_percent": summary["loss_percent"],
            "sample_count": summary["sample_count"],
        })
    return result
