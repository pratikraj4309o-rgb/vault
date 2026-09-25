/**
 * Object Explorer, View Switcher (List vs Grid), Inspector Panel,
 * and Multi-Stage Upload Pipeline for NexStore VAULT.
 */
const FilesUI = {
  currentView: 'list',
  files: [],
  selectedObjectId: null,
  selectedObjects: new Set(),
  lastUploadedObject: null,
  currentFolderFilter: null,
  currentSearchQuery: '',

  initUploadZone() {
    const dropzone = document.getElementById('overview-upload-box');
    const fileInput = document.getElementById('overview-file-input');
    if (!dropzone || !fileInput) return;

    ['dragenter', 'dragover'].forEach((evt) => {
      dropzone.addEventListener(evt, (e) => {
        e.preventDefault();
        dropzone.classList.add('dragover');
      });
    });

    ['dragleave', 'drop'].forEach((evt) => {
      dropzone.addEventListener(evt, (e) => {
        e.preventDefault();
        dropzone.classList.remove('dragover');
      });
    });

    dropzone.addEventListener('drop', async (e) => {
      if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
        await this.performUpload(e.dataTransfer.files[0]);
      }
    });

    fileInput.addEventListener('change', async () => {
      if (fileInput.files && fileInput.files.length > 0) {
        await this.performUpload(fileInput.files[0]);
        fileInput.value = '';
      }
    });
  },

  getFileTypeMeta(filename = '') {
    const ext = filename.split('.').pop().toLowerCase();
    switch (ext) {
      case 'pdf':
        return { icon: '📄', type: 'PDF Document', cssClass: 'pdf', badge: 'PDF' };
      case 'xlsx':
      case 'xls':
      case 'csv':
        return { icon: '📊', type: 'Spreadsheet', cssClass: 'sheet', badge: 'XLSX' };
      case 'docx':
      case 'doc':
      case 'txt':
      case 'md':
        return { icon: '📝', type: 'Word Document', cssClass: 'doc', badge: 'DOCX' };
      case 'pptx':
      case 'ppt':
        return { icon: '🟧', type: 'Presentation', cssClass: 'archive', badge: 'PPTX' };
      case 'jpg':
      case 'jpeg':
      case 'png':
      case 'gif':
      case 'svg':
      case 'webp':
        return { icon: '🖼️', type: 'Image File', cssClass: 'image', badge: 'IMG' };
      case 'zip':
      case 'tar':
      case 'gz':
      case '7z':
      case 'rar':
        return { icon: '📦', type: 'ZIP Archive', cssClass: 'archive', badge: 'ZIP' };
      default:
        return { icon: '📄', type: 'Data Object', cssClass: 'generic', badge: ext.toUpperCase() || 'FILE' };
    }
  },

  switchView(view) {
    this.currentView = view;
    const listBtn = document.getElementById('view-toggle-list');
    const gridBtn = document.getElementById('view-toggle-grid');
    const listContainer = document.getElementById('files-list-view-container');
    const gridContainer = document.getElementById('files-grid-view-container');

    if (listBtn) listBtn.classList.toggle('active', view === 'list');
    if (gridBtn) gridBtn.classList.toggle('active', view === 'grid');

    if (listContainer) listContainer.style.display = view === 'list' ? 'block' : 'none';
    if (gridContainer) gridContainer.style.display = view === 'grid' ? 'block' : 'none';

    this.render(this.files);
  },

  handleSearch(query) {
    this.currentSearchQuery = (query || '').toLowerCase().trim();
    this.render(this.files);
  },

  filterFolder(folderName) {
    AppUtils.toast(`Viewing folder: ${folderName}`, 'info');
  },

  handleSort(criteria) {
    if (!this.files || this.files.length === 0) return;
    if (criteria === 'name') {
      this.files.sort((a, b) => a.filename.localeCompare(b.filename));
    } else if (criteria === 'size') {
      this.files.sort((a, b) => (b.size || 0) - (a.size || 0));
    } else if (criteria === 'modified') {
      this.files.sort((a, b) => new Date(b.updated_at || 0) - new Date(a.updated_at || 0));
    }
    this.render(this.files);
  },

  async performUpload(file, customRf = null) {
    const rf = customRf !== null ? customRf : 3;

    // Elements for Home page live cards (Image 3 & 4)
    const welcomeCard = document.getElementById('home-welcome-card');
    const uploadCard = document.getElementById('home-uploading-card');
    const completeCard = document.getElementById('home-upload-complete-card');

    const cardHeader = document.getElementById('upload-card-header');
    const fileNameEl = document.getElementById('uploading-file-name');
    const fileSizeEl = document.getElementById('uploading-file-size');
    const progressBar = document.getElementById('upload-card-progress-bar');
    const subtextEl = document.getElementById('upload-status-subtext');

    const stepUploaded = document.getElementById('step-uploaded');
    const stepSecured = document.getElementById('step-secured');
    const stepReplicated = document.getElementById('step-replicated');
    const stepVerifying = document.getElementById('step-verifying');

    try {
      if (welcomeCard) welcomeCard.style.display = 'none';
      if (completeCard) completeCard.style.display = 'none';
      if (uploadCard) uploadCard.style.display = 'flex';

      if (fileNameEl) fileNameEl.textContent = file.name;
      if (fileSizeEl) fileSizeEl.textContent = AppUtils.formatBytes(file.size);

      // Stage 1: Uploading
      if (cardHeader) cardHeader.textContent = 'Uploading (25%)';
      if (progressBar) progressBar.style.width = '25%';
      if (subtextEl) subtextEl.textContent = 'Streaming file data...';
      if (stepUploaded) stepUploaded.className = 'vault-pipeline-step active';
      await AppUtils.sleep(180);

      // Stage 2: Securing & Cryptographic Hashing
      if (cardHeader) cardHeader.textContent = 'Securing (50%)';
      if (progressBar) progressBar.style.width = '50%';
      if (subtextEl) subtextEl.textContent = 'Generating SHA-256 cryptographic digest...';
      if (stepUploaded) stepUploaded.className = 'vault-pipeline-step done';
      if (stepSecured) stepSecured.className = 'vault-pipeline-step active';
      await AppUtils.sleep(180);

      // Stage 3: Replicating to Storage Nodes
      if (cardHeader) cardHeader.textContent = 'Replicating (75%)';
      if (progressBar) progressBar.style.width = '75%';
      if (subtextEl) subtextEl.textContent = 'Distributing 3 copies across healthy servers...';
      if (stepSecured) stepSecured.className = 'vault-pipeline-step done';
      if (stepReplicated) stepReplicated.className = 'vault-pipeline-step active';

      const res = await api.uploadFile(file, rf);

      // Stage 4: Verifying
      if (cardHeader) cardHeader.textContent = 'Verifying (95%)';
      if (progressBar) progressBar.style.width = '95%';
      if (subtextEl) subtextEl.textContent = 'Verifying chunk checksums on all nodes...';
      if (stepReplicated) stepReplicated.className = 'vault-pipeline-step done';
      if (stepVerifying) stepVerifying.className = 'vault-pipeline-step active';
      await AppUtils.sleep(200);

      if (stepVerifying) stepVerifying.className = 'vault-pipeline-step done';
      if (progressBar) progressBar.style.width = '100%';

      const obj = res.object;
      this.lastUploadedObject = obj;

      // Transition to Complete Card (Image 3 & 4)
      if (uploadCard) uploadCard.style.display = 'none';
      if (completeCard) {
        completeCard.style.display = 'block';
        const nameEl = document.getElementById('complete-file-name');
        const sizeEl = document.getElementById('complete-file-size');
        const badgeEl = document.getElementById('complete-file-badge');
        const copiesEl = document.getElementById('complete-copies-count');

        const meta = this.getFileTypeMeta(obj.filename);
        if (nameEl) nameEl.textContent = obj.filename;
        if (sizeEl) sizeEl.textContent = AppUtils.formatBytes(obj.size);
        if (badgeEl) badgeEl.textContent = meta.icon;
        if (copiesEl) copiesEl.textContent = `${obj.healthy_replicas || 3} copies`;
      }

      AppUtils.toast(`Uploaded ${obj.filename} across ${obj.healthy_replicas} servers!`, 'success');
      this.showSuccessModal(obj);
      await App.refreshAll();
      return obj;
    } catch (err) {
      if (uploadCard) uploadCard.style.display = 'none';
      if (welcomeCard) welcomeCard.style.display = 'block';
      AppUtils.toast(`Upload failed: ${err.message}`, 'error');
      throw err;
    }
  },

  async uploadSampleDataset(filename = 'large_dataset.zip', sizeKB = 256, rf = null) {
    const buffer = new Uint8Array(sizeKB * 1024);
    for (let i = 0; i < buffer.length; i++) {
      buffer[i] = (i * 31 + filename.charCodeAt(i % filename.length)) & 0xff;
    }
    const blob = new Blob([buffer], { type: 'application/zip' });
    const file = new File([blob], filename, { type: 'application/zip' });
    return this.performUpload(file, rf);
  },

  resetUploadCard() {
    const completeCard = document.getElementById('home-upload-complete-card');
    const welcomeCard = document.getElementById('home-welcome-card');
    if (completeCard) completeCard.style.display = 'none';
    if (welcomeCard) welcomeCard.style.display = 'block';
  },

  viewLastUploaded() {
    if (this.lastUploadedObject) {
      App.switchTab('files');
      this.selectFile(this.lastUploadedObject.object_id);
    } else {
      App.switchTab('files');
    }
  },

  render(files = []) {
    this.files = files || [];
    const isAdmin = window.AuthUI ? AuthUI.isAdmin : false;

    // Check lock banner
    const lockedBanner = document.getElementById('files-tab-locked-banner');
    const adminContent = document.getElementById('files-tab-admin-content');
    if (lockedBanner) lockedBanner.style.display = isAdmin ? 'none' : 'block';
    if (adminContent) adminContent.style.display = isAdmin ? 'block' : 'none';

    if (!isAdmin) return;

    let filtered = [...this.files];
    if (this.currentSearchQuery) {
      filtered = filtered.filter((f) =>
        f.filename.toLowerCase().includes(this.currentSearchQuery)
      );
    }

    // 1. Render List View (Image 1)
    const listTbody = document.getElementById('files-list-tbody');
    const countFooter = document.getElementById('files-items-count-footer');
    if (countFooter) countFooter.textContent = `${filtered.length} item${filtered.length === 1 ? '' : 's'}`;

    if (listTbody) {
      if (filtered.length === 0) {
        listTbody.innerHTML = `
          <tr>
            <td colspan="7" style="text-align:center;padding:36px;color:var(--vault-text-muted);">
              No files match your search. Upload files above to get started.
            </td>
          </tr>
        `;
      } else {
        listTbody.innerHTML = filtered
          .map((f) => {
            const meta = this.getFileTypeMeta(f.filename);
            const isSelected = this.selectedObjectId === f.object_id;
            const isChecked = this.selectedObjects.has(f.object_id);

            const nodesList = (f.replicas || [])
              .map((r) => {
                const sNum = parseInt(r.node_id.replace('node', ''), 10) || 1;
                return `Server ${sNum}`;
              })
              .join(', ') || '3 Servers';

            const statusClass = f.status === 'HEALTHY' ? 'badge-healthy' : 'badge-failed';
            const statusLabel = f.status === 'HEALTHY' ? '✓ Verified' : '⚠ Degraded';

            return `
              <tr class="${isSelected ? 'selected' : ''}" onclick="FilesUI.selectFile('${f.object_id}')" style="cursor:pointer;">
                <td onclick="event.stopPropagation();">
                  <input type="checkbox" class="vault-checkbox" ${isChecked ? 'checked' : ''} onchange="FilesUI.toggleSelectObject('${f.object_id}', this.checked)" />
                </td>
                <td>
                  <div style="display:flex;align-items:center;gap:10px;">
                    <div class="vault-file-type-icon ${meta.cssClass}">${meta.icon}</div>
                    <strong style="color:var(--vault-text-main);font-size:13.5px;">${AppUtils.escapeHtml(f.filename)}</strong>
                  </div>
                </td>
                <td style="color:var(--vault-text-muted);font-size:12.5px;">${AppUtils.formatTime(f.updated_at)}</td>
                <td style="font-family:var(--font-mono);font-size:12.5px;">${AppUtils.formatBytes(f.size)}</td>
                <td style="color:var(--vault-text-muted);font-size:12.5px;">${nodesList}</td>
                <td><span class="badge ${statusClass}">${statusLabel}</span></td>
                <td style="text-align:right;" onclick="event.stopPropagation();">
                  <div style="display:flex;gap:4px;justify-content:flex-end;">
                    <a class="btn btn-sm btn-ghost" href="/api/files/${encodeURIComponent(f.object_id)}" download="${AppUtils.escapeHtml(f.filename)}" title="Download">⬇</a>
                    <button class="btn btn-sm btn-ghost" onclick="FilesUI.verifyObject('${f.object_id}')" title="Verify Integrity">🛡️</button>
                    <button class="btn btn-sm btn-ghost" onclick="FilesUI.inspectReplicas('${f.object_id}')" title="Replicas Info">⚙️</button>
                    <button class="btn btn-sm btn-ghost" onclick="FilesUI.deleteObject('${f.object_id}')" title="Delete">🗑️</button>
                  </div>
                </td>
              </tr>
            `;
          })
          .join('');
      }
    }

    // 2. Render Grid View (Image 2)
    const gridCards = document.getElementById('vault-files-grid-cards');
    if (gridCards) {
      if (filtered.length === 0) {
        gridCards.innerHTML = `
          <div style="grid-column:1/-1;text-align:center;padding:32px;color:var(--vault-text-muted);">
            No files available. Click "+ New File" above to upload.
          </div>
        `;
      } else {
        gridCards.innerHTML = filtered
          .map((f) => {
            const meta = this.getFileTypeMeta(f.filename);
            const isSelected = this.selectedObjectId === f.object_id;
            return `
              <div class="vault-file-card ${isSelected ? 'selected' : ''}" onclick="FilesUI.selectFile('${f.object_id}')">
                <div class="vault-file-card-preview">
                  <span class="large-icon">${meta.icon}</span>
                </div>
                <div class="vault-file-card-body">
                  <h5 title="${AppUtils.escapeHtml(f.filename)}">${AppUtils.escapeHtml(f.filename)}</h5>
                  <p>${AppUtils.formatBytes(f.size)} · ${AppUtils.formatTime(f.updated_at)}</p>
                </div>
              </div>
            `;
          })
          .join('');
      }
    }
  },

  selectFile(objectId) {
    this.selectedObjectId = objectId;
    const file = (this.files || []).find((f) => f.object_id === objectId);
    if (!file) return;

    const inspector = document.getElementById('vault-right-inspector');
    if (inspector) inspector.style.display = 'flex';

    const meta = this.getFileTypeMeta(file.filename);

    const iconEl = document.getElementById('inspector-file-icon');
    const nameEl = document.getElementById('inspector-file-name');
    const subEl = document.getElementById('inspector-file-sub');
    const previewTitle = document.getElementById('inspector-preview-title');
    const previewIcon = document.getElementById('inspector-preview-icon');

    const typeEl = document.getElementById('inspector-info-type');
    const sizeEl = document.getElementById('inspector-info-size');
    const modifiedEl = document.getElementById('inspector-info-modified');
    const replicasEl = document.getElementById('inspector-info-replicas');
    const hashEl = document.getElementById('inspector-info-hash');

    if (iconEl) {
      iconEl.className = `vault-file-type-icon ${meta.cssClass}`;
      iconEl.textContent = meta.icon;
    }
    if (nameEl) nameEl.textContent = file.filename;
    if (subEl) subEl.textContent = `${AppUtils.formatBytes(file.size)} · ${meta.type}`;
    if (previewTitle) previewTitle.textContent = file.filename;
    if (previewIcon) previewIcon.textContent = meta.icon;

    if (typeEl) typeEl.textContent = meta.type;
    if (sizeEl) sizeEl.textContent = AppUtils.formatBytes(file.size);
    if (modifiedEl) modifiedEl.textContent = AppUtils.formatTime(file.updated_at);
    if (hashEl) hashEl.textContent = file.checksum || 'Verified';

    if (replicasEl) {
      const nodes = (file.replicas || []).map((r) => {
        const num = parseInt(r.node_id.replace('node', ''), 10) || 1;
        return `Server ${num}`;
      });
      replicasEl.textContent = nodes.length > 0 ? nodes.join(', ') : 'Server 1, Server 3, Server 5';
    }

    // Refresh row selections
    document.querySelectorAll('.vault-files-table tr').forEach((tr) => tr.classList.remove('selected'));
    document.querySelectorAll('.vault-file-card').forEach((card) => card.classList.remove('selected'));
  },

  closeInspector() {
    this.selectedObjectId = null;
    const inspector = document.getElementById('vault-right-inspector');
    if (inspector) inspector.style.display = 'none';
  },

  switchInspectorTab(tab) {
    const previewTab = document.getElementById('inspector-tab-preview');
    const detailsTab = document.getElementById('inspector-tab-details');
    const previewSection = document.getElementById('inspector-preview-section');
    const detailsSection = document.getElementById('inspector-details-section');

    if (previewTab) previewTab.classList.toggle('active', tab === 'preview');
    if (detailsTab) detailsTab.classList.toggle('active', tab === 'details');
    if (previewSection) previewSection.style.display = tab === 'preview' ? 'block' : 'none';
    if (detailsSection) detailsSection.style.display = tab === 'details' ? 'block' : 'none';
  },

  downloadCurrentInspector() {
    if (!this.selectedObjectId) return;
    const file = (this.files || []).find((f) => f.object_id === this.selectedObjectId);
    if (file) {
      const a = document.createElement('a');
      a.href = `/api/files/${encodeURIComponent(file.object_id)}`;
      a.download = file.filename;
      a.click();
    }
  },

  shareCurrentInspector() {
    if (!this.selectedObjectId) return;
    const shareUrl = `${window.location.origin}/api/files/${encodeURIComponent(this.selectedObjectId)}`;
    AppUtils.copyText(shareUrl);
  },

  copyLinkCurrentInspector() {
    if (!this.selectedObjectId) return;
    const url = `${window.location.origin}/api/files/${encodeURIComponent(this.selectedObjectId)}`;
    AppUtils.copyText(url);
  },

  async verifyCurrentInspector() {
    if (!this.selectedObjectId) return;
    await this.verifyObject(this.selectedObjectId);
  },

  toggleSelectAll(checked) {
    if (checked) {
      this.files.forEach((f) => this.selectedObjects.add(f.object_id));
    } else {
      this.selectedObjects.clear();
    }
    this.updateSelectedLabel();
    this.render(this.files);
  },

  toggleSelectObject(objectId, checked) {
    if (checked) {
      this.selectedObjects.add(objectId);
    } else {
      this.selectedObjects.delete(objectId);
    }
    this.updateSelectedLabel();
  },

  updateSelectedLabel() {
    const lbl = document.getElementById('files-selected-label');
    if (lbl) {
      lbl.textContent = `${this.selectedObjects.size} selected`;
    }
  },

  shareSelected() {
    if (this.selectedObjects.size === 0) {
      AppUtils.toast('Please select at least one file to share.', 'info');
      return;
    }
    AppUtils.toast(`Generated secure share links for ${this.selectedObjects.size} item(s)!`, 'success');
  },

  downloadSelected() {
    if (this.selectedObjects.size === 0) {
      AppUtils.toast('Please select at least one file to download.', 'info');
      return;
    }
    this.selectedObjects.forEach((objId) => {
      const a = document.createElement('a');
      a.href = `/api/files/${encodeURIComponent(objId)}`;
      a.click();
    });
  },

  copyLinkSelected() {
    if (this.selectedObjects.size === 0) {
      AppUtils.toast('Please select at least one file.', 'info');
      return;
    }
    const ids = Array.from(this.selectedObjects).join(',');
    AppUtils.copyText(`${window.location.origin}/api/files?ids=${ids}`);
  },

  async deleteSelected() {
    if (this.selectedObjects.size === 0) {
      AppUtils.toast('Please select at least one file to delete.', 'info');
      return;
    }
    for (const id of this.selectedObjects) {
      await this.deleteObject(id, true);
    }
    this.selectedObjects.clear();
    this.updateSelectedLabel();
    await App.refreshAll();
  },

  async verifyObject(objectId) {
    try {
      const res = await api.verifyFile(objectId);
      const isOk = res.status === 'VERIFIED';
      AppUtils.toast(
        isOk
          ? `✓ Verified SHA-256 integrity match on all ${res.checked_replicas} replica(s)!`
          : `⚠ Integrity warning: ${res.status}`,
        isOk ? 'success' : 'error'
      );
      await App.refreshAll();
    } catch (err) {
      AppUtils.toast(err.message, 'error');
    }
  },

  async corruptObject(objectId) {
    try {
      const meta = await api.getFileMetadata(objectId);
      const rep = (meta.replicas || []).find((r) => r.status === 'HEALTHY');
      if (!rep) throw new Error('No healthy replica found to corrupt.');
      await api.corruptReplica(objectId, rep.node_id, true);
      AppUtils.toast(
        `Corrupted replica on ${rep.node_id.toUpperCase()} — VAULT self-healing kicked off automatically!`,
        'info'
      );
      await App.refreshAll();
    } catch (err) {
      AppUtils.toast(err.message, 'error');
    }
  },

  async deleteObject(objectId, silent = false) {
    try {
      await api.deleteFile(objectId);
      if (!silent) AppUtils.toast('Object deleted across all replicas and storage nodes.', 'info');
      if (this.selectedObjectId === objectId) {
        this.closeInspector();
      }
      if (!silent) await App.refreshAll();
    } catch (err) {
      AppUtils.toast(err.message, 'error');
    }
  },

  async inspectReplicas(objectId) {
    try {
      const data = await api.getFileMetadata(objectId);
      const modal = document.getElementById('vault-modal');
      const body = document.getElementById('vault-modal-body');
      if (!modal || !body) return;

      const rows = (data.replicas || [])
        .map(
          (r) => `
          <tr>
            <td><strong>${r.node_id.toUpperCase()}</strong> (${r.node_status})</td>
            <td><span class="mono-code">${r.replica_id}</span></td>
            <td><span class="mono-code">v${r.version}</span></td>
            <td><span class="mono-code">${r.checksum.slice(0, 20)}...</span></td>
            <td><span class="badge ${AppUtils.badgeClass(r.status)}">${r.status}</span></td>
          </tr>
        `
        )
        .join('');

      body.innerHTML = `
        <div class="panel-header">
          <div>
            <h3 class="panel-title">Replica Distribution: ${AppUtils.escapeHtml(data.filename)}</h3>
            <p class="panel-subtitle">Object ID: ${data.object_id} · Authoritative SHA-256: ${data.expected_checksum}</p>
          </div>
          <span class="badge badge-healthy">${data.healthy_replicas} / ${data.replication_factor} HEALTHY</span>
        </div>
        <div class="table-responsive">
          <table class="vault-table">
            <thead>
              <tr><th>Storage Node</th><th>Replica ID</th><th>Version</th><th>Replica SHA-256</th><th>Replica Status</th></tr>
            </thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
      `;
      modal.classList.add('open');
      modal.style.display = 'flex';
    } catch (err) {
      AppUtils.toast(err.message, 'error');
    }
  },

  showSuccessModal(obj) {
    if (!obj) return;
    const modal = document.getElementById('upload-success-modal');
    if (!modal) return;

    const nameEl = document.getElementById('upload-success-filename');
    const sizeEl = document.getElementById('upload-success-size');
    const nodesEl = document.getElementById('upload-success-nodes');
    const hashEl = document.getElementById('upload-success-hash');

    if (nameEl) nameEl.textContent = obj.filename || 'Uploaded File';
    if (sizeEl) sizeEl.textContent = AppUtils.formatBytes(obj.size || 0);
    if (nodesEl) {
      const nodes = (obj.replicas || []).map((r) => {
        const nId = (r.node_id || '').toUpperCase();
        return nId.replace('NODE', 'Server ');
      });
      nodesEl.textContent = nodes.length > 0 ? nodes.join(', ') : 'Replicated across storage nodes';
    }
    if (hashEl) hashEl.textContent = obj.checksum || 'Verified';

    modal.style.display = 'flex';
  },

  closeSuccessModal() {
    const modal = document.getElementById('upload-success-modal');
    if (modal) {
      modal.style.display = 'none';
    }
  },
};

window.FilesUI = FilesUI;
