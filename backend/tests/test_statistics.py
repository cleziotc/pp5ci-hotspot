from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pp5ci_hotspot import api, db


class StatisticsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        db.DB_PATH = Path(self.tmp.name) / "statistics.db"
        db.initialise()
        api.TZ_NAME = "UTC"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_live_traffic_is_enriched_before_qso_ends(self) -> None:
        now = datetime.now(timezone.utc)
        db.replace_callsign_directory(
            [{"callsign": "PU2PYC", "name": "Jefferson", "location": "W3 MD US"}],
            now.isoformat().replace("+00:00", "Z"),
            "users.csv",
        )

        traffic = api._enrich_live_traffic({
            "state": "active",
            "station": "pu2pyc",
            "direction": "NET_TO_RF",
        })

        self.assertEqual(traffic["name"], "Jefferson")
        self.assertEqual(traffic["location"], "W3 MD US")

    def test_live_traffic_unknown_callsign_does_not_invent_identity(self) -> None:
        traffic = api._enrich_live_traffic({
            "state": "active",
            "station": "ZZ0ZZZ",
            "direction": "NET_TO_RF",
        })
        self.assertIsNone(traffic["name"])
        self.assertIsNone(traffic["location"])

    def test_statistics_can_be_scoped_to_reflector(self) -> None:
        now = datetime.now(timezone.utc)
        started = now - timedelta(minutes=5)
        for reflector, duration in (("XLX300 D", 10.0), ("REF018 C", 20.0), ("REF018 C", 30.0)):
            db.insert_transmission({
                "started_at": started.isoformat().replace("+00:00", "Z"),
                "ended_at": (started + timedelta(seconds=duration)).isoformat().replace("+00:00", "Z"),
                "direction": "NET_TO_RF",
                "source": "network",
                "src_callsign": "N0CALL",
                "src_ext": None,
                "dst_callsign": "CQCQCQ",
                "reflector": reflector,
                "duration_seconds": duration,
                "packet_loss_percent": 0.0,
            })

        all_stats = api.statistics()
        ref_stats = api.statistics("REF018 C")

        self.assertEqual(all_stats["today"]["transmissions"], 3)
        self.assertEqual(ref_stats["scope"]["reflector"], "REF018 C")
        self.assertEqual(ref_stats["today"]["transmissions"], 2)
        self.assertEqual(ref_stats["today"]["airtime_seconds"], 50.0)
        self.assertEqual(ref_stats["last_30d"]["transmissions"], 2)
        self.assertEqual(ref_stats["available_reflectors"], ["REF018 C", "XLX300 D"])
        self.assertEqual(len(ref_stats["reflector_usage_30d"]), 2)

        recent = db.list_transmissions(10, reflector="REF018 C")
        self.assertEqual(len(recent), 2)
        self.assertTrue(all(row["reflector"] == "REF018 C" for row in recent))

    def test_statistics_can_be_scoped_to_direct_callsign(self) -> None:
        now = datetime.now(timezone.utc)
        started = now - timedelta(minutes=3)
        for direction, src, dst, duration in (
            ("RF_TO_NET", "N0CALL", "PY2ABC", 12.0),
            ("NET_TO_RF", "PY2ABC", "N0CALL", 18.0),
        ):
            db.insert_transmission({
                "started_at": started.isoformat().replace("+00:00", "Z"),
                "ended_at": (started + timedelta(seconds=duration)).isoformat().replace("+00:00", "Z"),
                "direction": direction,
                "source": "rf" if direction == "RF_TO_NET" else "network",
                "src_callsign": src,
                "src_ext": "ID52" if direction == "RF_TO_NET" else None,
                "dst_callsign": dst,
                "reflector": None,
                "route_type": "callsign",
                "contact_callsign": "PY2ABC",
                "duration_seconds": duration,
                "ber_percent": 0.0 if direction == "RF_TO_NET" else None,
                "packet_loss_percent": 0.0 if direction == "NET_TO_RF" else None,
            })

        result = api.statistics(callsign="PY2ABC")

        self.assertEqual(result["scope"]["type"], "callsign")
        self.assertEqual(result["scope"]["callsign"], "PY2ABC")
        self.assertEqual(result["today"]["transmissions"], 2)
        self.assertEqual(result["today"]["airtime_seconds"], 30.0)
        self.assertIn("PY2ABC", result["available_callsigns"])
        self.assertEqual(result["callsign_usage_30d"][0]["callsign"], "PY2ABC")

        recent = db.list_transmissions(10, callsign="PY2ABC")
        self.assertEqual(len(recent), 2)
        self.assertTrue(all(row["route_type"] == "callsign" for row in recent))

    def test_statistics_are_live_and_enriched(self) -> None:
        now = datetime.now(timezone.utc)
        db.replace_callsign_directory(
            [{"callsign": "N0CALL", "name": "Clezio", "location": "Cidade - SC"}],
            now.isoformat().replace("+00:00", "Z"),
            "users.csv",
        )
        for seconds in (10.0, 20.0):
            started = now - timedelta(minutes=5)
            db.insert_transmission({
                "started_at": started.isoformat().replace("+00:00", "Z"),
                "ended_at": (started + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z"),
                "direction": "RF_TO_NET",
                "source": "rf",
                "src_callsign": "N0CALL",
                "src_ext": "ID52",
                "dst_callsign": "CQCQCQ",
                "duration_seconds": seconds,
            })

        result = api.statistics()
        self.assertEqual(result["today"]["transmissions"], 2)
        self.assertEqual(result["last_30d"]["transmissions"], 2)
        self.assertEqual(result["average_qso_seconds_30d"], 15.0)
        self.assertEqual(result["top_stations"][0]["callsign"], "N0CALL")
        self.assertEqual(result["top_stations"][0]["name"], "Clezio")
        self.assertEqual(result["top_stations"][0]["location"], "Cidade - SC")
        self.assertEqual(result["directory_coverage_30d"]["matched_callsigns"], 1)
        self.assertEqual(result["directory_coverage_30d"]["enriched_transmissions"], 2)
        self.assertIsNotNone(result["peak_hour_today"])


if __name__ == "__main__":
    unittest.main()
