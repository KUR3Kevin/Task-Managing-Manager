// === Task Managing Manager – Frontend ===

const API = '';
let socket = null;
let currentView = 'apps';
let allApps = [];
let appsLoaded = false;
let allProcesses = [];
let runningAppNames = [];
let runningAppsDetailed = {};   // name (lower) -> { pid, memory_mb, cpu_percent }
let sourceFilter = '';
let processSort = { key: 'cpu_percent', dir: 'desc' };
let monitoringActive = false;

// === Init ===
document.addEventListener('DOMContentLoaded', () => {
    initSocket();
    loadApps();
    loadSources();
    loadRunningApps();
    bindEvents();
});

// ============================================================
//  Socket.IO  –  with automatic reconnect
// ============================================================
function initSocket() {
    socket = io({
        reconnection:        true,
        reconnectionAttempts: Infinity,
        reconnectionDelay:   1500,
        reconnectionDelayMax: 8000,
    });

    socket.on('connect', () => {
        console.log('Connected to server');
        setLiveBadge(true);
        // Re-start monitoring after a reconnect
        monitoringActive = false;
        startMonitoring();
    });

    socket.on('disconnect', () => {
        setLiveBadge(false);
        monitoringActive = false;
    });

    socket.on('reconnect_attempt', () => {
        setLiveBadge(false);
    });

    socket.on('system_update', (data) => {
        updateSystemStats(data.stats);
        if (currentView === 'processes') {
            renderProcesses(data.top_processes, data.total_processes);
        }
        // Keep a copy for the process view
        allProcesses = data.top_processes;
        document.getElementById('processCount').textContent = data.total_processes;
    });

    socket.on('monitor_error', (data) => {
        console.warn('Monitor error:', data.error);
    });
}

function setLiveBadge(online) {
    const badge = document.getElementById('liveBadge');
    if (!badge) return;
    if (online) {
        badge.classList.remove('offline');
        badge.lastChild.textContent = ' Live';
    } else {
        badge.classList.add('offline');
        badge.lastChild.textContent = ' Reconnecting…';
    }
}

function startMonitoring() {
    if (!monitoringActive && socket && socket.connected) {
        socket.emit('start_monitoring');
        monitoringActive = true;
    }
}

function stopMonitoring() {
    if (monitoringActive) {
        socket.emit('stop_monitoring');
        monitoringActive = false;
    }
}

// ============================================================
//  Navigation & events
// ============================================================
function bindEvents() {
    document.querySelectorAll('.nav-item[data-view]').forEach(el => {
        el.addEventListener('click', () => switchView(el.dataset.view));
    });

    document.getElementById('searchInput').addEventListener('input', debounce(() => {
        if (currentView === 'apps')      filterAndRenderApps();
        else if (currentView === 'processes') loadProcesses();
    }, 280));

    // Start real-time monitoring
    startMonitoring();
    loadSystemStats();

    // Refresh running-apps list every 5 s so status badges stay fresh
    setInterval(() => {
        loadRunningApps().then(() => {
            if (currentView === 'apps' && appsLoaded) {
                filterAndRenderApps();
                renderRunningStrip();
            }
        });
    }, 5000);
}

function switchView(view) {
    currentView = view;

    document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
    document.querySelector(`.nav-item[data-view="${view}"]`)?.classList.add('active');

    document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
    document.getElementById(`view-${view}`)?.classList.add('active');

    const search = document.getElementById('searchInput');
    if      (view === 'apps')      search.placeholder = 'Search apps by name, bundle ID, or path…';
    else if (view === 'processes') search.placeholder = 'Search processes by name or command…';
    else if (view === 'packages')  search.placeholder = 'Search package IDs…';
    else                           search.placeholder = 'Search…';

    if      (view === 'processes') renderProcesses(allProcesses, allProcesses.length);
    else if (view === 'packages')  loadPackages();
    else if (view === 'removed')   loadRemoved();
}

