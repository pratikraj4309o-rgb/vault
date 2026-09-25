/**
 * Replication View: Displays object-to-node trees, Replication Factor, Current, Required, and Missing Replicas.
 */
const ReplicationUI = {
  render(files = [], stats = null) {
    const container = document.getElementById('replication-trees-container');
    if (!container) return;

    if (stats) {
      const setEl = (id, val) => {
        const el = document.getElementById(id);
        if (el) el.textContent = val;
      };
      setEl('rep-global-rf', `${stats.replication_factor}x`);
      setEl('rep-total-replicas', String(stats.total_replicas));
      setEl('rep-healthy-replicas', String(stats.healthy_replicas));
      setEl('rep-degraded-objects', String(stats.degraded_objects));
    }

    if (!files || files.length === 0) {
      container.innerHTML = `<div class="panel" style="text-align:center;color:var(--text-muted)">No replicated objects yet. Upload an object to inspect replica placement trees.</div>`;
      return;
    }

    container.innerHTML = files
      .map((f) => {
        const branches = (f.replicas || [])
          .map((r) => {
            const isHealthy = r.status === 'HEALTHY' && r.node_status === 'ONLINE';
            const mark = isHealthy ? '✓' : '✕';
            return `
              <div class="replica-branch-item">
                <div>
                  <strong style="font-family:var(--font-mono)">|-- ${r.node_id.toUpperCase()} ${mark}</strong>
                  <span style="margin-left:10px;color:var(--text-secondary);font-size:12px">
                    Replica: <span class="mono-code">${r.replica_id}</span> · Version: <strong>v${r.version}</strong> · Node State: <strong>${r.node_status}</strong>
                  </span>
                </div>
                <div style="display:flex;align-items:center;gap:8px">
                  <span class="mono-code">SHA256: ${r.checksum.slice(0, 14)}...</span>
                  <span class="badge ${AppUtils.badgeClass(r.status)}">${r.status}</span>
                </div>
              </div>
            `;
          })
          .join('');

        return `
          <div class="replication-tree-card">
            <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px">
              <div>
                <span style="font-size:15px;font-weight:800;font-family:var(--font-mono);color:var(--accent-cyan)">
                  OBJECT: ${AppUtils.escapeHtml(f.filename)}
                </span>
                <span style="margin-left:10px" class="badge ${AppUtils.badgeClass(f.status)}">${f.status}</span>
              </div>
              <div style="display:flex;gap:14px;font-size:12.5px;font-family:var(--font-mono)">
                <span>Replication Factor: <strong>${f.replication_factor}</strong></span>
                <span>Required: <strong>${f.replication_factor}</strong></span>
                <span>Healthy Replicas: <strong style="color:var(--accent-emerald)">${f.healthy_replicas}</strong></span>
                <span>Missing Replicas: <strong style="color:${f.missing_replicas > 0 ? 'var(--accent-rose)' : 'var(--text-muted)'}">${f.missing_replicas}</strong></span>
              </div>
            </div>
            <div class="replica-branch-list">
              ${branches}
            </div>
          </div>
        `;
      })
      .join('');
  },
};

window.ReplicationUI = ReplicationUI;
