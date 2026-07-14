#!/usr/bin/env python3
"""Task Managing Manager - macOS Application & Process Manager"""

import os
import sys
import json
import threading
import time
from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scanner.app_scanner import AppScanner
from scanner.process_monitor import ProcessMonitor
from scanner.pkg_history import PkgHistory
from scanner.snapshot import SnapshotManager

app = Flask(__name__)
_secret = os.environ.get('SECRET_KEY')
if not _secret:
    import secrets as _secrets
    _secret = _secrets.token_hex(32)
app.config['SECRET_KEY'] = _secret
socketio = SocketIO(app, cors_allowed_origins="http://127.0.0.1:5050", async_mode='threading')

# Initialize scanner modules
scanner = AppScanner()
monitor = ProcessMonitor()
pkg_history = PkgHistory()

snapshot_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "snapshots")
snapshots = SnapshotManager(snapshot_dir)

# Cache for apps (scanning is slow)
app_cache = {"apps": [], "last_scan": 0}
CACHE_TTL = 60  # seconds

# Background monitoring flag
monitoring_active = False


def get_cached_apps(force=False):
    """Get apps from cache or scan if stale."""
    now = time.time()
    if force or not app_cache["apps"] or (now - app_cache["last_scan"]) > CACHE_TTL:
        app_cache["apps"] = scanner.scan_all_apps()
        app_cache["last_scan"] = now
    return app_cache["apps"]


# --- Routes ---

@app.route("/")
def index():
    return render_template("index.html")


# --- API Endpoints ---

@app.route("/api/apps")
def api_apps():
    """Get all installed applications."""
    force = request.args.get("force", "false").lower() == "true"
    apps = get_cached_apps(force=force)

    # Apply filters
    source_filter = request.args.get("source", "")
    search = request.args.get("search", "").lower()

    filtered = apps
    if source_filter:
        filtered = [a for a in filtered if a["install_source"] == source_filter]
    if search:
        filtered = [a for a in filtered
                    if search in a["name"].lower()
                    or search in a["bundle_id"].lower()
                    or search in a["path"].lower()]

    return jsonify({"apps": filtered, "total": len(apps), "filtered": len(filtered)})


@app.route("/api/apps/sources")
def api_app_sources():
    """Get unique install source categories."""
    apps = get_cached_apps()
    sources = {}
    for a in apps:
        src = a["install_source"]
        sources[src] = sources.get(src, 0) + 1
    return jsonify({"sources": sources})


@app.route("/api/processes")
def api_processes():
    """Get all running processes."""
    procs = monitor.get_all_processes()

    search = request.args.get("search", "").lower()
    show = request.args.get("show", "all")  # all, apps, system

    if search:
        procs = [p for p in procs if search in p["name"].lower() or search in p["cmdline"].lower()]
    if show == "apps":
        procs = [p for p in procs if p["is_app"]]
    elif show == "system":
        procs = [p for p in procs if not p["is_app"]]

    return jsonify({"processes": procs, "count": len(procs)})


@app.route("/api/system")
def api_system():
    """Get system resource stats."""
    stats = monitor.get_system_stats()
    return jsonify(stats)


ALLOWED_APP_DIRS = [
    "/Applications",
    os.path.expanduser("~/Applications"),
    "/System/Applications",
]


def is_allowed_app_path(app_path):
    """Return whether an app resolves inside one of the managed app folders."""
    real_path = os.path.realpath(app_path)
    for directory in ALLOWED_APP_DIRS:
        allowed_dir = os.path.realpath(directory)
        try:
            if os.path.commonpath([real_path, allowed_dir]) == allowed_dir:
                return True
        except ValueError:
            continue
    return False

@app.route("/api/launch", methods=["POST"])
def api_launch():
    """Launch an application."""
    data = request.get_json(silent=True) or {}
    app_path = data.get("path", "")
    if not app_path or not os.path.exists(app_path):
        return jsonify({"success": False, "message": "Invalid app path"}), 400
    if not app_path.endswith(".app"):
        return jsonify({"success": False, "message": "Only .app bundles can be launched"}), 400
    if not is_allowed_app_path(app_path):
        return jsonify({"success": False, "message": "App path is outside allowed directories"}), 400
    result = monitor.launch_app(app_path)
    return jsonify(result)


