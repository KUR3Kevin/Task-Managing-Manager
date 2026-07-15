import psutil
import subprocess
import os
import signal
import time


class ProcessMonitor:
    """Real-time process monitoring for macOS."""

    def prime_cpu_measurements(self):
        """
        Call cpu_percent once for all processes to prime the measurement.
        psutil returns 0.0 on the very first call per process (no prior
        reference point). After this warm-up + a short sleep, subsequent
        calls with interval=None return accurate values.
        """
        try:
            for proc in psutil.process_iter():
                try:
                    proc.cpu_percent(interval=None)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        except Exception:
            pass

    def get_all_processes(self):
        """Get all running processes with details."""
        processes = []
        for proc in psutil.process_iter(['pid', 'name', 'status', 'cpu_percent',
                                          'memory_info', 'create_time', 'username',
                                          'ppid', 'cmdline', 'exe']):
            try:
                info = proc.info
                mem = info.get('memory_info')
                processes.append({
                    "pid": info['pid'],
                    "name": info['name'] or "Unknown",
                    "status": info['status'],
                    # interval=None: use elapsed time since last call (accurate in loops)
                    "cpu_percent": proc.cpu_percent(interval=None),
                    "memory_mb": round(mem.rss / (1024 * 1024), 1) if mem else 0,
                    "memory_bytes": mem.rss if mem else 0,
                    "create_time": info.get('create_time', 0),
                    "username": info.get('username', 'Unknown'),
                    "ppid": info.get('ppid', 0),
                    "cmdline": ' '.join(info.get('cmdline') or [])[:200],
                    "is_app": self._is_gui_app(info),
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

        processes.sort(key=lambda x: x['cpu_percent'], reverse=True)
        return processes

    def get_running_apps(self):
        """Get only GUI applications that are currently running."""
        apps = []
        try:
            result = subprocess.run(
                ["osascript", "-e",
                 'tell application "System Events" to get name of every process whose background only is false'],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                app_names = [n.strip() for n in result.stdout.strip().split(",")]
                return app_names
        except Exception:
            pass
        return apps

    def get_running_apps_detailed(self):
        """
        Get running GUI apps with PID, name, and resource usage.

        Uses two independent methods so that when one fails (e.g. AppleScript
        times out under high CPU), the other still provides data:

          1. AppleScript / System Events  – authoritative list of foreground
             GUI apps shown in the Dock / App Switcher.
          2. psutil exe-path inspection  – catches *every* process whose
             binary lives inside a .app bundle, including FaceTime and all
             apps in /System/Applications that AppleScript might miss or
             time-out on.
        """
        apps_by_pid = {}

        # ── Method 1: AppleScript ────────────────────────────────────────────
        try:
            script = '''
            tell application "System Events"
                set appList to ""
                repeat with p in (every process whose background only is false)
                    set appList to appList & name of p & "|" & unix id of p & ","
                end repeat
                return appList
            end tell
            '''
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, text=True, timeout=5   # was 10; 5 s is plenty
            )
            if result.returncode == 0:
                entries = [e.strip() for e in result.stdout.strip().split(",") if e.strip()]
                for entry in entries:
                    parts = entry.split("|")
                    if len(parts) == 2:
                        name = parts[0].strip()
                        try:
                            pid = int(parts[1].strip())
                        except ValueError:
                            continue
                        mem_mb, cpu = 0, 0.0
                        try:
                            proc = psutil.Process(pid)
                            mem = proc.memory_info()
                            mem_mb = round(mem.rss / (1024 * 1024), 1)
                            cpu = proc.cpu_percent(interval=None)
                        except Exception:
                            pass
                        apps_by_pid[pid] = {
                            "name": name,
                            "pid": pid,
                            "memory_mb": mem_mb,
                            "cpu_percent": cpu,
                        }
        except Exception:
            pass

        # ── Method 2: psutil exe-path scan ──────────────────────────────────
        # Catches every process whose executable is inside a .app bundle,
        # even if AppleScript timed out or the app is backgrounded.
        marker = '.app/Contents/MacOS/'
        try:
            for proc in psutil.process_iter(['pid', 'name', 'exe', 'cmdline', 'memory_info']):
                try:
                    pid = proc.info['pid']
                    if pid in apps_by_pid:
                        continue   # already found via AppleScript

                    exe = proc.info.get('exe') or ''
                    cmdline = ' '.join(proc.info.get('cmdline') or [])

                    source_str = ''
                    if marker in exe:
                        source_str = exe
                    elif marker in cmdline:
                        source_str = cmdline

                    if not source_str:
                        continue

                    # Extract the human-readable app name from the path
                    idx = source_str.find(marker)
                    segment = source_str[:idx]          # e.g. "/System/Applications/FaceTime"
                    app_name = segment.rsplit('/', 1)[-1]
                    if app_name.endswith('.app'):
                        app_name = app_name[:-4]
                    if not app_name:
                        app_name = proc.info.get('name') or 'Unknown'

                    mem_mb = 0
                    try:
                        mem = proc.info.get('memory_info')
                        mem_mb = round(mem.rss / (1024 * 1024), 1) if mem else 0
                    except Exception:
                        pass

                    apps_by_pid[pid] = {
                        "name": app_name,
                        "pid": pid,
                        "memory_mb": mem_mb,
                        "cpu_percent": proc.cpu_percent(interval=None),
                    }
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except Exception:
            pass

        return list(apps_by_pid.values())

    def graceful_quit_by_name(self, app_name):
        """Gracefully quit an app using AppleScript (like clicking Quit)."""
        try:
            import re
            # Strict whitelist: only alphanumeric, spaces, dots, hyphens (no quotes, backslashes, etc.)
            safe_name = re.sub(r'[^a-zA-Z0-9 ._-]', '', str(app_name)).strip()

            # Reject empty names or suspiciously long ones (real app names are <100 chars)
            if not safe_name or len(safe_name) > 100:
                return {"success": False, "message": "Invalid application name"}

            # Validate against the list of currently running GUI app names
            running_names = set(self.get_running_apps())
            if safe_name not in running_names:
                return {"success": False, "message": f"App '{safe_name}' is not currently running"}

            result = subprocess.run(
                ["osascript", "-e", f'tell application "{safe_name}" to quit'],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                return {"success": True, "message": f"Sent quit to {safe_name}"}
            else:
                return {"success": False, "message": f"Failed to quit {safe_name}"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def get_system_stats(self):
        """Get overall system resource usage."""
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage("/")

        # CPU per core
        cpu_per_core = psutil.cpu_percent(interval=0, percpu=True)

        # Swap
        swap = psutil.swap_memory()

        # Boot time
        boot_time = psutil.boot_time()

        return {
            "cpu_percent": cpu_percent,
            "cpu_count": psutil.cpu_count(),
            "cpu_per_core": cpu_per_core,
            "memory_total": memory.total,
            "memory_used": memory.used,
            "memory_percent": memory.percent,
            "memory_available": memory.available,
            "swap_total": swap.total,
            "swap_used": swap.used,
            "swap_percent": swap.percent,
            "disk_total": disk.total,
            "disk_used": disk.used,
            "disk_percent": disk.percent,
            "disk_free": disk.free,
            "boot_time": boot_time,
            "process_count": len(psutil.pids()),
        }

    def launch_app(self, app_path):
        """Launch an application by path."""
        try:
            subprocess.Popen(["open", app_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return {"success": True, "message": f"Launched {os.path.basename(app_path)}"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def force_quit_app(self, pid):
        """Force quit a process by PID."""
        try:
            proc = psutil.Process(pid)
            name = proc.name()
            proc.kill()
            return {"success": True, "message": f"Force quit {name} (PID {pid})"}
        except psutil.NoSuchProcess:
            return {"success": False, "message": f"Process {pid} not found"}
        except psutil.AccessDenied:
            try:
                subprocess.run(
                    ["kill", "-9", str(pid)],
                    capture_output=True, timeout=5
                )
                return {"success": True, "message": f"Force quit PID {pid}"}
            except Exception as e:
                return {"success": False, "message": f"Access denied for PID {pid}. Try running with sudo."}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def graceful_quit_app(self, pid):
        """Gracefully quit a process by PID."""
        try:
            proc = psutil.Process(pid)
            name = proc.name()
            proc.terminate()
            return {"success": True, "message": f"Sent quit signal to {name} (PID {pid})"}
        except psutil.NoSuchProcess:
            return {"success": False, "message": f"Process {pid} not found"}
        except psutil.AccessDenied:
            return {"success": False, "message": f"Access denied for PID {pid}"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _is_gui_app(self, proc_info):
        """
        Detect if a process is a GUI app.
        Checks both the executable path and the command-line arguments for the
        '.app/Contents/MacOS/' pattern — this reliably covers all app bundles
        including those in /System/Applications/ (FaceTime, Calendar, etc.).
        """
        marker = '.app/Contents/MacOS/'

        # Check the resolved executable path first (most reliable)
        exe = proc_info.get('exe') or ''
        if marker in exe:
            return True

        # Fall back to checking the full command line
        cmdline = proc_info.get('cmdline') or []
        if cmdline:
            cmd = ' '.join(cmdline)
            if marker in cmd:
                return True

        return False

    def get_process_tree(self, pid):
        """Get the process tree for a given PID."""
        try:
            proc = psutil.Process(pid)
            children = proc.children(recursive=True)
            return {
                "pid": pid,
                "name": proc.name(),
                "children": [{"pid": c.pid, "name": c.name()} for c in children]
            }
        except Exception:
            return None
