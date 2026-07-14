import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app import app, is_allowed_app_path
from scanner.app_scanner import AppScanner
from scanner.snapshot import SnapshotManager


class ApiSafetyTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_index_loads(self):
        self.assertEqual(self.client.get("/").status_code, 200)

    def test_launch_rejects_missing_json(self):
        response = self.client.post("/api/launch")
        self.assertEqual(response.status_code, 400)

    def test_quit_rejects_missing_json(self):
        response = self.client.post("/api/quit")
        self.assertEqual(response.status_code, 400)

    def test_allowed_path_check_uses_directory_boundaries(self):
        self.assertTrue(is_allowed_app_path("/Applications/Example.app"))
        self.assertFalse(is_allowed_app_path("/Applications-Evil/Example.app"))


class ScannerTests(unittest.TestCase):
    def test_mdls_errors_fall_back_to_creation_date(self):
        scanner = AppScanner()
        failed = SimpleNamespace(returncode=1, stdout="could not find app", stderr="")
        with tempfile.TemporaryDirectory() as app_path:
            with patch("scanner.app_scanner.subprocess.run", return_value=failed):
                metadata = scanner._get_mdls_metadata(app_path)

        self.assertIn("install_date", metadata)
        self.assertNotIn("could not find", metadata["install_date"])

    def test_architectures_are_read_from_lipo(self):
        scanner = AppScanner()
        result = SimpleNamespace(returncode=0, stdout="arm64 x86_64\n", stderr="")
        with tempfile.TemporaryDirectory(suffix=".app") as app_path:
            executable_dir = os.path.join(app_path, "Contents", "MacOS")
            os.makedirs(executable_dir)
            executable_path = os.path.join(executable_dir, "Example")
            with open(executable_path, "w", encoding="utf-8"):
                pass
            with patch("scanner.app_scanner.subprocess.run", return_value=result):
                architectures = scanner._get_architectures(
                    app_path, {"CFBundleExecutable": "Example"}
                )

        self.assertEqual(architectures, ["arm64", "x86_64"])


class SnapshotSafetyTests(unittest.TestCase):
    def test_delete_rejects_non_snapshot_names(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = SnapshotManager(directory)
            self.assertFalse(manager.delete_snapshot("../settings.json"))
            self.assertFalse(manager.delete_snapshot("notes.json"))


if __name__ == "__main__":
    unittest.main()
