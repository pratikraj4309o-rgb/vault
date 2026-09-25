/**
 * Unified Authentication & Admin Controller
 * Handles user authentication and privileged cluster session management.
 */
const AuthUI = {
  token: localStorage.getItem("vault_auth_token") || null,
  isAdmin: localStorage.getItem("vault_is_admin") === "true",
  currentUser: null,
  activeTab: "login",

  async init() {
    if (this.token) {
      await this.fetchCurrentUser();
    } else {
      this.updateHeader();
    }
  },

  async fetchCurrentUser() {
    if (!this.token) return;
    try {
      const res = await fetch("/api/auth/user", {
        headers: { Authorization: `Bearer ${this.token}` },
      });
      if (res.ok) {
        const data = await res.json();
        this.currentUser = data.user;
        this.isAdmin = !!data.is_admin;
        if (this.isAdmin) {
          localStorage.setItem("vault_is_admin", "true");
        } else {
          localStorage.removeItem("vault_is_admin");
        }
      } else {
        // Token expired or invalid
        this.token = null;
        this.currentUser = null;
        this.isAdmin = false;
        localStorage.removeItem("vault_auth_token");
        localStorage.removeItem("vault_is_admin");
      }
    } catch (err) {
      console.warn("Could not verify session:", err);
    }
    this.updateHeader();
  },

  updateHeader() {
    const btn = document.getElementById("open-auth-modal-btn");
    const text = document.getElementById("auth-header-text");
    const icon = document.getElementById("auth-header-icon");
    const adminBadge = document.getElementById("header-admin-badge");

    if (adminBadge) {
      adminBadge.style.display = this.isAdmin ? "inline-flex" : "none";
    }

    const headerAvatar = document.getElementById("auth-header-avatar");
    const sidebarAvatar = document.getElementById("sidebar-avatar-circle");
    const sidebarName = document.getElementById("sidebar-user-name");
    const sidebarSub = document.getElementById("sidebar-user-sub");

    if (this.isAdmin) {
      btn.classList.add("logged-in");
      text.textContent = "Admin";
      if (icon) icon.textContent = "👑";
      btn.title = "Cluster Administrator Access";
      if (headerAvatar) headerAvatar.textContent = "👑";
      if (sidebarAvatar) sidebarAvatar.textContent = "👑";
      if (sidebarName) sidebarName.textContent = "Administrator";
      if (sidebarSub) sidebarSub.textContent = "admin@vault.local";
    } else if (this.currentUser) {
      btn.classList.add("logged-in");
      const shortName = this.currentUser.email.split("@")[0];
      text.textContent = shortName;
      if (icon) icon.textContent = "👤";
      btn.title = `Logged in as ${this.currentUser.email}`;
      const initials = shortName.slice(0, 2).toUpperCase();
      if (headerAvatar) headerAvatar.textContent = initials;
      if (sidebarAvatar) sidebarAvatar.textContent = initials;
      if (sidebarName) sidebarName.textContent = shortName;
      if (sidebarSub) sidebarSub.textContent = this.currentUser.email;
    } else {
      btn.classList.remove("logged-in");
      text.textContent = "Sign In";
      if (icon) icon.textContent = "👤";
      btn.title = "Sign In or Register with Supabase";
      if (headerAvatar) headerAvatar.textContent = "JD";
      if (sidebarAvatar) sidebarAvatar.textContent = "JD";
      if (sidebarName) sidebarName.textContent = "User Account";
      if (sidebarSub) sidebarSub.textContent = "Sign In / Admin";
    }

    // Toggle My Files navigation tab (Admin only)
    const navFilesBtn = document.getElementById("nav-tab-files");
    if (navFilesBtn) {
      navFilesBtn.style.display = this.isAdmin ? "inline-flex" : "none";
    }

    // Toggle Overview tab files section
    const overviewLocked = document.getElementById("overview-files-locked-banner");
    const overviewTable = document.getElementById("overview-files-table-wrapper");
    if (overviewLocked) overviewLocked.style.display = this.isAdmin ? "none" : "block";
    if (overviewTable) overviewTable.style.display = this.isAdmin ? "block" : "none";

    // Toggle Tab 2 locked banner
    const filesTabLocked = document.getElementById("files-tab-locked-banner");
    const filesTabContent = document.getElementById("files-tab-admin-content");
    if (filesTabLocked) filesTabLocked.style.display = this.isAdmin ? "none" : "block";
    if (filesTabContent) filesTabContent.style.display = this.isAdmin ? "block" : "none";

    // If non-admin is currently on the files tab, switch to overview tab
    if (!this.isAdmin && window.App && App.activeTab === "files") {
      App.switchTab("overview");
    }
  },

  openModal(tab = "login") {
    const modal = document.getElementById("auth-modal");
    if (!modal) return;
    modal.style.display = "flex";
    this.hideMessages();

    if (this.currentUser || this.isAdmin) {
      this.showLoggedInView();
    } else {
      this.switchTab(tab);
    }
  },

  closeModal() {
    const modal = document.getElementById("auth-modal");
    if (modal) modal.style.display = "none";
    this.hideMessages();
  },

  switchTab(tab) {
    this.activeTab = tab;
    this.hideMessages();

    const loggedInView = document.getElementById("auth-logged-in-view");
    const formView = document.getElementById("auth-form-view");

    if (loggedInView) loggedInView.style.display = "none";
    if (formView) formView.style.display = "block";

    const tabLogin = document.getElementById("auth-tab-login");
    const tabSignup = document.getElementById("auth-tab-signup");
    const submitBtn = document.getElementById("auth-submit-btn");
    const togglePrompt = document.getElementById("auth-toggle-prompt");

    if (tab === "login") {
      if (tabLogin) tabLogin.classList.add("active");
      if (tabSignup) tabSignup.classList.remove("active");
      if (submitBtn) submitBtn.textContent = "Sign In";
      if (togglePrompt) {
        togglePrompt.innerHTML = `Don't have an account? <a href="#" class="text-link" onclick="AuthUI.switchTab('signup'); return false;">Sign Up</a>`;
      }
    } else {
      if (tabLogin) tabLogin.classList.remove("active");
      if (tabSignup) tabSignup.classList.add("active");
      if (submitBtn) submitBtn.textContent = "Create Account";
      if (togglePrompt) {
        togglePrompt.innerHTML = `Already have an account? <a href="#" class="text-link" onclick="AuthUI.switchTab('login'); return false;">Sign In</a>`;
      }
    }
  },

  async showLoggedInView() {
    const loggedInView = document.getElementById("auth-logged-in-view");
    const formView = document.getElementById("auth-form-view");
    if (formView) formView.style.display = "none";

    if (loggedInView) {
      loggedInView.style.display = "block";
      const emailEl = document.getElementById("auth-profile-email");
      const idEl = document.getElementById("auth-profile-id");
      const adminRoleBadge = document.getElementById("auth-profile-admin-badge");
      const subtext = document.getElementById("auth-profile-subtext");
      const adminPanel = document.getElementById("admin-supabase-panel");

      if (emailEl) emailEl.textContent = this.currentUser ? this.currentUser.email : (this.isAdmin ? "admin@vault.local" : "");
      if (idEl) idEl.textContent = this.currentUser ? this.currentUser.id : (this.isAdmin ? "admin-root" : "");
      if (adminRoleBadge) adminRoleBadge.style.display = this.isAdmin ? "inline-block" : "none";
      if (subtext) {
        subtext.textContent = this.isAdmin ? "● Administrator Privileges Active" : "● Active Supabase Session";
        subtext.style.color = this.isAdmin ? "var(--status-amber)" : "var(--status-green)";
      }

      // Option 2: Show Supabase Cloud panel only if admin
      if (adminPanel) {
        if (this.isAdmin) {
          adminPanel.style.display = "block";
          this.refreshAdminSupabaseStatus();
        } else {
          adminPanel.style.display = "none";
        }
      }
    }
  },

  async refreshAdminSupabaseStatus() {
    try {
      const res = await fetch("/api/supabase/status");
      if (!res.ok) return;
      const data = await res.json();
      const pill = document.getElementById("admin-supabase-status-pill");
      const summary = document.getElementById("admin-supabase-summary");

      if (pill) {
        if (data.connected) {
          pill.textContent = "● Connected";
          pill.style.background = "var(--status-green-bg)";
          pill.style.color = "var(--status-green)";
        } else if (data.configured) {
          pill.textContent = "● Offline";
          pill.style.background = "var(--status-amber-bg)";
          pill.style.color = "var(--status-amber)";
        } else {
          pill.textContent = "● Disconnected";
          pill.style.background = "var(--bg-subtle)";
          pill.style.color = "var(--text-muted)";
        }
      }

      if (summary) {
        if (data.connected) {
          const stats = data.stats || {};
          const n = stats.nodes !== undefined ? stats.nodes : 7;
          const o = stats.objects !== undefined ? stats.objects : 0;
          summary.textContent = `Connected to cloud: ${n} storage nodes, ${o} objects synchronized to PostgreSQL & Storage.`;
        } else {
          summary.textContent = "Supabase cloud sync is currently offline. Operating in local mode.";
        }
      }
    } catch (e) {
      console.warn("Could not check admin supabase status:", e);
    }
  },

  async handleSubmit() {
    this.hideMessages();
    const emailInput = document.getElementById("auth-input-email");
    const passInput = document.getElementById("auth-input-password");
    const submitBtn = document.getElementById("auth-submit-btn");

    const email = (emailInput ? emailInput.value : "").trim();
    const password = (passInput ? passInput.value : "").trim();

    if (!email || !password) {
      this.showError("Please enter both email and password.");
      return;
    }

    const origText = submitBtn.textContent;
    submitBtn.textContent = "⏳ Processing...";
    submitBtn.disabled = true;

    try {
      const endpoint = this.activeTab === "login" ? "/api/auth/login" : "/api/auth/signup";
      const res = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });

      const data = await res.json();
      if (!res.ok) {
        const detail = data.detail || "Authentication failed.";
        this.showError(typeof detail === "string" ? detail : (detail.message || "Failed to authenticate."));
        return;
      }

      if (this.activeTab === "signup") {
        if (data.requires_confirmation) {
          this.showSuccess(
            "Account registered! Please check your email to confirm, or turn off 'Confirm email' in Supabase to log in immediately."
          );
        } else if (data.access_token) {
          this.token = data.access_token;
          this.currentUser = data.user;
          this.isAdmin = false;
          localStorage.setItem("vault_auth_token", this.token);
          localStorage.removeItem("vault_is_admin");
          this.updateHeader();
          this.showLoggedInView();
          if (window.App && App.showToast) {
            App.showToast(`🎉 Welcome to NexStore VAULT, ${this.currentUser.email}!`);
          }
        } else {
          this.showSuccess(data.message || "Registration successful! You can now sign in.");
          this.switchTab("login");
        }
      } else {
        // Logged in successfully
        this.token = data.access_token;
        this.currentUser = data.user;
        this.isAdmin = !!data.is_admin;

        localStorage.setItem("vault_auth_token", this.token);
        if (this.isAdmin) {
          localStorage.setItem("vault_is_admin", "true");
        } else {
          localStorage.removeItem("vault_is_admin");
        }

        this.updateHeader();
        this.showLoggedInView();

        if (window.App && App.showToast) {
          if (this.isAdmin) {
            App.showToast("👑 Administrator Privileges Granted!");
          } else {
            App.showToast(`👋 Welcome back, ${this.currentUser.email}!`);
          }
        }
        if (window.App && App.refreshAll) {
          App.refreshAll();
        }
      }
    } catch (err) {
      this.showError("Network error: " + err.message);
    } finally {
      submitBtn.textContent = origText;
      submitBtn.disabled = false;
    }
  },

  async handleLogout() {
    try {
      if (this.token) {
        await fetch("/api/auth/logout", {
          method: "POST",
          headers: { Authorization: `Bearer ${this.token}` },
        });
      }
    } catch (e) {
      // Ignore network errors on logout
    }

    this.token = null;
    this.currentUser = null;
    this.isAdmin = false;
    localStorage.removeItem("vault_auth_token");
    localStorage.removeItem("vault_is_admin");
    this.updateHeader();
    this.switchTab("login");
    if (window.App && App.refreshAll) {
      App.refreshAll();
    }
    if (window.App && App.showToast) {
      App.showToast("Signed out successfully.");
    }
  },

  showError(msg) {
    const el = document.getElementById("auth-error-msg");
    if (el) {
      el.textContent = msg;
      el.style.display = "block";
    }
  },

  showSuccess(msg) {
    const el = document.getElementById("auth-success-msg");
    if (el) {
      el.textContent = msg;
      el.style.display = "block";
    }
  },

  hideMessages() {
    const err = document.getElementById("auth-error-msg");
    const succ = document.getElementById("auth-success-msg");
    if (err) err.style.display = "none";
    if (succ) succ.style.display = "none";
  },
};

window.AuthUI = AuthUI;
document.addEventListener("DOMContentLoaded", () => {
  AuthUI.init();
});
