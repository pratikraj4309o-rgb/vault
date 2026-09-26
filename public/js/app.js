/**
 * Human-Friendly Application Controller for NexStore VAULT.
 * Features:
 * - Clean Theme Switcher (Light / Dark)
 * - 4-Tab Navigation (Overview, My Files, Servers, Advanced Tools)
 * - Single-Click Restore All Servers
 * - Real-Time Background Synchronization
 */
const AppUtils = {
  formatBytes(bytes) {
    const b = Number(bytes || 0);
    if (b === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.min(sizes.length - 1, Math.floor(Math.log(b) / Math.log(k)));
    return `${parseFloat((b / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`;
  },

  formatTime(iso) {
    if (!iso) return '—';
    try {
      const d = new Date(iso);
      return d.toLocaleTimeString([], { hour12: false });
    } catch (_) {
      return iso;
    }
  },

  escapeHtml(str) {
    return String(str || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  },

  badgeClass(status) {
    const s = String(status || '').toUpperCase();
    if (['HEALTHY', 'ONLINE', 'VERIFIED', 'COMPLETED', 'INFO'].includes(s)) return 'badge-healthy';
    if (['DEGRADED', 'PARTITIONED', 'REPAIRING', 'RUNNING', 'QUEUED', 'STALE', 'WARNING', 'VERIFYING'].includes(s)) {
      return 'badge-degraded';
    }
    return 'badge-failed';
  },

  sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  },

  toast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;
    const el = document.createElement('div');
    el.className = 'toast-box';
    const icon = type === 'success' ? '✅' : type === 'error' ? '❌' : 'ℹ️';
    el.innerHTML = `<strong>${icon}</strong> ${this.escapeHtml(message)}`;
    container.appendChild(el);
    setTimeout(() => {
      el.remove();
    }, 4500);
  },

  async copyText(text) {
    try {
      await navigator.clipboard.writeText(text);
      this.toast(`Copied: ${text.slice(0, 24)}...`, 'info');
    } catch (_) {
      const ta = document.createElement('textarea');
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      ta.remove();
      this.toast(`Copied: ${text.slice(0, 24)}...`, 'info');
    }
  },
};

window.AppUtils = AppUtils;

const App = {
  state: {
    stats: null,
    nodes: [],
    files: [],
    replicas: [],
    repairs: [],
    rebalance: null,
    events: [],
  },

  currentTab: 'overview',

  async init() {
    this.initTheme();
    this.bindNavigation();
    if (window.FilesUI && FilesUI.initUploadZone) {
      FilesUI.initUploadZone();
    }
    await this.refreshAll();

    // Auto-refresh cluster state every 3.5 seconds
    setInterval(() => {
      this.refreshAll();
    }, 3500);
  },

  initTheme() {
    const saved = localStorage.getItem('vault_theme') || 'light';
    this.setTheme(saved);
  },

  setTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('vault_theme', theme);
    const icon = document.getElementById('theme-icon');
    const label = document.getElementById('theme-label');
    if (icon && label) {
      if (theme === 'dark') {
        icon.textContent = '☀️';
        label.textContent = 'Light';
      } else {
        icon.textContent = '🌙';
        label.textContent = 'Dark';
      }
    }
  },

  toggleTheme() {
    const current = document.documentElement.getAttribute('data-theme') || 'light';
    this.setTheme(current === 'light' ? 'dark' : 'light');
  },

  bindNavigation() {
    const buttons = document.querySelectorAll('.vault-nav-item[data-tab], .nav-tab-btn[data-tab]');
    buttons.forEach((btn) => {
      btn.addEventListener('click', () => {
        const tab = btn.getAttribute('data-tab');
        this.switchTab(tab);
      });
    });

    const modal = document.getElementById('vault-modal');
    const closeBtn = document.getElementById('vault-modal-close');
    if (closeBtn && modal) {
      closeBtn.addEventListener('click', () => this.closeVaultModal());
      modal.addEventListener('click', (e) => {
        if (e.target === modal) this.closeVaultModal();
      });
    }
  },

  openVaultModal() {
    const modal = document.getElementById('vault-modal');
    if (modal) {
      modal.classList.add('open');
      modal.style.display = 'flex';
    }
  },

  closeVaultModal() {
    const modal = document.getElementById('vault-modal');
    if (modal) {
      modal.classList.remove('open');
      modal.style.display = 'none';
      const body = document.getElementById('vault-modal-body');
      if (body) body.innerHTML = '';
    }
  },

  switchTab(tabId) {
    this.currentTab = tabId;
    document.querySelectorAll('.vault-nav-item[data-tab], .nav-tab-btn[data-tab]').forEach((b) => {
      b.classList.toggle('active', b.getAttribute('data-tab') === tabId);
    });
    document.querySelectorAll('.tab-view').forEach((view) => {
      view.classList.toggle('active', view.id === `tab-${tabId}`);
    });
  },

  async restoreAllNodes() {
    try {
      const offline = (this.state.nodes || []).filter((n) => n.status !== 'ONLINE');
      for (const n of offline) {
        await api.restoreNode(n.node_id);
      }
      AppUtils.toast(`Restored ${offline.length} server(s) to Online!`, 'success');
      await this.refreshAll();
    } catch (err) {
      AppUtils.toast(err.message, 'error');
    }
  },

  async refreshAll() {
    try {
      const [stats, nodesRes, filesRes, replicasRes, repairsRes, rebalanceRes, activityRes] = await Promise.all([
        api.getStats(),
        api.getNodes(),
        api.getFiles(),
        api.getReplicas(),
        api.getRepairs(),
        api.getRebalanceStatus(),
        api.getActivity(60),
      ]);

      this.state.stats = stats;
      this.state.nodes = nodesRes.nodes || [];
      this.state.files = filesRes.files || [];
      this.state.replicas = replicasRes.replicas || [];
      this.state.repairs = repairsRes.repairs || [];
      this.state.rebalance = rebalanceRes;
      this.state.events = activityRes.events || [];

      // Render the clean main overview
      DashboardUI.render(stats, this.state.nodes, this.state.files, this.state.repairs, this.state.events);

      // Render other tabs in case user navigates to them
      if (window.NodesUI) NodesUI.render(this.state.nodes, this.state.repairs);
      if (window.FilesUI) FilesUI.render(this.state.files);
      if (window.SimulationUI) SimulationUI.updateSelectors(this.state.nodes, this.state.files);
      if (window.RepairUI) RepairUI.render(this.state.repairs, stats);
      if (window.RebalancingUI) RebalancingUI.render(this.state.rebalance, this.state.nodes);
    } catch (err) {
      console.error('Refresh error:', err);
    }
  },
};

window.App = App;
document.addEventListener('DOMContentLoaded', () => App.init());
