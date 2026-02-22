import subprocess
import os
import plistlib
from datetime import datetime


class PkgHistory:
    """Track historically installed packages via pkgutil receipts."""

    def get_all_pkg_receipts(self):
        """Get all package receipts from pkgutil."""
        receipts = []
        try:
            result = subprocess.run(
                ["pkgutil", "--pkgs"],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0:
                pkg_ids = [p.strip() for p in result.stdout.strip().split("\n") if p.strip()]
                for pkg_id in pkg_ids:
                    info = self._get_pkg_info(pkg_id)
                    if info:
                        receipts.append(info)
        except Exception:
            pass

        receipts.sort(key=lambda x: x.get("install_date", ""), reverse=True)
        return receipts

    def _get_pkg_info(self, pkg_id):
        """Get detailed info about a specific package."""
        try:
            result = subprocess.run(
                ["pkgutil", "--pkg-info", pkg_id],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode != 0:
                return None

            info = {"pkg_id": pkg_id}
            for line in result.stdout.strip().split("\n"):
                if ": " in line:
                    key, val = line.split(": ", 1)
                    key = key.strip().lower().replace(" ", "_")
                    info[key] = val.strip()

            # Check if the package files still exist
            info["still_installed"] = self._check_pkg_files_exist(pkg_id, info.get("volume", "/"))
            info["install_date"] = info.get("install-time", "Unknown")

            return info
        except Exception:
            return None

    def _check_pkg_files_exist(self, pkg_id, volume="/"):
        """Check if the package's installed files still exist on disk."""
        try:
            result = subprocess.run(
                ["pkgutil", "--files", pkg_id],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                files = result.stdout.strip().split("\n")
                if files:
                    # Check first few files
                    check_count = min(3, len(files))
                    existing = 0
                    for f in files[:check_count]:
                        full_path = os.path.join(volume, f)
                        if os.path.exists(full_path):
                            existing += 1
                    return existing > 0
        except Exception:
            pass
        return True  # Assume installed if we can't check

    def get_recently_installed_pkgs(self, days=30):
        """Get packages installed in the last N days."""
        all_pkgs = self.get_all_pkg_receipts()
        now = datetime.now()
        recent = []
        for pkg in all_pkgs:
            try:
                install_time = int(pkg.get("install-time", 0))
                if install_time > 0:
                    install_date = datetime.fromtimestamp(install_time)
                    if (now - install_date).days <= days:
                        pkg["install_date_formatted"] = install_date.strftime("%Y-%m-%d %H:%M")
                        recent.append(pkg)
            except (ValueError, TypeError):
                continue
        return recent

    def find_potentially_removed_pkgs(self):
        """Find packages whose files no longer exist (potentially uninstalled)."""
        all_pkgs = self.get_all_pkg_receipts()
        removed = []
        for pkg in all_pkgs:
            if not pkg.get("still_installed", True):
                removed.append(pkg)
        return removed
