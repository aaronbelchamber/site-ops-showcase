import React, { useState, useEffect } from "react";
import api from "../services/api";
import { showToast } from "../services/toast";
import { useTaskPolling } from "../hooks/useTaskPolling";

import UserManagementTab from "./UserManagementTab";
import SecurityScanTab from "./SecurityScanTab";
import ImageLightbox from "./ImageLightbox";

export default function SiteDetails({ siteName, onBack, onEditClick, onCloneClick }) {
    const [site, setSite] = useState(null);
    const [activeTab, setActiveTab] = useState(() => new URLSearchParams(window.location.search).get("tab") || "overview");

    useEffect(() => {
        const updateTabFromUrl = () => {
            const tab = new URLSearchParams(window.location.search).get("tab") || "overview";
            setActiveTab(tab);
        };
        updateTabFromUrl();
        window.addEventListener("popstate", updateTabFromUrl);
        return () => window.removeEventListener("popstate", updateTabFromUrl);
    }, [siteName]);

    const handleTabChange = (tabName) => {
        setActiveTab(tabName);
        const url = tabName === "overview" ? `/site/${siteName}/details` : `/site/${siteName}/details?tab=${tabName}`;
        window.history.pushState({}, "", url);
    };

    const [backups, setBackups] = useState([]);
    const [healthHistory, setHealthHistory] = useState([]);
    const [visibleCount, setVisibleCount] = useState(5);
    const [updateOffers, setUpdateOffers] = useState(null);
    const [includeMedia, setIncludeMedia] = useState(false);
    const [clearedCaches, setClearedCaches] = useState([]);
    
    // Decoupled pre-update safety controls (both default to true)
    const [createBackup, setCreateBackup] = useState(true);
    const [qualityChecks, setQualityChecks] = useState(true);

    const [latestSnapshot, setLatestSnapshot] = useState(null);
    const [snapshotDesktopUrl, setSnapshotDesktopUrl] = useState(null);
    const [snapshotMobileUrl, setSnapshotMobileUrl] = useState(null);
    const [lightboxImage, setLightboxImage] = useState(null);
    const [updatesHistory, setUpdatesHistory] = useState([]);

    const [loadingDetails, setLoadingDetails] = useState(true);
    const [loadingBackups, setLoadingBackups] = useState(false);
    const [loadingHealth, setLoadingHealth] = useState(false);
    const [checkingUpdates, setCheckingUpdates] = useState(false);
    const [loadingUpdatesHistory, setLoadingUpdatesHistory] = useState(false);
    const [visibleUpdatesCount, setVisibleUpdatesCount] = useState(5);

    const { pollTask, activeTasks } = useTaskPolling();

    const siteTasks = Object.values(activeTasks).filter(task => 
        task.name && task.name.includes(siteName)
    );
    const hasRunningTask = siteTasks.some(task => task.status === "running");

    const getTaskConfig = (taskName) => {
        if (taskName.includes("Update All")) {
            return {
                successMsg: "All updates applied successfully!",
                callback: (result) => {
                    fetchAllData();
                    if (result && result.steps) {
                        const allCaches = [];
                        result.steps.forEach(step => {
                            if (step.cleared_caches) {
                                allCaches.push(...step.cleared_caches);
                            }
                        });
                        if (allCaches.length > 0) {
                            setClearedCaches([...new Set(allCaches)]);
                        }
                    }
                }
            };
        }
        if (taskName.includes("Update Core")) {
            return {
                successMsg: "Core update completed!",
                callback: (result) => {
                    fetchAllData();
                    if (result && result.cleared_caches) {
                        setClearedCaches(result.cleared_caches);
                    }
                }
            };
        }
        if (taskName.includes("Update Plugins")) {
            return {
                successMsg: "Plugins updated!",
                callback: (result) => {
                    fetchAllData();
                    if (result && result.cleared_caches) {
                        setClearedCaches(result.cleared_caches);
                    }
                }
            };
        }
        if (taskName.includes("Update Themes")) {
            return {
                successMsg: "Themes updated!",
                callback: (result) => {
                    fetchAllData();
                    if (result && result.cleared_caches) {
                        setClearedCaches(result.cleared_caches);
                    }
                }
            };
        }
        if (taskName.includes("Backup")) {
            return {
                successMsg: "Backup created successfully!",
                callback: () => {
                    fetchBackups();
                }
            };
        }
        if (taskName.includes("Restore")) {
            return {
                successMsg: "Restore completed successfully!",
                callback: () => {
                    fetchAllData();
                }
            };
        }
        return null;
    };

    useEffect(() => {
        const resumeActiveTasks = async () => {
            try {
                const systemStatus = await api.getSystemStatus();
                if (systemStatus && systemStatus.tasks) {
                    systemStatus.tasks.forEach(task => {
                        if (task.status === "running" && task.name && task.name.includes(siteName)) {
                            const config = getTaskConfig(task.name);
                            if (config) {
                                pollTask(task.task_id, config.successMsg, config.callback);
                            }
                        }
                    });
                }
            } catch (error) {
                console.error("Failed to resume active tasks:", error);
            }
        };
        resumeActiveTasks();
    }, [siteName]);

    const fetchAllData = async () => {
        setLoadingDetails(true);
        try {
            const siteData = await api.getSite(siteName);
            setSite(siteData);
            setIncludeMedia(false);
            setLoadingDetails(false);

            fetchHealthHistory();

            if (siteData.status === "Ready") {
                fetchBackups();
                fetchUpdates();
                fetchLatestSnapshot();
                fetchUpdatesHistory();
            } else {
                setBackups([]);
                setUpdateOffers(null);
                setLatestSnapshot(null);
                setUpdatesHistory([]);
            }
        } catch (error) {
            showToast(`Failed to load details: ${error.message}`, "error");
            onBack();
        }
    };

    const fetchUpdatesHistory = async () => {
        setLoadingUpdatesHistory(true);
        try {
            const data = await api.getUpdateHistory(siteName);
            setUpdatesHistory(data);
        } catch (error) {
            console.error("Failed to load updates history:", error);
        } finally {
            setLoadingUpdatesHistory(false);
        }
    };

    const fetchBackups = async () => {
        setLoadingBackups(true);
        try {
            const data = await api.getBackups(siteName);
            setBackups(data);
        } catch (error) {
            console.error("Failed to load backups:", error);
        } finally {
            setLoadingBackups(false);
        }
    };

    const fetchHealthHistory = async () => {
        setLoadingHealth(true);
        try {
            const data = await api.getHealthHistory(siteName);
            setHealthHistory(data);
        } catch (error) {
            console.error("Failed to load health history:", error);
        } finally {
            setLoadingHealth(false);
        }
    };

    const fetchUpdates = async (force = false) => {
        setCheckingUpdates(true);
        try {
            const data = await api.checkUpdates(siteName, force);
            setUpdateOffers(data);
        } catch (error) {
            console.error("Failed to check updates:", error);
            showToast(`Failed to check updates: ${error.message}`, "error");
        } finally {
            setCheckingUpdates(false);
        }
    };

    const fetchLatestSnapshot = async () => {
        try {
            let data = await api.getLatestSnapshot(siteName);
            let hasScreenshot = data && data.id && (data.checks?.http?.screenshots?.desktop || data.checks?.http?.screenshots);

            if (!data || !hasScreenshot) {
                try {
                    data = await api.runHealthCheck(siteName);
                } catch (e) {
                    console.debug("Auto snapshot backfill failed in SiteDetails for", siteName, e);
                }
            }

            setLatestSnapshot(data);
            
            if (snapshotDesktopUrl) URL.revokeObjectURL(snapshotDesktopUrl);
            if (snapshotMobileUrl) URL.revokeObjectURL(snapshotMobileUrl);
            setSnapshotDesktopUrl(null);
            setSnapshotMobileUrl(null);

            if (data && data.id) {
                try {
                    const desktopBlob = await api.getScreenshotBlob(siteName, data.id, "desktop");
                    setSnapshotDesktopUrl(URL.createObjectURL(desktopBlob));
                } catch (e) {
                    console.error("Failed to load snapshot desktop img", e);
                }
                try {
                    const mobileBlob = await api.getScreenshotBlob(siteName, data.id, "mobile");
                    setSnapshotMobileUrl(URL.createObjectURL(mobileBlob));
                } catch (e) {
                    console.error("Failed to load snapshot mobile img", e);
                }
            }
        } catch (error) {
            console.error("Failed to fetch latest snapshot:", error);
        }
    };

    useEffect(() => {
        fetchAllData();
    }, [siteName]);

    const handleCreateBackup = async () => {
        try {
            showToast(`Initiating backup for ${site.display_name}...`, "info");
            const description = `Manual Backup via Dashboard (${new Date().toLocaleString()})`;
            const task = await api.createBackup(siteName, description, includeMedia);
            pollTask(task.task_id, "Backup created successfully!", () => {
                fetchBackups();
            });
        } catch (error) {
            showToast(`Failed to trigger backup: ${error.message}`, "error");
        }
    };

    const handleRestoreBackup = async (backupId) => {
        if (!confirm(`Are you sure you want to restore backup '${backupId}'? Current site state will be overwritten.`)) {
            return;
        }

        try {
            showToast(`Initiating restore for ${site.display_name}...`, "info");
            const task = await api.restoreBackup(siteName, backupId);
            pollTask(task.task_id, "Restore completed successfully!", () => {
                fetchAllData();
            });
        } catch (error) {
            showToast(`Failed to trigger restore: ${error.message}`, "error");
        }
    };

    const handleDeleteBackup = async (backupId) => {
        if (!confirm(`Are you sure you want to delete backup '${backupId}'?`)) {
            return;
        }

        try {
            await api.deleteBackup(siteName, backupId);
            showToast("Backup deleted.", "success");
            fetchBackups();
        } catch (error) {
            showToast(`Failed to delete backup: ${error.message}`, "error");
        }
    };

    // Updates actions using decoupled createBackup & qualityChecks
    const handleUpdateCore = async () => {
        const confirmMsg = (!createBackup && !qualityChecks)
            ? "WARNING: Both Pre-Update Backup and Quality Checks are disabled.\n\nProceed with direct WordPress Core Update?"
            : "Proceed with WordPress Core Update?";
        if (!confirm(confirmMsg)) {
            return;
        }

        try {
            const task = await api.updateCore(siteName, true, createBackup, qualityChecks);
            pollTask(task.task_id, "Core update completed!", (result) => {
                fetchAllData();
                if (result && result.cleared_caches) {
                    setClearedCaches(result.cleared_caches);
                }
            });
        } catch (error) {
            showToast(`Failed to trigger core update: ${error.message}`, "error");
        }
    };

    const handleUpdatePlugins = async () => {
        const confirmMsg = (!createBackup && !qualityChecks)
            ? "WARNING: Both Pre-Update Backup and Quality Checks are disabled.\n\nProceed to update all available plugins?"
            : "Proceed to update all available plugins?";
        if (!confirm(confirmMsg)) {
            return;
        }

        try {
            const task = await api.updatePlugins(siteName, null, createBackup, qualityChecks);
            pollTask(task.task_id, "Plugins updated!", (result) => {
                fetchAllData();
                if (result && result.cleared_caches) {
                    setClearedCaches(result.cleared_caches);
                }
            });
        } catch (error) {
            showToast(`Failed to trigger plugins update: ${error.message}`, "error");
        }
    };

    const handleUpdateThemes = async () => {
        const confirmMsg = (!createBackup && !qualityChecks)
            ? "WARNING: Both Pre-Update Backup and Quality Checks are disabled.\n\nProceed to update all available themes?"
            : "Proceed to update all available themes?";
        if (!confirm(confirmMsg)) {
            return;
        }

        try {
            const task = await api.updateThemes(siteName, null, createBackup, qualityChecks);
            pollTask(task.task_id, "Themes updated!", (result) => {
                fetchAllData();
                if (result && result.cleared_caches) {
                    setClearedCaches(result.cleared_caches);
                }
            });
        } catch (error) {
            showToast(`Failed to trigger themes update: ${error.message}`, "error");
        }
    };

    const handleUpdateAll = async () => {
        const confirmMsg = (!createBackup && !qualityChecks)
            ? "WARNING: Both Pre-Update Backup and Quality Checks are disabled.\n\nProceed with updating all components (Plugins, Themes, and WordPress Core)?"
            : "Proceed with updating all components (Plugins, Themes, and WordPress Core)?";
        if (!confirm(confirmMsg)) {
            return;
        }

        try {
            const task = await api.updateAll(siteName, createBackup, qualityChecks);
            pollTask(task.task_id, "All updates applied successfully!", (result) => {
                fetchAllData();
                if (result && result.steps) {
                    const allCaches = [];
                    result.steps.forEach(step => {
                        if (step.cleared_caches) {
                            allCaches.push(...step.cleared_caches);
                        }
                    });
                    if (allCaches.length > 0) {
                        setClearedCaches([...new Set(allCaches)]);
                    }
                }
            });
        } catch (error) {
            showToast(`Failed to trigger update all: ${error.message}`, "error");
        }
    };

    if (loadingDetails || !site) {
        return (
            <div style={{ textAlign: "center", padding: "4rem 0" }}>
                <span className="material-symbols-outlined animate-spin" style={{ fontSize: "3rem" }}>
                    sync
                </span>
                <p style={{ marginTop: "1rem" }}>Loading site details...</p>
            </div>
        );
    }

    return (
        <div id="detailView" className="view compact-rows">
            {/* Top-Level Navigation Bar - Positioned above everything */}
            <div className="site-details-top-bar" style={{ marginBottom: "1rem" }}>
                <button id="backToDashboardBtn" className="md-button md-button-tonal" onClick={onBack}>
                    <span className="material-symbols-outlined">arrow_back</span> Back
                </button>
            </div>

            {/* Site Header */}
            <div className="page-title-section" style={{ display: "flex", alignItems: "center", gap: "1rem", marginBottom: "1.5rem" }}>
                <div className="site-details-header-thumb" style={{ width: "52px", height: "38px", flexShrink: 0 }}>
                    {snapshotDesktopUrl ? (
                        <img 
                            src={snapshotDesktopUrl} 
                            alt={`${site.display_name} thumbnail`} 
                            className="detail-thumb-small"
                            style={{ width: "52px", height: "38px", objectFit: "cover", borderRadius: "4px", border: "1px solid var(--md-sys-color-outline-variant)", display: "block" }} 
                        />
                    ) : (
                        <div style={{ width: "52px", height: "38px", borderRadius: "4px", backgroundColor: "var(--md-sys-color-surface-variant)", display: "flex", alignItems: "center", justifyContent: "center", color: "var(--md-sys-color-outline)" }}>
                            <span className="material-symbols-outlined" style={{ fontSize: "18px" }}>language</span>
                        </div>
                    )}
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: "0.2rem", flex: 1 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
                        <h2 id="detailSiteTitle" style={{ margin: 0 }}>{site.display_name}</h2>
                        {latestSnapshot && (
                            <span 
                                className={`badge badge-sm ${
                                    (latestSnapshot.overall_status || "").toLowerCase() === "healthy" || (latestSnapshot.overall_status || "").toLowerCase() === "healthy with exception" ? "badge-success" :
                                    (latestSnapshot.overall_status || "").toLowerCase() === "notice" ? "badge-info" :
                                    (latestSnapshot.overall_status || "").toLowerCase() === "degraded" ? "badge-warning" : "badge-error"
                                }`}
                                style={{ fontSize: "0.75rem", textTransform: "uppercase", fontWeight: "bold" }}
                                title={
                                    (latestSnapshot.overall_status || "").toLowerCase() === "healthy with exception"
                                        ? "Healthy with Exceptions: All functional checks passed, but visual diffs or console errors were accepted by an admin."
                                        : "Current Site Health Status"
                                }
                            >
                                {(latestSnapshot.overall_status || "").toLowerCase() === "healthy with exception" ? "HEALTHY*" : (latestSnapshot.overall_status || "UNKNOWN")}
                            </span>
                        )}
                        <span 
                            className="badge badge-sm badge-lowercase badge-neutral" 
                            style={{ fontSize: "0.75rem" }}
                            title={`Onboarding source: ${site.creation_source || "manual"}`}
                        >
                            {site.creation_source === "auto_discovered" ? "⚡ auto discovered" : "✍️ manually added"}
                        </span>
                    </div>
                    <span style={{ fontSize: "0.85rem", color: "var(--md-sys-color-outline)" }}>{site.site_name}</span>
                </div>
                <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
                    <button className="md-button md-button-outlined" onClick={() => onCloneClick(site)} disabled={hasRunningTask}>
                        <span className="material-symbols-outlined">content_copy</span> Clone
                    </button>
                    <button className="md-button md-button-outlined" onClick={() => onEditClick(site)} disabled={hasRunningTask}>
                        <span className="material-symbols-outlined">edit</span> Edit
                    </button>
                </div>
            </div>

            {/* Tab Navigation */}
            <div className="md-tabs" style={{ marginBottom: "1.5rem" }}>
                <button
                    className={`md-tab ${activeTab === "overview" ? "active" : ""}`}
                    onClick={() => handleTabChange("overview")}
                >
                    <span className="material-symbols-outlined">dashboard</span> Overview
                </button>
                <button
                    className={`md-tab ${activeTab === "updates" ? "active" : ""}`}
                    onClick={() => handleTabChange("updates")}
                >
                    <span className="material-symbols-outlined">update</span> Updates
                    {updateOffers && (updateOffers.core?.update_available || updateOffers.plugins?.updates_available || updateOffers.themes?.updates_available) && (
                        <span className="badge badge-warning badge-sm" style={{ marginLeft: "0.4rem" }}>New</span>
                    )}
                </button>
                <button
                    className={`md-tab ${activeTab === "backups" ? "active" : ""}`}
                    onClick={() => handleTabChange("backups")}
                >
                    <span className="material-symbols-outlined">backup</span> Backups ({backups.length})
                </button>

                <button
                    className={`md-tab ${activeTab === "users" ? "active" : ""}`}
                    onClick={() => handleTabChange("users")}
                >
                    <span className="material-symbols-outlined">group</span> User Management
                </button>

                <button
                    className={`md-tab ${activeTab === "security" ? "active" : ""}`}
                    onClick={() => handleTabChange("security")}
                >
                    <span className="material-symbols-outlined">security</span> Security Audit
                </button>
            </div>

            {/* Notifications & Cache Alerts */}
            {clearedCaches.length > 0 && (
                <div className="alert alert-info" style={{ marginBottom: "1.5rem", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <div>
                        <strong>Cache Cleared:</strong> Flushed object/page caches: {clearedCaches.join(", ")}
                    </div>
                    <button className="btn-icon" onClick={() => setClearedCaches([])}>
                        <span className="material-symbols-outlined">close</span>
                    </button>
                </div>
            )}

            {/* TAB CONTENTS */}
            {activeTab === "overview" && (
                <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: "1.5rem" }}>
                    {/* Left Column: Quick Info & Status */}
                    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
                        <div className="md-card">
                            <div className="card-header">
                                <h3>Site Configuration</h3>
                            </div>
                            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem", marginTop: "1rem" }}>
                                <div>
                                    <strong style={{ color: "var(--md-sys-color-outline)" }}>Status:</strong>
                                    <div>{site.status}</div>
                                </div>
                                <div>
                                    <strong style={{ color: "var(--md-sys-color-outline)" }}>SSH Host:</strong>
                                    <div>{site.ssh_host || "n/a"}</div>
                                </div>
                                <div>
                                    <strong style={{ color: "var(--md-sys-color-outline)" }}>WP Path:</strong>
                                    <div>{site.wp_path || "n/a"}</div>
                                </div>
                                <div>
                                    <strong style={{ color: "var(--md-sys-color-outline)" }}>Database Name:</strong>
                                    <div>{site.db_name || "n/a"}</div>
                                </div>
                                <div style={{ gridColumn: "1 / -1" }}>
                                    <strong style={{ color: "var(--md-sys-color-outline)" }}>Health Check URL:</strong>
                                    <div>
                                        <a href={site.health_check_url} target="_blank" rel="noopener noreferrer" style={{ color: "var(--md-sys-color-primary)" }}>
                                            {site.health_check_url}
                                        </a>
                                    </div>
                                </div>
                            </div>
                        </div>

                        {/* Recent Health History */}
                        <div className="md-card">
                            <div className="card-header">
                                <h3>Recent Health Checks</h3>
                            </div>
                            {loadingHealth ? (
                                <p style={{ marginTop: "1rem", color: "var(--md-sys-color-outline)" }}>Loading history...</p>
                            ) : healthHistory.length === 0 ? (
                                <p style={{ marginTop: "1rem", color: "var(--md-sys-color-outline)" }}>No health checks recorded yet.</p>
                            ) : (
                                <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem", marginTop: "1rem" }}>
                                    {healthHistory.slice(0, 5).map((check) => (
                                        <div 
                                            key={check.id} 
                                            style={{ 
                                                display: "flex", 
                                                justifyContent: "space-between", 
                                                alignItems: "center",
                                                padding: "0.75rem",
                                                backgroundColor: "var(--md-sys-color-surface-variant)",
                                                borderRadius: "var(--md-sys-shape-corner-small)",
                                                cursor: "pointer"
                                            }}
                                            onClick={() => {
                                                window.history.pushState({}, "", `/site/${siteName}/health-check/${check.id}`);
                                                window.dispatchEvent(new Event("popstate"));
                                            }}
                                            title="Click to view detailed health report"
                                        >
                                            <div>
                                                <strong>{check.overall_status.toUpperCase()}</strong>
                                                <div style={{ fontSize: "0.8rem", color: "var(--md-sys-color-outline)" }}>
                                                    {new Date(check.timestamp).toLocaleString()}
                                                </div>
                                            </div>
                                            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.875rem" }}>
                                                <span>HTTP {check.checks?.http?.status_code || "N/A"}</span>
                                                <span className="material-symbols-outlined" style={{ fontSize: "1.1rem", color: "var(--md-sys-color-primary)" }}>chevron_right</span>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    </div>

                    {/* Right Column: Latest Snapshot */}
                    <div>
                        <div className="md-card">
                            <div className="card-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                                <h3>Latest Live Snapshot</h3>
                                <button
                                    className="md-button md-button-tonal md-button-sm"
                                    disabled={loadingHealth}
                                    onClick={() => fetchHealth(true)}
                                    title="Re-run live health check and capture fresh desktop/mobile screenshots"
                                >
                                    <span className="material-symbols-outlined" style={{ fontSize: "16px" }}>sync</span> Re-run Snapshot
                                </button>
                            </div>
                            <div style={{ marginTop: "1rem" }}>
                                {snapshotDesktopUrl ? (
                                    <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                                        <div>
                                            <span style={{ fontSize: "0.8rem", color: "var(--md-sys-color-outline)", display: "block", marginBottom: "0.25rem" }}>Desktop View</span>
                                            <img 
                                                src={snapshotDesktopUrl} 
                                                alt="Desktop View" 
                                                onClick={() => setLightboxImage({ src: snapshotDesktopUrl, alt: `${site?.display_name || siteName} Desktop View` })}
                                                style={{ width: "100%", borderRadius: "8px", border: "1px solid var(--md-sys-color-outline-variant)", cursor: "zoom-in" }} 
                                                title="Click to enlarge & magnify"
                                            />
                                        </div>
                                        {snapshotMobileUrl && (
                                            <div>
                                                <span style={{ fontSize: "0.8rem", color: "var(--md-sys-color-outline)", display: "block", marginBottom: "0.25rem" }}>Mobile View</span>
                                                <img 
                                                    src={snapshotMobileUrl} 
                                                    alt="Mobile View" 
                                                    onClick={() => setLightboxImage({ src: snapshotMobileUrl, alt: `${site?.display_name || siteName} Mobile View` })}
                                                    style={{ width: "140px", borderRadius: "8px", border: "1px solid var(--md-sys-color-outline-variant)", cursor: "zoom-in" }} 
                                                    title="Click to enlarge & magnify"
                                                />
                                            </div>
                                        )}
                                    </div>
                                ) : (
                                    <div style={{ textAlign: "center", padding: "2rem 0", color: "var(--md-sys-color-outline)" }}>
                                        <span className="material-symbols-outlined" style={{ fontSize: "2.5rem" }}>image_not_supported</span>
                                        <p style={{ marginTop: "0.5rem", fontSize: "0.875rem" }}>No snapshot captured yet.</p>
                                    </div>
                                )}
                            </div>
                        </div>
                    </div>
                </div>
            )}

            {activeTab === "updates" && (
                <div style={{ display: "flex", flexDirection: "column", gap: "2rem" }}>
                    {/* Updates Card */}
                    <div className="md-card" style={{ boxShadow: "none" }}>
                        <div className="admin-section-header">
                            <div>
                                <h3 style={{ margin: 0 }}>Updates Management</h3>
                                <span style={{ fontSize: "0.85rem", color: "var(--md-sys-color-outline)" }}>
                                    {checkingUpdates ? (
                                        "Scanning WordPress for available updates..."
                                    ) : updateOffers && updateOffers.timestamp ? (
                                        `Last scan: ${new Date(updateOffers.timestamp).toLocaleString()} (Cached)`
                                    ) : (
                                        "No update scan on record. Click 'Scan Available Updates' to check for changes."
                                    )}
                                </span>
                            </div>
                            <div style={{ display: "flex", gap: "1rem", alignItems: "center" }}>
                                {hasRunningTask && siteTasks.some(t => t.name.includes("Update All")) && (
                                    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginRight: "0.5rem", fontSize: "0.8rem", color: "var(--md-sys-color-primary)" }}>
                                        <span className="material-symbols-outlined animate-spin" style={{ fontSize: "1.1rem" }}>sync</span>
                                        <span>{siteTasks.find(t => t.name.includes("Update All"))?.progress}</span>
                                    </div>
                                )}

                                {/* Decoupled Independent Controls */}
                                <label 
                                    style={{ display: "flex", alignItems: "center", gap: "0.35rem", fontSize: "0.85rem", cursor: "pointer", userSelect: "none" }}
                                    title="Creates an automatic file and database backup snapshot before applying updates."
                                >
                                    <input
                                        type="checkbox"
                                        checked={createBackup}
                                        onChange={(e) => setCreateBackup(e.target.checked)}
                                        style={{ cursor: "pointer" }}
                                        disabled={checkingUpdates || hasRunningTask}
                                    />
                                    Create Pre-Update Backup
                                    <span className="material-symbols-outlined" style={{ fontSize: "14px", color: "var(--md-sys-color-outline)" }}>info</span>
                                </label>

                                <label 
                                    style={{ display: "flex", alignItems: "center", gap: "0.35rem", fontSize: "0.85rem", cursor: "pointer", userSelect: "none" }}
                                    title="Runs HTTP baseline check before updating and post-update health check after updating. Automatically rolls back if an update fails."
                                >
                                    <input
                                        type="checkbox"
                                        checked={qualityChecks}
                                        onChange={(e) => setQualityChecks(e.target.checked)}
                                        style={{ cursor: "pointer" }}
                                        disabled={checkingUpdates || hasRunningTask}
                                    />
                                    Perform Quality Checks
                                    <span className="material-symbols-outlined" style={{ fontSize: "14px", color: "var(--md-sys-color-outline)" }}>info</span>
                                </label>

                                <button
                                    className={`md-button md-button-outlined ${checkingUpdates ? "btn-throbbing" : ""}`}
                                    onClick={() => fetchUpdates(true)}
                                    disabled={checkingUpdates || hasRunningTask}
                                    title="Perform a live WP-CLI scan for core, plugin, and theme updates"
                                >
                                    <span className={`material-symbols-outlined ${checkingUpdates ? "spin-icon" : ""}`}>sync</span>
                                    {checkingUpdates ? "Scanning Available Updates..." : "Scan Available Updates"}
                                </button>
                                <button
                                    className="md-button md-button-primary"
                                    onClick={handleUpdateAll}
                                    disabled={checkingUpdates || hasRunningTask || !updateOffers || (!updateOffers.core?.update_available && !updateOffers.plugins?.updates_available && !updateOffers.themes?.updates_available)}
                                >
                                    <span className="material-symbols-outlined">update</span> Update All
                                </button>
                            </div>
                        </div>

                        <div
                            id="updatesContainer"
                            style={{ display: "flex", flexDirection: "column", gap: "1rem", marginTop: "1rem" }}
                        >
                            {checkingUpdates ? (
                                <p style={{ color: "var(--md-sys-color-outline)" }}>Checking updates...</p>
                            ) : updateOffers ? (
                                <>
                                    {/* Core Update Offer */}
                                    <div
                                        className="form-group"
                                        style={{
                                            padding: "1rem",
                                            border: "1px solid var(--md-sys-color-outline-variant)",
                                            borderRadius: "var(--md-sys-shape-corner-medium)",
                                        }}
                                    >
                                        {updateOffers.core?.update_available ? (
                                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                                                <div>
                                                    <strong>WordPress Core Update Available</strong>
                                                    <br />
                                                    <span style={{ fontSize: "0.875rem", color: "var(--md-sys-color-outline)" }}>
                                                        Version Offer: {updateOffers.core.details.version}
                                                    </span>
                                                </div>
                                                <button
                                                    className="md-button md-button-primary"
                                                    onClick={handleUpdateCore}
                                                    disabled={hasRunningTask}
                                                >
                                                    Update Core
                                                </button>
                                            </div>
                                        ) : (
                                            <span style={{ color: "var(--md-sys-color-success)" }}>
                                                ✔ WordPress Core is up to date.
                                            </span>
                                        )}
                                    </div>

                                    {/* Plugins Update Offer */}
                                    <div
                                        className="form-group"
                                        style={{
                                            padding: "1rem",
                                            border: "1px solid var(--md-sys-color-outline-variant)",
                                            borderRadius: "var(--md-sys-shape-corner-medium)",
                                        }}
                                    >
                                        {updateOffers.plugins?.updates_available ? (
                                            <div>
                                                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
                                                    <strong>Plugin Updates ({updateOffers.plugins.plugins.length})</strong>
                                                    <button
                                                        className="md-button md-button-primary"
                                                        onClick={handleUpdatePlugins}
                                                        disabled={hasRunningTask}
                                                    >
                                                        Update All Plugins
                                                    </button>
                                                </div>
                                                <div className="update-items-grid">
                                                    {updateOffers.plugins.plugins.map((plug) => (
                                                        <div
                                                            key={plug.name}
                                                            className="update-item-chip"
                                                        >
                                                            <span>
                                                                <strong>{plug.name}</strong> ({plug.version} → {plug.update_version})
                                                            </span>
                                                        </div>
                                                    ))}
                                                </div>
                                            </div>
                                        ) : (
                                            <span style={{ color: "var(--md-sys-color-success)" }}>
                                                ✔ All plugins are up to date.
                                            </span>
                                        )}
                                    </div>

                                    {/* Themes Update Offer */}
                                    <div
                                        className="form-group"
                                        style={{
                                            padding: "1rem",
                                            border: "1px solid var(--md-sys-color-outline-variant)",
                                            borderRadius: "var(--md-sys-shape-corner-medium)",
                                        }}
                                    >
                                        {updateOffers.themes?.updates_available ? (
                                            <div>
                                                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
                                                    <strong>Theme Updates ({updateOffers.themes.themes.length})</strong>
                                                    <button
                                                        className="md-button md-button-primary"
                                                        onClick={handleUpdateThemes}
                                                        disabled={hasRunningTask}
                                                    >
                                                        Update All Themes
                                                    </button>
                                                </div>
                                                <div className="update-items-grid">
                                                    {updateOffers.themes.themes.map((th) => (
                                                        <div
                                                            key={th.name}
                                                            className="update-item-chip"
                                                        >
                                                            <span>
                                                                <strong>{th.name}</strong> ({th.version} → {th.update_version})
                                                            </span>
                                                        </div>
                                                    ))}
                                                </div>
                                            </div>
                                        ) : (
                                            <span style={{ color: "var(--md-sys-color-success)" }}>
                                                ✔ All themes are up to date.
                                            </span>
                                        )}
                                    </div>
                                </>
                            ) : (
                                <p style={{ color: "var(--md-sys-color-outline)" }}>
                                    No update check results cached. Click 'Scan Available Updates' above to perform a live scan.
                                </p>
                            )}
                        </div>
                    </div>

                    {/* Update History */}
                    <div className="md-card">
                        <div className="card-header">
                            <h3>Update History</h3>
                        </div>
                        {loadingUpdatesHistory ? (
                            <p style={{ marginTop: "1rem", color: "var(--md-sys-color-outline)" }}>Loading update history...</p>
                        ) : updatesHistory.length === 0 ? (
                            <p style={{ marginTop: "1rem", color: "var(--md-sys-color-outline)" }}>No updates recorded yet.</p>
                        ) : (
                            <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem", marginTop: "1rem" }}>
                                {updatesHistory.slice(0, visibleUpdatesCount).map((entry, idx) => (
                                    <div
                                        key={entry.update_id || idx}
                                        style={{
                                            padding: "1rem",
                                            border: "1px solid var(--md-sys-color-outline-variant)",
                                            borderRadius: "var(--md-sys-shape-corner-medium)",
                                            display: "flex",
                                            justifyContent: "space-between",
                                            alignItems: "center"
                                        }}
                                    >
                                        <div>
                                            <div style={{ fontWeight: 600 }}>
                                                {entry.type ? entry.type.toUpperCase() : "UPDATE"}: {entry.target || "system"}
                                            </div>
                                            <div style={{ fontSize: "0.8rem", color: "var(--md-sys-color-outline)", marginTop: "0.2rem" }}>
                                                {new Date(entry.timestamp).toLocaleString()}
                                            </div>
                                            {entry.error && (
                                                <div style={{ color: "var(--md-sys-color-error)", fontSize: "0.85rem", marginTop: "0.3rem" }}>
                                                    {entry.error}
                                                </div>
                                            )}
                                        </div>
                                        <div>
                                            <span className={`badge ${entry.status === "completed" ? "badge-success" : entry.status === "rolled_back" ? "badge-warning" : "badge-error"}`}>
                                                {entry.status}
                                            </span>
                                        </div>
                                    </div>
                                ))}

                                {updatesHistory.length > visibleUpdatesCount && (
                                    <button 
                                        className="md-button md-button-outlined"
                                        onClick={() => setVisibleUpdatesCount(prev => prev + 5)}
                                        style={{ alignSelf: "center", marginTop: "0.5rem" }}
                                    >
                                        Load More History
                                    </button>
                                )}
                            </div>
                        )}
                    </div>
                </div>
            )}

            {activeTab === "backups" && (
                <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
                    <div className="md-card">
                        <div className="card-header">
                            <h3>Create Manual Backup</h3>
                        </div>
                        <div style={{ display: "flex", gap: "1rem", alignItems: "center", marginTop: "1rem" }}>
                            <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", cursor: "pointer", fontSize: "0.875rem" }}>
                                <input
                                    type="checkbox"
                                    checked={includeMedia}
                                    onChange={(e) => setIncludeMedia(e.target.checked)}
                                />
                                Include wp-content/uploads (Media)
                            </label>
                            <button
                                className="md-button md-button-primary"
                                onClick={handleCreateBackup}
                                disabled={hasRunningTask}
                            >
                                <span className="material-symbols-outlined">backup</span> Create Backup Now
                            </button>
                        </div>
                    </div>

                    <div className="md-card">
                        <div className="card-header">
                            <h3>Available Backups ({backups.length})</h3>
                        </div>
                        {loadingBackups ? (
                            <p style={{ marginTop: "1rem", color: "var(--md-sys-color-outline)" }}>Loading backups...</p>
                        ) : backups.length === 0 ? (
                            <p style={{ marginTop: "1rem", color: "var(--md-sys-color-outline)" }}>No backups found.</p>
                        ) : (
                            <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem", marginTop: "1rem" }}>
                                {backups.slice(0, visibleCount).map((b) => (
                                    <div
                                        key={b.backup_id}
                                        style={{
                                            display: "flex",
                                            justifyContent: "space-between",
                                            alignItems: "center",
                                            padding: "1rem",
                                            border: "1px solid var(--md-sys-color-outline-variant)",
                                            borderRadius: "var(--md-sys-shape-corner-medium)"
                                        }}
                                    >
                                        <div>
                                            <strong>{b.backup_id}</strong>
                                            <div style={{ fontSize: "0.8rem", color: "var(--md-sys-color-outline)" }}>
                                                {new Date(b.created_at).toLocaleString()} • {(b.size_bytes / (1024 * 1024)).toFixed(2)} MB
                                            </div>
                                            <div style={{ fontSize: "0.85rem", marginTop: "0.25rem" }}>
                                                {b.description || "Manual backup"}
                                            </div>
                                        </div>
                                        <div style={{ display: "flex", gap: "0.5rem" }}>
                                            <button
                                                className="md-button md-button-outlined"
                                                onClick={() => handleRestoreBackup(b.backup_id)}
                                                disabled={hasRunningTask}
                                            >
                                                Restore
                                            </button>
                                            <button
                                                className="md-button md-button-outlined"
                                                onClick={() => handleDeleteBackup(b.backup_id)}
                                                disabled={hasRunningTask}
                                                style={{ color: "var(--md-sys-color-error)", borderColor: "var(--md-sys-color-error)" }}
                                            >
                                                Delete
                                            </button>
                                        </div>
                                    </div>
                                ))}

                                {backups.length > visibleCount && (
                                    <button 
                                        className="md-button md-button-outlined"
                                        onClick={() => setVisibleCount(prev => prev + 5)}
                                        style={{ alignSelf: "center", marginTop: "0.5rem" }}
                                    >
                                        Load More Backups
                                    </button>
                                )}
                            </div>
                        )}
                    </div>
                </div>
            )}

            {activeTab === "users" && (
                <UserManagementTab siteName={siteName} />
            )}

            {activeTab === "security" && (
                <SecurityScanTab siteName={siteName} />
            )}

            {lightboxImage && (
                <ImageLightbox
                    src={lightboxImage.src}
                    alt={lightboxImage.alt}
                    onClose={() => setLightboxImage(null)}
                />
            )}
        </div>
    );
}
