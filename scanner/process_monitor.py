import psutil
import subprocess
import os
import signal


class ProcessMonitor:
    """Real-time process monitoring for macOS."""

    def get_all_processes(self):
        """Get all running processes with details."""
        processes = []
        for proc in psutil.process_iter(['pid', 'name', 'status', 'cpu_percent',
                                          'memory_info', 'create_time', 'username',
                                          'ppid', 'cmdline']):
            try:
                info = proc.info
                mem = info.get('memory_info')
                processes.append({
                    "pid": info['pid'],
                    "name": info['name'] or "Unknown",
                    "status": info['status'],
                    "cpu_percent": proc.cpu_percent(interval=0),
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
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                app_names = [n.strip() for n in result.stdout.strip().split(",")]
                return app_names
        except Exception:
            pass
        return apps

    def get_running_apps_detailed(self):
        """Get running GUI apps with PID, name, and memory usage."""
        apps = []
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
                capture_output=True, text=True, timeout=10
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
                        # Get memory info from psutil
                        mem_mb = 0
                        cpu = 0
                        try:
                            proc = psutil.Process(pid)
                            mem = proc.memory_info()
                            mem_mb = round(mem.rss / (1024 * 1024), 1)
                            cpu = proc.cpu_percent(interval=0)
                        except Exception:
                            pass
                        apps.append({
                            "name": name,
                            "pid": pid,
                            "memory_mb": mem_mb,
                            "cpu_percent": cpu,
                        })
        except Exception:
            pass
        return apps

    def graceful_quit_by_name(self, app_name):
        """Gracefully quit an app using AppleScript (like clicking Quit)."""
        try:
            result = subprocess.run(
                ["osascript", "-e", f'tell application "{app_name}" to quit'],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                return {"success": True, "message": f"Sent quit to {app_name}"}
            else:
                return {"success": False, "message": f"Failed to quit {app_name}: {result.stderr}"}
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
            # Try with sudo via osascript
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
        """Heuristic to detect if a process is a GUI app."""
        cmdline = proc_info.get('cmdline') or []
        if cmdline:
            cmd = ' '.join(cmdline)
            if '.app/Contents/MacOS/' in cmd:
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
