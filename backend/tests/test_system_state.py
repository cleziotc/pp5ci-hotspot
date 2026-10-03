from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pp5ci_hotspot.system_state import _active_reflector_from_links_log


class SystemStateTests(unittest.TestCase):
    def test_links_log_detects_xlx_outgoing_link(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Links.log"
            path.write_text(
                "2026-10-02 00:55:04: DCS link - Type: Repeater Rptr: N0CALL  A Refl: XLX300 D Dir: Outgoing\n",
                encoding="utf-8",
            )
            available, reflector = _active_reflector_from_links_log(path)
            self.assertTrue(available)
            self.assertEqual(reflector, "XLX300 D")

    def test_links_log_supports_ref_xrf_and_dcs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Links.log"
            for expected in ("REF001 C", "XRF123 A", "DCS300 D"):
                path.write_text(
                    f"2026-10-02 00:55:04: DPlus link - Type: Repeater Rptr: N0CALL  A Refl: {expected} Dir: Outgoing\n",
                    encoding="utf-8",
                )
                available, reflector = _active_reflector_from_links_log(path)
                self.assertTrue(available)
                self.assertEqual(reflector, expected)

    def test_existing_empty_links_log_means_unlinked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Links.log"
            path.write_text("", encoding="utf-8")
            available, reflector = _active_reflector_from_links_log(path)
            self.assertTrue(available)
            self.assertIsNone(reflector)

    def test_missing_links_log_allows_compatibility_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            available, reflector = _active_reflector_from_links_log(Path(tmp) / "missing.log")
            self.assertFalse(available)
            self.assertIsNone(reflector)


if __name__ == "__main__":
    unittest.main()
