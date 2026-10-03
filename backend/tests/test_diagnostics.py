from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from pp5ci_hotspot.diagnostics_api import _hosts_schedule, _ipv4_proc_hex, _seconds_since


class DiagnosticsTests(unittest.TestCase):
    def test_ipv4_proc_encoding(self) -> None:
        self.assertEqual(_ipv4_proc_hex("127.0.0.1"), "0100007F")

    def test_schedule_parser(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "schedule.conf"
            path.write_text("[Timer]\nOnCalendar=*-*-* 03:45:00\n", encoding="utf-8")
            with patch("pp5ci_hotspot.diagnostics_api.HOST_TIMER_DROPIN", path):
                self.assertEqual(_hosts_schedule(), "03:45")

    def test_seconds_since_unix_timestamp(self) -> None:
        value = str(int(time.time()) - 5)
        seconds = _seconds_since(value)
        self.assertIsNotNone(seconds)
        assert seconds is not None
        self.assertGreaterEqual(seconds, 4)
        self.assertLess(seconds, 30)

    def test_seconds_since_invalid_is_safe(self) -> None:
        self.assertIsNone(_seconds_since("invalid"))


if __name__ == "__main__":
    unittest.main()