// ============================================================
//  Apps
// ============================================================
async function loadApps(force = false) {
    const container = document.getElementById('appGrid');
    appsLoaded = false;
    container.innerHTML = '<div class="loading"><div class="spinner"></div>Scanning applications…</div>';

    try {
        const res = await fetch(`${API}/api/apps?force=${force}`);
        const data = await res.json();
        allApps = data.apps;
        appsLoaded = true;
        document.getElementById('appCount').textContent = data.total;
        filterAndRenderApps();
        renderRunningStrip();
    } catch (err) {
        appsLoaded = false;
        container.innerHTML = '<div class="empty-state">Failed to load apps. Is the server running?</div>';
    }
}

async function loadRunningApps() {
    try {
        const res = await fetch(`${API}/api/running-apps-detailed`);
        const data = await res.json();
        runningAppNames = data.apps.map(a => a.name.toLowerCase().trim());
        runningAppsDetailed = {};
        data.apps.forEach(a => {
            runningAppsDetailed[a.name.toLowerCase().trim()] = a;
        });
    } catch (err) {
        runningAppNames = [];
        runningAppsDetailed = {};
    }
}

function renderRunningStrip() {
    const strip = document.getElementById('runningStrip');
    if (!strip) return;

    if (runningAppNames.length === 0) {
        strip.style.display = 'none';
        return;
    }

    strip.style.display = 'flex';
    const label = strip.querySelector('.running-strip-label') || '';

    // Build chips (sorted alphabetically)
    const sorted = [...runningAppNames].sort();
    const chips = sorted.map(name => {
        const display = runningAppsDetailed[name]?.name || name;
        return `<div class="running-chip" title="${escHtml(display)}">
            <span class="running-chip-dot"></span>
            ${escHtml(display)}
        </div>`;
    }).join('');

    strip.innerHTML = `<span class="running-strip-label">Active</span>${chips}`;
}

function filterAndRenderApps() {
    const search = document.getElementById('searchInput').value.toLowerCase();
    let filtered = allApps;

    if (sourceFilter) {
        filtered = filtered.filter(a => a.install_source === sourceFilter);
    }
    if (search) {
        filtered = filtered.filter(a =>
            a.name.toLowerCase().includes(search) ||
            a.bundle_id.toLowerCase().includes(search) ||
            a.path.toLowerCase().includes(search)
        );
    }

    document.getElementById('filteredCount').textContent =
        `${filtered.length} of ${allApps.length}`;
    renderAppGrid(filtered);
}

function renderAppGrid(apps) {
    const container = document.getElementById('appGrid');

    if (apps.length === 0) {
        container.innerHTML = '<div class="empty-state">No apps found matching your filters.</div>';
        return;
    }

    const protectedApps = ['finder'];

    container.innerHTML = apps.map(app => {
        const initial     = app.name.charAt(0).toUpperCase();
        const key         = app.name.toLowerCase();
        const isRunning   = runningAppNames.includes(key);
        const isProtected = protectedApps.includes(key);
        const sourceClass = getSourceClass(app.install_source);
        const runInfo     = runningAppsDetailed[key];

        let actionButtons = '';
        if (isRunning && !isProtected) {
            actionButtons = `
                <button class="btn"        onclick="event.stopPropagation(); gracefulQuitApp('${escHtml(app.name)}')" title="Quit">Quit</button>
                <button class="btn danger" onclick="event.stopPropagation(); forceQuitByName('${escHtml(app.name)}')" title="Force Quit">Force</button>`;
        } else if (isRunning && isProtected) {
            actionButtons = `<span style="color:var(--text-muted);font-size:10px;font-weight:600">System</span>`;
        } else {
            actionButtons = `<button class="btn success" onclick="event.stopPropagation(); launchApp('${escHtml(app.path)}')" title="Launch">Open</button>`;
        }

        return `
            <div class="app-card ${isRunning ? 'running' : ''}"
                 onclick="showAppDetail(${JSON.stringify(app).replace(/"/g, '&quot;')})">
                <div class="app-icon-placeholder">${initial}</div>
                <div class="app-card-info">
                    <div class="app-card-name">${escHtml(app.name)}</div>
                    <div class="app-card-meta">
                        <span class="source-tag ${sourceClass}">${escHtml(app.install_source)}</span>
                        <span>${escHtml(app.version)}</span>
                        <span>${escHtml(app.size_human)}</span>
                        ${isRunning ? '<span class="running-tag">Running</span>' : ''}
                        ${runInfo ? `<span style="color:var(--text-muted)">${runInfo.memory_mb} MB</span>` : ''}
                    </div>
                </div>
                <div class="app-card-actions">
                    ${actionButtons}
                </div>
            </div>`;
    }).join('');
}

