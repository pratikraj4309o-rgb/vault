/**
 * Centralized API Client for NexStore VAULT Distributed Object Storage System.
 * All communication with the FastAPI backend passes through this module.
 */
const API_BASE = (function () {
  if (typeof window !== 'undefined') {
    if (window.location.protocol === 'file:') return 'http://127.0.0.1:8000';
    if (
      (window.location.hostname === '127.0.0.1' || window.location.hostname === 'localhost') &&
      window.location.port &&
      window.location.port !== '8000'
    ) {
      return 'http://127.0.0.1:8000';
    }
  }
  return '';
})();
window.API_BASE = API_BASE;

const api = {
  async _request(path, options = {}) {
    const headers = options.headers || {};
    if (!(options.body instanceof FormData) && !headers['Content-Type']) {
      headers['Content-Type'] = 'application/json';
    }
    headers['Accept'] = 'application/json';

    const token = localStorage.getItem('vault_auth_token');
    if (token && !headers['Authorization']) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    const fullPath = path.startsWith('http') ? path : (window.API_BASE || '') + path;
    const response = await fetch(fullPath, {
      ...options,
      headers,
    });

    if (!response.ok) {
      let errPayload = {};
      const rawText = await response.text();
      try {
        errPayload = JSON.parse(rawText);
      } catch (_) {
        errPayload = { detail: rawText || `HTTP ${response.status}` };
      }
      let msg = errPayload.detail || errPayload.error || errPayload.message;
      if (typeof msg === 'object') {
        if (Array.isArray(msg)) {
          msg = msg.map(m => (m && (m.msg || m.message)) || JSON.stringify(m)).join('; ');
        } else {
          msg = msg.msg || msg.message || JSON.stringify(msg);
        }
      }
      if (!msg) {
        msg = `HTTP ${response.status}: Request failed`;
      }
      const error = new Error(String(msg));
      error.status = response.status;
      error.payload = errPayload;
      throw error;
    }

    return response.json();
  },

  getHealth() {
    return this._request('/api/health');
  },

  getStats() {
    return this._request('/api/system/stats');
  },

  getSettings() {
    return this._request('/api/system/settings');
  },

  updateSettings(settingsData) {
    return this._request('/api/system/settings', {
      method: 'POST',
      body: JSON.stringify(settingsData),
    });
  },

  getActivity(limit = 60) {
    return this._request(`/api/activity?limit=${limit}`);
  },

  getNodes() {
    return this._request('/api/nodes');
  },

  getNode(nodeId) {
    return this._request(`/api/nodes/${encodeURIComponent(nodeId)}`);
  },

  provisionNode(reason = 'Manual cluster auto-scale') {
    return this._request('/api/nodes/provision', {
      method: 'POST',
      body: JSON.stringify({ reason }),
    });
  },

  decommissionNode(nodeId) {
    return this._request(`/api/nodes/${encodeURIComponent(nodeId)}`, {
      method: 'DELETE',
    });
  },

  failNode(nodeId, autoRepair = true, forceAutoscale = false) {
    return this._request(
      `/api/nodes/${encodeURIComponent(nodeId)}/fail?auto_repair=${autoRepair}&force_autoscale=${forceAutoscale}`,
      {
        method: 'POST',
      }
    );
  },

  restoreNode(nodeId) {
    return this._request(`/api/nodes/${encodeURIComponent(nodeId)}/restore`, {
      method: 'POST',
    });
  },

  partitionNode(nodeId) {
    return this._request(`/api/nodes/${encodeURIComponent(nodeId)}/partition`, {
      method: 'POST',
    });
  },

  reconnectNode(nodeId) {
    return this._request(`/api/nodes/${encodeURIComponent(nodeId)}/reconnect`, {
      method: 'POST',
    });
  },

  getFiles() {
    return this._request('/api/files');
  },

  getFileMetadata(objectId) {
    return this._request(`/api/files/${encodeURIComponent(objectId)}/metadata`);
  },

  getFileReplicas(objectId) {
    return this._request(`/api/files/${encodeURIComponent(objectId)}/replicas`);
  },

  uploadFile(file, replicationFactor = null, objectId = null, expectedVersion = null) {
    const formData = new FormData();
    formData.append('file', file);
    if (replicationFactor !== null && replicationFactor !== '') {
      formData.append('replication_factor', String(replicationFactor));
    }
    if (objectId) {
      formData.append('object_id', objectId);
    }
    if (expectedVersion !== null && expectedVersion !== '') {
      formData.append('expected_version', String(expectedVersion));
    }
    return this._request('/api/files/upload', {
      method: 'POST',
      body: formData,
    });
  },

  deleteFile(objectId) {
    return this._request(`/api/files/${encodeURIComponent(objectId)}`, {
      method: 'DELETE',
    });
  },

  verifyObject(objectId, queueRepair = true) {
    return this._request(`/api/files/${encodeURIComponent(objectId)}/verify?queue_repair=${queueRepair}`, {
      method: 'POST',
    });
  },

  corruptReplica(objectId, nodeId = null, autoRepair = false) {
    return this._request(`/api/files/${encodeURIComponent(objectId)}/corrupt`, {
      method: 'POST',
      body: JSON.stringify({
        node_id: nodeId,
        auto_repair: autoRepair,
      }),
    });
  },

  getReplicas() {
    return this._request('/api/replicas');
  },

  getRepairs() {
    return this._request('/api/repairs');
  },

  runRepairs() {
    return this._request('/api/repairs/run', {
      method: 'POST',
    });
  },

  retryRepair(repairId) {
    return this._request(`/api/repairs/${encodeURIComponent(repairId)}/retry`, {
      method: 'POST',
    });
  },

  startRebalance() {
    return this._request('/api/rebalance', {
      method: 'POST',
    });
  },

  getRebalanceStatus() {
    return this._request('/api/rebalance/status');
  },

  scanIntegrity() {
    return this._request('/api/integrity/scan', {
      method: 'POST',
    });
  },
};

window.api = api;
