import React, { useState, useEffect } from "react";
import api from "../services/api";
import { showToast } from "../services/toast";

const arePathsEqual = (pathA, pathB, homeDir) => {
    if (!pathA || !pathB) return false;
    
    const norm = (p) => {
        let res = p.replace(/\\/g, "/").trim();
        if (homeDir) {
            if (res.startsWith("~/")) {
                res = homeDir.replace(/\\/g, "/") + res.substring(1);
            }
        }
        if (res.endsWith("/")) {
            res = res.slice(0, -1);
        }
        return res.toLowerCase();
    };
    
    return norm(pathA) === norm(pathB);
};

export default function AddSiteForm({ siteToEdit, siteNameFromUrl, cloneFrom, onCancel, onSuccess, onDeleteSuccess, onManageProfiles }) {
    const isCloneMode = !!cloneFrom || (siteToEdit && siteToEdit.isClone);
    const isEditMode = (!!siteToEdit || !!siteNameFromUrl) && !isCloneMode;

    const [siteName, setSiteName] = useState("");
    const [displayName, setDisplayName] = useState("");
    const [healthCheckUrl, setHealthCheckUrl] = useState("");
    const [includeMedia, setIncludeMedia] = useState(false);

    const [sshHost, setSshHost] = useState("");
    const [sshUser, setSshUser] = useState("");
    const [sshPassword, setSshPassword] = useState("");
    const [sshPrivateKey, setSshPrivateKey] = useState("");

    const [wpPath, setWpPath] = useState("");
    const [dbHost, setDbHost] = useState("localhost");
    const [dbName, setDbName] = useState("");
    const [dbUser, setDbUser] = useState("");
    const [dbPassword, setDbPassword] = useState("");

    const [status, setStatus] = useState("In Progress");
    const [source, setSource] = useState("local");
    const [domain, setDomain] = useState("");
    const [credentialProfiles, setCredentialProfiles] = useState([]);
    const [selectedCredentialProfile, setSelectedCredentialProfile] = useState("");
    const [submitting, setSubmitting] = useState(false);
    const [testingConnection, setTestingConnection] = useState(false);
    const [confirmDelete, setConfirmDelete] = useState(false);
    const [cloneCredentialsFrom, setCloneCredentialsFrom] = useState("");

    useEffect(() => {
        const fetchProfiles = async () => {
            try {
                const profileData = await api.getProfiles();
                setCredentialProfiles(profileData || []);
            } catch (error) {
                console.error("Failed to load credential profiles:", error);
            }
        };
        fetchProfiles();
    }, []);

    const handleTestConnection = async () => {
        if (!sshHost) {
            showToast("Please fill in the SSH Host field first.", "error");
            return;
        }
        setTestingConnection(true);
        try {
            const siteConfig = {
                site_name: siteName || null,
                credential_profile: selectedCredentialProfile || null,
                ssh_host: sshHost,
                ssh_port: 22,
                ssh_user: sshUser,
                wp_path: wpPath
            };
            const credentials = {
                ssh_password: sshPassword,
                ssh_private_key: sshPrivateKey
            };
            const result = await api.testConnection(siteConfig, credentials);
            setStatus("Ready");
            showToast(`Connection successful! Status set to Ready. (${result.wp_path_status})`, "success");
        } catch (error) {
            showToast(`Connection test failed: ${error.message}`, "error");
        } finally {
            setTestingConnection(false);
        }
    };

    useEffect(() => {
        const loadSite = async () => {
            if (isEditMode || isCloneMode) {
                let site = siteToEdit;
                const activeName = siteNameFromUrl || cloneFrom;
                if (!site && activeName) {
                    try {
                        site = await api.getSite(activeName);
                    } catch (err) {
                        showToast(`Failed to load site config: ${err.message}`, "error");
                        return;
                    }
                }
                if (site) {
                    if (isCloneMode) {
                        setSiteName(site.site_name ? `${site.site_name}-copy` : "");
                        setDisplayName(site.display_name ? `${site.display_name} (Copy)` : "");
                        setStatus("In Progress");
                        setCloneCredentialsFrom(site.site_name || cloneFrom || "");
                    } else {
                        setSiteName(site.site_name || "");
                        setDisplayName(site.display_name || "");
                        setStatus(site.status || "In Progress");
                        setCloneCredentialsFrom("");
                    }
                    setHealthCheckUrl(site.health_check_url || "");
                    setIncludeMedia(site.include_media === true);
                    setSelectedCredentialProfile(site.credential_profile || "");
                    setSshHost(site.ssh_host || "");
                    setSshUser(site.ssh_user || "");
                    setSshPassword(""); // Keep blank
                    setSshPrivateKey(site.ssh_private_key || "");
                    setWpPath(site.wp_path || "");
                    setDbHost(site.db_host || "localhost");
                    setDbName(site.db_name || "");
                    setDbUser(site.db_user || "");
                    setDbPassword(""); // Keep blank
                    setSource(site.source || "local");
                    setDomain(site.domain || "");
                }
            } else {
                setSiteName("");
                setDisplayName("");
                setStatus("In Progress");
                setHealthCheckUrl("");
                setIncludeMedia(true);
                setSelectedCredentialProfile("");
                setSshHost("");
                setSshUser("");
                setSshPassword("");
                setSshPrivateKey("");
                setWpPath("");
                setDbHost("localhost");
                setDbName("");
                setDbUser("");
                setDbPassword("");
                setSource("local");
                setDomain("");
                setCloneCredentialsFrom("");
            }
        };
        loadSite();
    }, [siteToEdit, isEditMode, isCloneMode, siteNameFromUrl, cloneFrom]);



    const handleSubmit = async (e) => {
        e.preventDefault();
        setSubmitting(true);

        const payload = {
            display_name: displayName,
            status: status,
            health_check_url: healthCheckUrl || null,
            credential_profile: selectedCredentialProfile || null,
            ssh_host: sshHost || null,
            ssh_user: sshUser || null,
            wp_path: wpPath || null,
            db_host: dbHost || "localhost",
            db_name: dbName || null,
            db_user: dbUser || null,
            include_media: includeMedia,
            source: source,
            domain: domain || null
        };

        if (sshPassword) payload.ssh_password = sshPassword;
        if (sshPrivateKey) payload.ssh_private_key = sshPrivateKey;
        if (dbPassword) payload.db_password = dbPassword;

        if (isCloneMode && cloneCredentialsFrom) {
            payload.clone_credentials_from = cloneCredentialsFrom;
        }

        try {
            if (isEditMode) {
                await api.updateSite(siteName, payload);
                showToast("Site updated successfully!", "success");
                onSuccess(siteName);
            } else {
                const addPayload = {
                    site_name: siteName,
                    ...payload
                };
                await api.addSite(addPayload);
                showToast(isCloneMode ? "Site cloned successfully!" : "Site added successfully!", "success");
                onSuccess();
            }
        } catch (error) {
            showToast(`Failed to save site: ${error.message}`, "error");
        } finally {
            setSubmitting(false);
        }
    };

    const handleDeleteSite = async () => {
        const activeSiteName = siteNameFromUrl || siteToEdit?.site_name;
        if (!activeSiteName) return;
        if (
            confirm(
                `Are you absolutely sure you want to delete and unmonitor site '${activeSiteName}'?\nThis will remove it from the Sites list and delete sensitive credentials. Backups on this manager will NOT be deleted, but config files will.`
            )
        ) {
            try {
                await api.deleteSite(activeSiteName);
                showToast("Site unmonitored.", "success");
                if (onDeleteSuccess) {
                    onDeleteSuccess();
                }
            } catch (error) {
                showToast(`Failed to delete site: ${error.message}`, "error");
            }
        }
    };

    return (
        <div id="addSiteView" className="view">
            <div className="page-title-section">
                <div className="page-title-heading">
                    <button type="button" className="md-button md-button-tonal" onClick={onCancel}>
                        <span className="material-symbols-outlined">arrow_back</span> {isEditMode ? "Cancel" : "Back"}
                    </button>
                    <h2>{isEditMode ? "Edit Site Configuration" : isCloneMode ? "Clone Site Configuration" : "Add New Site"}</h2>
                </div>
                
                {/* 3-Way Status Toggle Switch */}
                <div className="status-toggle-container">
                    <span className="status-toggle-label">Status:</span>
                    <div className="status-toggle-group">
                        <button
                            type="button"
                            className={`md-button status-toggle-pill${status === "In Progress" ? " active" : ""}`}
                            onClick={() => setStatus("In Progress")}
                        >
                            In Progress
                        </button>
                        <button
                            type="button"
                            className={`md-button status-toggle-pill ready${status === "Ready" ? " active" : ""}`}
                            disabled={true}
                            title="Set automatically when SSH connection test succeeds"
                        >
                            Ready {status === "Ready" ? "✓" : "🔒"}
                        </button>
                        <button
                            type="button"
                            className={`md-button status-toggle-pill${status === "Archived" ? " active" : ""}`}
                            onClick={() => setStatus("Archived")}
                        >
                            Archived
                        </button>
                    </div>
                </div>
            </div>

            {isCloneMode && (
                <div className="md-card clone-info-card">
                    <span className="material-symbols-outlined">content_copy</span>
                    <div>
                        <strong>Cloning Site Configuration</strong>
                        <span className="clone-info-text">
                            You are cloning from <strong>{cloneCredentialsFrom}</strong>. Sensitive credentials (SSH passwords, private keys, database passwords) will be safely copied on the server. Please update the path, domain, and database name below to avoid conflicts with the original site.
                        </span>
                    </div>
                </div>
            )}

            <form id="addSiteForm" onSubmit={handleSubmit}>
                <div className="form-grid">
                    {/* Column 1: Basic & Options */}
                    <div className="form-column">
                        <div className="md-card">
                            <div className="card-header">
                                <div className="card-title">
                                    <h3>Basic Configuration</h3>
                                    <span>Core identifier & address</span>
                                </div>
                            </div>
                            <div className="form-group">
                                <label htmlFor="site_name">Identifier Slug (e.g. test-site)</label>
                                <input
                                    type="text"
                                    id="site_name"
                                    className="form-control"
                                    required
                                    disabled={isEditMode}
                                    placeholder="lowercase-letters-and-hyphens-only"
                                    value={siteName}
                                    onChange={(e) => setSiteName(e.target.value)}
                                />
                            </div>
                            <div className="form-group">
                                <label htmlFor="display_name">Display Name</label>
                                <input
                                    type="text"
                                    id="display_name"
                                    className="form-control"
                                    required
                                    placeholder="My WordPress Site"
                                    value={displayName}
                                    onChange={(e) => setDisplayName(e.target.value)}
                                />
                            </div>
                            <div className="form-group">
                                <label htmlFor="health_check_url">Health Check URL</label>
                                <input
                                    type="url"
                                    id="health_check_url"
                                    className="form-control"
                                    required={status === "Ready"}
                                    placeholder="https://example.com"
                                    value={healthCheckUrl}
                                    onChange={(e) => setHealthCheckUrl(e.target.value)}
                                />
                            </div>

                            <div className="form-group">
                                <label htmlFor="source">Storage Destination</label>
                                <select
                                    id="source"
                                    className="form-control"
                                    value={source}
                                    onChange={(e) => setSource(e.target.value)}
                                >
                                    <option value="local">Local Config (sites.yaml)</option>
                                    <option value="json">Versioned Config (admin_data.json)</option>
                                </select>
                            </div>

                            <div className="form-group">
                                <label htmlFor="domain">Custom Domain Override (Optional)</label>
                                <input
                                    type="text"
                                    id="domain"
                                    className="form-control"
                                    placeholder="e.g. example.com (overrides auto-detection)"
                                    value={domain}
                                    onChange={(e) => setDomain(e.target.value)}
                                />
                            </div>

                            <details className="help-accordion">
                                <summary>💡 Field Descriptions & Help</summary>
                                <div className="help-content">
                                    <p>
                                        <strong>Identifier Slug</strong>: A unique, URL-friendly name using lowercase letters and
                                        hyphens. This is used for directories and filenames on this manager.
                                    </p>
                                    <p>
                                        <strong>Display Name</strong>: The user-friendly name of the WordPress site that will be
                                        shown across the dashboard.
                                    </p>
                                    <p>
                                        <strong>Health Check URL</strong>: The public homepage or a status URL that the manager will
                                        check to verify server availability.
                                    </p>
                                </div>
                            </details>
                        </div>

                        <div className="md-card">
                            <div className="card-header">
                                <div className="card-title">
                                    <h3>Backup Settings</h3>
                                    <span>Options for automated and manual backups</span>
                                </div>
                            </div>
                            <div className="form-group inline">
                                <input
                                    type="checkbox"
                                    id="include_media"
                                    checked={includeMedia}
                                    onChange={(e) => setIncludeMedia(e.target.checked)}
                                />
                                <label htmlFor="include_media">Include uploads/media folder in backups</label>
                            </div>

                            <details className="help-accordion">
                                <summary>💡 Backup Info & Help</summary>
                                <div className="help-content">
                                    <p>
                                        <strong>Include uploads/media</strong>: If checked, the backup will include media files
                                        (images, PDF documents, videos). Unchecking this reduces backup file size and improves
                                        execution time significantly.
                                    </p>
                                </div>
                            </details>
                        </div>
                    </div>

                    {/* Column 2: SSH & Database Settings */}
                    <div className="form-column">
                        
                        {/* SSH Credentials Card */}
                        <div className="md-card">
                            <div className="card-header">
                                <div className="card-title">
                                    <h3>SSH Credentials</h3>
                                    <span>Credentials for WordPress server access</span>
                                </div>
                            </div>

                            <div className="form-group compact">
                                <label htmlFor="credential_profile" className="highlight-label">Shared Login Profile</label>
                                <select
                                    id="credential_profile"
                                    className="form-control"
                                    value={selectedCredentialProfile}
                                    required={status === "Ready"}
                                    onChange={(e) => {
                                        const pId = e.target.value;
                                        setSelectedCredentialProfile(pId);
                                        if (pId) {
                                            const profile = credentialProfiles.find(p => p.id === pId);
                                            if (profile) {
                                                setSshHost(profile.ssh_host || "");
                                                setSshUser(profile.ssh_user || "");
                                                setSshPrivateKey(profile.ssh_private_key || "");
                                                setSshPassword("");
                                            }
                                        } else {
                                            setSshHost("");
                                            setSshUser("");
                                            setSshPrivateKey("");
                                            setSshPassword("");
                                        }
                                    }}
                                >
                                    <option value="">-- Select Shared SSH Profile --</option>
                                    {credentialProfiles.map(p => (
                                        <option key={p.id} value={p.id}>
                                            🔑 {p.title} ({p.ssh_user}@{p.ssh_host})
                                        </option>
                                    ))}
                                </select>
                                <span className="form-note">
                                    Sites must use a credential profile for remote SSH connections.
                                </span>
                            </div>

                            <div className="button-row">
                                <button
                                    type="button"
                                    className="md-button md-button-tonal full-width-button"
                                    onClick={onManageProfiles}
                                >
                                    <span className="material-symbols-outlined">manage_accounts</span>
                                    Manage SSH Credentials
                                </button>
                            </div>

                            {/* Test Connection Button */}
                            <div className="button-row">
                                <button
                                    type="button"
                                    className="md-button md-button-outlined full-width-button"
                                    onClick={handleTestConnection}
                                    disabled={testingConnection}
                                >
                                    <span className="material-symbols-outlined">network_check</span>
                                    {testingConnection ? "Testing Connection..." : "Test Connection & Mark Ready"}
                                </button>
                            </div>
                        </div>

                        {/* Database Connection Card */}
                        <div className="md-card">
                            <div className="card-header">
                                <div className="card-title">
                                    <h3>Database Connection</h3>
                                    <span>Database details for backup & rollback operations</span>
                                </div>
                            </div>
                            <div className="form-group">
                                <label htmlFor="wp_path">WordPress Absolute Path</label>
                                <input
                                    type="text"
                                    id="wp_path"
                                    className="form-control"
                                    required={status === "Ready"}
                                    placeholder="/var/www/html"
                                    value={wpPath}
                                    onChange={(e) => setWpPath(e.target.value)}
                                />
                            </div>
                            <div className="form-group">
                                <label htmlFor="db_host">Database Host</label>
                                <input
                                    type="text"
                                    id="db_host"
                                    className="form-control"
                                    required={status === "Ready"}
                                    placeholder="localhost"
                                    value={dbHost}
                                    onChange={(e) => setDbHost(e.target.value)}
                                />
                            </div>
                            <div className="form-group">
                                <label htmlFor="db_name">Database Name</label>
                                <input
                                    type="text"
                                    id="db_name"
                                    className="form-control"
                                    required={status === "Ready"}
                                    placeholder="wordpress_db"
                                    value={dbName}
                                    onChange={(e) => setDbName(e.target.value)}
                                />
                            </div>
                            <div className="form-group">
                                <label htmlFor="db_user">Database User</label>
                                <input
                                    type="text"
                                    id="db_user"
                                    className="form-control"
                                    required={status === "Ready"}
                                    placeholder="db_user"
                                    value={dbUser}
                                    onChange={(e) => setDbUser(e.target.value)}
                                />
                            </div>
                            <div className="form-group">
                                <label htmlFor="db_password">
                                    Database Password {isEditMode && "(optional, leave blank to keep)"}
                                </label>
                                <input
                                    type="password"
                                    id="db_password"
                                    className="form-control"
                                    placeholder={isEditMode ? "••••••••" : "db_password"}
                                    value={dbPassword}
                                    onChange={(e) => setDbPassword(e.target.value)}
                                />
                            </div>

                            <details className="help-accordion">
                                <summary>💡 Database Info Help</summary>
                                <div className="help-content">
                                    <p>
                                        <strong>WordPress Absolute Path</strong>: The folder containing <code>wp-config.php</code> on
                                        the destination server.
                                    </p>
                                    <p>
                                        <strong>Database Host</strong>: The host address of the MySQL/MariaDB database server (typically
                                        <code>localhost</code> or <code>127.0.0.1</code>).
                                    </p>
                                    <p>
                                        <strong>Credentials</strong>: Must have permissions to read and dump the configured database
                                        name.
                                    </p>
                                </div>
                            </details>
                        </div>
                    </div>
                </div>

                {isEditMode && (
                    <div className="danger-zone-container">
                        <div className="md-card danger-zone-card">
                            <div className="card-header">
                                <div className="card-title">
                                    <h3 className="danger-zone-title">
                                        <span className="material-symbols-outlined">warning</span> Danger Zone
                                    </h3>
                                    <span>Irreversible operations for this site</span>
                                </div>
                            </div>
                            <div className="danger-zone-content">
                                <p className="danger-zone-message">
                                    Deleting this site will unmonitor it, remove it from the Sites list, and permanently delete sensitive credentials. 
                                    Backups stored on this manager will NOT be deleted, but configuration files will be.
                                </p>
                                
                                <div className="danger-zone-checkbox-container" onClick={() => setConfirmDelete(!confirmDelete)}>
                                    <input 
                                        type="checkbox" 
                                        id="confirmDeleteCheckbox" 
                                        className="danger-zone-checkbox"
                                        checked={confirmDelete}
                                        onChange={(e) => {
                                            e.stopPropagation();
                                            setConfirmDelete(e.target.checked);
                                        }}
                                    />
                                    <label 
                                        htmlFor="confirmDeleteCheckbox" 
                                        className="checkbox-label"
                                        onClick={(e) => e.stopPropagation()}
                                    >
                                        I confirm that I want to permanently delete <strong>{siteNameFromUrl || siteToEdit?.site_name}</strong>
                                    </label>
                                </div>
                                
                                <div>
                                    <button
                                        type="button"
                                        className={`md-button danger-zone-button ${confirmDelete ? 'danger-zone-button-active' : 'danger-zone-button-disabled'}`}
                                        disabled={!confirmDelete}
                                        onClick={handleDeleteSite}
                                    >
                                        <span className="material-symbols-outlined">delete</span> Delete Site
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>
                )}

                <div className="form-actions-bar">
                    <button type="button" className="md-button md-button-tonal" onClick={onCancel}>
                        Cancel
                    </button>
                    <button type="submit" className="md-button md-button-primary" disabled={submitting}>
                        {submitting ? "Saving..." : "Save WordPress Site"}
                    </button>
                </div>
            </form>
        </div>
    );
}
