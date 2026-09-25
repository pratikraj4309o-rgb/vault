/**
 * Storage Nodes Grid, Dynamic Auto-Scaling Controls, Interactive Topology Page, and Clickable Node Detail Modal.
 */
const NodesUI = {
  autoSpawnOnFailure: true,

  toggleAutoSpawn(checked) {
    this.autoSpawnOnFailure = Boolean(checked);
    AppUtils.toast(
      `Auto-Spawn Replacement Node on Failure: ${this.autoSpawnOnFailure ? 'ENABLED (spawns NODE6+)' : 'STANDBY ONLY (uses existing spare nodes first)'}`,
      'info'
    );
  },

  render(nodes = [], repairs = []) {
    const grid = document.getElementById('nodes-cards-grid');
    if (grid) {
      grid.innerHTML = nodes
        .map((n) => {
          const cardStateClass =
            n.status === 'FAILED'
              ? 'node-failed'
              : n.status === 'PARTITIONED'
              ? 'node-partitioned'
              : '';
          const fillClass = n.utilization_percent >= 80 ? 'high' : '';
          const nodeNum = parseInt(n.node_id.replace('node', ''), 10) || 0;
          const isAutoScaled = nodeNum > 5;

          return `
            <div class="node-card ${cardStateClass}" onclick="NodesUI.openNodeModal('${n.node_id}')">
              <div class="node-card-header">
                <div class="node-id-title">
                  <span class="status-dot ${n.status === 'ONLINE' ? 'healthy' : n.status === 'PARTITIONED' ? 'degraded' : 'critical'}"></span>
                  ${n.node_id.toUpperCase()}
                  ${isAutoScaled ? `<span class="badge" style="background:rgba(56,189,248,0.18);color:#38bdf8;border:1px solid rgba(56,189,248,0.45);font-size:10px">⚡ AUTO-SCALED</span>` : ''}
                </div>
                <span class="badge ${AppUtils.badgeClass(n.status)}">${n.status}</span>
              </div>

              <div class="node-metrics-list">
                <div class="node-metric-item">
                  <div class="node-metric-label">Health</div>
                  <div class="node-metric-value">${n.health_status}</div>
                </div>
                <div class="node-metric-item">
                  <div class="node-metric-label">Network</div>
                  <div class="node-metric-value">${n.network_status}</div>
                </div>
                <div class="node-metric-item">
                  <div class="node-metric-label">Objects / Replicas</div>
                  <div class="node-metric-value">${n.object_count} / ${n.replica_count || 0}</div>
                </div>
                <div class="node-metric-item">
                  <div class="node-metric-label">Heartbeat</div>
                  <div class="node-metric-value">${AppUtils.formatTime(n.last_heartbeat)}</div>
                </div>
              </div>

              <div class="util-bar-container">
                <div class="util-bar-header">
                  <span>Used: ${AppUtils.formatBytes(n.used_capacity)} / ${AppUtils.formatBytes(n.capacity)}</span>
                  <strong>${n.utilization_percent}%</strong>
                </div>
                <div class="util-bar-track">
                  <div class="util-bar-fill ${fillClass}" style="width:${Math.max(3, n.utilization_percent)}%"></div>
                </div>
              </div>

              <div class="node-actions-row" onclick="event.stopPropagation()">
                ${
                  n.status === 'ONLINE'
                    ? `<button class="btn btn-danger btn-sm" onclick="NodesUI.failNode('${n.node_id}')">Simulate Failure</button>
                       <button class="btn btn-warning btn-sm" onclick="NodesUI.partitionNode('${n.node_id}')">Partition</button>`
                    : n.status === 'PARTITIONED'
                    ? `<button class="btn btn-success btn-sm" onclick="NodesUI.reconnectNode('${n.node_id}')">Reconnect Network</button>`
                    : `<button class="btn btn-success btn-sm" onclick="NodesUI.restoreNode('${n.node_id}')">Restore Node</button>`
                }
                ${
                  isAutoScaled
                    ? `<button class="btn btn-sm" onclick="NodesUI.decommissionNode('${n.node_id}')" title="Remove dynamically scaled node">Decommission</button>`
                    : ''
                }
              </div>
            </div>
          `;
        })
        .join('');
    }

    TopologyUI.render('nodes-topology-canvas', nodes, repairs);
  },

  async provisionNewNode() {
    try {
      const res = await api.provisionNode('Manual auto-scale request from console');
      AppUtils.toast(`⚡ Auto-Scaled Cluster: Provisioned new storage node ${res.node.node_id.toUpperCase()} (ONLINE)!`, 'success');
      await App.refreshAll();
    } catch (err) {
      AppUtils.toast(err.message, 'error');
    }
  },

  async decommissionNode(nodeId) {
    try {
      await api.decommissionNode(nodeId);
      AppUtils.toast(`Decommissioned dynamically scaled node ${nodeId.toUpperCase()}.`, 'info');
      await App.refreshAll();
    } catch (err) {
      AppUtils.toast(err.message, 'error');
    }
  },

  async openNodeModal(nodeId) {
    try {
      const node = await api.getNode(nodeId);
      const modal = document.getElementById('vault-modal');
      const body = document.getElementById('vault-modal-body');
      if (!modal || !body) return;

      const repRows = (node.replicas || [])
        .map(
          (r) => `
          <tr>
            <td><strong>${AppUtils.escapeHtml(r.filename || r.object_id)}</strong></td>
            <td><span class="mono-code">v${r.version}</span></td>
            <td><span class="mono-code">${r.checksum.slice(0, 16)}...</span></td>
            <td><span class="badge ${AppUtils.badgeClass(r.status)}">${r.status}</span></td>
          </tr>
        `
        )
        .join('');

      body.innerHTML = `
        <div class="panel-header">
          <div>
            <h3 class="panel-title">Storage Node Inspector: ${node.node_id.toUpperCase()}</h3>
            <p class="panel-subtitle">Physical Path: storage_nodes/${node.node_id}/data/</p>
          </div>
          <span class="badge ${AppUtils.badgeClass(node.status)}">${node.status}</span>
        </div>
        <div class="node-metrics-list" style="grid-template-columns:repeat(4,1fr);margin-bottom:16px">
          <div class="node-metric-item"><div class="node-metric-label">Status</div><div class="node-metric-value">${node.status}</div></div>
          <div class="node-metric-item"><div class="node-metric-label">Network</div><div class="node-metric-value">${node.network_status}</div></div>
          <div class="node-metric-item"><div class="node-metric-label">Used Storage</div><div class="node-metric-value">${AppUtils.formatBytes(node.used_capacity)}</div></div>
          <div class="node-metric-item"><div class="node-metric-label">Stored Replicas</div><div class="node-metric-value">${node.replica_count}</div></div>
        </div>
        <h4 style="margin-bottom:10px;font-size:13px;color:var(--text-secondary)">Physical Replicas on ${node.node_id.toUpperCase()}</h4>
        <div class="table-responsive">
          <table class="vault-table">
            <thead>
              <tr><th>Object</th><th>Version</th><th>SHA-256 Checksum</th><th>Status</th></tr>
            </thead>
            <tbody>
              ${repRows || '<tr><td colspan="4" style="text-align:center;color:var(--text-muted)">No replicas currently stored on this node.</td></tr>'}
            </tbody>
          </table>
        </div>
      `;
      modal.classList.add('open');
      modal.style.display = 'flex';
    } catch (err) {
      AppUtils.toast(`Failed to load node details: ${err.message}`, 'error');
    }
  },

  async failNode(nodeId) {
    try {
      const num = parseInt(nodeId.replace('node', ''), 10) || 1;
      const res = await api.failNode(nodeId, true, this.autoSpawnOnFailure);
      if (res.auto_scaled_nodes && res.auto_scaled_nodes.length > 0) {
        const newNames = res.auto_scaled_nodes.map((n) => `Server ${n.node_id.replace('node', '')}`).join(', ');
        AppUtils.toast(
          `💥 Server ${num} crashed! Auto-scaled ${newNames} & repaired all file copies automatically.`,
          'success'
        );
      } else {
        AppUtils.toast(`💥 Server ${num} crashed! VAULT's self-healing repair triggered.`, 'error');
      }
      await App.refreshAll();
    } catch (err) {
      AppUtils.toast(err.message, 'error');
    }
  },

  async restoreNode(nodeId) {
    try {
      const num = parseInt(nodeId.replace('node', ''), 10) || 1;
      await api.restoreNode(nodeId);
      AppUtils.toast(`🔄 Server ${num} turned back ON and safe!`, 'success');
      await App.refreshAll();
    } catch (err) {
      AppUtils.toast(err.message, 'error');
    }
  },

  async partitionNode(nodeId) {
    try {
      await api.partitionNode(nodeId);
      AppUtils.toast(`Network partition active on ${nodeId.toUpperCase()} (TEMPORARILY UNREACHABLE).`, 'warning');
      await App.refreshAll();
    } catch (err) {
      AppUtils.toast(err.message, 'error');
    }
  },

  async reconnectNode(nodeId) {
    try {
      await api.reconnectNode(nodeId);
      AppUtils.toast(`Node ${nodeId.toUpperCase()} reconnected & replica state reconciled.`, 'success');
      await App.refreshAll();
    } catch (err) {
      AppUtils.toast(err.message, 'error');
    }
  },
};

window.NodesUI = NodesUI;
