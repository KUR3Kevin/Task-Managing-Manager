import json
import os
from datetime import datetime
from pathlib import Path


class SnapshotManager:
    """Manage snapshots of installed apps for tracking changes over time."""

    def __init__(self, snapshot_dir="snapshots"):
        self.snapshot_dir = snapshot_dir
        os.makedirs(snapshot_dir, exist_ok=True)

    def save_snapshot(self, apps):
        """Save current app list as a timestamped snapshot."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"snapshot_{timestamp}.json"
        filepath = os.path.join(self.snapshot_dir, filename)

        snapshot_data = {
            "timestamp": datetime.now().isoformat(),
            "app_count": len(apps),
            "apps": {
                app["bundle_id"]: {
                    "name": app["name"],
                    "version": app["version"],
                    "path": app["path"],
                    "size_human": app["size_human"],
                    "install_source": app["install_source"],
                }
                for app in apps
            }
        }

        with open(filepath, "w") as f:
            json.dump(snapshot_data, f, indent=2)

        return {"filename": filename, "path": filepath, "app_count": len(apps)}

    def list_snapshots(self):
        """List all available snapshots."""
        snapshots = []
        for f in sorted(os.listdir(self.snapshot_dir)):
            if f.startswith("snapshot_") and f.endswith(".json"):
                filepath = os.path.join(self.snapshot_dir, f)
                try:
                    with open(filepath, "r") as fh:
                        data = json.load(fh)
                    snapshots.append({
                        "filename": f,
                        "timestamp": data.get("timestamp", "Unknown"),
                        "app_count": data.get("app_count", 0),
                    })
                except Exception:
                    continue
        return snapshots

    def compare_with_latest(self, current_apps):
        """Compare current apps with the most recent snapshot."""
        snapshots = self.list_snapshots()
        if not snapshots:
            return {"has_previous": False, "message": "No previous snapshots found. Save one first."}

        latest = snapshots[-1]
        filepath = os.path.join(self.snapshot_dir, latest["filename"])

        with open(filepath, "r") as f:
            previous = json.load(f)

        prev_apps = previous.get("apps", {})
        curr_bundle_ids = {app["bundle_id"] for app in current_apps}
        prev_bundle_ids = set(prev_apps.keys())

        # New apps (in current but not in previous)
        added = []
        for app in current_apps:
            if app["bundle_id"] not in prev_bundle_ids:
                added.append({
                    "name": app["name"],
                    "bundle_id": app["bundle_id"],
                    "version": app["version"],
                    "install_source": app["install_source"],
                })

        # Removed apps (in previous but not in current)
        removed = []
        for bid, info in prev_apps.items():
            if bid not in curr_bundle_ids:
                removed.append({
                    "name": info["name"],
                    "bundle_id": bid,
                    "version": info["version"],
                    "install_source": info.get("install_source", "Unknown"),
                })

        # Updated apps (version changed)
        updated = []
        for app in current_apps:
            if app["bundle_id"] in prev_bundle_ids:
                prev_ver = prev_apps[app["bundle_id"]].get("version", "")
                if prev_ver and prev_ver != app["version"]:
                    updated.append({
                        "name": app["name"],
                        "bundle_id": app["bundle_id"],
                        "old_version": prev_ver,
                        "new_version": app["version"],
                    })

        return {
            "has_previous": True,
            "snapshot_date": previous.get("timestamp", "Unknown"),
            "previous_count": len(prev_bundle_ids),
            "current_count": len(curr_bundle_ids),
            "added": added,
            "removed": removed,
            "updated": updated,
            "added_count": len(added),
            "removed_count": len(removed),
            "updated_count": len(updated),
        }

    def delete_snapshot(self, filename):
        """Delete a specific snapshot."""
        # Resolve both paths to their real, canonical forms so that any
        # remaining traversal sequences (e.g. symlinks) are eliminated before
        # we compare.  If the resolved file path doesn't start with the
        # resolved snapshot directory, refuse the operation.
        safe_dir = os.path.realpath(self.snapshot_dir)
        filepath = os.path.realpath(os.path.join(self.snapshot_dir, filename))
        if not filepath.startswith(safe_dir + os.sep):
            return False
        # Only delete files that look like our own snapshots.
        if not (os.path.basename(filepath).startswith("snapshot_")
                and filepath.endswith(".json")):
            return False
        if os.path.exists(filepath):
            os.remove(filepath)
            return True
        return False
