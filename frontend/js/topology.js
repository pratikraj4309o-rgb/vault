/**
 * Interactive SVG Topology Visualization for VAULT Distributed Router & Storage Nodes.
 * Shows VAULT -> DISTRIBUTED ROUTER -> Node1..Node5, active replica links, and animated repair arcs.
 */
const TopologyUI = {
  render(containerId, nodes = [], repairs = []) {
    const container = document.getElementById(containerId);
    if (!container) return;

    if (window.Vault3DEngine) {
      Vault3DEngine.updateData(nodes, repairs);
      if (Vault3DEngine.mode === '3D') {
        const canvasId = containerId === 'dashboard-topology-canvas' ? 'canvas-3d-dashboard' : 'canvas-3d-nodes';
        if (!document.getElementById(canvasId)) {
          container.innerHTML = `<canvas id="${canvasId}" width="900" height="340" class="topology-svg" style="cursor:grab"></canvas>`;
        }
        Vault3DEngine.renderCanvas(document.getElementById(canvasId));
        return;
      }
    }

    const width = 900;
    const height = 325;
    const routerX = width / 2;
    const routerY = 115;

    const count = Math.max(1, nodes.length);
    const spacing = width / (count + 1);

    const nodePositions = {};
    nodes.forEach((n, idx) => {
      nodePositions[n.node_id] = {
        x: Math.round(spacing * (idx + 1)),
        y: 255,
        node: n,
      };
    });

    // Find recent completed or active repair to draw repair arc (e.g., Node1 -> Node4)
    const recentRepair = repairs.find(
      (r) => r.source_node_id && r.target_node_id && r.source_node_id !== r.target_node_id
    );

    let linksSvg = '';
    nodes.forEach((n) => {
      const pos = nodePositions[n.node_id];
      const isOnline = n.status === 'ONLINE';
      const isPartitioned = n.status === 'PARTITIONED';
      const strokeColor = isOnline
        ? '#38bdf8'
        : isPartitioned
        ? '#f59e0b'
        : '#f43f5e';
      const flowClass = isOnline ? 'svg-flow-line' : '';

      linksSvg += `
        <line x1="${routerX}" y1="${routerY + 22}" x2="${pos.x}" y2="${pos.y - 34}"
              stroke="${strokeColor}" stroke-width="2" stroke-opacity="${isOnline ? 0.65 : 0.45}"
              class="${flowClass}" />
      `;
    });

    let repairArcSvg = '';
    if (recentRepair && nodePositions[recentRepair.source_node_id] && nodePositions[recentRepair.target_node_id]) {
      const src = nodePositions[recentRepair.source_node_id];
      const dst = nodePositions[recentRepair.target_node_id];
      const midX = (src.x + dst.x) / 2;
      const arcY = 315;
      repairArcSvg = `
        <path d="M ${src.x} ${src.y + 24} Q ${midX} ${arcY} ${dst.x} ${dst.y + 24}"
              fill="none" stroke="#10b981" stroke-width="2.5" class="svg-repair-arc" />
        <rect x="${midX - 75}" y="${arcY - 22}" width="150" height="20" rx="6" fill="#062e22" stroke="#10b981" stroke-width="1" />
        <text x="${midX}" y="${arcY - 9}" fill="#34d399" font-size="10.5" font-family="monospace" font-weight="bold" text-anchor="middle">
          REPAIR: ${recentRepair.source_node_id.toUpperCase()} → ${recentRepair.target_node_id.toUpperCase()}
        </text>
      `;
    }

    let nodesSvg = '';
    nodes.forEach((n) => {
      const pos = nodePositions[n.node_id];
      const isOnline = n.status === 'ONLINE';
      const isPartitioned = n.status === 'PARTITIONED';
      const fillBg = isOnline ? '#0f233d' : isPartitioned ? '#36260b' : '#3b121e';
      const stroke = isOnline ? '#10b981' : isPartitioned ? '#f59e0b' : '#f43f5e';
      const dotColor = stroke;

      nodesSvg += `
        <g transform="translate(${pos.x - 58}, ${pos.y - 32})" style="cursor:pointer" onclick="NodesUI.openNodeModal('${n.node_id}')">
          <rect width="116" height="64" rx="10" fill="${fillBg}" stroke="${stroke}" stroke-width="2" />
          <circle cx="18" cy="20" r="5" fill="${dotColor}" />
          <text x="30" y="24" fill="#ffffff" font-size="12.5" font-weight="bold" font-family="monospace">${n.node_id.toUpperCase()}</text>
          <text x="14" y="42" fill="#94a3b8" font-size="10.5" font-family="monospace">${n.status} · ${n.replica_count || 0} reps</text>
          <text x="14" y="56" fill="${stroke}" font-size="10" font-family="monospace">${n.utilization_percent}% cap</text>
        </g>
      `;
    });

    container.innerHTML = `
      <svg viewBox="0 0 ${width} ${height}" class="topology-svg" aria-label="VAULT Storage Topology">
        <!-- VAULT Core to Distributed Router -->
        <line x1="${routerX}" y1="48" x2="${routerX}" y2="${routerY - 22}" stroke="#38bdf8" stroke-width="2.5" class="svg-flow-line" />

        <!-- VAULT Header Box -->
        <rect x="${routerX - 75}" y="12" width="150" height="36" rx="8" fill="#132242" stroke="#38bdf8" stroke-width="2" />
        <text x="${routerX}" y="35" fill="#ffffff" font-size="13" font-weight="bold" font-family="monospace" text-anchor="middle">VAULT ENGINE</text>

        <!-- DISTRIBUTED ROUTER Box -->
        <rect x="${routerX - 105}" y="${routerY - 20}" width="210" height="40" rx="8" fill="#18203c" stroke="#6366f1" stroke-width="2" />
        <text x="${routerX}" y="${routerY + 5}" fill="#a5b4fc" font-size="12" font-weight="bold" font-family="monospace" text-anchor="middle">DISTRIBUTED ROUTER</text>

        ${linksSvg}
        ${repairArcSvg}
        ${nodesSvg}
      </svg>
    `;
  },
};

window.TopologyUI = TopologyUI;
