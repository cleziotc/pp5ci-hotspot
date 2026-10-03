from __future__ import annotations

import json
import os
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from collections.abc import Iterable, Iterator
from typing import Any

DB_PATH = Path(os.getenv("PP5CI_HOTSPOT_DB_PATH", "/var/lib/pp5ci-hotspot/pp5ci-hotspot.db"))

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS transmissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    ended_at TEXT NOT NULL,
    direction TEXT NOT NULL,
    source TEXT NOT NULL,
    src_callsign TEXT,
    src_ext TEXT,
    dst_callsign TEXT,
    reflector TEXT,
    duration_seconds REAL,
    ber_percent REAL,
    rssi_min_dbm INTEGER,
    rssi_max_dbm INTEGER,
    rssi_ave_dbm INTEGER,
    packet_loss_percent REAL,
    slow_text TEXT,
    route_type TEXT,
    contact_callsign TEXT
);

CREATE INDEX IF NOT EXISTS idx_transmissions_started_at
ON transmissions(started_at DESC);

CREATE INDEX IF NOT EXISTS idx_transmissions_callsign
ON transmissions(src_callsign);

CREATE TABLE IF NOT EXISTS runtime_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    updated_at TEXT NOT NULL,
    state_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS callsign_directory (
    callsign TEXT PRIMARY KEY,
    name TEXT,
    location TEXT,
    imported_at TEXT NOT NULL,
    source_file TEXT
);

CREATE INDEX IF NOT EXISTS idx_callsign_directory_callsign
ON callsign_directory(callsign);
"""


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
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
    with connect() as conn:
        conn.executescript(SCHEMA)
        transmission_columns = {row["name"] for row in conn.execute("PRAGMA table_info(transmissions)").fetchall()}
        if "route_type" not in transmission_columns:
            conn.execute("ALTER TABLE transmissions ADD COLUMN route_type TEXT")
        if "contact_callsign" not in transmission_columns:
            conn.execute("ALTER TABLE transmissions ADD COLUMN contact_callsign TEXT")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_transmissions_route_type ON transmissions(route_type)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_transmissions_contact_callsign ON transmissions(contact_callsign)")
        if conn.execute("SELECT 1 FROM runtime_state WHERE id=1").fetchone() is None:
            state = {
                "state": "idle",
                "direction": None,
                "source": None,
                "started_at": None,
                "station": None,
                "src_ext": None,
                "destination": None,
                "reflector": None,
                "duration_seconds": 0,
                "ber_percent": None,
                "rssi_dbm": None,
                "rssi": None,
                "slow_text": None,
                "route_type": None,
                "contact_callsign": None,
            }
            conn.execute(
                "INSERT INTO runtime_state(id, updated_at, state_json) VALUES(1, datetime('now'), ?)",
                (json.dumps(state, ensure_ascii=False),),
            )


def get_runtime_state_fast() -> dict[str, Any]:
    """Read runtime state without re-running schema initialisation.

    Intended for high-frequency readers such as SSE streams. API startup and the
    collector already initialise the database before this is used.
    """
    with connect() as conn:
        row = conn.execute("SELECT updated_at, state_json FROM runtime_state WHERE id=1").fetchone()
    if row is None:
        return {}
    state = json.loads(row["state_json"])
    state["updated_at"] = row["updated_at"]
    return state


def get_runtime_state() -> dict[str, Any]:
    initialise()
    return get_runtime_state_fast()


def set_runtime_state(state: dict[str, Any], updated_at: str) -> None:
    initialise()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO runtime_state(id, updated_at, state_json)
            VALUES(1, ?, ?)
            ON CONFLICT(id) DO UPDATE SET updated_at=excluded.updated_at, state_json=excluded.state_json
            """,
            (updated_at, json.dumps(state, ensure_ascii=False)),
        )


