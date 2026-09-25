/**
 * Cluster Settings & Configuration Validation Controller.
 */
const SettingsUI = {
  initialized: false,

  render(settings = null, stats = null) {
    if (!settings) return;

    if (!this.initialized) {
      const setVal = (id, val) => {
        const el = document.getElementById(id);
        if (el && document.activeElement !== el) el.value = val;
      };
      setVal('set-rf', settings.replication_factor);
      setVal('set-health-interval', settings.health_check_interval);
      setVal('set-repair-interval', settings.repair_interval);
      setVal('set-integrity-interval', settings.integrity_check_interval);
      setVal('set-rebalance-threshold', settings.rebalance_threshold);
      setVal('set-node-capacity-gb', Math.round(settings.max_storage_per_node / (1024 * 1024 * 1024)));
      this.initialized = true;
    }

    const note = document.getElementById('settings-healthy-nodes-hint');
    if (note && stats) {
      note.textContent = `Validation rule: 1 <= Replication Factor <= Healthy Node Count (currently ${stats.active_nodes} healthy nodes online).`;
    }
  },

  async saveSettings(e) {
    if (e) e.preventDefault();
    try {
      const rf = parseInt(document.getElementById('set-rf').value, 10);
      const healthInt = parseInt(document.getElementById('set-health-interval').value, 10);
      const repairInt = parseInt(document.getElementById('set-repair-interval').value, 10);
      const integrityInt = parseInt(document.getElementById('set-integrity-interval').value, 10);
      const rebThresh = parseInt(document.getElementById('set-rebalance-threshold').value, 10);
      const capGb = parseFloat(document.getElementById('set-node-capacity-gb').value);

      const payload = {
        replication_factor: rf,
        health_check_interval: healthInt,
        repair_interval: repairInt,
        integrity_check_interval: integrityInt,
        rebalance_threshold: rebThresh,
        max_storage_per_node: Math.round(capGb * 1024 * 1024 * 1024),
      };

      const res = await api.updateSettings(payload);
      this.initialized = false;
      AppUtils.toast(`Cluster settings saved! Replication Factor = ${res.settings.replication_factor}x.`, 'success');
      await App.refreshAll();
    } catch (err) {
      AppUtils.toast(`Configuration rejected: ${err.message}`, 'error');
    }
  },
};

window.SettingsUI = SettingsUI;