@app.route("/api/quit", methods=["POST"])
def api_quit():
    """Force quit a process."""
    data = request.get_json(silent=True) or {}
    pid = data.get("pid")
    force = data.get("force", True)
    if not pid:
        return jsonify({"success": False, "message": "PID required"}), 400
    if force:
        result = monitor.force_quit_app(int(pid))
    else:
        result = monitor.graceful_quit_app(int(pid))
    return jsonify(result)


@app.route("/api/pkg-history")
def api_pkg_history():
    """Get package installation history."""
    receipts = pkg_history.get_all_pkg_receipts()
    return jsonify({"receipts": receipts, "count": len(receipts)})


@app.route("/api/pkg-removed")
def api_pkg_removed():
    """Get potentially removed packages."""
    removed = pkg_history.find_potentially_removed_pkgs()
    return jsonify({"removed": removed, "count": len(removed)})


@app.route("/api/snapshots")
def api_snapshots():
    """List all snapshots."""
    snaps = snapshots.list_snapshots()
    return jsonify({"snapshots": snaps})


@app.route("/api/snapshots/save", methods=["POST"])
def api_save_snapshot():
    """Save current app list as snapshot."""
    apps = get_cached_apps(force=True)
    result = snapshots.save_snapshot(apps)
    return jsonify(result)


@app.route("/api/snapshots/compare")
def api_compare_snapshot():
    """Compare current apps with latest snapshot."""
    apps = get_cached_apps()
    result = snapshots.compare_with_latest(apps)
    return jsonify(result)


@app.route("/api/snapshots/<filename>", methods=["DELETE"])
def api_delete_snapshot(filename):
    """Delete a snapshot."""
    success = snapshots.delete_snapshot(filename)
    return jsonify({"success": success})


@app.route("/api/running-apps")
def api_running_apps():
    """Get list of running GUI applications."""
    apps = monitor.get_running_apps()
    return jsonify({"apps": apps})


@app.route("/api/running-apps-detailed")
def api_running_apps_detailed():
    """Get running GUI apps with PID and resource usage."""
    apps = monitor.get_running_apps_detailed()
    return jsonify({"apps": apps, "count": len(apps)})


@app.route("/api/quit-by-name", methods=["POST"])
def api_quit_by_name():
    """Gracefully quit an app by name (AppleScript)."""
    data = request.get_json(silent=True) or {}
    name = data.get("name", "")
    if not name:
        return jsonify({"success": False, "message": "App name required"}), 400
    result = monitor.graceful_quit_by_name(name)
    return jsonify(result)


# --- WebSocket Events ---

@socketio.on('connect')
def handle_connect():
    """Client connected."""
    emit('connected', {'status': 'ok'})


@socketio.on('start_monitoring')
def handle_start_monitoring():
    """Start real-time process monitoring."""
    global monitoring_active
    monitoring_active = True

    def monitor_loop():
        while monitoring_active:
            try:
                stats = monitor.get_system_stats()
                procs = monitor.get_all_processes()
                # Send top 50 processes by CPU
                top_procs = sorted(procs, key=lambda x: x['cpu_percent'], reverse=True)[:50]
                socketio.emit('system_update', {
                    'stats': stats,
                    'top_processes': top_procs,
                    'total_processes': len(procs),
                })
            except Exception as e:
                socketio.emit('monitor_error', {'error': str(e)})
            time.sleep(2)

    thread = threading.Thread(target=monitor_loop, daemon=True)
    thread.start()


@socketio.on('stop_monitoring')
def handle_stop_monitoring():
    """Stop real-time monitoring."""
    global monitoring_active
    monitoring_active = False


@socketio.on('disconnect')
def handle_disconnect():
    """Client disconnected."""
    global monitoring_active
    monitoring_active = False


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  Task Managing Manager")
    print("  macOS Application & Process Manager")
    print("=" * 60)
    print(f"\n  Open in browser: http://127.0.0.1:5050")
    print(f"  Press Ctrl+C to stop\n")
    socketio.run(app, host="127.0.0.1", port=5050, debug=False, allow_unsafe_werkzeug=True)
