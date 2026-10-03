from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pp5ci_hotspot import updates_api
from pp5ci_hotspot.updates_api import _asset_info, _release_record, _version_key


class UpdatesTests(unittest.TestCase):
    def test_stable_version_sorts_after_dev(self) -> None:
        self.assertGreater(_version_key("v0.2.0"), _version_key("0.2.0-dev"))

    def test_new_minor_sorts_after_old(self) -> None:
        self.assertGreater(_version_key("v0.3.0"), _version_key("v0.2.9"))

    def test_assets_are_detected(self) -> None:
        release = {
            "assets": [
                {"name": "pp5ci-hotspot-v0.2.0.tar.gz", "size": 10, "browser_download_url": "a", "url": "api-a"},
                {"name": "pp5ci-hotspot-v0.2.0.tar.gz.sha256", "size": 2, "browser_download_url": "b", "url": "api-b"},
            ]
        }
        assets = _asset_info(release)
        self.assertEqual(assets["artifact"]["name"], "pp5ci-hotspot-v0.2.0.tar.gz")
        self.assertEqual(assets["checksum"]["name"], "pp5ci-hotspot-v0.2.0.tar.gz.sha256")

    def test_release_record_has_notes(self) -> None:
        item = _release_record({"tag_name": "v0.2.0", "body": "Notas", "assets": []})
        self.assertEqual(item["tag"], "v0.2.0")
        self.assertEqual(item["body"], "Notas")

    def test_operation_defaults_to_idle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "missing.json"
            with patch.object(updates_api, "UPDATE_STATUS", path):
                operation = updates_api._operation()
        self.assertEqual(operation["state"], "idle")
        self.assertEqual(operation["progress"], 0)

    def test_operation_reads_real_status_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "status.json"
            path.write_text(json.dumps({
                "state": "running",
                "operation": "install",
                "step": "backup",
                "progress": 40,
                "message": "Backup",
            }), encoding="utf-8")
            with patch.object(updates_api, "UPDATE_STATUS", path):
                operation = updates_api._operation()
        self.assertEqual(operation["state"], "running")
        self.assertEqual(operation["step"], "backup")
        self.assertEqual(operation["progress"], 40)

    def test_rollback_options_expose_id_not_filesystem_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            backup = root / "20261002T000000Z-0.2.0"
            backup.mkdir()
            (backup / "metadata.json").write_text(json.dumps({
                "id": backup.name,
                "version": "0.2.0",
                "created_at": "2026-10-02T00:00:00Z",
                "sha256": "abc",
            }), encoding="utf-8")
            with patch.object(updates_api, "RELEASES_ROOT", root):
                items = updates_api._rollback_items()
        self.assertEqual(items[0]["id"], backup.name)
        self.assertNotIn("path", items[0])


if __name__ == "__main__":
    unittest.main()
