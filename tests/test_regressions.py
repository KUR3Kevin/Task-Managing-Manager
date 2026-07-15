import os
import subprocess
import threading
import time
import unittest
from unittest.mock import patch


os.environ.setdefault("FLASK_SECRET_KEY", "test-secret-key")

import app as app_module
from scanner.app_scanner import AppScanner
from scanner.process_monitor import ProcessMonitor


class ApiRegressionTests(unittest.TestCase):
    def setUp(self):
        app_module.app.config.update(TESTING=True)
        app_module._rate_store.clear()
        self.client = app_module.app.test_client()

    def test_index_renders(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Task Managing Manager", response.data)

    @patch.object(app_module.scanner, "scan_all_apps")
    def test_concurrent_cache_misses_share_one_scan(self, scan_all_apps):
        scan_started = threading.Event()
        release_scan = threading.Event()

        def slow_scan():
            scan_started.set()
            release_scan.wait(timeout=2)
            return [{"name": "Test App"}]

        scan_all_apps.side_effect = slow_scan
        app_module.app_cache.update(apps=[], last_scan=0)
        results = []
        workers = [
            threading.Thread(target=lambda: results.append(app_module.get_cached_apps()))
            for _ in range(2)
        ]

        workers[0].start()
        self.assertTrue(scan_started.wait(timeout=1))
        workers[1].start()
        time.sleep(0.02)
        release_scan.set()
        for worker in workers:
            worker.join(timeout=2)

        self.assertEqual(scan_all_apps.call_count, 1)
        self.assertEqual(results, [[{"name": "Test App"}], [{"name": "Test App"}]])

    def test_json_endpoints_reject_missing_bodies_cleanly(self):
        for endpoint in ("/api/launch", "/api/quit", "/api/quit-by-name"):
            with self.subTest(endpoint=endpoint):
                response = self.client.post(endpoint)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.get_json()["success"], False)

    def test_quit_rejects_invalid_pids(self):
        for pid in (None, "", "abc", 0, -1):
            with self.subTest(pid=pid):
                response = self.client.post("/api/quit", json={"pid": pid})
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.get_json()["message"], "Valid PID required")

    @patch.object(app_module.monitor, "graceful_quit_app")
    @patch.object(app_module.monitor, "force_quit_app")
    def test_quit_routes_to_requested_mode(self, force_quit, graceful_quit):
        force_quit.return_value = {"success": True}
        graceful_quit.return_value = {"success": True}

        force_response = self.client.post("/api/quit", json={"pid": "42"})
        graceful_response = self.client.post(
            "/api/quit", json={"pid": 43, "force": False}
        )

        self.assertEqual(force_response.status_code, 200)
        self.assertEqual(graceful_response.status_code, 200)
        force_quit.assert_called_once_with(42)
        graceful_quit.assert_called_once_with(43)

    @patch.object(app_module.monitor, "launch_app")
    def test_launch_validates_path_before_launching(self, launch_app):
        missing = self.client.post("/api/launch", json={"path": "/not/here.app"})
        self.assertEqual(missing.status_code, 400)
        launch_app.assert_not_called()


class ProcessMonitorRegressionTests(unittest.TestCase):
    @patch("scanner.process_monitor.subprocess.run")
    def test_graceful_quit_accepts_name_from_running_app_list(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, "", "")
        monitor = ProcessMonitor()

        with patch.object(monitor, "get_running_apps", return_value=["Safari"]):
            result = monitor.graceful_quit_by_name("Safari")

        self.assertTrue(result["success"])
        self.assertEqual(run.call_args.args[0][-1], 'tell application "Safari" to quit')

    @patch("scanner.process_monitor.subprocess.run")
    def test_graceful_quit_rejects_unknown_or_unsafe_names(self, run):
        monitor = ProcessMonitor()

        with patch.object(monitor, "get_running_apps", return_value=["Safari"]):
            unknown = monitor.graceful_quit_by_name("Notes")
            unsafe = monitor.graceful_quit_by_name('Safari" & do shell script "bad')

        self.assertFalse(unknown["success"])
        self.assertFalse(unsafe["success"])
        run.assert_not_called()


class AppScannerRegressionTests(unittest.TestCase):
    @patch("scanner.app_scanner.subprocess.run")
    def test_pkg_receipts_are_loaded_only_once_per_scan(self, run):
        run.return_value = subprocess.CompletedProcess(
            [], 0, "com.example.first\ncom.example.second\n", ""
        )
        scanner = AppScanner()
        scanner._homebrew_prefix = None

        first = scanner._detect_install_source(
            "/Applications/First.app", "com.example.first"
        )
        second = scanner._detect_install_source(
            "/Applications/Second.app", "com.example.second"
        )

        self.assertEqual(first, ".pkg Installer")
        self.assertEqual(second, ".pkg Installer")
        run.assert_called_once_with(
            ["pkgutil", "--pkgs"], capture_output=True, text=True, timeout=10
        )


if __name__ == "__main__":
    unittest.main()