def set_metadata(key: str, value: str) -> None:
    initialise()
    with connect() as conn:
        conn.execute(
            "INSERT INTO metadata(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )


def get_metadata(key: str, default: str | None = None) -> str | None:
    initialise()
    with connect() as conn:
        row = conn.execute("SELECT value FROM metadata WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def insert_transmission(record: dict[str, Any]) -> int:
    initialise()
    columns = [
        "started_at", "ended_at", "direction", "source", "src_callsign", "src_ext",
        "dst_callsign", "reflector", "duration_seconds", "ber_percent",
        "rssi_min_dbm", "rssi_max_dbm", "rssi_ave_dbm", "packet_loss_percent", "slow_text",
        "route_type", "contact_callsign",
    ]
    values = [record.get(column) for column in columns]
    values[columns.index("reflector")] = normalise_reflector(record.get("reflector"))
    with connect() as conn:
        cur = conn.execute(
            f"INSERT INTO transmissions ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
            values,
        )
        return int(cur.lastrowid)


REFLECTOR_ID_RE = re.compile(r"^((?:REF|XRF|DCS|XLX)[A-Z0-9]{3})\s*([A-Z])$", re.IGNORECASE)


def normalise_reflector(reflector: str | None) -> str | None:
    value = " ".join(str(reflector or "").strip().upper().split())
    if not value:
        return None
    compact = value.replace(" ", "")
    match = REFLECTOR_ID_RE.match(compact)
    if match:
        return f"{match.group(1).upper()} {match.group(2).upper()}"
    return value


def _normalise_reflector(reflector: str | None) -> str | None:
    return normalise_reflector(reflector)


DIRECT_CALLSIGN_RE = re.compile(r"^[A-Z0-9]{3,7}$")
NON_DIRECT_DESTINATIONS = {"CQCQCQ", "ECHO", "INFO"}


def normalise_callsign(value: str | None) -> str | None:
    callsign = "".join(str(value or "").strip().upper().split())
    return callsign or None


def direct_contact_callsign(source: str | None, src_callsign: str | None, dst_callsign: str | None) -> str | None:
    destination = normalise_callsign(dst_callsign)
    if not destination or destination in NON_DIRECT_DESTINATIONS or not DIRECT_CALLSIGN_RE.fullmatch(destination):
        return None
    if str(source or "").lower() == "network":
        station = normalise_callsign(src_callsign)
        return station if station and DIRECT_CALLSIGN_RE.fullmatch(station) else None
    return destination


def route_type_for(reflector: str | None, contact_callsign: str | None) -> str:
    if contact_callsign:
        return "callsign"
    if normalise_reflector(reflector):
        return "reflector"
    return "local"


def list_transmissions(
    limit: int = 20,
    reflector: str | None = None,
    callsign: str | None = None,
) -> list[dict[str, Any]]:
    initialise()
    limit = max(1, min(int(limit), 500))
    selected = _normalise_reflector(reflector)
    selected_callsign = normalise_callsign(callsign)
    where_parts: list[str] = []
    params: list[Any] = []
    if selected:
        where_parts.append("REPLACE(UPPER(TRIM(COALESCE(t.reflector, ''))), ' ', '') = REPLACE(?, ' ', '')")
        params.append(selected)
    if selected_callsign:
        where_parts.append("LOWER(COALESCE(t.route_type, '')) = 'callsign'")
        where_parts.append("UPPER(TRIM(COALESCE(t.contact_callsign, ''))) = ?")
        params.append(selected_callsign)
    where = "WHERE " + " AND ".join(where_parts) if where_parts else ""
    params.append(limit)

    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT
              t.*,
              d.name AS name,
              d.location AS location
            FROM transmissions t
            LEFT JOIN callsign_directory d
              ON UPPER(COALESCE(t.src_callsign, '')) = d.callsign
            {where}
            ORDER BY t.id DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
    result = [dict(row) for row in rows]
    for item in result:
        item["reflector"] = normalise_reflector(item.get("reflector"))
    return result


def list_transmissions_since(
    since_utc: str,
    reflector: str | None = None,
    callsign: str | None = None,
) -> list[dict[str, Any]]:
    initialise()
    selected = _normalise_reflector(reflector)
    selected_callsign = normalise_callsign(callsign)
    where = ["t.started_at >= ?"]
    params: list[Any] = [since_utc]
    if selected:
        where.append("REPLACE(UPPER(TRIM(COALESCE(t.reflector, ''))), ' ', '') = REPLACE(?, ' ', '')")
        params.append(selected)
    if selected_callsign:
        where.append("LOWER(COALESCE(t.route_type, '')) = 'callsign'")
        where.append("UPPER(TRIM(COALESCE(t.contact_callsign, ''))) = ?")
        params.append(selected_callsign)

    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT
              t.*,
              d.name AS name,
              d.location AS location
            FROM transmissions t
            LEFT JOIN callsign_directory d
              ON UPPER(COALESCE(t.src_callsign, '')) = d.callsign
            WHERE {' AND '.join(where)}
            ORDER BY t.started_at ASC
            """,
            params,
        ).fetchall()
    result = [dict(row) for row in rows]
    for item in result:
        item["reflector"] = normalise_reflector(item.get("reflector"))
    return result


def aggregate_since(
    since_utc: str,
    reflector: str | None = None,
    callsign: str | None = None,
) -> dict[str, Any]:
    initialise()
    selected = _normalise_reflector(reflector)
    selected_callsign = normalise_callsign(callsign)
    where = ["started_at >= ?"]
    params: list[Any] = [since_utc]
    if selected:
        where.append("REPLACE(UPPER(TRIM(COALESCE(reflector, ''))), ' ', '') = REPLACE(?, ' ', '')")
        params.append(selected)
    if selected_callsign:
        where.append("LOWER(COALESCE(route_type, '')) = 'callsign'")
        where.append("UPPER(TRIM(COALESCE(contact_callsign, ''))) = ?")
        params.append(selected_callsign)

    with connect() as conn:
        row = conn.execute(
            f"""
            SELECT
              COUNT(*) AS transmissions,
              COALESCE(SUM(duration_seconds), 0) AS airtime_seconds,
              COALESCE(SUM(CASE WHEN direction='RF_TO_NET' THEN duration_seconds ELSE 0 END), 0) AS rf_to_net_seconds,
              COALESCE(SUM(CASE WHEN direction='NET_TO_RF' THEN duration_seconds ELSE 0 END), 0) AS net_to_rf_seconds
            FROM transmissions
            WHERE {' AND '.join(where)}
            """,
            params,
        ).fetchone()
    return dict(row)


def replace_callsign_directory(
    records: Iterable[dict[str, str]],
    imported_at: str,
    source_file: str,
    batch_size: int = 5000,
) -> int:
    """Atomically replace the callsign directory from an iterable.

    Records are staged in a temporary SQLite table in bounded batches so large
    CSV imports do not need to be held in Python memory.  The live directory is
    only replaced after the whole iterable has been consumed successfully.
    """
    initialise()
    with connect() as conn:
        conn.execute(
            """
            CREATE TEMP TABLE callsign_directory_import (
                callsign TEXT PRIMARY KEY,
                name TEXT,
                location TEXT,
                imported_at TEXT NOT NULL,
                source_file TEXT
            )
            """
        )

        sql = """
            INSERT INTO callsign_directory_import(callsign, name, location, imported_at, source_file)
            VALUES(?, ?, ?, ?, ?)
            ON CONFLICT(callsign) DO UPDATE SET
                name=excluded.name,
                location=excluded.location,
                imported_at=excluded.imported_at,
                source_file=excluded.source_file
        """
        batch: list[tuple[str, str, str, str, str]] = []
        for record in records:
            batch.append(
                (
                    record["callsign"].upper(),
                    record.get("name", ""),
                    record.get("location", ""),
                    imported_at,
                    source_file,
                )
            )
            if len(batch) >= batch_size:
                conn.executemany(sql, batch)
                batch.clear()

        if batch:
            conn.executemany(sql, batch)

        row = conn.execute("SELECT COUNT(*) AS count FROM callsign_directory_import").fetchone()
        count = int(row["count"] if row else 0)
        if count == 0:
            raise ValueError("Nenhum registro válido encontrado no CSV")

        conn.execute("DELETE FROM callsign_directory")
        conn.execute(
            """
            INSERT INTO callsign_directory(callsign, name, location, imported_at, source_file)
            SELECT callsign, name, location, imported_at, source_file
            FROM callsign_directory_import
            """
        )
        conn.execute(
            "INSERT INTO metadata(key, value) VALUES('callsign_directory_imported_at', ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (imported_at,),
        )
        conn.execute(
            "INSERT INTO metadata(key, value) VALUES('callsign_directory_source_file', ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (source_file,),
        )
        return count


def lookup_callsign(callsign: str | None) -> dict[str, Any] | None:
    initialise()
    normalized = str(callsign or "").strip().upper()
    if not normalized:
        return None
    with connect() as conn:
        row = conn.execute(
            """
            SELECT callsign, name, location
            FROM callsign_directory
            WHERE callsign = ?
            """,
            (normalized,),
        ).fetchone()
    return dict(row) if row else None


def directory_summary() -> dict[str, Any]:
    initialise()
    with connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS count, MAX(imported_at) AS imported_at FROM callsign_directory"
        ).fetchone()
    return {
        "count": int(row["count"] if row else 0),
        "imported_at": row["imported_at"] if row else None,
        "source_file": get_metadata("callsign_directory_source_file"),
        "columns": ["callsign", "name", "location"],
    }
