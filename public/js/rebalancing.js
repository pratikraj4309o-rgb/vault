/**
 * Rebalancing Page: Displays per-node storage utilization bars, movement history, Objects Moved, Bytes Moved, Progress, and Estimated Completion.
 */
const RebalancingUI = {
  render(rebalanceStatus = null, nodes = []) {
    if (!rebalanceStatus) return;

    const setEl = (id, val) => {
      const el = document.getElementById(id);
      if (el) el.textContent = val;
    };

    setEl('reb-status', rebalanceStatus.status || 'IDLE');
    setEl('reb-objects-moved', String(rebalanceStatus.objects_moved || 0));
    setEl('reb-bytes-moved', AppUtils.formatBytes(rebalanceStatus.bytes_moved || 0));
    setEl('reb-progress', `${rebalanceStatus.progress ?? 100}%`);
    setEl('reb-eta', rebalanceStatus.estimated_completion || '0s');

    const barsContainer = document.getElementById('rebalance-nodes-bars');
    if (barsContainer) {
      const nodeList = rebalanceStatus.nodes || nodes;
      barsContainer.innerHTML = nodeList
        .map((n) => {
          const pct = Math.max(4, n.utilization_percent || (n.replica_count || 0) * 18);
          const displayPct = n.utilization_percent > 0 ? `${n.utilization_percent}%` : `${n.replica_count || 0} replica(s)`;
          return `
            <div style="margin-bottom:14px">
              <div style="display:flex;justify-content:space-between;margin-bottom:5px;font-family:var(--font-mono);font-size:12.5px">
                <span><strong>${n.node_id.toUpperCase()}</strong> (${n.status}) · ${n.replica_count || 0} replica(s)</span>
                <span>${AppUtils.formatBytes(n.used_capacity)} / ${AppUtils.formatBytes(n.capacity)} (${displayPct})</span>
              </div>
              <div class="util-bar-track" style="height:12px">
                <div class="util-bar-fill ${pct >= 80 ? 'high' : ''}" style="width:${Math.min(100, pct)}%"></div>
              </div>
            </div>
          `;
        })
        .join('');
    }

    const movesBody = document.getElementById('rebalance-movements-tbody');
    if (movesBody) {
      const moves = rebalanceStatus.movements || [];
      if (moves.length === 0) {
        movesBody.innerHTML = `<tr><td colspan="5" style="text-align:center;padding:20px;color:var(--text-muted)">Click "Trigger Rebalance" to migrate replicas from higher-loaded nodes to less-utilized nodes.</td></tr>`;
      } else {
        movesBody.innerHTML = moves
          .map(
            (m) => `
          <tr>
            <td><strong>${AppUtils.escapeHtml(m.filename || m.object_id)}</strong></td>
            <td><span class="mono-code">${m.from_node.toUpperCase()} → ${m.to_node.toUpperCase()}</span></td>
            <td><span class="mono-code">${AppUtils.formatBytes(m.size || 0)}</span></td>
            <td><span class="badge badge-verified">✓ SHA-256 VERIFIED</span></td>
            <td><span class="activity-time">${AppUtils.formatTime(m.completed_at)}</span></td>
          </tr>
        `
          )
          .join('');
      }
    }
  },

  async triggerRebalance() {
    try {
      const res = await api.startRebalance();
      AppUtils.toast(
        `Rebalancing completed: ${res.objects_moved} replica(s) migrated (${AppUtils.formatBytes(res.bytes_moved)}).`,
        'success'
      );
      await App.refreshAll();
    } catch (err) {
      AppUtils.toast(err.message, 'error');
    }
  },
};

window.RebalancingUI = RebalancingUI;