// ============================================================
//  App Detail panel
// ============================================================
function showAppDetail(app) {
    const panel    = document.getElementById('detailPanel');
    const key      = app.name.toLowerCase();
    const isRunning = runningAppNames.includes(key);
    const runInfo   = runningAppsDetailed[key];

    document.getElementById('detailContent').innerHTML = `
        <div class="detail-header">
            <div>
                <h2 style="font-size:15px;margin-bottom:4px;letter-spacing:-0.02em">${escHtml(app.name)}</h2>
                <div style="font-size:11px;color:var(--text-muted);font-family:monospace">${escHtml(app.bundle_id)}</div>
                ${isRunning ? '<div style="color:var(--green);font-size:10.5px;margin-top:5px;font-weight:700">● Running</div>' : ''}
            </div>
            <button class="detail-close" onclick="closeDetail()">&times;</button>
        </div>
        <div class="detail-body">
            ${isRunning && runInfo ? `
            <div style="display:flex;gap:14px;margin-bottom:16px;padding:12px;background:var(--green-dim);border:1px solid var(--border-green);border-radius:var(--radius-sm)">
                <div style="text-align:center">
                    <div style="font-size:18px;font-weight:700;color:var(--green);font-variant-numeric:tabular-nums">${runInfo.cpu_percent.toFixed(1)}%</div>
                    <div style="font-size:10px;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.06em">CPU</div>
                </div>
                <div style="text-align:center">
                    <div style="font-size:18px;font-weight:700;color:var(--cyan);font-variant-numeric:tabular-nums">${runInfo.memory_mb}</div>
                    <div style="font-size:10px;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.06em">MB</div>
                </div>
                <div style="text-align:center">
                    <div style="font-size:18px;font-weight:700;color:var(--text-secondary);font-variant-numeric:tabular-nums">${runInfo.pid}</div>
                    <div style="font-size:10px;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.06em">PID</div>
                </div>
            </div>` : ''}

            <div class="detail-row"><span class="label">Version</span><span class="value">${escHtml(app.version)}${app.build ? ' (' + escHtml(app.build) + ')' : ''}</span></div>
            <div class="detail-row"><span class="label">Install Source</span><span class="value"><span class="source-tag ${getSourceClass(app.install_source)}">${escHtml(app.install_source)}</span></span></div>
            <div class="detail-row"><span class="label">Size</span><span class="value">${escHtml(app.size_human)}</span></div>
            <div class="detail-row"><span class="label">Path</span><span class="value" style="font-size:10px;font-family:monospace">${escHtml(app.path)}</span></div>
            <div class="detail-row"><span class="label">Bundle ID</span><span class="value" style="font-size:10px;font-family:monospace">${escHtml(app.bundle_id)}</span></div>
            <div class="detail-row"><span class="label">Install Date</span><span class="value">${escHtml(app.install_date || 'Unknown')}</span></div>
            <div class="detail-row"><span class="label">Last Opened</span><span class="value">${escHtml(app.last_opened || 'Unknown')}</span></div>
            <div class="detail-row"><span class="label">Min macOS</span><span class="value">${escHtml(app.min_os || 'Unknown')}</span></div>
            <div class="detail-row"><span class="label">Category</span><span class="value">${escHtml(app.category || 'Unknown')}</span></div>
            <div class="detail-row"><span class="label">Architecture</span><span class="value">${Array.isArray(app.architecture) ? app.architecture.join(', ') : 'Unknown'}</span></div>
            ${app.copyright ? `<div class="detail-row"><span class="label">Copyright</span><span class="value" style="font-size:10px">${escHtml(app.copyright)}</span></div>` : ''}

            <div class="detail-actions">
                <button class="btn success" onclick="launchApp('${escHtml(app.path)}')">Open App</button>
                <button class="btn"         onclick="revealInFinder('${escHtml(app.path)}')">Show in Finder</button>
                ${isRunning && app.name.toLowerCase() !== 'finder' ? `
                    <button class="btn"        onclick="gracefulQuitApp('${escHtml(app.name)}')">Quit</button>
                    <button class="btn danger" onclick="forceQuitByName('${escHtml(app.name)}')">Force Quit</button>
                ` : ''}
            </div>
        </div>`;

    panel.classList.add('open');
}

