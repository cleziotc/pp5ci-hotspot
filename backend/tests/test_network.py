from __future__ import annotations

import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pp5ci_hotspot import db, network_api, network_db
from pp5ci_hotspot.network_monitor import NetworkMonitor, get_active_link, get_active_reflector, get_ircddb_user, remember_ircddb_user_from_line, resolve_reflector_host


class NetworkQualityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        db.DB_PATH = Path(self.tmp.name) / "network.db"
        network_db.initialise()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_summary_uses_rolling_latency_jitter_and_loss(self) -> None:
        rows = [
            {"success": 1, "rtt_ms": 30.0},
            {"success": 1, "rtt_ms": 34.0},
            {"success": 0, "rtt_ms": None},
            {"success": 1, "rtt_ms": 38.0},
        ]
        summary = network_db.summarize(rows)
        self.assertEqual(summary["latency_ms"], 34.0)
        self.assertEqual(summary["jitter_ms"], 4.0)
        self.assertEqual(summary["loss_percent"], 25.0)
        self.assertEqual(summary["state"], "poor")

    def test_latency_band_is_good_through_100_ms(self) -> None:
        rows = [
            {"success": 1, "rtt_ms": 98.0},
            {"success": 1, "rtt_ms": 100.0},
            {"success": 1, "rtt_ms": 100.0},
        ]
        summary = network_db.summarize(rows)
        self.assertEqual(summary["latency_ms"], 100.0)
        self.assertEqual(summary["state"], "good")

    def test_intercontinental_latency_band_is_attention_through_260_ms(self) -> None:
        rows = [
            {"success": 1, "rtt_ms": 238.0},
            {"success": 1, "rtt_ms": 245.0},
            {"success": 1, "rtt_ms": 260.0},
        ]
        summary = network_db.summarize(rows)
        self.assertEqual(summary["latency_ms"], 245.0)
        self.assertLess(summary["jitter_ms"], 40.0)
        self.assertEqual(summary["loss_percent"], 0.0)
        self.assertEqual(summary["state"], "degraded")

    def test_latency_above_260_ms_is_poor(self) -> None:
        rows = [
            {"success": 1, "rtt_ms": 261.0},
            {"success": 1, "rtt_ms": 270.0},
            {"success": 1, "rtt_ms": 265.0},
        ]
        summary = network_db.summarize(rows)
        self.assertGreater(summary["latency_ms"], 260.0)
        self.assertEqual(summary["state"], "poor")

    def test_loss_can_worsen_good_latency(self) -> None:
        rows = [
            {"success": 1, "rtt_ms": 50.0},
            {"success": 1, "rtt_ms": 52.0},
            {"success": 0, "rtt_ms": None},
            {"success": 1, "rtt_ms": 51.0},
        ]
        summary = network_db.summarize(rows)
        self.assertEqual(summary["state"], "poor")

    def test_samples_are_stored_and_bucketized(self) -> None:
        now = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)
        for index, rtt in enumerate((20.0, 24.0, 28.0)):
            network_db.insert_sample(
                sampled_at=(now + timedelta(minutes=index)).isoformat().replace("+00:00", "Z"),
                target="reflector",
                reflector="XLX300 D",
                host="93.95.227.114",
                ip="93.95.227.114",
                port=443,
                success=True,
                rtt_ms=rtt,
            )

        rows = network_db.list_samples(
            "reflector",
            (now - timedelta(minutes=1)).isoformat().replace("+00:00", "Z"),
            reflector="XLX300 D",
        )
        self.assertEqual(len(rows), 3)
        buckets = network_db.bucketize(rows, 10)
        self.assertEqual(len(buckets), 1)
        self.assertEqual(buckets[0]["latency_ms"], 24.0)

    def test_missing_transmission_reflector_is_recovered_from_nearby_network_sample(self) -> None:
        started = datetime(2026, 10, 3, 15, 0, 5, tzinfo=timezone.utc)
        db.insert_transmission({
            "started_at": started.isoformat().replace("+00:00", "Z"),
            "ended_at": (started + timedelta(seconds=4)).isoformat().replace("+00:00", "Z"),
            "direction": "RF_TO_NET",
            "source": "rf",
            "src_callsign": "N0CALL",
            "src_ext": "ID52",
            "dst_callsign": "CQCQCQ",
            "reflector": "",
            "duration_seconds": 4.0,
            "ber_percent": 0.0,
        })
        network_db.insert_sample(
            sampled_at=(started - timedelta(seconds=2)).isoformat().replace("+00:00", "Z"),
            target="reflector",
            reflector="XLX300 D",
            host="93.95.227.114",
            ip="93.95.227.114",
            port=443,
            success=True,
            rtt_ms=250.0,
        )

        changed = network_db.backfill_unassigned_transmission_reflectors()
        rows = db.list_transmissions(10, reflector="XLX300D")

        self.assertEqual(changed, 1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["reflector"], "XLX300 D")

    def test_ircddb_user_log_populates_direct_gateway_cache(self) -> None:
        line = "USER: PY2ABC    PY2ABC B  PY2ABC G  203.0.113.45"
        self.assertTrue(remember_ircddb_user_from_line(line))
        item = get_ircddb_user("PY2ABC")
        self.assertIsNotNone(item)
        self.assertEqual(item["address"], "203.0.113.45")

    def test_direct_target_is_held_for_60_seconds_and_cancelled_by_reflector_traffic(self) -> None:
        monitor = NetworkMonitor()
        db.set_runtime_state({
            "state": "active",
            "route_type": "callsign",
            "contact_callsign": "PY2ABC",
        }, "2026-10-03T20:00:00Z")
        remember_ircddb_user_from_line("USER: PY2ABC    PY2ABC B  PY2ABC G  203.0.113.45")

        with patch("pp5ci_hotspot.network_monitor.time.monotonic", return_value=100.0):
            callsign, endpoint = monitor._traffic_target()
        self.assertEqual(callsign, "PY2ABC")
        self.assertEqual(endpoint["address"], "203.0.113.45")

        db.set_runtime_state({
            "state": "idle",
            "route_type": None,
            "contact_callsign": None,
        }, "2026-10-03T20:00:08Z")
        with patch("pp5ci_hotspot.network_monitor.time.monotonic", return_value=150.0):
            callsign, _endpoint = monitor._traffic_target()
        self.assertEqual(callsign, "PY2ABC")

        db.set_runtime_state({
            "state": "active",
            "route_type": "reflector",
            "contact_callsign": None,
        }, "2026-10-03T20:00:20Z")
        with patch("pp5ci_hotspot.network_monitor.time.monotonic", return_value=151.0):
            callsign, endpoint = monitor._traffic_target()
        self.assertIsNone(callsign)
        self.assertIsNone(endpoint)

    def test_direct_target_expires_after_60_seconds_idle(self) -> None:
        monitor = NetworkMonitor()
        db.set_runtime_state({
            "state": "active",
            "route_type": "callsign",
            "contact_callsign": "PY2ABC",
        }, "2026-10-03T20:00:00Z")
        with patch("pp5ci_hotspot.network_monitor.time.monotonic", return_value=100.0):
            monitor._traffic_target()

        db.set_runtime_state({
            "state": "idle",
            "route_type": None,
            "contact_callsign": None,
        }, "2026-10-03T20:00:02Z")
        with patch("pp5ci_hotspot.network_monitor.time.monotonic", return_value=161.0):
            callsign, endpoint = monitor._traffic_target()
        self.assertIsNone(callsign)
        self.assertIsNone(endpoint)

    def test_network_api_prefers_recent_direct_target_and_live_reflector_override(self) -> None:
        now = datetime.now(timezone.utc)
        network_db.insert_sample(
            sampled_at=(now - timedelta(seconds=8)).isoformat().replace("+00:00", "Z"),
            target="reflector",
            reflector="XLX300 D",
            host="93.95.227.114",
            ip="93.95.227.114",
            port=443,
            success=True,
            rtt_ms=250.0,
        )
        network_db.insert_sample(
            sampled_at=now.isoformat().replace("+00:00", "Z"),
            target="direct",
            callsign="PY2ABC",
            host="203.0.113.45",
            ip="203.0.113.45",
            port=40000,
            success=True,
            rtt_ms=42.0,
        )
        db.set_runtime_state({
            "state": "idle",
            "route_type": None,
            "contact_callsign": None,
        }, now.isoformat().replace("+00:00", "Z"))

        with patch("pp5ci_hotspot.network_api.get_active_link", return_value={
            "reflector": "XLX300 D",
            "protocol": "DCS",
            "udp_port": 30051,
        }):
            result = network_api.current_network_quality()
        self.assertEqual(result["active_target"]["target_type"], "callsign")
        self.assertEqual(result["active_target"]["callsign"], "PY2ABC")
        self.assertEqual(result["active_target"]["ip"], "203.0.113.45")

        db.set_runtime_state({
            "state": "active",
            "route_type": "reflector",
            "contact_callsign": None,
        }, now.isoformat().replace("+00:00", "Z"))
        with patch("pp5ci_hotspot.network_api.get_active_link", return_value={
            "reflector": "XLX300 D",
            "protocol": "DCS",
            "udp_port": 30051,
        }):
            result = network_api.current_network_quality()
        self.assertEqual(result["active_target"]["target_type"], "reflector")
        self.assertEqual(result["active_target"]["name"], "XLX300 D")

    def test_xlx_host_and_links_log_are_resolved_without_icmp(self) -> None:
        root = Path(self.tmp.name)
        links = root / "Links.log"
        links.write_text(
            "2026-10-03 Refl: XLX300 D Dir: Outgoing Protocol: DCS\n",
            encoding="utf-8",
        )
        (root / "XLXHosts.txt").write_text(
            "300;93.95.227.114;40000\n301;example.invalid;40000\n",
            encoding="utf-8",
        )

        self.assertEqual(get_active_reflector(links), "XLX300 D")
        link = get_active_link(links)
        self.assertIsNotNone(link)
        self.assertEqual(link["protocol"], "DCS")
        self.assertEqual(link["udp_port"], 30051)
        host, ip = resolve_reflector_host("XLX300 D", root)
        self.assertEqual(host, "93.95.227.114")
        self.assertEqual(ip, "93.95.227.114")


if __name__ == "__main__":
    unittest.main()
