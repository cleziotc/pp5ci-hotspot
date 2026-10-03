from __future__ import annotations

import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from pp5ci_hotspot import db
from pp5ci_hotspot.events import EventProcessor


class EventProcessorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        db.DB_PATH = Path(self.tmp.name) / "test.db"
        db.initialise()
        self.processor = EventProcessor()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def emit(self, obj: dict) -> bool:
        return self.processor.process(json.dumps(obj))

    def test_rf_session_is_persisted(self) -> None:
        self.assertTrue(self.emit({"D-Star": {
            "timestamp": "2026-10-01T18:00:00.000Z",
            "src_callsign": "N0CALL",
            "src_ext": "ID52",
            "dst_callsign": "CQCQCQ",
            "source": "rf",
            "action": "start",
            "reflector": "",
        }}))
        self.assertTrue(self.emit({"BER": {"timestamp": "2026-10-01T18:00:01.000Z", "mode": "D-Star", "value": 0.3}}))
        self.assertTrue(self.emit({"RSSI": {"timestamp": "2026-10-01T18:00:01.100Z", "mode": "D-Star", "value": -91}}))
        self.assertTrue(self.emit({"Text": {"timestamp": "2026-10-01T18:00:01.200Z", "mode": "D-Star", "value": "Op. Clezio Cidade"}}))
        self.assertTrue(self.emit({"D-Star": {
            "timestamp": "2026-10-01T18:00:03.000Z",
            "duration": 3.0,
            "ber": 0.1,
            "rssi": {"min": -97, "max": -86, "ave": -91},
            "action": "end",
        }}))

        rows = db.list_transmissions(10)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["direction"], "RF_TO_NET")
        self.assertEqual(row["src_callsign"], "N0CALL")
        self.assertEqual(row["src_ext"], "ID52")
        self.assertEqual(row["dst_callsign"], "CQCQCQ")
        self.assertEqual(row["duration_seconds"], 3.0)
        self.assertEqual(row["ber_percent"], 0.1)
        self.assertEqual(row["rssi_ave_dbm"], -91)
        self.assertEqual(row["slow_text"], "Op. Clezio Cidade")
        self.assertEqual(db.get_runtime_state()["state"], "idle")

    def test_rf_session_inherits_active_reflector_when_mqtt_field_is_empty(self) -> None:
        with patch("pp5ci_hotspot.events.get_active_reflector", return_value="XLX300 D"):
            self.assertTrue(self.emit({"D-Star": {
                "timestamp": "2026-10-01T18:10:00.000Z",
                "src_callsign": "N0CALL",
                "src_ext": "ID52",
                "dst_callsign": "CQCQCQ",
                "source": "rf",
                "action": "start",
                "reflector": "",
            }}))
            self.assertTrue(self.emit({"D-Star": {
                "timestamp": "2026-10-01T18:10:05.000Z",
                "duration": 5.0,
                "ber": 0.0,
                "action": "end",
            }}))

        row = db.list_transmissions(1)[0]
        self.assertEqual(row["reflector"], "XLX300 D")

    def test_compact_reflector_is_canonicalized(self) -> None:
        with patch("pp5ci_hotspot.events.get_active_reflector", return_value=None):
            self.assertTrue(self.emit({"D-Star": {
                "timestamp": "2026-10-01T18:20:00.000Z",
                "src_callsign": "PU1KSU",
                "src_ext": "",
                "dst_callsign": "CQCQCQ",
                "source": "network",
                "action": "start",
                "reflector": "XLX300D",
            }}))
            self.assertTrue(self.emit({"D-Star": {
                "timestamp": "2026-10-01T18:20:02.000Z",
                "duration": 2.0,
                "loss": 0.0,
                "action": "end",
            }}))

        row = db.list_transmissions(1, reflector="XLX300 D")[0]
        self.assertEqual(row["reflector"], "XLX300 D")

    def test_gateway_journal_corrects_live_direct_target_even_if_host_reports_cqcqcq(self) -> None:
        with patch("pp5ci_hotspot.events.get_active_reflector", return_value="XLX300 D"):
            self.assertTrue(self.emit({"D-Star": {
                "timestamp": "2026-10-03T20:40:00.000Z",
                "src_callsign": "N0CALL",
                "src_ext": "ID52",
                "dst_callsign": "CQCQCQ",
                "source": "rf",
                "action": "start",
                "reflector": "",
            }}))
            before = db.get_runtime_state()
            self.assertEqual(before["reflector"], "XLX300 D")
            self.assertEqual(before["route_type"], "reflector")

            self.assertTrue(self.processor.process_journal_line(
                "N0CALL    is trying to G2 route to callsign PY2ABC   "
            ))
            live = db.get_runtime_state()
            self.assertEqual(live["destination"], "PY2ABC")
            self.assertEqual(live["route_type"], "callsign")
            self.assertEqual(live["contact_callsign"], "PY2ABC")
            self.assertIsNone(live["reflector"])

            self.assertTrue(self.emit({"D-Star": {
                "timestamp": "2026-10-03T20:40:07.000Z",
                "duration": 7.0,
                "ber": 0.0,
                "action": "end",
            }}))

        row = db.list_transmissions(1)[0]
        self.assertEqual(row["dst_callsign"], "PY2ABC")
        self.assertEqual(row["route_type"], "callsign")
        self.assertEqual(row["contact_callsign"], "PY2ABC")
        self.assertIsNone(row["reflector"])

    def test_gateway_callsign_route_can_arrive_before_mqtt_start(self) -> None:
        self.assertTrue(self.processor.process_journal_line(
            "N0CALL is trying to G2 route to callsign PY2ABC"
        ))
        with patch("pp5ci_hotspot.events.get_active_reflector", return_value="XLX300 D"):
            self.assertTrue(self.emit({"D-Star": {
                "timestamp": "2026-10-03T20:41:00.000Z",
                "src_callsign": "N0CALL",
                "src_ext": "ID52",
                "dst_callsign": "CQCQCQ",
                "source": "rf",
                "action": "start",
                "reflector": "",
            }}))

        live = db.get_runtime_state()
        self.assertEqual(live["destination"], "PY2ABC")
        self.assertEqual(live["route_type"], "callsign")
        self.assertEqual(live["contact_callsign"], "PY2ABC")
        self.assertIsNone(live["reflector"])

    def test_outgoing_callsign_routing_is_not_counted_as_reflector(self) -> None:
        with patch("pp5ci_hotspot.events.get_active_reflector", return_value="XLX300 D"):
            self.assertTrue(self.emit({"D-Star": {
                "timestamp": "2026-10-01T18:30:00.000Z",
                "src_callsign": "N0CALL",
                "src_ext": "ID52",
                "dst_callsign": "PY2ABC",
                "source": "rf",
                "action": "start",
                "reflector": "",
            }}))
            state = db.get_runtime_state()
            self.assertEqual(state["route_type"], "callsign")
            self.assertEqual(state["contact_callsign"], "PY2ABC")
            self.assertIsNone(state["reflector"])

            self.assertTrue(self.emit({"D-Star": {
                "timestamp": "2026-10-01T18:30:08.000Z",
                "duration": 8.0,
                "ber": 0.2,
                "action": "end",
            }}))

        row = db.list_transmissions(1)[0]
        self.assertEqual(row["route_type"], "callsign")
        self.assertEqual(row["contact_callsign"], "PY2ABC")
        self.assertIsNone(row["reflector"])

    def test_incoming_callsign_routing_uses_remote_station_as_contact(self) -> None:
        with patch("pp5ci_hotspot.events.get_active_reflector", return_value="XLX300 D"):
            self.assertTrue(self.emit({"D-Star": {
                "timestamp": "2026-10-01T18:40:00.000Z",
                "src_callsign": "PY2ABC",
                "src_ext": "",
                "dst_callsign": "N0CALL",
                "source": "network",
                "action": "start",
                "reflector": "",
            }}))
            self.assertTrue(self.emit({"D-Star": {
                "timestamp": "2026-10-01T18:40:06.000Z",
                "duration": 6.0,
                "loss": 0.0,
                "action": "end",
            }}))

        row = db.list_transmissions(1, callsign="PY2ABC")[0]
        self.assertEqual(row["direction"], "NET_TO_RF")
        self.assertEqual(row["route_type"], "callsign")
        self.assertEqual(row["contact_callsign"], "PY2ABC")
        self.assertIsNone(row["reflector"])

    def test_echo_destination_and_slow_text_are_enriched_from_journal(self) -> None:
        self.assertTrue(self.processor.process_journal_line(
            "M: 2026-10-01 19:51:59.861 D-Star, received RF header from N0CALL   /ID52 to        E"
        ))
        self.assertTrue(self.emit({"D-Star": {
            "timestamp": "2026-10-01T19:51:59.861Z",
            "src_callsign": "N0CALL",
            "src_ext": "ID52",
            "dst_callsign": "",
            "reflector": "",
            "source": "rf",
            "action": "start",
        }}))
        self.assertTrue(self.processor.process_journal_line(
            'M: 2026-10-01 19:52:00.160 D-Star, RF slow data text = "Op. Clezio Cidade"'
        ))
        self.assertTrue(self.emit({"D-Star": {
            "timestamp": "2026-10-01T19:52:04.004Z",
            "duration": 4.16,
            "ber": 0.0,
            "action": "end",
        }}))

        row = db.list_transmissions(1)[0]
        self.assertEqual(row["dst_callsign"], "E")
        self.assertEqual(row["slow_text"], "Op. Clezio Cidade")

    def test_journal_enrichment_also_works_when_mqtt_start_arrives_first(self) -> None:
        self.assertTrue(self.emit({"D-Star": {
            "timestamp": "2026-10-01T19:51:59.861Z",
            "src_callsign": "N0CALL",
            "src_ext": "ID52",
            "dst_callsign": "",
            "reflector": "",
            "source": "rf",
            "action": "start",
        }}))
        self.assertTrue(self.processor.process_journal_line(
            "M: 2026-10-01 19:51:59.861 D-Star, received RF header from N0CALL   /ID52 to        E"
        ))
        state = db.get_runtime_state()
        self.assertEqual(state["destination"], "E")

    def test_network_session_keeps_reflector_and_loss(self) -> None:
        self.assertTrue(self.emit({"D-Star": {
            "timestamp": "2026-10-01T19:00:00.000Z",
            "src_callsign": "PU2PNY",
            "src_ext": "",
            "dst_callsign": "CQCQCQ",
            "source": "network",
            "action": "start",
            "reflector": "XLX026 C",
        }}))
        self.assertTrue(self.emit({"D-Star": {
            "timestamp": "2026-10-01T19:00:05.000Z",
            "duration": 5.0,
            "loss": 2.0,
            "action": "end",
        }}))

        row = db.list_transmissions(1)[0]
        self.assertEqual(row["direction"], "NET_TO_RF")
        self.assertEqual(row["reflector"], "XLX026 C")
        self.assertEqual(row["packet_loss_percent"], 2.0)
        self.assertEqual(db.get_metadata("last_reflector"), "XLX026 C")

    def test_invalid_json_is_ignored(self) -> None:
        self.assertFalse(self.processor.process("{not-json}"))


if __name__ == "__main__":
    unittest.main()
