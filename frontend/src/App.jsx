import React, { useState, useEffect, useRef } from "react";
import api from "./services/api";
import { showToast } from "./services/toast";
import { useSitesContext } from "./context/SitesContext";
import { useTaskPolling } from "./hooks/useTaskPolling";
import { useConfirm } from "./hooks/useConfirm";
import ErrorBoundary from "./components/ErrorBoundary";
import ToastContainer from "./components/ToastContainer";
import TopStatusContainer from "./components/TopStatusContainer";
import AuthOverlay from "./components/AuthOverlay";
import SiteGrid from "./components/SiteGrid";
import SiteDetails from "./components/SiteDetails";
import AddSiteForm from "./components/AddSiteForm";
import HealthCheckDetails from "./components/HealthCheckDetails";
import ProductionHealthDashboard from "./components/ProductionHealthDashboard";
import ManageSitesView from "./components/ManageSitesView";
import AdminProfilesTab from "./components/admin/AdminProfilesTab";
import AdminBackupsTab from "./components/admin/AdminBackupsTab";
import AdminMaintenanceTab from "./components/admin/AdminMaintenanceTab";
import { STALE_THRESHOLD_HOURS, isSiteStale, arePathsEqual } from "./utils/siteHelpers";

export default function App() {
    const sitesContext = useSitesContext();
    const { pollTaskWithDelay } = useTaskPolling();
    const { confirm, confirmDialog } = useConfirm();
    const staleCheckTimeoutsRef = useRef([]);
    const [isAuthenticated, setIsAuthenticated] = useState(api.hasToken());
    const [appMode, setAppMode] = useState("full");
    const [sites, setSites] = useState([]);
    const [loadingSites, setLoadingSites] = useState(false);
    const [staleOnlyFilter, setStaleOnlyFilter] = useState(false);
    const [siteViewMode, setSiteViewMode] = useState(() => {
        try {
            return localStorage.getItem("wp_mgr_site_view_mode") || "grid";
        } catch (e) {
            return "grid";
        }
    });

    useEffect(() => {
        try {
            localStorage.setItem("wp_mgr_site_view_mode", siteViewMode);
        } catch (e) {
            // ignore localStorage failures
        }
    }, [siteViewMode]);

    // Routing and view states
    const [currentView, setCurrentView] = useState("dashboard"); // "dashboard", "manage-sites", "add", "edit", "details", "health-check-details", "logs", "admin", "profiles"
    const [selectedSiteName, setSelectedSiteName] = useState(null);
    const [selectedHealthCheckId, setSelectedHealthCheckId] = useState(null);
    const [siteToEdit, setSiteToEdit] = useState(null);
    const [manageSitesTab, setManageSitesTab] = useState("discovered");


    // Logs states
    const [logsContent, setLogsContent] = useState("");
    const [logsEntries, setLogsEntries] = useState([]);
    const [loadingLogs, setLoadingLogs] = useState(false);
    const [logsSearchQuery, setLogsSearchQuery] = useState("");
    const [logsLevelFilter, setLogsLevelFilter] = useState("");
    const [logsLimit, setLogsLimit] = useState(200);
    const [logSourceTab, setLogSourceTab] = useState("activity"); // "activity" | "system"
    const [activityHistory, setActivityHistory] = useState(() => {
        try {
            const saved = localStorage.getItem("wp_mgr_activity_history");
            return saved ? JSON.parse(saved) : [];
        } catch (e) {
            return [];
        }
    });

    const handleActivityLogged = (eventItem) => {
        setActivityHistory((prev) => {
            const updated = [eventItem, ...prev.slice(0, 499)]; // Keep up to 500 recent events
            try {
                localStorage.setItem("wp_mgr_activity_history", JSON.stringify(updated));
            } catch (e) {}
            return updated;
        });
    };

    // Admin notes states
    const [adminNotes, setAdminNotes] = useState("");
    const [loadingNotes, setLoadingNotes] = useState(false);
    const [savingNotes, setSavingNotes] = useState(false);

    // Admin backups and tabs states
    const [activeAdminTab, setActiveAdminTab] = useState("profiles"); // "profiles", "logs", "backups", "notes", "maintenance"
    const [systemBackups, setSystemBackups] = useState([]);
    const [loadingSystemBackups, setLoadingSystemBackups] = useState(false);
    const [creatingSystemBackup, setCreatingSystemBackup] = useState(false);
    const [restoringSystemBackup, setRestoringSystemBackup] = useState(false);
    const [uploadingSystemBackup, setUploadingSystemBackup] = useState(false);

    // Profiles states
    const [profiles, setProfiles] = useState([]);
    const [loadingProfiles, setLoadingProfiles] = useState(false);
    const [savingProfile, setSavingProfile] = useState(false);
    const [editingProfile, setEditingProfile] = useState(null);

    // Profiles form state
    const [profileTitle, setProfileTitle] = useState("");
    const [profileHost, setProfileHost] = useState("");
    const [profilePort, setProfilePort] = useState(22);
    const [profileUser, setProfileUser] = useState("");
    const [profilePassword, setProfilePassword] = useState("");
    const [profilePrivateKey, setProfilePrivateKey] = useState("");

    // SSH agent and ssh config helper states
    const [sshAgentActive, setSshAgentActive] = useState(false);
    const [discoveredKeys, setDiscoveredKeys] = useState([]);
    const [selectedDiscoveredKey, setSelectedDiscoveredKey] = useState("");
    const [sshConfigProfiles, setSshConfigProfiles] = useState([]);
    const [selectedSshProfile, setSelectedSshProfile] = useState("");
    const [loadingKeys, setLoadingKeys] = useState(false);

    const handleLoadProfiles = async () => {
        setLoadingProfiles(true);
        setEditingProfile(null);
        clearProfileForm();
        try {
            const data = await api.getProfiles();
            setProfiles(data || []);

            // Fetch SSH agent and ssh config profiles
            setLoadingKeys(true);
            const keyData = await api.getSSHKeys();
            setSshAgentActive(keyData.agent_active);
            setDiscoveredKeys(keyData.keys || []);
            
            const configData = await api.getSSHConfig();
            setSshConfigProfiles(configData.profiles || []);
        } catch (error) {
            showToast(`Failed to load profiles: ${error.message}`, "error");
        } finally {
            setLoadingProfiles(false);
            setLoadingKeys(false);
        }
    };

    const clearProfileForm = () => {
        setProfileTitle("");
        setProfileHost("");
        setProfilePort(22);
        setProfileUser("");
        setProfilePassword("");
        setProfilePrivateKey("");
        setSelectedSshProfile("");
        setSelectedDiscoveredKey("");
    };

    const handleEditProfile = (profile) => {
        setEditingProfile(profile);
        setProfileTitle(profile.title || "");
        setProfileHost(profile.ssh_host || "");
        setProfilePort(profile.ssh_port || 22);
        setProfileUser(profile.ssh_user || "");
        setProfilePassword(profile.ssh_password || "");
        setProfilePrivateKey(profile.ssh_private_key || "");
    };

    const handleUseDiscoveredKeyPath = () => {
        if (!selectedDiscoveredKey) return;
        const selectedKeyObj = discoveredKeys.find(k => k.name === selectedDiscoveredKey);
        if (selectedKeyObj) {
            setProfilePrivateKey(selectedKeyObj.path);
            showToast(`Set key path to ${selectedKeyObj.path}!`, "success");
        }
    };

    const handleApplySshProfile = (profileAlias) => {
        setSelectedSshProfile(profileAlias);
        if (!profileAlias) return;
        const profile = sshConfigProfiles.find(p => p.host_alias === profileAlias);
        if (profile) {
            if (profile.hostname) setProfileHost(profile.hostname);
            if (profile.user) setProfileUser(profile.user);
            if (profile.identity_file) setProfilePrivateKey(profile.identity_file);
            showToast(`Applied SSH settings from profile "${profileAlias}"!`, "success");
        }
    };

    const handleStartSSHAgent = async () => {
        setLoadingKeys(true);
        try {
            await api.startSSHAgent();
            showToast("SSH Agent started successfully!", "success");
            
            const keyData = await api.getSSHKeys();
            setSshAgentActive(keyData.agent_active);
            setDiscoveredKeys(keyData.keys || []);
        } catch (error) {
            showToast(`Failed to start SSH Agent: ${error.message}`, "error");
        } finally {
            setLoadingKeys(false);
        }
    };

    useEffect(() => {
        let homeDir = "";
        const firstKey = discoveredKeys[0];
        if (firstKey && firstKey.path) {
            const normalized = firstKey.path.replace(/\\/g, "/");
            const sshIdx = normalized.toLowerCase().indexOf("/.ssh");
            if (sshIdx !== -1) {
                homeDir = normalized.substring(0, sshIdx);
            }
        }

        if (sshConfigProfiles.length > 0 && profileHost) {
            const matchingProfile = sshConfigProfiles.find(
                p => p.hostname === profileHost &&
                     (!profileUser || p.user === profileUser) &&
                     (!profilePrivateKey || arePathsEqual(p.identity_file, profilePrivateKey, homeDir))
            );
            if (matchingProfile) {
                setSelectedSshProfile(matchingProfile.host_alias);
            } else {
                setSelectedSshProfile("");
            }
        } else {
            setSelectedSshProfile("");
        }
    }, [sshConfigProfiles, profileHost, profileUser, profilePrivateKey, discoveredKeys]);

    const handleSaveProfile = async (e) => {
        e.preventDefault();
        if (!profileTitle.trim()) {
            showToast("Profile title is required", "error");
            return;
        }
        setSavingProfile(true);
        try {
            await api.saveProfile({
                id: editingProfile?.id || null,
                title: profileTitle,
                ssh_host: profileHost,
                ssh_port: Number(profilePort),
                ssh_user: profileUser,
                ssh_password: profilePassword,
                ssh_private_key: profilePrivateKey
            });
            showToast("Profile saved successfully!", "success");
            
            // Reload profiles
            const list = await api.getProfiles();
            setProfiles(list || []);
            setEditingProfile(null);
            clearProfileForm();
        } catch (error) {
            showToast(`Failed to save profile: ${error.message}`, "error");
        } finally {
            setSavingProfile(false);
        }
    };

    const handleDeleteProfile = async (profileId) => {
        const ok = await confirm({
            title: "Delete credential profile?",
            message: "Sites referencing this profile will lose their connection credentials.",
            confirmLabel: "Delete profile",
            destructive: true,
        });
        if (!ok) {
            return;
        }
        try {
            await api.deleteProfile(profileId);
            showToast("Profile deleted successfully.", "success");
            const list = await api.getProfiles();
            setProfiles(list || []);
            if (editingProfile?.id === profileId) {
                setEditingProfile(null);
                clearProfileForm();
            }
        } catch (error) {
            showToast(`Failed to delete profile: ${error.message}`, "error");
        }
    };

    const handleLoadNotes = async () => {
        setLoadingNotes(true);
        try {
            const data = await api.getNotes();
            setAdminNotes(data?.notes || "");
        } catch (error) {
            showToast(`Failed to load admin notes: ${error.message}`, "error");
        } finally {
            setLoadingNotes(false);
        }
    };

    const handleSaveNotes = async () => {
        setSavingNotes(true);
        try {
            await api.updateNotes(adminNotes);
            showToast("Admin notes saved successfully!", "success");
            window.history.pushState({}, "", "/");
            window.dispatchEvent(new Event("popstate"));
        } catch (error) {
            showToast(`Failed to save admin notes: ${error.message}`, "error");
        } finally {
            setSavingNotes(false);
        }
    };
    const handleLoadSystemBackups = async () => {
        setLoadingSystemBackups(true);
        try {
            const list = await api.getSystemBackups();
            setSystemBackups(list || []);
        } catch (error) {
            showToast(`Failed to load system backups: ${error.message}`, "error");
        } finally {
            setLoadingSystemBackups(false);
        }
    };

    const handleCreateSystemBackup = async () => {
        setCreatingSystemBackup(true);
        try {
            const result = await api.createSystemBackup();
            showToast(result.message, "success");
            await handleLoadSystemBackups();
        } catch (error) {
            showToast(`Failed to create system backup: ${error.message}`, "error");
        } finally {
            setCreatingSystemBackup(false);
        }
    };

    const handleRestoreSystemBackup = async (filename) => {
        const ok = await confirm({
            title: "Restore configuration from backup?",
            message: `This overwrites your current site configurations and credentials database with the contents of "${filename}". You may be logged out and need to sign in again.`,
            confirmLabel: "Restore",
            destructive: true,
        });
        if (!ok) {
            return;
        }
        setRestoringSystemBackup(true);
        try {
            const result = await api.restoreSystemBackup(filename);
            showToast(result.message, "success");
            // Reload configuration and sites
            await loadSites();
            // Fetch system backups list again
            await handleLoadSystemBackups();
        } catch (error) {
            showToast(`Failed to restore system backup: ${error.message}`, "error");
        } finally {
            setRestoringSystemBackup(false);
        }
    };

    const handleDeleteSystemBackup = async (filename) => {
        const ok = await confirm({
            title: "Delete backup file?",
            message: `"${filename}" will be permanently removed. This cannot be undone.`,
            confirmLabel: "Delete backup",
            destructive: true,
        });
        if (!ok) {
            return;
        }
        try {
            const result = await api.deleteSystemBackup(filename);
            showToast(result.message, "success");
            await handleLoadSystemBackups();
        } catch (error) {
            showToast(`Failed to delete backup: ${error.message}`, "error");
        }
    };

    const handleUploadSystemBackup = async (event) => {
        const file = event.target.files[0];
        if (!file) return;
        if (!file.name.endsWith('.zip')) {
            showToast("Only ZIP files are supported.", "error");
            return;
        }
        const ok = await confirm({
            title: "Upload and restore configuration?",
            message: "This overwrites your current configuration files with the contents of the uploaded archive.",
            confirmLabel: "Upload and restore",
            destructive: true,
        });
        if (!ok) {
            return;
        }
        setUploadingSystemBackup(true);
        try {
            const result = await api.uploadSystemBackup(file);
            showToast(result.message, "success");
            await loadSites();
            await handleLoadSystemBackups();
            // Reset the file input
            event.target.value = null;
        } catch (error) {
            showToast(`Failed to upload/restore backup: ${error.message}`, "error");
        } finally {
            setUploadingSystemBackup(false);
        }
    };

    const handlePurgeHealthData = async (siteName, displayName) => {
        const ok = await confirm({
            title: "Purge all health data?",
            message: `Every health history log and screenshot for "${displayName}" will be deleted. This frees disk space but cannot be undone.`,
            requireTyped: siteName,
            confirmLabel: "Purge health data",
            destructive: true,
        });
        if (!ok) {
            return;
        }
        try {
            const result = await api.purgeHealthData(siteName);
            showToast(result.message, "success");
            if (selectedSiteName === siteName) {
                setSelectedHealthCheckId(null);
            }
        } catch (error) {
            showToast(`Failed to purge health data: ${error.message}`, "error");
        }
    };
    const triggerStaleChecks = (siteList) => {
        // Cancel any staggered checks still pending from a previous call
        // (e.g. a rapid site add/edit/delete triggering another refresh).
        staleCheckTimeoutsRef.current.forEach(clearTimeout);
        staleCheckTimeoutsRef.current = [];

        if (!siteList || !Array.isArray(siteList)) return;

        // Filter only Ready sites
        const readySites = siteList.filter(s => s.status === "Ready");

        const runStaleCheck = async (siteName) => {
            try {
                if (sitesContext?.setSiteCheckInFlight) {
                    sitesContext.setSiteCheckInFlight(siteName, true);
                }
                const res = await api.triggerCheckUpdates(siteName);
                if (res && res.task_id) {
                    pollTaskWithDelay(
                        res.task_id,
                        `Updates check completed for ${siteName}`,
                        (result) => {
                            if (sitesContext?.setSiteCheckInFlight) {
                                sitesContext.setSiteCheckInFlight(siteName, false);
                            }
                            if (result && sitesContext?.setSiteUpdates) {
                                sitesContext.setSiteUpdates(siteName, result);
                            }
                        }
                    );
                } else {
                    if (sitesContext?.setSiteCheckInFlight) {
                        sitesContext.setSiteCheckInFlight(siteName, false);
                    }
                }
            } catch (err) {
                // 409 just means the backend is already working on this site.
                console.debug("Stale check trigger skipped for", siteName, err);
                if (sitesContext?.setSiteCheckInFlight) {
                    sitesContext.setSiteCheckInFlight(siteName, false);
                }
            }
        };

        let staleIndex = 0;
        for (const site of readySites) {
            const siteName = site.site_name;
            const summary = site.update_summary;
            let isStale = true;

            if (summary && summary.timestamp) {
                const checkTime = new Date(summary.timestamp).getTime();
                if (!isNaN(checkTime)) {
                    const ageMs = Date.now() - checkTime;
                    isStale = ageMs > (24 * 60 * 60 * 1000);
                }
            }

            // Don't re-queue a site whose check is already running: loadSites()
            // is called on mount, after each completed task and on refresh, and
            // re-triggering produced 409s against the backend's per-site lock.
            const alreadyChecking = Boolean(sitesContext?.inFlightChecks?.has(siteName));

            if (isStale && !alreadyChecking) {
                // Stagger the trigger requests themselves (not just polling)
                // so we don't fire many concurrent SSH/WP-CLI checks at once.
                const timeoutId = setTimeout(() => runStaleCheck(siteName), staleIndex * 10000);
                staleCheckTimeoutsRef.current.push(timeoutId);
                staleIndex++;
            }
        }
    };

    const loadSites = async () => {
        if (!api.hasToken()) return;
        setLoadingSites(true);
        try {
            const data = await api.getSites();
            setSites(data);
            if (sitesContext?.setSites) {
                sitesContext.setSites(data);
            }
            triggerStaleChecks(data);
        } catch (error) {
            console.error("Failed to load sites:", error);
            // If it failed because of 401, the unauthorized event will fire
        } finally {
            setLoadingSites(false);
        }
    };

    const handleUrlRoute = () => {
        const path = window.location.pathname;
        if (path === "/manage-sites" || path === "/manage-sites/discovered") {
            setSelectedSiteName(null);
            setSelectedHealthCheckId(null);
            setSiteToEdit(null);
            setManageSitesTab("discovered");
            setCurrentView("manage-sites");
        } else if (path === "/manage-sites/add") {
            setSelectedSiteName(null);
            setSelectedHealthCheckId(null);
            setSiteToEdit(null);
            setManageSitesTab("add");
            setCurrentView("manage-sites");
        } else if (path === "/manage-sites/configured") {
            setSelectedSiteName(null);
            setSelectedHealthCheckId(null);
            setSiteToEdit(null);
            setManageSitesTab("configured");
            setCurrentView("manage-sites");
        } else if (path.startsWith("/site/") && path.endsWith("/edit")) {
            const match = path.match(/^\/site\/([^\/]+)\/edit\/?$/);
            if (match) {
                const siteName = match[1];
                setSelectedSiteName(siteName);
                setSiteToEdit(null);
                setCurrentView("edit");
            } else {
                setCurrentView("dashboard");
            }
        } else if (path.startsWith("/site/") && path.includes("/details")) {
            const match = path.match(/^\/site\/([^\/]+)\/details/);
            if (match) {
                const siteName = match[1];
                setSelectedSiteName(siteName);
                setSiteToEdit(null);
                setSelectedHealthCheckId(null);
                setCurrentView("details");
            } else {
                setCurrentView("dashboard");
            }

        } else if (path.startsWith("/site/") && path.includes("/health-check/")) {
            const match = path.match(/^\/site\/([^\/]+)\/health-check\/([^\/]+)\/?$/);
            if (match) {
                const siteName = match[1];
                const checkId = match[2];
                setSelectedSiteName(siteName);
                setSelectedHealthCheckId(checkId);
                setSiteToEdit(null);
                setCurrentView("health-check-details");
            } else {
                setCurrentView("dashboard");
            }
        } else if (path === "/production-health") {
            setSelectedSiteName(null);
            setSelectedHealthCheckId(null);
            setSiteToEdit(null);
            setCurrentView("production-health");
        } else if (path === "/logs") {
            setSelectedSiteName(null);
            setSelectedHealthCheckId(null);
            setSiteToEdit(null);
            setCurrentView("admin");
            setActiveAdminTab("logs");
        } else if (path === "/admin") {
            setSelectedSiteName(null);
            setSelectedHealthCheckId(null);
            setSiteToEdit(null);
            setCurrentView("admin");
        } else if (path === "/profiles") {
            setSelectedSiteName(null);
            setSelectedHealthCheckId(null);
            setSiteToEdit(null);
            setCurrentView("admin");
            setActiveAdminTab("profiles");
        } else {
            setCurrentView("dashboard");
            setSelectedSiteName(null);
            setSelectedHealthCheckId(null);
            setSiteToEdit(null);
        }
    };

    useEffect(() => {
        handleUrlRoute();
        const onPopState = () => {
            handleUrlRoute();
        };
        window.addEventListener("popstate", onPopState);
        return () => window.removeEventListener("popstate", onPopState);
    }, []);

    const loadAppMode = async () => {
        try {
            const data = await api.getSystemMode();
            const mode = data?.mode || "full";
            setAppMode(mode);
            // Standalone health-dashboard processes land directly on Production
            // Health instead of the full dashboard, since Admin/Manage Sites
            // aren't meant to be used from this locked-down instance.
            if (mode === "health-dashboard" && window.location.pathname === "/") {
                window.history.replaceState({}, "", "/production-health");
                window.dispatchEvent(new Event("popstate"));
            }
        } catch (error) {
            console.debug("Failed to load app mode:", error);
        }
    };

    useEffect(() => {
        // Initial load
        if (isAuthenticated) {
            loadSites();
            loadAppMode();
        }

        // Listen for 401 unauthorized events from API client
        const handleUnauthorized = () => {
            setIsAuthenticated(false);
            setCurrentView("dashboard");
            setSelectedSiteName(null);
            setSiteToEdit(null);
            window.history.pushState({}, "", "/");
            window.dispatchEvent(new Event("popstate"));
        };

        window.addEventListener("unauthorized", handleUnauthorized);
        return () => window.removeEventListener("unauthorized", handleUnauthorized);
    }, [isAuthenticated]);

    // Automatic view data loader hook
    useEffect(() => {
        if (!isAuthenticated) return;
        
        if (currentView === "admin") {
            if (activeAdminTab === "notes") {
                handleLoadNotes();
            } else if (activeAdminTab === "backups") {
                handleLoadSystemBackups();
            } else if (activeAdminTab === "logs") {
                handleLoadLogs();
            } else if (activeAdminTab === "profiles") {
                handleLoadProfiles();
            }
        }
    }, [currentView, activeAdminTab, isAuthenticated, logsLevelFilter]);

    // Run a health check for one site on demand. Uses the async endpoint and
    // polls the task, so it never blocks a request thread the way the old
    // per-card auto-backfill did.
    const handleRequestSiteCheck = async (siteName) => {
        try {
            const res = await api.triggerHealthCheckAsync(siteName);
            if (res && res.task_id) {
                pollTaskWithDelay(res.task_id, `Health check complete for ${siteName}`, (result) => {
                    if (result) loadSites();
                });
            } else {
                showToast(`Could not start health check for ${siteName}`, "error");
            }
        } catch (error) {
            showToast(`Health check failed: ${error.message}`, "error");
        }
    };

    const handleBackToDashboard = () => {
        window.history.pushState({}, "", "/");
        window.dispatchEvent(new Event("popstate"));
    };

    const handleAuthenticated = (token) => {
        setIsAuthenticated(true);
        loadSites();
        loadAppMode();
    };

    const handleLogout = async () => {
        const ok = await confirm({
            title: "Disconnect?",
            message: "Your stored API token will be cleared from this browser.",
            confirmLabel: "Disconnect",
        });
        if (ok) {
            api.clearToken();
            setIsAuthenticated(false);
            setSites([]);
            setCurrentView("dashboard");
            setSelectedSiteName(null);
            setSiteToEdit(null);
            window.history.pushState({}, "", "/");
            showToast("Logged out successfully.", "success");
        }
    };

    const handleLoadLogs = async () => {
        setLoadingLogs(true);
        setLogsContent("Loading logs...");
        try {
            const data = await api.getSystemLogs(logsLimit, logsLevelFilter, logsSearchQuery);
            if (data.log_file_found) {
                setLogsEntries(data.entries || []);
                if (data.lines && data.lines.length > 0) {
                    setLogsContent(data.lines.join("\n"));
                } else {
                    setLogsContent("No matching log lines found.");
                }
            } else {
                setLogsEntries([]);
                setLogsContent("No log lines found. The system log is currently empty.");
            }
        } catch (error) {
            setLogsContent(`Failed to load logs: ${error.message}`);
            setLogsEntries([]);
        } finally {
            setLoadingLogs(false);
        }
    };

    const handleAddSiteSuccess = () => {
        window.history.pushState({}, "", "/");
        window.dispatchEvent(new Event("popstate"));
        loadSites();
    };

    const handleEditSiteSuccess = (siteName) => {
        window.history.pushState({}, "", `/site/${siteName}/details`);
        window.dispatchEvent(new Event("popstate"));
        loadSites();
    };

    const handleDeleteSiteSuccess = () => {
        window.history.pushState({}, "", "/");
        setCurrentView("dashboard");
        loadSites();
    };

    return (
        <div className="app-wrapper">
            {/* API Token Authentication Guard */}
            <AuthOverlay
                isOpen={!isAuthenticated}
                onAuthenticated={handleAuthenticated}
            />

            {/* Application Layout */}
            <header className="app-header">
                <div className="brand" onClick={handleBackToDashboard} style={{ cursor: "pointer" }} title="Return to Dashboard">
                    <span className="material-symbols-outlined logo-icon">dns</span>
                    <h1>WP Site Manager</h1>
                </div>
                {isAuthenticated && (
                    <div className="header-actions">
                        <button
                            type="button"
                            className={`md-button ${currentView === "production-health" ? "md-button-primary" : "md-button-outlined"}`}
                            onClick={() => {
                                window.history.pushState({}, "", "/production-health");
                                window.dispatchEvent(new Event("popstate"));
                            }}
                        >
                            <span className="material-symbols-outlined">monitor_heart</span> Production Health
                        </button>

                        {appMode !== "health-dashboard" && (
                            <>
                                <button
                                    type="button"
                                    className={`md-button ${currentView === "admin" ? "md-button-primary" : "md-button-outlined"}`}
                                    onClick={() => {
                                        window.history.pushState({}, "", "/admin");
                                        window.dispatchEvent(new Event("popstate"));
                                    }}
                                >
                                    <span className="material-symbols-outlined">settings</span> Admin
                                </button>

                                <button
                                    id="manageSitesBtn"
                                    type="button"
                                    className="md-button md-button-primary"
                                    onClick={() => {
                                        window.history.pushState({}, "", "/manage-sites");
                                        window.dispatchEvent(new Event("popstate"));
                                    }}
                                >
                                    <span className="material-symbols-outlined">tune</span> Manage Sites
                                </button>
                            </>
                        )}
                        <button type="button" className="md-button md-button-tonal header-action-logout" onClick={handleLogout}>
                            <span className="material-symbols-outlined">logout</span>
                        </button>
                    </div>
                )}
            </header>

            <main className="app-container">
                {isAuthenticated && (
                    <TopStatusContainer onActivityLogged={handleActivityLogged} />
                )}
                {/* Scoped per view: navigating to another view clears a caught error. */}
                <ErrorBoundary key={`${currentView}:${selectedSiteName || ""}:${activeAdminTab}`}>
                {isAuthenticated && currentView === "production-health" && (
                    <ProductionHealthDashboard />
                )}
                {isAuthenticated && currentView === "manage-sites" && (
                    <ManageSitesView
                        initialTab={manageSitesTab}
                        onBackToDashboard={handleBackToDashboard}
                        onSitesUpdated={loadSites}
                    />
                )}
                {isAuthenticated && currentView === "dashboard" && (
                    <div id="dashboardView">
                        <div className="page-title-section page-title-dashboard">
                            <div>
                                <h2>Monitored Sites</h2>
                                <div className="page-subtitle">Total sites monitored: <span>{sites.length}</span></div>
                            </div>
                            <div className="page-title-actions">
                                <div className="view-toggle-group" role="group" aria-label="Site view mode">
                                    {[
                                        { key: "grid", label: "Default" },
                                        { key: "compact", label: "Compact" },
                                        { key: "details", label: "Details" }
                                    ].map((option) => (
                                        <button
                                            key={option.key}
                                            type="button"
                                            className={`md-button ${siteViewMode === option.key ? "md-button-primary" : "md-button-outlined"}`}
                                            onClick={() => setSiteViewMode(option.key)}
                                        >
                                            {option.label}
                                        </button>
                                    ))}
                                </div>
                                <button type="button" className="md-button md-button-tonal" onClick={loadSites}>
                                    <span className="material-symbols-outlined" aria-hidden="true">refresh</span> Refresh
                                </button>
                            </div>
                        </div>
                        <div className="dashboard-summary-chips" aria-label="Site status summary">
                            <span className="badge badge-success">Ready: {sites.filter(s => s.status === "Ready").length}</span>
                            <span className="badge badge-warning">In Progress: {sites.filter(s => s.status === "In Progress").length}</span>
                            <span className="badge badge-neutral">Archived: {sites.filter(s => s.status === "Archived").length}</span>
                            <button
                                type="button"
                                className={`badge badge-clickable ${staleOnlyFilter ? "badge-stale-orange" : "badge-neutral"}`}
                                onClick={() => setStaleOnlyFilter(v => !v)}
                                title={`Sites whose last update check was more than ${STALE_THRESHOLD_HOURS}h ago. Click to ${staleOnlyFilter ? "clear" : "apply"} this filter.`}
                                aria-pressed={staleOnlyFilter}
                            >
                                <span className="material-symbols-outlined" aria-hidden="true" style={{ fontSize: "14px", verticalAlign: "middle" }}>
                                    {staleOnlyFilter ? "filter_alt" : "filter_alt_off"}
                                </span>
                                {" "}Stale (&gt;{STALE_THRESHOLD_HOURS}h): {sites.filter(isSiteStale).length}
                            </button>
                        </div>
                        <SiteGrid
                            sites={staleOnlyFilter ? sites.filter(isSiteStale) : sites}
                            loading={loadingSites}
                            viewMode={siteViewMode}
                            onViewDetails={(siteName) => {
                                window.history.pushState({}, "", `/site/${siteName}/details`);
                                window.dispatchEvent(new Event("popstate"));
                            }}
                            onAddSiteClick={() => {
                                window.history.pushState({}, "", "/manage-sites/add");
                                window.dispatchEvent(new Event("popstate"));
                            }}
                            onRequestCheck={handleRequestSiteCheck}
                        />
                    </div>
                )}

                {isAuthenticated && currentView === "details" && selectedSiteName && (
                    <SiteDetails
                        siteName={selectedSiteName}
                        onBack={() => {
                            window.history.pushState({}, "", "/");
                            window.dispatchEvent(new Event("popstate"));
                            loadSites(); // Refresh dashboard card statuses
                        }}
                        onEditClick={(site) => {
                            window.history.pushState({}, "", `/site/${site.site_name}/edit`);
                            window.dispatchEvent(new Event("popstate"));
                        }}
                        onCloneClick={(site) => {
                            window.history.pushState({}, "", `/manage-sites/add?clone=${site.site_name}`);
                            window.dispatchEvent(new Event("popstate"));
                        }}
                    />
                )}

                {isAuthenticated && currentView === "health-check-details" && selectedSiteName && selectedHealthCheckId && (
                    <HealthCheckDetails
                        siteName={selectedSiteName}
                        healthCheckId={selectedHealthCheckId}
                        onBack={() => {
                            window.history.pushState({}, "", `/site/${selectedSiteName}/details`);
                            window.dispatchEvent(new Event("popstate"));
                        }}
                    />
                )}

                {isAuthenticated && (currentView === "add" || currentView === "edit") && (
                    <AddSiteForm
                        siteToEdit={siteToEdit}
                        siteNameFromUrl={currentView === "edit" ? selectedSiteName : null}
                        cloneFrom={currentView === "add" ? new URLSearchParams(window.location.search).get("clone") : null}
                        onCancel={() => {
                            const params = new URLSearchParams(window.location.search);
                            const cloneFromUrl = params.get("clone");
                            if (siteToEdit || selectedSiteName || cloneFromUrl) {
                                window.history.pushState({}, "", `/site/${selectedSiteName || cloneFromUrl}/details`);
                                window.dispatchEvent(new Event("popstate"));
                            } else {
                                window.history.pushState({}, "", "/");
                                window.dispatchEvent(new Event("popstate"));
                            }
                        }}
                        onSuccess={siteToEdit || currentView === "edit" ? handleEditSiteSuccess : handleAddSiteSuccess}
                        onDeleteSuccess={handleDeleteSiteSuccess}
                        onManageProfiles={() => {
                            window.history.pushState({}, "", "/profiles");
                            window.dispatchEvent(new Event("popstate"));
                        }}
                    />
                )}



                {/* Standalone Admin Page */}
                {isAuthenticated && currentView === "admin" && (
                    <div className="view">
                        <div className="page-title-section page-title-dashboard">
                            <div className="page-title-heading">
                                <button className="md-button md-button-tonal md-button-icon" onClick={handleBackToDashboard}>
                                    <span className="material-symbols-outlined">arrow_back</span>
                                </button>
                                <h2>Admin Settings</h2>
                            </div>
                        </div>

                        {/* Tabs Navigation */}
                        <div className="md-tabs admin-tabs" role="tablist" aria-label="Admin sections">
                            <button
                                type="button"
                                className={`md-tab ${activeAdminTab === "profiles" ? "active" : ""}`}
                                role="tab"
                                aria-selected={activeAdminTab === "profiles"}
                                onClick={() => setActiveAdminTab("profiles")}
                            >
                                <span className="material-symbols-outlined">key</span> Credential Profiles
                            </button>
                            <button
                                type="button"
                                className={`md-tab ${activeAdminTab === "logs" ? "active" : ""}`}
                                role="tab"
                                aria-selected={activeAdminTab === "logs"}
                                onClick={() => setActiveAdminTab("logs")}
                            >
                                <span className="material-symbols-outlined">terminal</span> Activity Logs
                            </button>
                            <button
                                type="button"
                                className={`md-tab ${activeAdminTab === "backups" ? "active" : ""}`}
                                role="tab"
                                aria-selected={activeAdminTab === "backups"}
                                onClick={() => setActiveAdminTab("backups")}
                            >
                                <span className="material-symbols-outlined">backup</span> Configuration Backups
                            </button>
                            <button
                                type="button"
                                className={`md-tab ${activeAdminTab === "notes" ? "active" : ""}`}
                                role="tab"
                                aria-selected={activeAdminTab === "notes"}
                                onClick={() => setActiveAdminTab("notes")}
                            >
                                <span className="material-symbols-outlined">description</span> Admin Notes
                            </button>
                            <button
                                type="button"
                                className={`md-tab ${activeAdminTab === "maintenance" ? "active" : ""}`}
                                role="tab"
                                aria-selected={activeAdminTab === "maintenance"}
                                onClick={() => setActiveAdminTab("maintenance")}
                            >
                                <span className="material-symbols-outlined">delete_sweep</span> Disk Maintenance
                            </button>
                        </div>

                        {/* Tab Content: Credential Profiles */}
                        {activeAdminTab === "profiles" && (
                            <AdminProfilesTab
                                profiles={profiles}
                                loadingProfiles={loadingProfiles}
                                editingProfile={editingProfile}
                                profileTitle={profileTitle}
                                setProfileTitle={setProfileTitle}
                                profileHost={profileHost}
                                setProfileHost={setProfileHost}
                                profilePort={profilePort}
                                setProfilePort={setProfilePort}
                                profileUser={profileUser}
                                setProfileUser={setProfileUser}
                                profilePassword={profilePassword}
                                setProfilePassword={setProfilePassword}
                                profilePrivateKey={profilePrivateKey}
                                setProfilePrivateKey={setProfilePrivateKey}
                                sshAgentActive={sshAgentActive}
                                discoveredKeys={discoveredKeys}
                                selectedDiscoveredKey={selectedDiscoveredKey}
                                setSelectedDiscoveredKey={setSelectedDiscoveredKey}
                                sshConfigProfiles={sshConfigProfiles}
                                selectedSshProfile={selectedSshProfile}
                                loadingKeys={loadingKeys}
                                savingProfile={savingProfile}
                                handleSaveProfile={handleSaveProfile}
                                handleEditProfile={handleEditProfile}
                                handleDeleteProfile={handleDeleteProfile}
                                clearProfileForm={clearProfileForm}
                                handleStartSSHAgent={handleStartSSHAgent}
                                handleUseDiscoveredKeyPath={handleUseDiscoveredKeyPath}
                                handleApplySshProfile={handleApplySshProfile}
                                setEditingProfile={setEditingProfile}
                            />
                        )}

                        {/* Tab Content 1: Admin Notes */}
                        {activeAdminTab === "notes" && (
                            <div className="md-card admin-note-card">
                                {loadingNotes ? (
                                    <div>Loading notes...</div>
                                ) : (
                                    <div className="admin-note-body">
                                        <div className="form-group admin-note-group">
                                            <label htmlFor="admin_notes" className="admin-note-label">
                                                Useful Admin Notes (Versioned in config/admin_notes.txt)
                                            </label>
                                            <textarea
                                                id="admin_notes"
                                                className="form-control admin-note-textarea"
                                                placeholder="Write admin notes, emails, tags, etc. to be saved in config/admin_notes.txt"
                                                value={adminNotes}
                                                onChange={(e) => setAdminNotes(e.target.value)}
                                            />
                                        </div>
                                        <div className="admin-note-description">
                                            💡 Admin notes are stored as plaintext and versioned separately from the system settings.
                                        </div>
                                        <div className="modal-footer admin-note-footer">
                                            <button type="button" className="md-button md-button-tonal" onClick={handleBackToDashboard}>
                                                Cancel
                                            </button>
                                            <button
                                                type="button"
                                                className="md-button md-button-primary"
                                                disabled={savingNotes}
                                                onClick={handleSaveNotes}
                                            >
                                                {savingNotes ? "Saving..." : "Save Changes"}
                                            </button>
                                        </div>
                                    </div>
                                )}
                            </div>
                        )}

                        {/* Tab Content 2: Configuration Backups */}
                        {activeAdminTab === "backups" && (
                            <AdminBackupsTab
                                systemBackups={systemBackups}
                                loadingSystemBackups={loadingSystemBackups}
                                creatingSystemBackup={creatingSystemBackup}
                                restoringSystemBackup={restoringSystemBackup}
                                uploadingSystemBackup={uploadingSystemBackup}
                                handleCreateSystemBackup={handleCreateSystemBackup}
                                handleRestoreSystemBackup={handleRestoreSystemBackup}
                                handleDeleteSystemBackup={handleDeleteSystemBackup}
                                handleUploadSystemBackup={handleUploadSystemBackup}
                            />
                        )}

                        {/* Tab Content: Activity Logs */}
                        {activeAdminTab === "logs" && (
                            <div className="md-card admin-log-card">
                                <div className="admin-log-header">
                                    <div>
                                        <h3>System Activity & Event Logs</h3>
                                        <span className="admin-log-subtitle">
                                            View recorded system activities, status updates, process start/end indicators, and backend system logs.
                                        </span>
                                    </div>
                                    <div className="admin-log-toggle-group view-toggle-group" role="group" aria-label="Log source">
                                        <button 
                                            type="button"
                                            className={`md-button ${logSourceTab === "activity" ? "md-button-primary" : "md-button-outlined"}`}
                                            onClick={() => setLogSourceTab("activity")}
                                        >
                                            <span className="material-symbols-outlined">history</span> Activity History ({activityHistory.length})
                                        </button>
                                        <button 
                                            type="button"
                                            className={`md-button ${logSourceTab === "system" ? "md-button-primary" : "md-button-outlined"}`}
                                            onClick={() => {
                                                setLogSourceTab("system");
                                                handleLoadLogs();
                                            }}
                                        >
                                            <span className="material-symbols-outlined">terminal</span> System Log File
                                        </button>
                                    </div>
                                </div>

                                {/* Filters & Actions Row */}
                                <form onSubmit={(e) => { e.preventDefault(); if (logSourceTab === "system") handleLoadLogs(); }} className="log-filter-panel">
                                    <div className="log-filter-group log-filter-search">
                                        <label htmlFor="logsSearch">Search Filter</label>
                                        <input
                                            id="logsSearch"
                                            type="text"
                                            className="form-control"
                                            placeholder="Filter activity history or search terms..."
                                            value={logsSearchQuery}
                                            onChange={(e) => setLogsSearchQuery(e.target.value)}
                                        />
                                    </div>

                                    <div className="log-filter-group log-filter-select">
                                        <label htmlFor="logsLevel">Log Level</label>
                                        <select
                                            id="logsLevel"
                                            className="form-control"
                                            value={logsLevelFilter}
                                            onChange={(e) => setLogsLevelFilter(e.target.value)}
                                        >
                                            <option value="">All Levels</option>
                                            <option value="info">INFO / SUCCESS</option>
                                            <option value="warning">WARNING</option>
                                            <option value="error">ERROR</option>
                                            <option value="process">PROCESS</option>
                                        </select>
                                    </div>

                                    {logSourceTab === "system" && (
                                        <div className="log-filter-group log-filter-limit">
                                            <label htmlFor="logsLimit">Limit</label>
                                            <input
                                                id="logsLimit"
                                                type="number"
                                                className="form-control"
                                                min="10"
                                                max="1000"
                                                value={logsLimit}
                                                onChange={(e) => setLogsLimit(parseInt(e.target.value) || 200)}
                                            />
                                        </div>
                                    )}

                                    <div className="log-filter-actions">
                                        {logSourceTab === "system" ? (
                                            <>
                                                <button type="submit" className="md-button md-button-primary" disabled={loadingLogs}>
                                                    <span className="material-symbols-outlined">search</span> Fetch Logs
                                                </button>
                                                <button
                                                    type="button"
                                                    className="md-button md-button-outlined"
                                                    onClick={() => {
                                                        setLogsSearchQuery("");
                                                        setLogsLevelFilter("");
                                                        setLogsLimit(200);
                                                        setTimeout(() => handleLoadLogs(), 50);
                                                    }}
                                                    disabled={loadingLogs}
                                                >
                                                    Reset
                                                </button>
                                            </>
                                        ) : (
                                            <>
                                                <button
                                                    type="button"
                                                    className="md-button md-button-outlined"
                                                    onClick={() => {
                                                        setLogsSearchQuery("");
                                                        setLogsLevelFilter("");
                                                    }}
                                                >
                                                    Reset Filters
                                                </button>
                                                {activityHistory.length > 0 && (
                                                    <button
                                                        type="button"
                                                        className="md-button md-button-tonal md-button-destructive"
                                                        onClick={async () => {
                                                            const ok = await confirm({
                                                                title: "Clear activity history?",
                                                                message: "All locally recorded activity entries will be removed from this browser.",
                                                                confirmLabel: "Clear history",
                                                                destructive: true,
                                                            });
                                                            if (ok) {
                                                                setActivityHistory([]);
                                                                localStorage.removeItem("wp_mgr_activity_history");
                                                            }
                                                        }}
                                                    >
                                                        Clear Activity Logs
                                                    </button>
                                                )}
                                            </>
                                        )}
                                    </div>
                                </form>

                                {/* Activity History View */}
                                {logSourceTab === "activity" && (() => {
                                    const filtered = activityHistory.filter((item) => {
                                        if (logsLevelFilter) {
                                            const filterLower = logsLevelFilter.toLowerCase();
                                            if (filterLower === "info" && item.type !== "info" && item.type !== "success") return false;
                                            if (filterLower !== "info" && item.type !== filterLower) return false;
                                        }
                                        if (logsSearchQuery) {
                                            const queryLower = logsSearchQuery.toLowerCase();
                                            const msgLower = (item.message || "").toLowerCase();
                                            const titleLower = (item.title || "").toLowerCase();
                                            const detailsLower = (item.details || "").toLowerCase();
                                            if (!msgLower.includes(queryLower) && !titleLower.includes(queryLower) && !detailsLower.includes(queryLower)) {
                                                return false;
                                            }
                                        }
                                        return true;
                                    });

                                    return filtered.length === 0 ? (
                                        <div className="log-empty-state">
                                            No activity logs match the selected filter criteria.
                                        </div>
                                    ) : (
                                        <div className="log-list">
                                            {filtered.map((entry) => {
                                                let logLevelClass = "log-entry-info";
                                                if (entry.type === "success") logLevelClass = "log-entry-success";
                                                if (entry.type === "error") logLevelClass = "log-entry-error";
                                                if (entry.type === "warning") logLevelClass = "log-entry-warning";
                                                if (entry.type === "process") logLevelClass = "log-entry-process";

                                                return (
                                                    <div key={entry.id || Math.random()} className={`log-item ${logLevelClass}`}>
                                                        <div className="log-item-header">
                                                            <div className="log-entry-title">
                                                                <span className="log-entry-tag">{entry.type || "INFO"}</span>
                                                                {entry.title && (
                                                                    <span className="log-entry-summary">{entry.title}</span>
                                                                )}
                                                            </div>
                                                            <span className="log-entry-time">
                                                                {entry.timestamp ? new Date(entry.timestamp).toLocaleString() : "N/A"}
                                                            </span>
                                                        </div>
                                                        <div className="log-entry-message">{entry.message}</div>
                                                        {entry.details && (
                                                            <pre className="log-item-details">{entry.details}</pre>
                                                        )}
                                                    </div>
                                                );
                                            })}
                                        </div>
                                    );
                                })()}

                                {/* System Backend app.log File View */}
                                {logSourceTab === "system" && (
                                    loadingLogs ? (
                                        <div className="log-empty-state">Loading system logs...</div>
                                    ) : logsEntries.length === 0 ? (
                                        <div className="log-empty-state">No system log entries found matching criteria.</div>
                                    ) : (
                                        <div className="log-list system-log-list">
                                            {logsEntries.map((entry, index) => {
                                                const levelClass = entry.level === "ERROR" ? "system-log-item-error" : entry.level === "WARNING" ? "system-log-item-warning" : "system-log-item-normal";
                                                return (
                                                    <div key={index} className={`system-log-item ${levelClass}`}>
                                                        <span className="system-log-time">{entry.timestamp ? new Date(entry.timestamp).toLocaleString() : "N/A"}</span>
                                                        <span className="system-log-level">{entry.level}</span>
                                                        <span className="system-log-message">{entry.message}</span>
                                                    </div>
                                                );
                                            })}
                                        </div>
                                    )
                                )}
                            </div>
                        )}

                        {/* Tab Content 3: Disk Maintenance */}
                        {activeAdminTab === "maintenance" && (
                            <AdminMaintenanceTab
                                sites={sites}
                                handlePurgeHealthData={handlePurgeHealthData}
                            />
                        )}
                    </div>
                )}
                </ErrorBoundary>
            </main>

            {/* Alert Toasts Container */}
            <ToastContainer />

            {/* Destructive-action confirmation */}
            {confirmDialog}
        </div>
    );
}
