from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pp5ci_hotspot import db
from pp5ci_hotspot.settings_api import _column_map, _format_location, _parse_host_line, _reflector_parts


class SettingsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        db.DB_PATH = Path(self.tmp.name) / "settings.db"
        db.initialise()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_callsign_directory_enriches_existing_transmissions(self) -> None:
        db.insert_transmission({
            "started_at": "2026-10-01T18:00:00Z",
            "ended_at": "2026-10-01T18:00:02Z",
            "direction": "RF_TO_NET",
            "source": "rf",
            "src_callsign": "N0CALL",
            "src_ext": "ID52",
            "dst_callsign": "CQCQCQ",
            "duration_seconds": 2.0,
        })
        db.replace_callsign_directory(
            [{"callsign": "N0CALL", "name": "Operator", "location": "SC"}],
            "2026-10-01T21:00:00Z",
            "users.csv",
        )

        row = db.list_transmissions(1)[0]
        self.assertEqual(row["name"], "Operator")
        self.assertEqual(row["location"], "SC")
        self.assertEqual(db.directory_summary()["count"], 1)

    def test_csv_aliases_are_detected(self) -> None:
        mapping = _column_map(["Indicativo", "Nome", "QTH"])
        self.assertEqual(mapping["callsign"], "Indicativo")
        self.assertEqual(mapping["name"], "Nome")
        self.assertEqual(mapping["location"], "QTH")

    def test_csv_city_and_state_are_detected_and_combined(self) -> None:
        mapping = _column_map(["Callsign", "Name", "City", "State"])
        self.assertEqual(mapping["callsign"], "Callsign")
        self.assertEqual(mapping["name"], "Name")
        self.assertEqual(mapping["location"], "City")
        self.assertEqual(mapping["state"], "State")
        self.assertEqual(_format_location("Cidade", "SC"), "Cidade - SC")
        self.assertEqual(_format_location("Cidade - SC", "SC"), "Cidade - SC")

    def test_streaming_directory_replace_deduplicates_without_list(self) -> None:
        def records():
            yield {"callsign": "N0CALL", "name": "Primeiro", "location": "SC"}
            yield {"callsign": "N0CALL", "name": "Atualizado", "location": "Cidade"}
            yield {"callsign": "PY2ABC", "name": "Outro", "location": "SP"}

        count = db.replace_callsign_directory(records(), "2026-10-01T22:00:00Z", "large.csv", batch_size=1)
        self.assertEqual(count, 2)
        rows = {row["callsign"]: row for row in db.list_callsign_directory()} if hasattr(db, "list_callsign_directory") else None
        self.assertEqual(db.directory_summary()["count"], 2)

    def test_reflector_and_host_formats(self) -> None:
        self.assertEqual(_reflector_parts("XLX026 C"), ("XLX026", "C"))
        self.assertEqual(_reflector_parts("REF001A"), ("REF001", "A"))
        self.assertEqual(_parse_host_line("DPlus", "REF001 1.2.3.4"), ("REF001", "1.2.3.4"))
        self.assertEqual(_parse_host_line("XLX", "026;82.152.175.30;4004"), ("XLX026", "82.152.175.30"))


if __name__ == "__main__":
    unittest.main()