function closeDetail() {
    document.getElementById('detailPanel').classList.remove('open');
}

// ============================================================
//  Processes
// ============================================================
async function loadProcesses() {
    const search = document.getElementById('searchInput').value;
    const show   = document.getElementById('processFilter')?.value || 'all';

    try {
        const res  = await fetch(`${API}/api/processes?search=${encodeURIComponent(search)}&show=${show}`);
        const data = await res.json();
        allProcesses = data.processes;
        renderProcesses(allProcesses, data.count);
    } catch (err) {
        console.error('Failed to load processes', err);
    }
}

function renderProcesses(processes, totalCount) {
    const container = document.getElementById('processTableBody');
    if (!container) return;

    // Apply filter from dropdown
    const show = document.getElementById('processFilter')?.value || 'all';
    let visible = processes;
    if (show === 'apps')   visible = processes.filter(p => p.is_app);
    if (show === 'system') visible = processes.filter(p => !p.is_app);

    // Apply search
    const search = document.getElementById('searchInput').value.toLowerCase();
    if (search) {
        visible = visible.filter(p =>
            p.name.toLowerCase().includes(search) ||
            p.cmdline.toLowerCase().includes(search)
        );
    }

    // Sort
    const sorted = [...visible].sort((a, b) => {
        let va = a[processSort.key];
        let vb = b[processSort.key];
        if (typeof va === 'string') va = va.toLowerCase();
        if (typeof vb === 'string') vb = vb.toLowerCase();
        if (processSort.dir === 'asc') return va > vb ? 1 : -1;
        return va < vb ? 1 : -1;
    });

    document.getElementById('processCount').textContent = totalCount || processes.length;

    container.innerHTML = sorted.slice(0, 200).map(p => {
        const cpuClass   = p.cpu_percent > 50 ? 'cpu-high' : p.cpu_percent > 10 ? 'cpu-med' : 'cpu-low';
        const memClass   = p.memory_mb > 500 ? 'mem-high' : '';
        const statusCls  = p.status === 'running' ? 'running' : p.status === 'zombie' ? 'zombie' : 'sleeping';
        const cpuWidth   = Math.min(p.cpu_percent, 100).toFixed(1);

        return `<tr class="${p.is_app ? 'is-app' : ''}">
            <td class="pid">${p.pid}</td>
            <td>
                <div class="process-name-cell">
                    <span class="status-dot ${statusCls}"></span>
                    <span>${escHtml(p.name)}</span>
                </div>
            </td>
            <td>
                <div class="cpu-cell ${cpuClass}">
                    <span class="cpu-val">${p.cpu_percent.toFixed(1)}%</span>
                    <div class="cpu-mini-bar">
                        <div class="cpu-mini-fill" style="width:${cpuWidth}%"></div>
                    </div>
                </div>
            </td>
            <td class="${memClass}">${p.memory_mb.toFixed(1)} MB</td>
            <td>${escHtml(p.username)}</td>
            <td>${escHtml(p.status)}</td>
            <td>
                <button class="btn danger" onclick="forceQuit(${p.pid})"
                        style="padding:3px 9px;font-size:10px">Kill</button>
            </td>
        </tr>`;
    }).join('');
}

function sortProcesses(key) {
    if (processSort.key === key) {
        processSort.dir = processSort.dir === 'desc' ? 'asc' : 'desc';
    } else {
        processSort.key = key;
        processSort.dir = 'desc';
    }
    renderProcesses(allProcesses, allProcesses.length);
}

