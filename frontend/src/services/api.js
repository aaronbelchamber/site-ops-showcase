class APIClient {
    constructor() {
        this.baseUrl = "";
        this.tokenKey = "site_manager_api_token";

        // Allow local dev to bypass the login prompt when VITE_API_TOKEN is set in frontend/.env.local
        const envToken = import.meta.env.VITE_API_TOKEN;
        if (envToken && envToken.trim()) {
            try {
                localStorage.setItem(this.tokenKey, envToken.trim());
            } catch (error) {
                console.warn("Unable to persist API token to localStorage.", error);
            }
        }
    }

    getToken() {
        return localStorage.getItem(this.tokenKey) || "";
    }

    setToken(token) {
        localStorage.setItem(this.tokenKey, token);
    }

    clearToken() {
        localStorage.removeItem(this.tokenKey);
    }

    hasToken() {
        return !!this.getToken();
    }

    async request(endpoint, options = {}) {
        const url = `${this.baseUrl}${endpoint}`;
        
        // Setup headers
        const headers = new Headers(options.headers || {});
        if (!headers.has("Content-Type") && !(options.body instanceof FormData)) {
            headers.set("Content-Type", "application/json");
        }
        
        const token = this.getToken();
        if (token) {
            headers.set("Authorization", `Bearer ${token}`);
        }

        const config = {
            ...options,
            headers
        };

        try {
            const response = await fetch(url, config);
            
            // Handle HTTP errors
            if (response.status === 401) {
                this.clearToken();
                // Custom event to notify React App to show authentication guard
                window.dispatchEvent(new Event("unauthorized"));
                throw new Error("Unauthorized access. Token has been cleared.");
            }

            const json = await response.json();
            
            if (!response.ok || !json.success) {
                throw new Error(json.error || `HTTP error! status: ${response.status}`);
            }

            return json.data;
        } catch (error) {
            console.error("API Request failed:", error);
            throw error;
        }
    }

    // Site methods
    getSites() {
        return this.request("/api/sites");
    }

    getSite(siteName) {
        return this.request(`/api/sites/${siteName}`);
    }

    addSite(siteData) {
        return this.request("/api/sites", {
            method: "POST",
            body: JSON.stringify(siteData)
        });
    }

    updateSite(siteName, siteData) {
        return this.request(`/api/sites/${siteName}`, {
            method: "PUT",
            body: JSON.stringify(siteData)
        });
    }

    deleteSite(siteName) {
        return this.request(`/api/sites/${siteName}`, {
            method: "DELETE"
        });
    }

    // Backup methods
    getBackups(siteName) {
        return this.request(`/api/sites/${siteName}/backups`);
    }

    createBackup(siteName, description, includeMedia) {
        return this.request(`/api/sites/${siteName}/backups`, {
            method: "POST",
            body: JSON.stringify({ description, include_media: includeMedia })
        });
    }

    restoreBackup(siteName, backupId) {
        return this.request(`/api/sites/${siteName}/backups/${backupId}/restore`, {
            method: "POST"
        });
    }

    deleteBackup(siteName, backupId) {
        return this.request(`/api/sites/${siteName}/backups/${backupId}`, {
            method: "DELETE"
        });
    }

    // Health methods
    runHealthCheck(siteName) {
        return this.request(`/api/sites/${siteName}/health`);
    }

    getHealthHistory(siteName) {
        return this.request(`/api/sites/${siteName}/health/history`);
    }

    getLatestSnapshot(siteName) {
        return this.request(`/api/sites/${siteName}/health/latest`);
    }

    getHealthCheck(siteName, checkId) {
        return this.request(`/api/sites/${siteName}/health/${checkId}`);
    }

    async getScreenshotBlob(siteName, checkId, device) {
        const endpoint = `/api/sites/${siteName}/health/${checkId}/screenshot/${device}`;
        const url = `${this.baseUrl}${endpoint}`;
        const headers = new Headers();
        const token = this.getToken();
        if (token) {
            headers.set("Authorization", `Bearer ${token}`);
        }
        const response = await fetch(url, { headers });
        if (!response.ok) {
            throw new Error(`Failed to load screenshot: ${response.status}`);
        }
        return await response.blob();
    }


    // Update methods
    checkUpdates(siteName, force = false, isAsync = false) {
        const params = [];
        if (force) params.push("force=true");
        if (isAsync) params.push("async=true");
        const query = params.length > 0 ? `?${params.join("&")}` : "";
        return this.request(`/api/sites/${siteName}/updates${query}`);
    }

    triggerCheckUpdates(siteName) {
        return this.request(`/api/sites/${siteName}/updates/check`, {
            method: "POST"
        });
    }

    updateCore(siteName, major = false, createBackup = true, qualityChecks = true) {
        return this.request(`/api/sites/${siteName}/updates/core`, {
            method: "POST",
            body: JSON.stringify({ major, create_backup: createBackup, quality_checks: qualityChecks })
        });
    }

    updatePlugins(siteName, plugin = null, createBackup = true, qualityChecks = true) {
        return this.request(`/api/sites/${siteName}/updates/plugins`, {
            method: "POST",
            body: JSON.stringify({ plugin, create_backup: createBackup, quality_checks: qualityChecks })
        });
    }

    updateThemes(siteName, theme = null, createBackup = true, qualityChecks = true) {
        return this.request(`/api/sites/${siteName}/updates/themes`, {
            method: "POST",
            body: JSON.stringify({ theme, create_backup: createBackup, quality_checks: qualityChecks })
        });
    }

    updateAll(siteName, createBackup = true, qualityChecks = true) {
        return this.request(`/api/sites/${siteName}/updates/all`, {
            method: "POST",
            body: JSON.stringify({ create_backup: createBackup, quality_checks: qualityChecks })
        });
    }

    getUpdateHistory(siteName) {
        return this.request(`/api/sites/${siteName}/updates/history`);
    }

    // System methods
    getSystemStatus() {
        return this.request("/api/system/status");
    }

    getTaskStatus(taskId) {
        return this.request(`/api/tasks/${taskId}`);
    }

    getSystemLogs(limit = 100, level = "", query = "") {
        return this.request(`/api/system/logs?limit=${limit}&level=${encodeURIComponent(level)}&query=${encodeURIComponent(query)}`);
    }

    getSSHKeys() {
        return this.request("/api/system/ssh-keys");
    }

    getSSHKeyContent(keyName) {
        return this.request("/api/system/ssh-key-content", {
            method: "POST",
            body: JSON.stringify({ name: keyName })
        });
    }

    getSSHConfig() {
        return this.request("/api/system/ssh-config");
    }

    startSSHAgent() {
        return this.request("/api/system/ssh-agent/start", {
            method: "POST"
        });
    }

    testConnection(siteConfig, credentials) {
        return this.request("/api/system/test-connection", {
            method: "POST",
            body: JSON.stringify({ site_config: siteConfig, credentials })
        });
    }

    getAdminData() {
        return this.request("/api/system/admin-data");
    }

    updateAdminData(data) {
        return this.request("/api/system/admin-data", {
            method: "PUT",
            body: JSON.stringify(data)
        });
    }

    getNotes() {
        return this.request("/api/system/notes");
    }

    updateNotes(notes) {
        return this.request("/api/system/notes", {
            method: "PUT",
            body: JSON.stringify({ notes })
        });
    }

    // Health purge
    purgeHealthData(siteName) {
        return this.request(`/api/sites/${siteName}/health/purge`, {
            method: "POST"
        });
    }

    // Console error acknowledgment methods
    getAcknowledgedErrors(siteName) {
        return this.request(`/api/sites/${siteName}/health/errors/acknowledged`);
    }

    acknowledgeConsoleError(siteName, fingerprint, reason = "") {
        return this.request(`/api/sites/${siteName}/health/errors/acknowledge`, {
            method: "POST",
            body: JSON.stringify({ fingerprint, reason })
        });
    }

    unacknowledgeConsoleError(siteName, fingerprint) {
        return this.request(`/api/sites/${siteName}/health/errors/acknowledge/${fingerprint}`, {
            method: "DELETE"
        });
    }

    // Visual diff acceptance methods
    getAcceptedVisualDiffs(siteName) {
        return this.request(`/api/sites/${siteName}/health/diffs/accepted`);
    }

    acceptVisualDiff(siteName, checkId, reason = "") {
        return this.request(`/api/sites/${siteName}/health/diffs/accept`, {
            method: "POST",
            body: JSON.stringify({ check_id: checkId, reason })
        });
    }

    unacceptVisualDiff(siteName, checkId) {
        return this.request(`/api/sites/${siteName}/health/diffs/accept/${checkId}`, {
            method: "DELETE"
        });
    }


    // System Backups API
    getSystemBackups() {
        return this.request("/api/system/backups");
    }

    createSystemBackup() {
        return this.request("/api/system/backups/create", {
            method: "POST"
        });
    }

    restoreSystemBackup(filename) {
        return this.request("/api/system/backups/restore", {
            method: "POST",
            body: JSON.stringify({ filename })
        });
    }

    deleteSystemBackup(filename) {
        return this.request(`/api/system/backups/${filename}`, {
            method: "DELETE"
        });
    }

    async downloadSystemBackup(filename) {
        const endpoint = `/api/system/backups/${filename}/download`;
        const url = `${this.baseUrl}${endpoint}`;
        const headers = new Headers();
        const token = this.getToken();
        if (token) {
            headers.set("Authorization", `Bearer ${token}`);
        }
        const response = await fetch(url, { headers });
        if (!response.ok) {
            throw new Error(`Failed to download backup: ${response.status}`);
        }
        const blob = await response.blob();
        const downloadUrl = window.URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = downloadUrl;
        anchor.download = filename;
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
        window.URL.revokeObjectURL(downloadUrl);
    }

    uploadSystemBackup(file) {
        const formData = new FormData();
        formData.append("file", file);
        return this.request("/api/system/backups/upload", {
            method: "POST",
            body: formData
        });
    }

    // Profiles API endpoints
    getProfiles() {
        return this.request("/api/profiles");
    }

    saveProfile(profile) {
        return this.request("/api/profiles", {
            method: "POST",
            body: JSON.stringify(profile)
        });
    }

    deleteProfile(profileId) {
        return this.request(`/api/profiles/${profileId}`, {
            method: "DELETE"
        });
    }

    async scanSites(data = {}, returnFullEnvelope = false) {

        const endpoint = "/api/sites/scan";
        const options = {
            method: "POST",
            body: JSON.stringify(data)
        };
        if (returnFullEnvelope) {
            const url = `${this.baseUrl}${endpoint}`;
            const headers = new Headers();
            headers.set("Content-Type", "application/json");
            const token = this.getToken();
            if (token) headers.set("Authorization", `Bearer ${token}`);
            const resp = await fetch(url, { ...options, headers });
            const json = await resp.json();
            if (!resp.ok || !json.success) throw new Error(json.error || "Scan failed");
            return json;
        }
        return this.request(endpoint, options);
    }


    runVulnerabilityScan(siteName) {
        return this.request(`/api/sites/${siteName}/vulnerability-scan`, {
            method: "POST"
        });
    }

    installVulnerabilityPackage(siteName) {
        return this.request(`/api/sites/${siteName}/vulnerability-package`, {
            method: "POST"
        });
    }


    getUsers(siteName) {
        return this.request(`/api/sites/${siteName}/users`);
    }

    updateUserRole(siteName, userId, role) {
        return this.request(`/api/sites/${siteName}/users/${userId}/role`, {
            method: "PUT",
            body: JSON.stringify({ role })
        });
    }

    deactivateUser(siteName, userId) {
        return this.request(`/api/sites/${siteName}/users/${userId}/deactivate`, {
            method: "POST"
        });
    }

    deleteUser(siteName, userId, reassignId) {
        return this.request(`/api/sites/${siteName}/users/${userId}?reassign_id=${reassignId}`, {
            method: "DELETE"
        });
    }

    // Git integration methods
    getGitStatus(siteName) {
        return this.request(`/api/sites/${siteName}/git/status`);
    }

    initGitRepo(siteName, options = {}) {
        return this.request(`/api/sites/${siteName}/git/init`, {
            method: "POST",
            body: JSON.stringify(options)
        });
    }

    pushGitRepo(siteName) {
        return this.request(`/api/sites/${siteName}/git/push`, {
            method: "POST"
        });
    }
}

const api = new APIClient();
export default api;


