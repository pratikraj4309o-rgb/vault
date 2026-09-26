/**
 * Repair Center View: Displays active & historical self-healing repair jobs, progress bars, recovery metrics, and manual retry/run controls.
 */
const RepairUI = {
  render(repairs = [], stats = null) {
    if (stats) {
      const setEl = (id, val) => {
        const el = document.getElementById(id);
        if (el) el.textContent = val;
      };
      setEl('repair-kpi-avg-time', `${stats.average_recovery_time_ms} ms`);
      setEl('repair-kpi-success', String(stats.successful_repairs));
      setEl('repair-kpi-failed', String(stats.failed_repairs));
      setEl('repair-kpi-active', String(stats.active_repairs));
    }

    const tbody = document.getElementById('repairs-table-tbody');
    if (!tbody) return;

    if (!repairs || repairs.length === 0) {
      tbody.innerHTML = `<tr><td colspan="8" style="text-align:center;padding:24px;color:var(--text-muted)">No repair jobs recorded yet. Simulate a node failure or replica corruption to observe automatic self-healing.</td></tr>`;
      return;
    }

    tbody.innerHTML = repairs
      .map((j) => {
        const src = j.source_node_id ? j.source_node_id.toUpperCase() : 'AUTO';
        const dst = j.target_node_id ? j.target_node_id.toUpperCase() : 'PENDING';
        const failedNode = j.failed_node_id ? j.failed_node_id.toUpperCase() : '—';
        const duration = j.duration_ms ? `${j.duration_ms} ms` : 'In Progress';

        return `
          <tr>
            <td>
              <strong>${AppUtils.escapeHtml(j.filename || j.object_id)}</strong>
              <div style="font-size:11px;color:var(--text-muted)">${j.repair_id}</div>
            </td>
            <td><span class="badge badge-failed">${failedNode}</span></td>
            <td><span class="mono-code">${src} → ${dst}</span></td>
            <td>${AppUtils.escapeHtml(j.reason)}</td>
            <td>
              <div style="width:120px">
                <div style="display:flex;justify-content:space-between;font-size:11px;margin-bottom:3px">
                  <span>${j.status}</span>
                  <span>${j.progress}%</span>
                </div>
                <div class="util-bar-track">
                  <div class="util-bar-fill" style="width:${j.progress}%"></div>
                </div>
              </div>
            </td>
            <td><span class="activity-time">${AppUtils.formatTime(j.started_at)}</span></td>
            <td><span class="mono-code">${duration}</span></td>
            <td>
              <div style="display:flex;align-items:center;gap:6px">
                <span class="badge ${AppUtils.badgeClass(j.status)}">${j.status}</span>
                ${
                  j.status !== 'COMPLETED'
                    ? `<button class="btn btn-sm btn-primary" onclick="RepairUI.retryJob('${j.repair_id}')">Execute / Retry</button>`
                    : ''
                }
              </div>
            </td>
          </tr>
        `;
      })
      .join('');
  },

  async runPendingRepairs() {
    try {
      const res = await api.runRepairs();
      AppUtils.toast(`Executed ${res.processed} pending repair job(s). All target replicas verified!`, 'success');
      await App.refreshAll();
    } catch (err) {
      AppUtils.toast(err.message, 'error');
    }
  },

  async retryJob(repairId) {
    try {
      await api.retryRepair(repairId);
      AppUtils.toast(`Repair job ${repairId} executed & verified.`, 'success');
      await App.refreshAll();
    } catch (err) {
      AppUtils.toast(err.message, 'error');
    }
  },
};

window.RepairUI = RepairUI;
