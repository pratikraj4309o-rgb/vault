/**
 * Supabase Cloud Sync UI Controller
 * Manages 1-click cloud sync, credentials, schema copy, and connection states.
 */
const SupabaseUI = {
  schemaSql: "",
  isConfigured: false,
  isConnected: false,

  async init() {
    await this.refreshStatus();
    this.fetchSchema();
  },

  async refreshStatus() {
    try {
      const apiBase = window.API_BASE || "";
      const res = await fetch(apiBase + "/api/supabase/status");
      if (!res.ok) return;
      const data = await res.json();

      this.isConfigured = !!data.configured;
      this.isConnected = !!data.connected;

      // Update header pill
      const headerBtn = document.getElementById("open-supabase-modal-btn");
      const headerText = document.getElementById("supabase-header-text");
      if (headerBtn && headerText) {
        if (this.isConnected) {
          headerBtn.classList.add("connected");
          headerText.textContent = "Supabase: Connected";
        } else if (this.isConfigured) {
          headerBtn.classList.remove("connected");
          headerText.textContent = "Supabase: Configured (Offline)";
        } else {
          headerBtn.classList.remove("connected");
          headerText.textContent = "Connect Supabase";
        }
      }

      // Update modal status box if modal is open
      this.updateModalState(data);
    } catch (err) {
      console.warn("Could not fetch Supabase status:", err);
    }
  },

  updateModalState(data) {
    const statusBox = document.getElementById("supabase-modal-status-box");
    const statusText = document.getElementById("supabase-modal-status-text");
    const syncInfo = document.getElementById("supabase-modal-sync-info");
    const urlInput = document.getElementById("supabase-input-url");
    const syncBtn = document.getElementById("supabase-btn-sync");
    const disconnectBtn = document.getElementById("supabase-btn-disconnect");

    if (!statusBox || !statusText) return;

    if (data.url && urlInput && !urlInput.value) {
      urlInput.value = data.url;
    }

    if (data.connected) {
      statusBox.className = "supabase-status-banner connected";
      statusText.innerHTML = "Status: <strong>Connected to Supabase Cloud</strong>";
      const stats = data.stats || {};
      const nodeCount = stats.nodes !== undefined ? stats.nodes : "Active";
      const objCount = stats.objects !== undefined ? stats.objects : "0";
      syncInfo.textContent = `Live Syncing | ${nodeCount} nodes, ${objCount} files synced`;
      if (syncBtn) syncBtn.style.display = "inline-flex";
      if (disconnectBtn) disconnectBtn.style.display = "inline-flex";
    } else if (data.configured) {
      statusBox.className = "supabase-status-banner warning";
      statusText.innerHTML = "Status: <strong>Configured, but tables missing or offline</strong>";
      syncInfo.textContent = data.last_error || "Please run SQL schema in Supabase";
      if (syncBtn) syncBtn.style.display = "none";
      if (disconnectBtn) disconnectBtn.style.display = "inline-flex";
    } else {
      statusBox.className = "supabase-status-banner";
      statusText.innerHTML = "Status: <strong>Disconnected (Local SQLite Mode)</strong>";
      syncInfo.textContent = "Files and replicas stored locally on your machine";
      if (syncBtn) syncBtn.style.display = "none";
      if (disconnectBtn) disconnectBtn.style.display = "none";
    }
  },

  async fetchSchema() {
    try {
      const apiBase = window.API_BASE || "";
      const res = await fetch(apiBase + "/api/supabase/schema");
      if (res.ok) {
        const data = await res.json();
        this.schemaSql = data.sql || "";
        const codeBox = document.getElementById("supabase-schema-code");
        if (codeBox) codeBox.textContent = this.schemaSql;
      }
    } catch (e) {
      console.warn("Could not load schema:", e);
    }
  },

  openModal() {
    const modal = document.getElementById("supabase-modal");
    if (modal) {
      modal.style.display = "flex";
      this.refreshStatus();
    }
  },

  closeModal() {
    const modal = document.getElementById("supabase-modal");
    if (modal) modal.style.display = "none";
    this.hideMessages();
  },

  async copySchemaSQL() {
    if (!this.schemaSql) {
      await this.fetchSchema();
    }

    try {
      await navigator.clipboard.writeText(this.schemaSql);
      const btn = document.getElementById("btn-copy-schema");
      if (btn) {
        const orig = btn.innerHTML;
        btn.innerHTML = "✅ Copied to Clipboard!";
        btn.classList.add("btn-primary");
        setTimeout(() => {
          btn.innerHTML = orig;
          btn.classList.remove("btn-primary");
        }, 2500);
      }
      if (window.App && App.showToast) {
        App.showToast("📋 Schema SQL copied to clipboard! Paste it into Supabase SQL Editor.");
      }
    } catch (err) {
      alert("Could not copy automatically. Please open 'View SQL Code' and copy manually.");
    }
  },

  toggleSchemaPreview() {
    const box = document.getElementById("supabase-schema-preview");
    if (box) {
      box.style.display = box.style.display === "none" ? "block" : "none";
    }
  },

  async testAndConnect() {
    this.hideMessages();
    const urlInput = document.getElementById("supabase-input-url");
    const keyInput = document.getElementById("supabase-input-key");
    const connectBtn = document.getElementById("supabase-btn-connect");

    const url = (urlInput ? urlInput.value : "").trim();
    const key = (keyInput ? keyInput.value : "").trim();

    if (!url || !key) {
      this.showError("Please enter both your Supabase Project URL and API Key.");
      return;
    }

    const origText = connectBtn.innerHTML;
    connectBtn.innerHTML = "⏳ Connecting...";
    connectBtn.disabled = true;

    try {
      const apiBase = window.API_BASE || "";
      const res = await fetch(apiBase + "/api/supabase/connect", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ supabase_url: url, supabase_key: key }),
      });

      const data = await res.json();
      if (!res.ok) {
        const detail = data.detail || {};
        this.showError(detail.message || "Failed to connect to Supabase. Check credentials.");
        return;
      }

      if (data.code === "TABLES_MISSING") {
        this.showError(
          "Connected to your Supabase project, but tables are missing! Click 'Copy SQL Schema Script' above and run it in your Supabase SQL Editor."
        );
      } else {
        const sync = data.sync || {};
        this.showSuccess(
          `Connected to Supabase! Initial sync completed: ${sync.nodes_synced || 0} nodes, ${sync.objects_synced || 0} objects, and ${sync.replicas_synced || 0} replicas synced.`
        );
        if (window.App && App.showToast) {
          App.showToast("☁ Successfully connected & synced to Supabase Cloud!");
        }
      }

      await this.refreshStatus();
    } catch (err) {
      this.showError("Network error contacting server: " + err.message);
    } finally {
      connectBtn.innerHTML = origText;
      connectBtn.disabled = false;
    }
  },

  async syncNow() {
    this.hideMessages();
    const syncBtn = document.getElementById("supabase-btn-sync");
    const origText = syncBtn.innerHTML;
    syncBtn.innerHTML = "⏳ Syncing...";
    syncBtn.disabled = true;

    try {
      const apiBase = window.API_BASE || "";
      const res = await fetch(apiBase + "/api/supabase/sync", { method: "POST" });
      const data = await res.json();
      if (!res.ok) {
        this.showError(data.detail || "Manual sync failed.");
        return;
      }
      this.showSuccess(
        `Sync Complete: ${data.nodes_synced} nodes, ${data.objects_synced} files, ${data.replicas_synced} replicas pushed to Supabase.`
      );
      if (window.App && App.showToast) {
        App.showToast(`☁ Synced ${data.objects_synced} files and ${data.nodes_synced} nodes to Supabase!`);
      }
      await this.refreshStatus();
    } catch (err) {
      this.showError("Failed to trigger sync: " + err.message);
    } finally {
      syncBtn.innerHTML = origText;
      syncBtn.disabled = false;
    }
  },

  async disconnect() {
    if (!confirm("Are you sure you want to disconnect Supabase cloud sync? Your local files will stay safe.")) {
      return;
    }
    this.hideMessages();
    try {
      const apiBase = window.API_BASE || "";
      const res = await fetch(apiBase + "/api/supabase/disconnect", { method: "POST" });
      if (res.ok) {
        const keyInput = document.getElementById("supabase-input-key");
        if (keyInput) keyInput.value = "";
        this.showSuccess("Disconnected from Supabase. Cluster is running in local SQLite mode.");
        if (window.App && App.showToast) {
          App.showToast("Supabase cloud sync disconnected.");
        }
        await this.refreshStatus();
      }
    } catch (err) {
      this.showError("Failed to disconnect: " + err.message);
    }
  },

  showError(msg) {
    const el = document.getElementById("supabase-error-msg");
    if (el) {
      el.textContent = msg;
      el.style.display = "block";
    }
  },

  showSuccess(msg) {
    const el = document.getElementById("supabase-success-msg");
    if (el) {
      el.textContent = msg;
      el.style.display = "block";
    }
  },

  hideMessages() {
    const err = document.getElementById("supabase-error-msg");
    const succ = document.getElementById("supabase-success-msg");
    if (err) err.style.display = "none";
    if (succ) succ.style.display = "none";
  },
};

window.SupabaseUI = SupabaseUI;
document.addEventListener("DOMContentLoaded", () => {
  SupabaseUI.init();
});
