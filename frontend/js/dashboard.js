/**
 * Modern Dashboard Controller for NexStore VAULT.
 * Populates:
 * - Home page Recent Uploads list (matching Image 3)
 * - Sidebar storage usage meter & health status
 * - Emergency alerts
 * - 3D topology & activity feed
 */
const DashboardUI = {
  render(stats, nodes = [], files = [], repairs = [], events = []) {
    if (!stats) return;

    // 1. Header Status Indicator
    const headerStatusBadge = document.getElementById('header-status-badge');
    const headerStatusText = document.getElementById('header-status-text');
    if (headerStatusBadge && headerStatusText) {
      if (stats.failed_nodes === 0 && stats.degraded_objects === 0) {
        headerStatusBadge.className = 'status-badge';
        headerStatusText.textContent = `${stats.active_nodes || 5} Servers Safe & Online`;
      } else {
        headerStatusBadge.className = 'status-badge degraded';
        headerStatusText.textContent = `${stats.failed_nodes} Offline — Auto-Healing`;
      }
    }

    // 2. Emergency Alert Banner
    const alertBanner = document.getElementById('main-alert-banner');
    if (alertBanner) {
      const isDamaged = stats.failed_nodes > 0 || stats.degraded_objects > 0 || stats.corrupted_objects > 0;
      if (isDamaged) {
        alertBanner.classList.add('active');
        const title = document.getElementById('alert-banner-title');
        const desc = document.getElementById('alert-banner-desc');
        if (title) {
          title.textContent = `Alert: ${stats.failed_nodes} Server(s) Crashed · ${stats.degraded_objects + stats.corrupted_objects} File(s) Recovering`;
        }
        if (desc) {
          desc.textContent = `VAULT's autonomous self-healing is replicating data to replacement servers. Zero files will be lost.`;
        }
      } else {
        alertBanner.classList.remove('active');
      }
    }

    // 3. Sidebar Storage Usage Meter
    const storageText = document.getElementById('sidebar-storage-text');
    const storageFill = document.getElementById('sidebar-storage-fill');
    if (storageText && storageFill) {
      const used = stats.used_storage || 0;
      const total = stats.total_storage || 200 * 1024 * 1024 * 1024;
      storageText.textContent = `${AppUtils.formatBytes(used)} of ${AppUtils.formatBytes(total)} used`;
      const pct = Math.min(100, Math.max(3, (used / Math.max(1, total)) * 100));
      storageFill.style.width = `${pct}%`;
    }

    // 4. Home Page Recent Uploads (Image 3)
    const recentUploadsList = document.getElementById('home-recent-uploads-list');
    if (recentUploadsList) {
      const displayFiles = files && files.length > 0 ? files.slice(0, 6) : [];
      if (displayFiles.length === 0) {
        recentUploadsList.innerHTML = `
          <div style="padding:18px;text-align:center;color:var(--vault-text-muted);font-size:12.5px;">
            No uploads yet. Drag &amp; drop a file above or click "Browse files".
          </div>
        `;
      } else {
        recentUploadsList.innerHTML = displayFiles
          .map((f) => {
            const meta = window.FilesUI ? FilesUI.getFileTypeMeta(f.filename) : { icon: '📄', cssClass: 'generic' };
            return `
              <div class="vault-recent-item" onclick="FilesUI.viewLastUploaded()">
                <div class="vault-recent-file-info">
                  <div class="vault-file-type-icon ${meta.cssClass}">${meta.icon}</div>
                  <div>
                    <div class="vault-recent-filename">${AppUtils.escapeHtml(f.filename)}</div>
                    <div style="font-size:11px;color:var(--vault-text-muted);">${AppUtils.formatTime(f.updated_at)}</div>
                  </div>
                </div>
                <div style="display:flex;align-items:center;gap:12px;">
                  <span class="vault-badge-secure">✓ Secure</span>
                  <span style="font-family:var(--font-mono);font-size:12px;color:var(--vault-text-muted);">${AppUtils.formatBytes(f.size)}</span>
                </div>
              </div>
            `;
          })
          .join('');
      }
    }

    // 5. Activity Feed on Recent Tab
    const activityList = document.getElementById('activity-feed-list');
    if (activityList && events && events.length > 0) {
      activityList.innerHTML = events
        .slice(0, 20)
        .map((ev) => `
          <div class="activity-feed-item">
            <span class="activity-bullet ${ev.severity === 'ERROR' ? 'critical' : ev.severity === 'WARNING' ? 'warning' : 'healthy'}"></span>
            <div style="flex:1;">
              <strong>${AppUtils.escapeHtml(ev.message)}</strong>
              <div style="font-size:11.5px;color:var(--vault-text-muted);margin-top:2px;">
                ${ev.event_type} · ${AppUtils.formatTime(ev.created_at)}
              </div>
            </div>
          </div>
        `)
        .join('');
    }

    // 6. Update 3D Topology view if available
    if (window.TopologyUI) {
      TopologyUI.render('dashboard-topology-canvas', nodes, repairs);
    }
  },
};

window.DashboardUI = DashboardUI;
