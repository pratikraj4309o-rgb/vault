/**
 * Integrity Center View: Displays Expected SHA-256 vs Actual SHA-256 for every replica and provides cluster-wide integrity scanning.
 */
const IntegrityUI = {
  render(replicas = []) {
    const tbody = document.getElementById('integrity-table-tbody');
    if (!tbody) return;

    if (!replicas || replicas.length === 0) {
      tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;padding:24px;color:var(--text-muted)">No replicas to verify yet. Upload an object first.</td></tr>`;
      return;
    }

    tbody.innerHTML = replicas
      .map((r) => {
        const isCorrupted = r.status === 'CORRUPTED';
        const isHealthy = r.status === 'HEALTHY' && r.node_status === 'ONLINE';
        const expectedSha = r.expected_checksum || r.checksum;
        const actualSha = isCorrupted
          ? 'e3b0c44298fc1c149afbf4c8996fb924... [BITROT_TAMPERED]'
          : r.checksum;

        const badgeHtml = isCorrupted
          ? `<span class="badge badge-mismatch">⚠ CHECKSUM MISMATCH</span>`
          : isHealthy
          ? `<span class="badge badge-verified">✓ VERIFIED</span>`
          : `<span class="badge badge-degraded">${r.status} (${r.node_status})</span>`;

        return `
          <tr>
            <td><strong>${AppUtils.escapeHtml(r.filename || r.object_id)}</strong></td>
            <td><span class="mono-code">${r.node_id.toUpperCase()}</span> (${r.replica_id})</td>
            <td><span class="mono-code">${expectedSha.slice(0, 24)}...</span></td>
            <td><span class="mono-code" style="color:${isCorrupted ? 'var(--accent-rose)' : 'var(--accent-emerald)'}">${actualSha.slice(0, 28)}...</span></td>
            <td>${badgeHtml}</td>
            <td>
              <div style="display:flex;gap:6px">
                <button class="btn btn-sm btn-success" onclick="FilesUI.verifyObject('${r.object_id}')">Verify SHA-256</button>
                <button class="btn btn-sm btn-warning" onclick="FilesUI.corruptObject('${r.object_id}', '${r.node_id}')">Corrupt Replica</button>
              </div>
            </td>
          </tr>
        `;
      })
      .join('');
  },

  async triggerClusterScan() {
    try {
      const res = await api.scanIntegrity();
      AppUtils.toast(
        `Integrity Scan Complete: ${res.scanned_objects} object(s) verified, ${res.corrupted_replicas_detected} corruption(s) detected.`,
        res.corrupted_replicas_detected > 0 ? 'warning' : 'success'
      );
      await App.refreshAll();
    } catch (err) {
      AppUtils.toast(err.message, 'error');
    }
  },
};

window.IntegrityUI = IntegrityUI;
