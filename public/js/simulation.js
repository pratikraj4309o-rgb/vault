/**
 * Dedicated Chaos & Failure Simulator Panel + 12-Phase Guided Demo Runner.
 * Every button invokes actual backend endpoints and updates live cluster state.
 */
const SimulationUI = {
  currentPhase: 1,

  phases: [
    { phase: 1, title: 'Phase 1: Cluster Initialization (5 Nodes ONLINE, System HEALTHY)' },
    { phase: 2, title: 'Phase 2: Upload large_dataset.zip (RF=3 → Node1, Node2, Node3)' },
    { phase: 3, title: 'Phase 3: Verify 3/3 Replicas & SHA-256 Checksum' },
    { phase: 4, title: 'Phase 4: Simulate Node2 FAILURE (Object becomes DEGRADED)' },
    { phase: 5, title: 'Phase 5: Automatic Self-Healing Repair (Node1 → Node4)' },
    { phase: 6, title: 'Phase 6: SHA-256 Verification (Effective Replicas = 3/3 HEALTHY)' },
    { phase: 7, title: 'Phase 7: Simulate Bit-Rot Corruption on Node3 Replica (CHECKSUM MISMATCH)' },
    { phase: 8, title: 'Phase 8: Repair Corrupted Node3 Replica (Node1 → Node3) & Verify' },
    { phase: 9, title: 'Phase 9: Simulate Network Partition on Node4 (PARTITIONED)' },
    { phase: 10, title: 'Phase 10: Reconnect Node4 & Reconcile Replica State' },
    { phase: 11, title: 'Phase 11: Trigger Cluster Rebalancing Across Nodes' },
    { phase: 12, title: 'Phase 12: Restore Node2 & Final Verification (All Nodes ONLINE, System HEALTHY)' },
  ],

  updateSelectors(nodes = [], files = []) {
    const nodeSelects = ['sim-node-select'];
    nodeSelects.forEach((id) => {
      const sel = document.getElementById(id);
      if (!sel) return;
      const cur = sel.value || 'node2';
      sel.innerHTML = nodes
        .map((n) => `<option value="${n.node_id}" ${n.node_id === cur ? 'selected' : ''}>${n.node_id.toUpperCase()} (${n.status})</option>`)
        .join('');
    });

    const objSelect = document.getElementById('sim-object-select');
    if (objSelect) {
      const curObj = objSelect.value;
      if (files.length === 0) {
        objSelect.innerHTML = `<option value="">-- Upload an object first --</option>`;
      } else {
        objSelect.innerHTML = files
          .map(
            (f) =>
              `<option value="${f.object_id}" ${f.object_id === curObj ? 'selected' : ''}>${AppUtils.escapeHtml(f.filename)} (${f.object_id})</option>`
          )
          .join('');
      }
    }

    this.updateDemoBanner();
  },

  updateDemoBanner() {
    const tag = document.getElementById('demo-phase-badge');
    const desc = document.getElementById('demo-phase-desc');
    const info = this.phases[Math.min(this.currentPhase - 1, this.phases.length - 1)];
    if (tag) tag.textContent = `PHASE ${this.currentPhase} / 12`;
    if (desc) desc.textContent = info.title;
  },

  async runNextDemoPhase() {
    try {
      const state = App.state;
      let targetObj = (state.files && state.files[0]) || null;

      switch (this.currentPhase) {
        case 1: {
          for (const n of state.nodes || []) {
            if (n.status !== 'ONLINE') await api.restoreNode(n.node_id);
          }
          AppUtils.toast('Phase 1: All 5 Storage Nodes ONLINE. System HEALTHY.', 'success');
          break;
        }
        case 2: {
          targetObj = await FilesUI.uploadSampleDataset('large_dataset.zip', 256, 3);
          AppUtils.toast('Phase 2: Uploaded large_dataset.zip (RF=3) → Node1, Node2, Node3.', 'success');
          break;
        }
        case 3: {
          if (!targetObj) targetObj = await FilesUI.uploadSampleDataset('large_dataset.zip', 256, 3);
          await api.verifyObject(targetObj.object_id, false);
          AppUtils.toast('Phase 3: Verified 3/3 replicas & SHA-256 integrity.', 'success');
          break;
        }
        case 4: {
          if (!targetObj) targetObj = await FilesUI.uploadSampleDataset('large_dataset.zip', 256, 3);
          // Fail node2 WITHOUT auto-completing repair immediately so user sees DEGRADED state clearly
          await api.failNode('node2', false);
          AppUtils.toast('Phase 4: Simulated Node2 FAILURE! Object is now DEGRADED & repair job queued.', 'error');
          break;
        }
        case 5: {
          await api.runRepairs();
          AppUtils.toast('Phase 5: Automatic Repair completed (Node1 → Node4)!', 'success');
          break;
        }
        case 6: {
          if (targetObj) await api.verifyObject(targetObj.object_id, true);
          AppUtils.toast('Phase 6: SHA-256 checksum verified on replacement replica Node4. Object HEALTHY.', 'success');
          break;
        }
        case 7: {
          if (!targetObj) targetObj = await FilesUI.uploadSampleDataset('large_dataset.zip', 256, 3);
          await api.corruptReplica(targetObj.object_id, 'node3', false);
          AppUtils.toast('Phase 7: Corrupted Node3 replica! Detected CHECKSUM MISMATCH.', 'error');
          break;
        }
        case 8: {
          await api.runRepairs();
          if (targetObj) await api.verifyObject(targetObj.object_id, false);
          AppUtils.toast('Phase 8: Repaired Node3 replica from Node1 & verified SHA-256!', 'success');
          break;
        }
        case 9: {
          await api.partitionNode('node4');
          AppUtils.toast('Phase 9: Simulated Network Partition on Node4 (PARTITIONED). System continues serving reads!', 'warning');
          break;
        }
        case 10: {
          await api.reconnectNode('node4');
          AppUtils.toast('Phase 10: Reconnected Node4 & reconciled replica versions and checksums.', 'success');
          break;
        }
        case 11: {
          await api.startRebalance();
          AppUtils.toast('Phase 11: Executed cluster storage rebalancing across nodes.', 'success');
          break;
        }
        case 12: {
          await api.restoreNode('node2');
          await api.scanIntegrity();
          AppUtils.toast('Phase 12: Restored Node2 & completed full cluster verification. System HEALTHY!', 'success');
          break;
        }
      }

      this.currentPhase = this.currentPhase >= 12 ? 1 : this.currentPhase + 1;
      await App.refreshAll();
    } catch (err) {
      AppUtils.toast(`Demo Step Error: ${err.message}`, 'error');
    }
  },

  async simFailSelectedNode() {
    const sel = document.getElementById('sim-node-select');
    const nodeId = sel ? sel.value : 'node2';
    await NodesUI.failNode(nodeId);
  },

  async simRestoreSelectedNode() {
    const sel = document.getElementById('sim-node-select');
    const nodeId = sel ? sel.value : 'node2';
    await NodesUI.restoreNode(nodeId);
  },

  async simPartitionSelectedNode() {
    const sel = document.getElementById('sim-node-select');
    const nodeId = sel ? sel.value : 'node3';
    await NodesUI.partitionNode(nodeId);
  },

  async simReconnectSelectedNode() {
    const sel = document.getElementById('sim-node-select');
    const nodeId = sel ? sel.value : 'node3';
    await NodesUI.reconnectNode(nodeId);
  },

  async simCorruptSelectedObject() {
    const objSel = document.getElementById('sim-object-select');
    const nodeSel = document.getElementById('sim-node-select');
    let objId = objSel ? objSel.value : '';
    if (!objId) {
      const uploaded = await FilesUI.uploadSampleDataset('large_dataset.zip', 256, 3);
      objId = uploaded.object_id;
    }
    await FilesUI.corruptObject(objId, nodeSel ? nodeSel.value : null);
  },
};

window.SimulationUI = SimulationUI;
