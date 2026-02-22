// === Task Managing Manager - Frontend ===

const API = '';
let socket = null;
let currentView = 'apps';
let allApps = [];
let allProcesses = [];
let runningAppNames = [];
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

// === Socket.IO ===
function initSocket() {
    socket = io();

    socket.on('connect', () => {
        console.log('Connected to server');
        showToast('Connected to Task Managing Manager', 'info');
    });

    socket.on('system_update', (data) => {
        updateSystemStats(data.stats);
        if (currentView === 'processes') {
            renderProcesses(data.top_processes, data.total_processes);
        }
    });

    socket.on('disconnect', () => {
        console.log('Disconnected');
    });
}

function startMonitoring() {
    if (!monitoringActive) {
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

// === Navigation ===
function bindEvents() {
    // Nav items
    document.querySelectorAll('.nav-item[data-view]').forEach(el => {
        el.addEventListener('click', () => {
            switchView(el.dataset.view);
        });
    });

    // Search
    document.getElementById('searchInput').addEventListener('input', debounce(() => {
        if (currentView === 'apps') filterAndRenderApps();
        else if (currentView === 'processes') loadProcesses();
    }, 300));

    // Start monitoring immediately
    startMonitoring();

    // Also load initial system stats
    loadSystemStats();
}

function switchView(view) {
    currentView = view;

    // Update nav
    document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
    document.querySelector(`.nav-item[data-view="${view}"]`)?.classList.add('active');

    // Update content
    document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
    document.getElementById(`view-${view}`)?.classList.add('active');

    // Update search placeholder
    const search = document.getElementById('searchInput');
    if (view === 'apps') search.placeholder = 'Search apps by name, bundle ID, or path...';
    else if (view === 'processes') search.placeholder = 'Search processes by name or command...';
    else if (view === 'packages') search.placeholder = 'Search package IDs...';
    else search.placeholder = 'Search...';

    // Load data for view
    if (view === 'processes') loadProcesses();
    else if (view === 'packages') loadPackages();
    else if (view === 'snapshots') loadSnapshots();
    else if (view === 'removed') loadRemoved();
}

// === Apps ===
async function loadApps(force = false) {
    const container = document.getElementById('appGrid');
    container.innerHTML = '<div class="loading"><div class="spinner"></div>Scanning applications...</div>';

    try {
        const res = await fetch(`${API}/api/apps?force=${force}`);
        const data = await res.json();
        allApps = data.apps;
        document.getElementById('appCount').textContent = data.total;
        filterAndRenderApps();
    } catch (err) {
        container.innerHTML = '<div class="empty-state">Failed to load apps. Is the server running?</div>';
    }
}

async function loadRunningApps() {
    try {
        const res = await fetch(`${API}/api/running-apps`);
        const data = await res.json();
        runningAppNames = data.apps.map(n => n.toLowerCase().trim());
    } catch (err) {
        runningAppNames = [];
    }
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

    document.getElementById('filteredCount').textContent = `${filtered.length} of ${allApps.length}`;
    renderAppGrid(filtered);
}

function renderAppGrid(apps) {
    const container = document.getElementById('appGrid');

    if (apps.length === 0) {
        container.innerHTML = '<div class="empty-state">No apps found matching your filters.</div>';
        return;
    }

    container.innerHTML = apps.map(app => {
        const initial = app.name.charAt(0).toUpperCase();
        const isRunning = runningAppNames.includes(app.name.toLowerCase());
        const sourceClass = getSourceClass(app.install_source);

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
                        ${isRunning ? '<span style="color:var(--silver)">Running</span>' : ''}
                    </div>
                </div>
                <div class="app-card-actions">
                    ${isRunning
                        ? `<button class="btn danger" onclick="event.stopPropagation(); quitAppByName('${escHtml(app.name)}')" title="Force Quit">Quit</button>`
                        : `<button class="btn success" onclick="event.stopPropagation(); launchApp('${escHtml(app.path)}')" title="Launch">Open</button>`
                    }
                </div>
            </div>`;
    }).join('');
}

// === App Detail ===
function showAppDetail(app) {
    const panel = document.getElementById('detailPanel');
    const isRunning = runningAppNames.includes(app.name.toLowerCase());

    document.getElementById('detailContent').innerHTML = `
        <div class="detail-header">
            <div>
                <h2 style="font-size:16px;margin-bottom:4px">${escHtml(app.name)}</h2>
                <div style="font-size:11px;color:var(--text-muted)">${escHtml(app.bundle_id)}</div>
                ${isRunning ? '<div style="color:var(--silver);font-size:11px;margin-top:4px">Running</div>' : ''}
            </div>
            <button class="detail-close" onclick="closeDetail()">&times;</button>
        </div>
        <div class="detail-body">
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
                <button class="btn" onclick="revealInFinder('${escHtml(app.path)}')">Show in Finder</button>
            </div>
        </div>`;

    panel.classList.add('open');
}

function closeDetail() {
    document.getElementById('detailPanel').classList.remove('open');
}

// === Processes ===
async function loadProcesses() {
    const search = document.getElementById('searchInput').value;
    const show = document.getElementById('processFilter')?.value || 'all';

    try {
        const res = await fetch(`${API}/api/processes?search=${encodeURIComponent(search)}&show=${show}`);
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

    // Sort
    const sorted = [...processes].sort((a, b) => {
        let va = a[processSort.key];
        let vb = b[processSort.key];
        if (typeof va === 'string') va = va.toLowerCase();
        if (typeof vb === 'string') vb = vb.toLowerCase();
        if (processSort.dir === 'asc') return va > vb ? 1 : -1;
        return va < vb ? 1 : -1;
    });

    document.getElementById('processCount').textContent = totalCount || processes.length;

    container.innerHTML = sorted.slice(0, 200).map(p => {
        const cpuClass = p.cpu_percent > 50 ? 'cpu-high' : p.cpu_percent > 10 ? 'cpu-med' : '';
        const memClass = p.memory_mb > 500 ? 'mem-high' : '';
        const statusClass = p.status === 'running' ? 'running' : p.status === 'zombie' ? 'zombie' : 'sleeping';

        return `<tr>
            <td class="pid">${p.pid}</td>
            <td><div class="process-name-cell"><span class="status-dot ${statusClass}"></span><span>${escHtml(p.name)}</span></div></td>
            <td class="${cpuClass}">${p.cpu_percent.toFixed(1)}%</td>
            <td class="${memClass}">${p.memory_mb.toFixed(1)} MB</td>
            <td>${escHtml(p.username)}</td>
            <td>${escHtml(p.status)}</td>
            <td>
                <button class="btn danger" onclick="forceQuit(${p.pid})" style="padding:2px 8px;font-size:10px">Kill</button>
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

// === Packages ===
async function loadPackages() {
    const container = document.getElementById('pkgList');
    container.innerHTML = '<div class="loading"><div class="spinner"></div>Loading package receipts...</div>';

    try {
        const res = await fetch(`${API}/api/pkg-history`);
        const data = await res.json();
        const search = document.getElementById('searchInput').value.toLowerCase();

        let receipts = data.receipts;
        if (search) {
            receipts = receipts.filter(r => r.pkg_id.toLowerCase().includes(search));
        }

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

// === Removed ===
async function loadRemoved() {
    const container = document.getElementById('removedList');
    container.innerHTML = '<div class="loading"><div class="spinner"></div>Checking for removed packages...</div>';

    try {
        const res = await fetch(`${API}/api/pkg-removed`);
        const data = await res.json();

        if (data.removed.length === 0) {
            container.innerHTML = '<div class="empty-state">No removed packages detected. All installed packages have their files intact.</div>';
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

// === Snapshots ===
async function loadSnapshots() {
    const container = document.getElementById('snapshotList');

    try {
        const res = await fetch(`${API}/api/snapshots`);
        const data = await res.json();

        if (data.snapshots.length === 0) {
            container.innerHTML = '<div class="empty-state">No snapshots yet. Take one to start tracking changes.</div>';
        } else {
            container.innerHTML = '<div class="snapshot-cards">' + data.snapshots.map(s => `
                <div class="snapshot-card">
                    <h4>${escHtml(s.filename)}</h4>
                    <div class="meta">${escHtml(s.timestamp)} &middot; ${s.app_count} apps</div>
                    <button class="btn danger" onclick="deleteSnapshot('${escHtml(s.filename)}')" style="font-size:10px;padding:3px 8px">Delete</button>
                </div>
            `).join('') + '</div>';
        }

        // Load comparison
        loadSnapshotComparison();
    } catch (err) {
        container.innerHTML = '<div class="empty-state">Failed to load snapshots.</div>';
    }
}

async function saveSnapshot() {
    try {
        const res = await fetch(`${API}/api/snapshots/save`, { method: 'POST' });
        const data = await res.json();
        showToast(`Snapshot saved: ${data.app_count} apps captured`, 'success');
        loadSnapshots();
    } catch (err) {
        showToast('Failed to save snapshot', 'error');
    }
}

async function deleteSnapshot(filename) {
    try {
        await fetch(`${API}/api/snapshots/${filename}`, { method: 'DELETE' });
        showToast('Snapshot deleted', 'info');
        loadSnapshots();
    } catch (err) {
        showToast('Failed to delete snapshot', 'error');
    }
}

async function loadSnapshotComparison() {
    const container = document.getElementById('snapshotComparison');

    try {
        const res = await fetch(`${API}/api/snapshots/compare`);
        const data = await res.json();

        if (!data.has_previous) {
            container.innerHTML = '<div class="empty-state">Save at least one snapshot to start comparing.</div>';
            return;
        }

        let html = `
            <div style="margin-bottom:12px;font-size:12px;color:var(--text-secondary)">
                Comparing with snapshot from ${escHtml(data.snapshot_date)}<br>
                Previous: ${data.previous_count} apps &rarr; Current: ${data.current_count} apps
            </div>
            <div style="display:flex;gap:8px;margin-bottom:12px">
                <span class="diff-badge added">+${data.added_count} Added</span>
                <span class="diff-badge removed">-${data.removed_count} Removed</span>
                <span class="diff-badge updated">${data.updated_count} Updated</span>
            </div>`;

        if (data.added.length > 0) {
            html += '<h4 style="font-size:12px;margin:12px 0 6px;color:var(--silver)">Added Apps</h4><div class="diff-list">';
            html += data.added.map(a => `<div class="diff-item added">+ ${escHtml(a.name)} (${escHtml(a.install_source)})</div>`).join('');
            html += '</div>';
        }
        if (data.removed.length > 0) {
            html += '<h4 style="font-size:12px;margin:12px 0 6px;color:var(--red)">Removed Apps</h4><div class="diff-list">';
            html += data.removed.map(a => `<div class="diff-item removed">- ${escHtml(a.name)}</div>`).join('');
            html += '</div>';
        }
        if (data.updated.length > 0) {
            html += '<h4 style="font-size:12px;margin:12px 0 6px;color:var(--tan)">Updated Apps</h4><div class="diff-list">';
            html += data.updated.map(a => `<div class="diff-item updated">${escHtml(a.name)}: ${escHtml(a.old_version)} &rarr; ${escHtml(a.new_version)}</div>`).join('');
            html += '</div>';
        }

        if (data.added.length === 0 && data.removed.length === 0 && data.updated.length === 0) {
            html += '<div class="empty-state">No changes since last snapshot.</div>';
        }

        container.innerHTML = html;
    } catch (err) {
        container.innerHTML = '<div class="empty-state">Failed to compare snapshots.</div>';
    }
}

// === System Stats ===
async function loadSystemStats() {
    try {
        const res = await fetch(`${API}/api/system`);
        const data = await res.json();
        updateSystemStats(data);
    } catch (err) {
        console.error('Failed to load system stats');
    }
}

function updateSystemStats(stats) {
    // CPU
    const cpuBar = document.getElementById('cpuBar');
    const cpuText = document.getElementById('cpuText');
    if (cpuBar && cpuText) {
        cpuBar.style.width = stats.cpu_percent + '%';
        cpuBar.className = 'stat-bar-fill cpu' + (stats.cpu_percent > 80 ? ' high' : '');
        cpuText.textContent = stats.cpu_percent.toFixed(0) + '%';
    }

    // Memory
    const memBar = document.getElementById('memBar');
    const memText = document.getElementById('memText');
    if (memBar && memText) {
        memBar.style.width = stats.memory_percent + '%';
        memBar.className = 'stat-bar-fill mem' + (stats.memory_percent > 80 ? ' high' : '');
        memText.textContent = stats.memory_percent.toFixed(0) + '%';
    }

    // Disk
    const diskBar = document.getElementById('diskBar');
    const diskText = document.getElementById('diskText');
    if (diskBar && diskText) {
        diskBar.style.width = stats.disk_percent + '%';
        diskBar.className = 'stat-bar-fill disk' + (stats.disk_percent > 90 ? ' high' : '');
        diskText.textContent = stats.disk_percent.toFixed(0) + '%';
    }

    // Process count
    const procCountEl = document.getElementById('totalProcessCount');
    if (procCountEl) procCountEl.textContent = stats.process_count;
}

// === Actions ===
async function launchApp(path) {
    try {
        const res = await fetch(`${API}/api/launch`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path })
        });
        const data = await res.json();
        showToast(data.message, data.success ? 'success' : 'error');
        if (data.success) {
            setTimeout(() => loadRunningApps().then(filterAndRenderApps), 2000);
        }
    } catch (err) {
        showToast('Failed to launch app', 'error');
    }
}

async function forceQuit(pid) {
    try {
        const res = await fetch(`${API}/api/quit`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ pid, force: true })
        });
        const data = await res.json();
        showToast(data.message, data.success ? 'success' : 'error');
        if (data.success) {
            setTimeout(() => {
                loadRunningApps().then(filterAndRenderApps);
                if (currentView === 'processes') loadProcesses();
            }, 1000);
        }
    } catch (err) {
        showToast('Failed to quit process', 'error');
    }
}

async function quitAppByName(appName) {
    // Find the process by app name
    try {
        const res = await fetch(`${API}/api/processes?search=${encodeURIComponent(appName)}&show=apps`);
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

async function revealInFinder(path) {
    try {
        await fetch(`${API}/api/launch`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path: path, reveal: true })
        });
    } catch (err) {}
    // Fallback: just open the parent directory
    const dir = path.substring(0, path.lastIndexOf('/'));
    launchApp(dir);
}

function refreshApps() {
    loadApps(true);
    loadRunningApps();
    loadSources();
}

// === Sources ===
async function loadSources() {
    try {
        const res = await fetch(`${API}/api/apps/sources`);
        const data = await res.json();
        const container = document.getElementById('sourceFilters');

        container.innerHTML = Object.entries(data.sources)
            .sort((a, b) => b[1] - a[1])
            .map(([src, count]) => {
                const cls = getSourceClass(src);
                return `<div class="source-item ${sourceFilter === src ? 'active' : ''}"
                             onclick="setSourceFilter('${escHtml(src)}')">
                    <div style="display:flex;align-items:center;gap:6px">
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

// === Utilities ===
function escHtml(str) {
    if (!str) return '';
    return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function getSourceClass(source) {
    if (!source) return 'unknown';
    const s = source.toLowerCase();
    if (s.includes('app store')) return 'app-store';
    if (s.includes('homebrew')) return 'homebrew';
    if (s.includes('pkg')) return 'pkg';
    if (s.includes('manual') || s.includes('dmg')) return 'manual';
    if (s.includes('system')) return 'system';
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
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = msg;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 4000);
}

function humanBytes(bytes) {
    if (!bytes) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    let i = 0;
    let size = bytes;
    while (size >= 1024 && i < units.length - 1) { size /= 1024; i++; }
    return size.toFixed(1) + ' ' + units[i];
}