// ============================================================
//  Packages
// ============================================================
async function loadPackages() {
    const container = document.getElementById('pkgList');
    container.innerHTML = '<div class="loading"><div class="spinner"></div>Loading package receipts…</div>';

    try {
        const res  = await fetch(`${API}/api/pkg-history`);
        const data = await res.json();
        const search = document.getElementById('searchInput').value.toLowerCase();

        let receipts = data.receipts;
        if (search) receipts = receipts.filter(r => r.pkg_id.toLowerCase().includes(search));

        document.getElementById('pkgCount').textContent = data.count;

        if (receipts.length === 0) {
            container.innerHTML = '<div class="empty-state">No packages found.</div>';
            return;
        }

        container.innerHTML = receipts.map(r => `
            <div class="pkg-item">
                <span class="pkg-id">${escHtml(r.pkg_id)}</span>
                <span class="pkg-status ${r.still_installed ? 'installed' : 'removed'}">
                    ${r.still_installed ? 'Installed' : 'Removed'}
                </span>
            </div>
        `).join('');
    } catch (err) {
        container.innerHTML = '<div class="empty-state">Failed to load packages.</div>';
    }
}

// ============================================================
//  Removed pkgs
// ============================================================
async function loadRemoved() {
    const container = document.getElementById('removedList');
    container.innerHTML = '<div class="loading"><div class="spinner"></div>Checking for removed packages…</div>';

    try {
        const res  = await fetch(`${API}/api/pkg-removed`);
        const data = await res.json();

        if (data.removed.length === 0) {
            container.innerHTML = '<div class="empty-state">No removed packages detected. All receipts have files intact.</div>';
            return;
        }

        container.innerHTML = data.removed.map(r => `
            <div class="pkg-item">
                <span class="pkg-id">${escHtml(r.pkg_id)}</span>
                <span class="pkg-status removed">Files Missing</span>
            </div>
        `).join('');
    } catch (err) {
        container.innerHTML = '<div class="empty-state">Failed to check removed packages.</div>';
    }
}

// ============================================================
//  System Stats
// ============================================================
async function loadSystemStats() {
    try {
        const res  = await fetch(`${API}/api/system`);
        const data = await res.json();
        updateSystemStats(data);
    } catch (err) {
        console.error('Failed to load system stats');
    }
}

function updateSystemStats(stats) {
    // CPU
    const cpuBar  = document.getElementById('cpuBar');
    const cpuText = document.getElementById('cpuText');
    if (cpuBar && cpuText) {
        const cpu = stats.cpu_percent;
        cpuBar.style.width = cpu + '%';
        cpuBar.className = 'stat-bar-fill cpu' +
            (cpu > 90 ? ' critical' : cpu > 70 ? ' high' : '');
        cpuText.textContent = cpu.toFixed(0) + '%';
    }

    // Memory
    const memBar  = document.getElementById('memBar');
    const memText = document.getElementById('memText');
    if (memBar && memText) {
        const mem = stats.memory_percent;
        memBar.style.width = mem + '%';
        memBar.className = 'stat-bar-fill mem' +
            (mem > 90 ? ' critical' : mem > 75 ? ' high' : '');
        memText.textContent = mem.toFixed(0) + '%';
    }

    // Disk
    const diskBar  = document.getElementById('diskBar');
    const diskText = document.getElementById('diskText');
    if (diskBar && diskText) {
        const disk = stats.disk_percent;
        diskBar.style.width = disk + '%';
        diskBar.className = 'stat-bar-fill disk' +
            (disk > 95 ? ' critical' : disk > 85 ? ' high' : '');
        diskText.textContent = disk.toFixed(0) + '%';
    }

    // Process count
    const procEl = document.getElementById('totalProcessCount');
    if (procEl) procEl.textContent = stats.process_count;
}

