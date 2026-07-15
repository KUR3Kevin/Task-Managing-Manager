import os
import subprocess
import plistlib
import json
from pathlib import Path
from datetime import datetime


class AppScanner:
    """Scans /Applications and ~/Applications for installed apps."""

    SEARCH_DIRS = [
        "/Applications",
        os.path.expanduser("~/Applications"),
        # Apple system apps live here on macOS Catalina+
        # (FaceTime, Calendar, Maps, Messages, etc.)
        "/System/Applications",
        "/System/Applications/Utilities",
    ]

    def __init__(self):
        self._cache = {}
        self._homebrew_prefix = self._detect_homebrew_prefix()
        self._homebrew_casks = None
        self._pkg_receipts = None

    def _detect_homebrew_prefix(self):
        """Detect Homebrew installation prefix."""
        for prefix in ["/opt/homebrew", "/usr/local"]:
            if os.path.isdir(os.path.join(prefix, "Cellar")):
                return prefix
        return None

    def scan_all_apps(self):
        """Scan all application directories and return app info list."""
        apps = []
        seen_bundles = set()
        seen_paths = set()

        # Refresh install-source data once per scan, then reuse it for every app.
        self._homebrew_casks = None
        self._pkg_receipts = None

        for search_dir in self.SEARCH_DIRS:
            if not os.path.isdir(search_dir):
                continue
            for item in os.listdir(search_dir):
                if item.endswith(".app"):
                    app_path = os.path.join(search_dir, item)
                    canonical_path = os.path.realpath(app_path)
                    if canonical_path in seen_paths:
                        continue
                    seen_paths.add(canonical_path)
                    info = self._get_app_info(app_path)
                    if info and info["bundle_id"] not in seen_bundles:
                        seen_bundles.add(info["bundle_id"])
                        apps.append(info)

            # Also scan subdirectories one level deep (e.g., /Applications/Utilities/)
            for subdir in os.listdir(search_dir):
                subdir_path = os.path.join(search_dir, subdir)
                if os.path.isdir(subdir_path) and not subdir.endswith(".app"):
                    try:
                        for item in os.listdir(subdir_path):
                            if item.endswith(".app"):
                                app_path = os.path.join(subdir_path, item)
                                canonical_path = os.path.realpath(app_path)
                                if canonical_path in seen_paths:
                                    continue
                                seen_paths.add(canonical_path)
                                info = self._get_app_info(app_path)
                                if info and info["bundle_id"] not in seen_bundles:
                                    seen_bundles.add(info["bundle_id"])
                                    apps.append(info)
                    except PermissionError:
                        continue

        apps.sort(key=lambda x: x["name"].lower())
        return apps

    def _get_app_info(self, app_path):
        """Extract detailed info from a .app bundle."""
        try:
            info_plist_path = os.path.join(app_path, "Contents", "Info.plist")
            if not os.path.exists(info_plist_path):
                # Some apps use different structure
                info_plist_path = os.path.join(app_path, "Info.plist")
                if not os.path.exists(info_plist_path):
                    return self._basic_app_info(app_path)

            with open(info_plist_path, "rb") as f:
                plist = plistlib.load(f)

            plist_name = plist.get("CFBundleDisplayName") or plist.get("CFBundleName") or Path(app_path).stem
            folder_name = Path(app_path).stem  # e.g., "Visual Studio Code"
            # Prefer folder name when plist name is too short/generic (e.g., "Code" vs "Visual Studio Code")
            if len(folder_name) > len(plist_name) and plist_name.lower() in folder_name.lower():
                name = folder_name
            else:
                name = plist_name
            bundle_id = plist.get("CFBundleIdentifier", f"unknown.{Path(app_path).stem}")
            version = plist.get("CFBundleShortVersionString", "Unknown")
            build = plist.get("CFBundleVersion", "")

            # Get file size
            size = self._get_app_size(app_path)

            # Get metadata via mdls
            metadata = self._get_mdls_metadata(app_path)

            # Detect install source
            source = self._detect_install_source(app_path, bundle_id)

            # Get icon path (for frontend reference)
            icon_file = plist.get("CFBundleIconFile", "")
            if icon_file and not icon_file.endswith(".icns"):
                icon_file += ".icns"

            return {
                "name": name,
                "bundle_id": bundle_id,
                "version": version,
                "build": build,
                "path": app_path,
                "size_bytes": size,
                "size_human": self._human_size(size),
                "install_source": source,
                "install_date": metadata.get("install_date", "Unknown"),
                "last_opened": metadata.get("last_opened", "Unknown"),
                "icon_file": icon_file,
                "architecture": plist.get("LSArchitecturePriority", ["Unknown"]),
                "min_os": plist.get("LSMinimumSystemVersion", "Unknown"),
                "copyright": plist.get("NSHumanReadableCopyright", ""),
                "category": plist.get("LSApplicationCategoryType", "Unknown"),
            }
        except Exception as e:
            return self._basic_app_info(app_path)

    def _basic_app_info(self, app_path):
        """Fallback for apps without readable Info.plist."""
        name = Path(app_path).stem
        size = self._get_app_size(app_path)
        return {
            "name": name,
            "bundle_id": f"unknown.{name.lower().replace(' ', '.')}",
            "version": "Unknown",
            "build": "",
            "path": app_path,
            "size_bytes": size,
            "size_human": self._human_size(size),
            "install_source": "unknown",
            "install_date": "Unknown",
            "last_opened": "Unknown",
            "icon_file": "",
            "architecture": ["Unknown"],
            "min_os": "Unknown",
            "copyright": "",
            "category": "Unknown",
        }

    def _get_app_size(self, app_path):
        """Get total size of an app bundle in bytes."""
        try:
            result = subprocess.run(
                ["du", "-sk", app_path],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                return int(result.stdout.split()[0]) * 1024
        except Exception:
            pass
        return 0

    def _get_mdls_metadata(self, app_path):
        """Get metadata from Spotlight (mdls)."""
        metadata = {}
        try:
            result = subprocess.run(
                ["mdls", "-name", "kMDItemDateAdded", "-name", "kMDItemLastUsedDate",
                 "-raw", app_path],
                capture_output=True, text=True, timeout=5
            )
            lines = result.stdout.strip().split("\n")
            # Parse the raw output
            if len(lines) >= 1 and lines[0] != "(null)":
                metadata["install_date"] = lines[0].strip()
            if len(lines) >= 2 and lines[1] != "(null)":
                metadata["last_opened"] = lines[1].strip()
        except Exception:
            pass

        # Fallback: use file creation date
        if "install_date" not in metadata:
            try:
                stat = os.stat(app_path)
                metadata["install_date"] = datetime.fromtimestamp(stat.st_birthtime).isoformat()
            except Exception:
                pass

        return metadata

    def _detect_install_source(self, app_path, bundle_id):
        """Detect how an app was installed."""
        # Check App Store receipt
        receipt_path = os.path.join(app_path, "Contents", "_MASReceipt", "receipt")
        if os.path.exists(receipt_path):
            return "App Store"

        # Check Homebrew
        if self._homebrew_prefix:
            cask_dir = os.path.join(self._homebrew_prefix, "Caskroom")
            if os.path.isdir(cask_dir):
                if self._homebrew_casks is None:
                    try:
                        self._homebrew_casks = {cask.lower() for cask in os.listdir(cask_dir)}
                    except OSError:
                        self._homebrew_casks = set()
                app_name = Path(app_path).stem.lower().replace(" ", "-")
                if app_name in self._homebrew_casks:
                    return "Homebrew Cask"

        # Check pkgutil receipts
        if self._pkg_receipts is None:
            self._pkg_receipts = []
            try:
                result = subprocess.run(
                    ["pkgutil", "--pkgs"],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0:
                    self._pkg_receipts = [
                        pkg.strip().lower()
                        for pkg in result.stdout.splitlines()
                        if pkg.strip()
                    ]
            except Exception:
                pass
        if bundle_id:
            bundle_id_lower = bundle_id.lower()
            if any(bundle_id_lower in pkg for pkg in self._pkg_receipts):
                return ".pkg Installer"

        # Check if it's a system / Apple OS app
        if (app_path.startswith("/System/Applications")
                or app_path.startswith("/System/Library")
                or app_path.startswith("/Applications/Utilities")):
            return "System"

        # Default
        return "Manual (.dmg/direct)"

    @staticmethod
    def _human_size(size_bytes):
        """Convert bytes to human readable string."""
        if size_bytes == 0:
            return "0 B"
        units = ["B", "KB", "MB", "GB", "TB"]
        unit_index = 0
        size = float(size_bytes)
        while size >= 1024 and unit_index < len(units) - 1:
            size /= 1024
            unit_index += 1
        return f"{size:.1f} {units[unit_index]}"
