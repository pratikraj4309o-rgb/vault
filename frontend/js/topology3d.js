/**
 * Interactive 3D WebGL / HTML5 3D Projection Engine & 3D Card Tilt Controller for NexStore VAULT.
 * Features:
 * - Orbitable 3D Camera (drag to rotate 360°, scroll to zoom, auto-orbit toggle)
 * - 3D Central Hexagonal Router Core with rotating energy rings
 * - 3D Server Monolith Towers (NODE1..NODE6+) with volumetric capacity fill & status beacons
 * - Animated 3D Data Packets flying along 3D conduits & green 3D Self-Healing Repair Arcs
 * - Click-to-Inspect 3D hit-testing + 3D Perspective Tilt on KPI & Node Cards
 */
const Vault3DEngine = {
  mode: '3D', // '3D' or '2D'
  autoRotate: true,
  yaw: 0.45,
  pitch: 0.42,
  zoom: 1.0,
  isDragging: false,
  lastMouseX: 0,
  lastMouseY: 0,
  nodes: [],
  repairs: [],
  hitBoxes: [],
  packets: [],
  animFrameId: null,
  tick: 0,

  init() {
    // Initialize flying 3D packets
    for (let i = 0; i < 18; i++) {
      this.packets.push({
        nodeIndex: i % 5,
        t: Math.random(),
        speed: 0.008 + Math.random() * 0.008,
      });
    }
    this.initCardTilt();
    this.startLoop();
  },

  toggleMode() {
    this.mode = this.mode === '3D' ? '2D' : '3D';
    const btns = document.querySelectorAll('.toggle-3d-btn');
    btns.forEach((b) => {
      b.innerHTML = this.mode === '3D' ? '🧊 3D View: ON (Switch to 2D)' : '📐 2D View: ON (Switch to 3D)';
    });
    if (window.App) {
      TopologyUI.render('dashboard-topology-canvas', App.state.nodes, App.state.repairs);
      TopologyUI.render('nodes-topology-canvas', App.state.nodes, App.state.repairs);
    }
  },

  updateData(nodes = [], repairs = []) {
    this.nodes = nodes;
    this.repairs = repairs;
  },

  initCardTilt() {
    document.addEventListener('mousemove', (e) => {
      const card = e.target.closest('.kpi-card, .node-card, .sim-card');
      if (!card) return;
      const rect = card.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      const cx = rect.width / 2;
      const cy = rect.height / 2;
      const rotY = ((x - cx) / cx) * 7;
      const rotX = -((y - cy) / cy) * 7;
      card.style.transform = `perspective(700px) rotateX(${rotX.toFixed(2)}deg) rotateY(${rotY.toFixed(2)}deg) translateZ(4px)`;
    });

    document.addEventListener('mouseout', (e) => {
      const card = e.target.closest('.kpi-card, .node-card, .sim-card');
      if (card && !card.contains(e.relatedTarget)) {
        card.style.transform = '';
      }
    });
  },

  attachCanvasEvents(canvas) {
    if (canvas._bound3D) return;
    canvas._bound3D = true;

    canvas.addEventListener('mousedown', (e) => {
      this.isDragging = true;
      this.autoRotate = false;
      this.lastMouseX = e.clientX;
      this.lastMouseY = e.clientY;
    });

    window.addEventListener('mousemove', (e) => {
      if (!this.isDragging) return;
      const dx = e.clientX - this.lastMouseX;
      const dy = e.clientY - this.lastMouseY;
      this.yaw += dx * 0.008;
      this.pitch = Math.max(0.15, Math.min(1.15, this.pitch + dy * 0.006));
      this.lastMouseX = e.clientX;
      this.lastMouseY = e.clientY;
    });

    window.addEventListener('mouseup', () => {
      this.isDragging = false;
    });

    canvas.addEventListener(
      'wheel',
      (e) => {
        e.preventDefault();
        this.zoom = Math.max(0.65, Math.min(1.5, this.zoom - e.deltaY * 0.0008));
      },
      { passive: false }
    );

    canvas.addEventListener('click', (e) => {
      const rect = canvas.getBoundingClientRect();
      const mx = ((e.clientX - rect.left) / rect.width) * canvas.width;
      const my = ((e.clientY - rect.top) / rect.height) * canvas.height;
      for (const hb of this.hitBoxes) {
        if (mx >= hb.x - hb.w / 2 && mx <= hb.x + hb.w / 2 && my >= hb.y - hb.h / 2 && my <= hb.y + hb.h / 2) {
          if (window.NodesUI) {
            NodesUI.openNodeModal(hb.nodeId);
          }
          break;
        }
      }
    });
  },

  project(x, y, z, cx, cy) {
    // Rotate around Y (yaw)
    const cosY = Math.cos(this.yaw);
    const sinY = Math.sin(this.yaw);
    const rx = x * cosY - z * sinY;
    const rz = x * sinY + z * cosY;

    // Rotate around X (pitch)
    const cosP = Math.cos(this.pitch);
    const sinP = Math.sin(this.pitch);
    const ry = y * cosP - rz * sinP;
    const rz2 = y * sinP + rz * cosP;

    const fov = 560 * this.zoom;
    const distance = 680;
    const scale = fov / Math.max(120, distance + rz2);

    return {
      sx: cx + rx * scale,
      sy: cy + ry * scale,
      scale,
      depth: rz2,
    };
  },

  draw3DTower(ctx, cx, cy, wx, wy, wz, width, height, depth, node, fillRatio) {
    const hw = width / 2;
    const hd = depth / 2;
    const isOnline = node.status === 'ONLINE';
    const isPartitioned = node.status === 'PARTITIONED';
    const num = parseInt(node.node_id.replace('node', ''), 10) || 0;
    const isAutoScaled = num > 5;

    const strokeColor = isAutoScaled && isOnline
      ? '#38bdf8'
      : isOnline
      ? '#10b981'
      : isPartitioned
      ? '#f59e0b'
      : '#f43f5e';

    const vertices = [
      { x: wx - hw, y: wy, z: wz - hd },
      { x: wx + hw, y: wy, z: wz - hd },
      { x: wx + hw, y: wy, z: wz + hd },
      { x: wx - hw, y: wy, z: wz + hd },
      { x: wx - hw, y: wy - height, z: wz - hd },
      { x: wx + hw, y: wy - height, z: wz - hd },
      { x: wx + hw, y: wy - height, z: wz + hd },
      { x: wx - hw, y: wy - height, z: wz + hd },
    ].map((v) => this.project(v.x, v.y, v.z, cx, cy));

    // Draw translucent 3D box faces
    const faces = [
      [0, 1, 5, 4],
      [1, 2, 6, 5],
      [2, 3, 7, 6],
      [3, 0, 4, 7],
      [4, 5, 6, 7], // top face
    ];

    ctx.lineWidth = 1.6;
    ctx.strokeStyle = strokeColor;
    ctx.fillStyle = isOnline
      ? 'rgba(15, 35, 61, 0.78)'
      : isPartitioned
      ? 'rgba(65, 44, 11, 0.78)'
      : 'rgba(65, 16, 30, 0.82)';

    faces.forEach((f, idx) => {
      ctx.beginPath();
      ctx.moveTo(vertices[f[0]].sx, vertices[f[0]].sy);
      for (let i = 1; i < f.length; i++) {
        ctx.lineTo(vertices[f[i]].sx, vertices[f[i]].sy);
      }
      ctx.closePath();
      if (idx === 4) {
        ctx.fillStyle = isOnline ? 'rgba(16, 185, 129, 0.25)' : 'rgba(244, 63, 94, 0.28)';
      }
      ctx.fill();
      ctx.stroke();
    });

    // Draw internal volumetric storage fill bar
    const fillH = Math.max(8, height * Math.min(0.95, Math.max(0.15, fillRatio)));
    const innerVerts = [
      { x: wx - hw * 0.68, y: wy - 4, z: wz - hd * 0.68 },
      { x: wx + hw * 0.68, y: wy - 4, z: wz - hd * 0.68 },
      { x: wx + hw * 0.68, y: wy - fillH, z: wz - hd * 0.68 },
      { x: wx - hw * 0.68, y: wy - fillH, z: wz - hd * 0.68 },
    ].map((v) => this.project(v.x, v.y, v.z, cx, cy));

    ctx.beginPath();
    ctx.moveTo(innerVerts[0].sx, innerVerts[0].sy);
    innerVerts.slice(1).forEach((p) => ctx.lineTo(p.sx, p.sy));
    ctx.closePath();
    ctx.fillStyle = strokeColor;
    ctx.globalAlpha = 0.48;
    ctx.fill();
    ctx.globalAlpha = 1.0;

    // Top label & status HUD above 3D tower
    const topCenter = this.project(wx, wy - height - 22, wz, cx, cy);
    ctx.font = 'bold 12px monospace';
    ctx.textAlign = 'center';
    ctx.fillStyle = '#ffffff';
    ctx.fillText(node.node_id.toUpperCase() + (isAutoScaled ? ' ⚡' : ''), topCenter.sx, topCenter.sy);

    ctx.font = '10.5px monospace';
    ctx.fillStyle = strokeColor;
    ctx.fillText(`${node.status} · ${node.replica_count || 0} reps`, topCenter.sx, topCenter.sy + 13);

    return {
      nodeId: node.node_id,
      x: topCenter.sx,
      y: topCenter.sy + 25,
      w: 85,
      h: 95,
    };
  },

  renderCanvas(canvas) {
    if (!canvas) return;
    this.attachCanvasEvents(canvas);
    const ctx = canvas.getContext('2d');
    const W = canvas.width;
    const H = canvas.height;
    const cx = W / 2;
    const cy = H / 2 + 25;

    ctx.clearRect(0, 0, W, H);

    // Draw 3D Perspective Floor Grid
    ctx.strokeStyle = 'rgba(56, 189, 248, 0.11)';
    ctx.lineWidth = 1;
    const gridSpan = 290;
    const step = 58;
    for (let g = -gridSpan; g <= gridSpan; g += step) {
      const p1 = this.project(g, 70, -gridSpan, cx, cy);
      const p2 = this.project(g, 70, gridSpan, cx, cy);
      ctx.beginPath();
      ctx.moveTo(p1.sx, p1.sy);
      ctx.lineTo(p2.sx, p2.sy);
      ctx.stroke();

      const p3 = this.project(-gridSpan, 70, g, cx, cy);
      const p4 = this.project(gridSpan, 70, g, cx, cy);
      ctx.beginPath();
      ctx.moveTo(p3.sx, p3.sy);
      ctx.lineTo(p4.sx, p4.sy);
      ctx.stroke();
    }

    const nodes = this.nodes || [];
    const count = Math.max(1, nodes.length);
    const radius = 215;

    // Compute 3D world positions of nodes in a circle around the Central Router Core
    const nodeWorld = nodes.map((n, idx) => {
      const angle = (idx / count) * Math.PI * 2 - Math.PI / 2;
      const wx = Math.cos(angle) * radius;
      const wz = Math.sin(angle) * radius;
      const proj = this.project(wx, 65, wz, cx, cy);
      return {
        node: n,
        idx,
        wx,
        wy: 65,
        wz,
        proj,
      };
    });

    const routerPos = this.project(0, -55, 0, cx, cy);

    // Draw 3D fiber conduits & animated flying 3D packets from Central Router Core to each Node
    nodeWorld.forEach((nw) => {
      const isOnline = nw.node.status === 'ONLINE';
      const isPart = nw.node.status === 'PARTITIONED';
      const basePos = this.project(nw.wx, 18, nw.wz, cx, cy);

      ctx.beginPath();
      ctx.moveTo(routerPos.sx, routerPos.sy);
      ctx.quadraticCurveTo(cx, cy - 10, basePos.sx, basePos.sy);
      ctx.strokeStyle = isOnline
        ? 'rgba(56, 189, 248, 0.55)'
        : isPart
        ? 'rgba(245, 158, 11, 0.45)'
        : 'rgba(244, 63, 94, 0.38)';
      ctx.lineWidth = 2;
      ctx.stroke();
    });

    // Draw flying 3D data packets along active conduits
    this.packets.forEach((pkt) => {
      if (nodeWorld.length === 0) return;
      const target = nodeWorld[pkt.nodeIndex % nodeWorld.length];
      if (!target || target.node.status !== 'ONLINE') return;

      const t = pkt.t;
      const px = target.wx * t;
      const py = -55 * (1 - t) + 18 * t - Math.sin(t * Math.PI) * 35;
      const pz = target.wz * t;
      const pProj = this.project(px, py, pz, cx, cy);

      ctx.beginPath();
      ctx.arc(pProj.sx, pProj.sy, Math.max(2.5, 4.2 * pProj.scale), 0, Math.PI * 2);
      ctx.fillStyle = '#38bdf8';
      ctx.shadowColor = '#38bdf8';
      ctx.shadowBlur = 10;
      ctx.fill();
      ctx.shadowBlur = 0;
    });

    // Draw 3D Self-Healing Repair Arc between source and target node if a repair occurred
    const recentRepair = (this.repairs || []).find(
      (r) => r.source_node_id && r.target_node_id && r.source_node_id !== r.target_node_id
    );
    if (recentRepair) {
      const srcW = nodeWorld.find((nw) => nw.node.node_id === recentRepair.source_node_id);
      const dstW = nodeWorld.find((nw) => nw.node.node_id === recentRepair.target_node_id);
      if (srcW && dstW) {
        const sP = this.project(srcW.wx, -20, srcW.wz, cx, cy);
        const dP = this.project(dstW.wx, -20, dstW.wz, cx, cy);
        const midP = this.project((srcW.wx + dstW.wx) / 2, -110, (srcW.wz + dstW.wz) / 2, cx, cy);

        ctx.beginPath();
        ctx.moveTo(sP.sx, sP.sy);
        ctx.quadraticCurveTo(midP.sx, midP.sy, dP.sx, dP.sy);
        ctx.strokeStyle = '#10b981';
        ctx.lineWidth = 2.8;
        ctx.setLineDash([7, 5]);
        ctx.stroke();
        ctx.setLineDash([]);

        ctx.fillStyle = '#34d399';
        ctx.font = 'bold 11px monospace';
        ctx.textAlign = 'center';
        ctx.fillText(
          `3D REPAIR STREAM: ${recentRepair.source_node_id.toUpperCase()} → ${recentRepair.target_node_id.toUpperCase()}`,
          midP.sx,
          midP.sy - 6
        );
      }
    }

    // Painter's algorithm: sort 3D objects (Router Core + Server Towers) back-to-front by depth
    const renderables = nodeWorld.map((nw) => ({
      type: 'node',
      depth: nw.proj.depth,
      data: nw,
    }));
    renderables.push({
      type: 'router',
      depth: routerPos.depth,
    });
    renderables.sort((a, b) => b.depth - a.depth);

    this.hitBoxes = [];
    renderables.forEach((item) => {
      if (item.type === 'router') {
        this.drawRouterCore(ctx, routerPos.sx, routerPos.sy, routerPos.scale);
      } else {
        const nw = item.data;
        const repFactor = Math.min(1, (nw.node.replica_count || 0) * 0.25 + (nw.node.utilization_percent || 0) / 100);
        const hb = this.draw3DTower(ctx, cx, cy, nw.wx, nw.wy, nw.wz, 46, 86, 46, nw.node, repFactor);
        this.hitBoxes.push(hb);
      }
    });

    // Top-left 3D Controls Overlay hint
    ctx.fillStyle = 'rgba(148, 163, 184, 0.8)';
    ctx.font = '11px monospace';
    ctx.textAlign = 'left';
    ctx.fillText('🧊 3D INTERACTIVE CLUSTER: Drag to Orbit 360° · Scroll to Zoom · Click Any 3D Node to Inspect', 14, 20);
  },

  drawRouterCore(ctx, sx, sy, scale) {
    const r = 26 * scale;
    ctx.save();
    ctx.translate(sx, sy);

    // Outer rotating energy ring
    ctx.rotate(this.tick * 0.02);
    ctx.strokeStyle = '#6366f1';
    ctx.lineWidth = 2.2;
    ctx.beginPath();
    for (let i = 0; i < 6; i++) {
      const a = (i / 6) * Math.PI * 2;
      const x = Math.cos(a) * (r * 1.35);
      const y = Math.sin(a) * (r * 1.35);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.closePath();
    ctx.stroke();

    // Inner glowing VAULT core
    ctx.fillStyle = 'rgba(56, 189, 248, 0.25)';
    ctx.strokeStyle = '#38bdf8';
    ctx.beginPath();
    ctx.arc(0, 0, r, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();

    ctx.rotate(-this.tick * 0.02);
    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 10.5px monospace';
    ctx.textAlign = 'center';
    ctx.fillText('VAULT 3D CORE', 0, -r - 12);
    ctx.fillStyle = '#38bdf8';
    ctx.font = '9.5px monospace';
    ctx.fillText('ROUTER', 0, 4);
    ctx.restore();
  },

  startLoop() {
    const step = () => {
      this.tick++;
      if (this.autoRotate && !this.isDragging) {
        this.yaw += 0.0045;
      }
      this.packets.forEach((p) => {
        p.t += p.speed;
        if (p.t > 1) p.t = 0;
      });

      if (this.mode === '3D') {
        const c1 = document.getElementById('canvas-3d-dashboard');
        const c2 = document.getElementById('canvas-3d-nodes');
        if (c1) this.renderCanvas(c1);
        if (c2) this.renderCanvas(c2);
      }
      this.animFrameId = requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  },
};

window.Vault3DEngine = Vault3DEngine;
document.addEventListener('DOMContentLoaded', () => Vault3DEngine.init());
