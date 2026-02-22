# Task Managing Manager

A lightweight macOS application and process manager built for the 2018 Mac Mini. Discover every app installed on your system, see what's running, launch or force-quit apps with a single click, and track what gets installed or removed over time.

## Features

- **Application Scanner** - Scans `/Applications` and `~/Applications` for all installed `.app` bundles
- **Install Source Detection** - Identifies how each app was installed: App Store, Homebrew Cask, .pkg installer, or manual download
- **Full App Details** - Version, bundle ID, size on disk, install date, last opened, CPU/memory usage, architecture, and more
- **Real-Time Process Monitor** - Live CPU and memory tracking for all processes (like Activity Monitor)
- **Launch & Force Quit** - Open any app or kill any process with one click
- **Package Receipt History** - View all `.pkg` packages ever registered on the system via `pkgutil`
- **Uninstall Detection** - Find packages whose files have been removed from disk
- **Snapshot Comparison** - Save snapshots of installed apps and compare over time to see what was added, removed, or updated
- **Search & Filter** - Filter apps by install source, search by name/bundle ID/path

## Requirements

- macOS 10.14+ (optimized for 2018 Mac Mini)
- Python 3.8+
- pip

## Quick Start

```bash
# Clone the repo
git clone https://github.com/YOUR_USERNAME/Task-Managing-Manager.git
cd Task-Managing-Manager

# Create virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the app
python app.py
```

Then open **http://127.0.0.1:5050** in your browser.

## Usage

### Applications Tab
Browse all installed apps grouped by install source. Click any app card to see full details. Use the **Open** button to launch an app or **Quit** to force-quit a running app.

### Processes Tab
Real-time view of all running processes with CPU and memory usage. Sort by any column. Click **Kill** to force-quit a process.

### Pkg Receipts Tab
View all package receipts registered via macOS's `pkgutil`. Shows whether package files still exist on disk.

### Removed Pkgs Tab
Packages that have receipts but whose files are no longer found — these were likely uninstalled.

### Snapshots Tab
Save snapshots of your current app list. Compare against previous snapshots to see what apps were added, removed, or updated since the last snapshot.

## Tech Stack

- **Backend**: Python, Flask, Flask-SocketIO, psutil
- **Frontend**: Vanilla HTML/CSS/JavaScript with Socket.IO
- **macOS Integration**: `pkgutil`, `mdls`, `system_profiler`, `lsappinfo`, plistlib

## Project Structure

```
task-managing-manager/
├── app.py                  # Flask server + API endpoints
├── requirements.txt        # Python dependencies
├── scanner/
│   ├── __init__.py
│   ├── app_scanner.py      # Application discovery & metadata
│   ├── process_monitor.py  # Real-time process monitoring
│   ├── pkg_history.py      # Package receipt tracking
│   └── snapshot.py         # Snapshot save/compare
├── templates/
│   └── index.html          # Dashboard UI
├── static/
│   ├── style.css           # Styles
│   └── app.js              # Frontend logic
└── snapshots/              # Saved snapshots (auto-created)
```

## License

MIT License - see [LICENSE](LICENSE) for details.