// ============================================================
//  App actions
// ============================================================
async function launchApp(path) {
    try {
        const res  = await fetch(`${API}/api/launch`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path }),
        });
        const data = await res.json();
        showToast(data.message, data.success ? 'success' : 'error');
        if (data.success) {
            setTimeout(() => loadRunningApps().then(() => {
                filterAndRenderApps();
                renderRunningStrip();
            }), 2000);
        }
    } catch (err) {
        showToast('Failed to launch app', 'error');
    }
}

async function forceQuit(pid) {
    try {
        const res  = await fetch(`${API}/api/quit`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ pid, force: true }),
        });
        const data = await res.json();
        showToast(data.message, data.success ? 'success' : 'error');
        if (data.success) {
            setTimeout(() => {
                loadRunningApps().then(() => {
                    filterAndRenderApps();
                    renderRunningStrip();
                });
            }, 1000);
        }
    } catch (err) {
        showToast('Failed to quit process', 'error');
    }
}

async function quitAppByName(appName) {
    try {
        const res  = await fetch(`${API}/api/processes?search=${encodeURIComponent(appName)}&show=apps`);
        const data = await res.json();
        if (data.processes.length > 0) {
            forceQuit(data.processes[0].pid);
        } else {
            showToast(`Could not find running process for ${appName}`, 'error');
        }
    } catch (err) {
        showToast('Failed to find process', 'error');
    }
}

async function gracefulQuitApp(appName) {
    try {
        const res  = await fetch(`${API}/api/quit-by-name`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: appName }),
        });
        const data = await res.json();
        showToast(data.message, data.success ? 'success' : 'error');
        if (data.success) {
            setTimeout(() => loadRunningApps().then(() => {
                filterAndRenderApps();
                renderRunningStrip();
            }), 2000);
        }
    } catch (err) {
        showToast('Failed to quit app', 'error');
    }
}

async function forceQuitByName(appName) {
    const info = runningAppsDetailed[appName.toLowerCase()];
    if (info && info.pid) {
        forceQuit(info.pid);
    } else {
        quitAppByName(appName);
    }
}

async function revealInFinder(path) {
    const dir = path.substring(0, path.lastIndexOf('/'));
    launchApp(dir);
}

function refreshApps() {
    loadApps(true);
    loadRunningApps();
    loadSources();
}

// ============================================================
//  Sources
// ============================================================
async function loadSources() {
    try {
        const res  = await fetch(`${API}/api/apps/sources`);
        const data = await res.json();
        const container = document.getElementById('sourceFilters');

        container.innerHTML = Object.entries(data.sources)
            .sort((a, b) => b[1] - a[1])
            .map(([src, count]) => {
                const cls = getSourceClass(src);
                return `<div class="source-item ${sourceFilter === src ? 'active' : ''}"
                             onclick="setSourceFilter('${escHtml(src)}')">
                    <div style="display:flex;align-items:center;gap:5px">
                        <span class="source-dot ${cls}"></span>
                        <span>${escHtml(src)}</span>
                    </div>
                    <span class="nav-badge">${count}</span>
                </div>`;
            }).join('');
    } catch (err) {}
}

function setSourceFilter(src) {
    sourceFilter = sourceFilter === src ? '' : src;
    loadSources();
    filterAndRenderApps();
}

// ============================================================
//  Utilities
// ============================================================
function escHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

function getSourceClass(source) {
    if (!source) return 'unknown';
    const s = source.toLowerCase();
    if (s.includes('app store')) return 'app-store';
    if (s.includes('homebrew'))  return 'homebrew';
    if (s.includes('pkg'))       return 'pkg';
    if (s.includes('manual') || s.includes('dmg')) return 'manual';
    if (s.includes('system'))    return 'system';
    return 'unknown';
}

function debounce(fn, ms) {
    let timer;
    return (...args) => {
        clearTimeout(timer);
        timer = setTimeout(() => fn(...args), ms);
    };
}

function showToast(msg, type = 'info') {
    const container = document.getElementById('toasts');
    const toast     = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = msg;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 4000);
}

function humanBytes(bytes) {
    if (!bytes) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    let i = 0, size = bytes;
    while (size >= 1024 && i < units.length - 1) { size /= 1024; i++; }
    return size.toFixed(1) + ' ' + units[i];
}
