import React, { useState, useEffect } from "react";
import api from "../services/api";
import { showToast } from "../services/toast";
import AddSiteForm from "./AddSiteForm";
import { useConfirm } from "../hooks/useConfirm";

const MANAGE_SITES_TABS = ["discovered", "add", "configured"];

// Reads the active tab from the URL path (/manage-sites/{tab}), so tab state
// survives a refresh and Back/Forward move between tabs instead of exiting
// the whole view. Mirrors the ?tab= pattern in SiteDetails.jsx.
function tabFromLocation() {
    const match = window.location.pathname.match(/^\/manage-sites\/([^/]+)\/?$/);
    if (match && MANAGE_SITES_TABS.includes(match[1])) return match[1];
    return null;
}

export default function ManageSitesView({ initialTab = "discovered", onBackToDashboard, onSitesUpdated }) {
    const { confirm, confirmDialog } = useConfirm();
    const [activeTab, setActiveTabState] = useState(() => tabFromLocation() || initialTab); // "discovered", "add", "configured"

    const setActiveTab = (tabName) => {
        setActiveTabState(tabName);
        window.history.pushState({}, "", `/manage-sites/${tabName}`);
    };

    useEffect(() => {
        const syncTabFromUrl = () => {
            const tab = tabFromLocation();
            if (tab) setActiveTabState(tab);
        };
        window.addEventListener("popstate", syncTabFromUrl);
        return () => window.removeEventListener("popstate", syncTabFromUrl);
    }, []);

    // Configured Sites list state
    const [configuredSites, setConfiguredSites] = useState([]);
    const [loadingConfigured, setLoadingConfigured] = useState(false);
    const [statusFilter, setStatusFilter] = useState("all");
    const [configuredSearch, setConfiguredSearch] = useState("");

    // Discovered Scan Sites state
    const [scanLoading, setScanLoading] = useState(false);
    const [scans, setScans] = useState({});
    const [flatResults, setFlatResults] = useState([]);
    const [sshTargets, setSshTargets] = useState([]);
    const [selectedTarget, setSelectedTarget] = useState("all");
    const [searchRoot, setSearchRoot] = useState("");
    const [scanSearch, setScanSearch] = useState("");
    const [lastScanned, setLastScanned] = useState(null);
    const [isCached, setIsCached] = useState(false);
    const [selectedPaths, setSelectedPaths] = useState([]);
    const [bulkImporting, setBulkImporting] = useState(false);

    // Load configured sites from API
    const loadConfiguredSites = async () => {
        setLoadingConfigured(true);
        try {
            const data = await api.getSites();
            setConfiguredSites(data || []);
            if (onSitesUpdated) onSitesUpdated();
        } catch (err) {
            showToast(`Failed to load configured sites: ${err.message}`, "error");
        } finally {
            setLoadingConfigured(false);
        }
    };

    // Load server scan data
    const loadScanData = async (forceRescan = false, targetUser = null) => {
        setScanLoading(true);
        try {
            const reqPayload = {
                search_root: searchRoot || undefined,
                force_rescan: forceRescan,
                ssh_user: targetUser || (selectedTarget !== "all" ? selectedTarget : undefined)
            };
            const resp = await api.scanSites(reqPayload, true);
            
            setScans(resp.scans || {});
            setFlatResults(resp.data || []);
            setSshTargets(resp.ssh_targets || []);
            setLastScanned(resp.last_scanned || null);
            setIsCached(!!resp.cached);
            setSelectedPaths([]);

            const totalSites = resp.data ? resp.data.length : 0;
            showToast(
                forceRescan 
                    ? `Scan complete. Discovered ${totalSites} site(s).` 
                    : `Loaded ${totalSites} site(s) from scan cache.`, 
                "success"
            );
        } catch (err) {
            showToast(`Scan failed: ${err.message}`, "error");
        } finally {
            setScanLoading(false);
        }
    };

    useEffect(() => {
        loadConfiguredSites();
        if (activeTab === "discovered") {
            loadScanData(false);
        }
    }, [activeTab]);

    // Performs the import and lets errors propagate. handleImportDiscovered
    // wraps this for single-site use; bulk import needs the throw so it can
    // count real successes.
    const importDiscoveredSite = async (site) => {
        {
            const hasConnectionInfo = site.credential_profile || (site.ssh_host && site.ssh_user);
            const siteSlug = site.name.toLowerCase().replace(/[^a-z0-9]/g, "-").replace(/-+/g, "-").replace(/^-|-$/g, "") || "scanned-site";
            
            const newSiteData = {
                site_name: siteSlug,
                display_name: site.name,
                status: hasConnectionInfo ? "Ready" : "In Progress",
                wp_path: site.wp_path,
                health_check_url: site.url || "",
                ssh_host: site.ssh_host || undefined,
                ssh_user: site.ssh_user || undefined,
                ssh_port: site.ssh_port || 22,
                db_name: site.db_name || undefined,
                db_user: site.db_user || undefined,
                credential_profile: site.credential_profile || undefined,
                clone_credentials_from: site.baseline_site_name || undefined,
                creation_source: "auto_discovered",
                created_by: "Admin User"
            };

            await api.addSite(newSiteData);
        }
    };

    // Handle importing a single discovered site
    const handleImportDiscovered = async (site) => {
        try {
            await importDiscoveredSite(site);
            showToast(`Site '${site.name}' imported successfully!`, "success");
            await loadConfiguredSites();
            loadScanData(false);
        } catch (err) {
            showToast(`Import failed: ${err.message}`, "error");
        }
    };

    // Handle bulk import.
    //
    // This used to call handleImportDiscovered, which swallows its own errors
    // and never rethrows -- so the catch here could not fire and every item
    // counted as a success ("imported 10 site(s)" when 8 had failed). It also
    // reloaded the site list and re-ran the discovery scan once per item.
    const handleBulkImport = async (pathsToImport) => {
        if (!pathsToImport || pathsToImport.length === 0) return;
        setBulkImporting(true);
        const failures = [];
        let successCount = 0;
        try {
            for (const path of pathsToImport) {
                const site = flatResults.find(r => r.wp_path === path);
                if (!site || site.already_imported) continue;
                try {
                    await importDiscoveredSite(site);
                    successCount++;
                } catch (e) {
                    console.error("Bulk import item error:", e);
                    failures.push(`${site.name}: ${e.message}`);
                }
            }
        } finally {
            // Refresh once, after the whole batch.
            await loadConfiguredSites();
            loadScanData(false);
            setBulkImporting(false);
        }

        if (failures.length === 0) {
            showToast(`Bulk import complete: ${successCount} site(s) imported.`, "success");
        } else {
            showToast(
                `Bulk import finished with errors: ${successCount} imported, ${failures.length} failed.`,
                "error",
                { title: "Bulk import", details: failures.join(String.fromCharCode(10)) }
            );
        }
    };

    // Archive / Unarchive site status toggle
    const handleToggleArchive = async (site) => {
        const isArchived = site.status === "Archived";
        const newStatus = isArchived ? "Ready" : "Archived";
        const actionLabel = isArchived ? "Unarchive" : "Archive";

        const ok = await confirm({
            title: `${actionLabel} site?`,
            message: isArchived
                ? `"${site.display_name}" will return to Ready status and resume monitoring.`
                : `"${site.display_name}" will be archived and excluded from routine monitoring. You can unarchive it later.`,
            confirmLabel: actionLabel,
        });
        if (!ok) {
            return;
        }

        try {
            await api.updateSite(site.site_name, {
                ...site,
                status: newStatus
            });
            showToast(`Site '${site.display_name}' has been set to ${newStatus}.`, "success");
            loadConfiguredSites();
        } catch (err) {
            showToast(`Failed to update site status: ${err.message}`, "error");
        }
    };

    // Delete site permanently
    const handleDeleteConfiguredSite = async (site) => {
        const ok = await confirm({
            title: "Permanently delete this site?",
            message: `"${site.display_name}" will be removed from Site Manager along with its configuration and stored credentials. This cannot be undone.`,
            requireTyped: site.site_name,
            confirmLabel: "Delete site",
            destructive: true,
        });
        if (!ok) {
            return;
        }

        try {
            await api.deleteSite(site.site_name);
            showToast(`Site '${site.display_name}' was successfully deleted.`, "success");
            loadConfiguredSites();
            if (activeTab === "discovered") {
                loadScanData(false);
            }
        } catch (err) {
            showToast(`Failed to delete site: ${err.message}`, "error");
        }
    };

    const toggleSelectSite = (path) => {
        if (selectedPaths.includes(path)) {
            setSelectedPaths(selectedPaths.filter(p => p !== path));
        } else {
            setSelectedPaths([...selectedPaths, path]);
        }
    };

    const toggleSelectGroup = (groupSites) => {
        const unimportedGroupPaths = groupSites.filter(s => !s.already_imported).map(s => s.wp_path);
        const allSelected = unimportedGroupPaths.every(p => selectedPaths.includes(p));

        if (allSelected) {
            setSelectedPaths(selectedPaths.filter(p => !unimportedGroupPaths.includes(p)));
        } else {
            const combined = new Set([...selectedPaths, ...unimportedGroupPaths]);
            setSelectedPaths(Array.from(combined));
        }
    };

    // Filter discovered scan results
    const groupedUserKeys = Object.keys(scans).filter(userKey => {
        if (selectedTarget !== "all" && userKey !== selectedTarget) {
            return false;
        }
        return true;
    });

    // Filter configured sites
    const filteredConfiguredSites = configuredSites.filter(s => {
        if (statusFilter !== "all" && s.status !== statusFilter) return false;
        if (configuredSearch) {
            const term = configuredSearch.toLowerCase();
            return (
                (s.display_name && s.display_name.toLowerCase().includes(term)) ||
                (s.site_name && s.site_name.toLowerCase().includes(term)) ||
                (s.health_check_url && s.health_check_url.toLowerCase().includes(term)) ||
                (s.wp_path && s.wp_path.toLowerCase().includes(term)) ||
                (s.ssh_user && s.ssh_user.toLowerCase().includes(term)) ||
                (s.credential_profile && s.credential_profile.toLowerCase().includes(term))
            );
        }
        return true;
    });

    return (
        <div className="manage-sites-container">
            {confirmDialog}
            
            {/* Top Navigation Header */}
            <div className="manage-sites-header">
                <div>
                    <div className="manage-sites-title-row">
                        <button className="md-button md-button-outlined manage-sites-back" onClick={onBackToDashboard}>
                            <span className="material-symbols-outlined">arrow_back</span> Dashboard
                        </button>
                        <h2 className="manage-sites-title">
                            <span className="material-symbols-outlined manage-sites-title-icon">tune</span>
                            Manage Sites Hub
                        </h2>
                    </div>
                    <p className="manage-sites-description">
                        Discover server WordPress sites by SSH account, manually add new sites, or manage existing configured sites.
                    </p>
                </div>
            </div>

            {/* Sub-Nav Tabs */}
            <div className="md-tabs manage-sites-tabs" role="tablist" aria-label="Manage sites sections">
                <button 
                    className={`md-tab ${activeTab === "discovered" ? "active" : ""}`}
                    role="tab"
                    aria-selected={activeTab === "discovered"}
                    onClick={() => setActiveTab("discovered")}
                >
                    <span className="material-symbols-outlined">radar</span> Discovered / Scan Sites
                </button>

                <button 
                    className={`md-tab ${activeTab === "add" ? "active" : ""}`}
                    role="tab"
                    aria-selected={activeTab === "add"}
                    onClick={() => setActiveTab("add")}
                >
                    <span className="material-symbols-outlined">add_circle</span> Add Site Manually
                </button>

                <button 
                    className={`md-tab ${activeTab === "configured" ? "active" : ""}`}
                    role="tab"
                    aria-selected={activeTab === "configured"}
                    onClick={() => setActiveTab("configured")}
                >
                    <span className="material-symbols-outlined">inventory_2</span> Configured Sites ({configuredSites.length})
                </button>
            </div>

            {/* TAB 1: DISCOVERED / SCAN SITES */}
            {activeTab === "discovered" && (
                <div>
                    {/* Scan Toolbar */}
                    <div className="scan-toolbar-panel">
                        <div className="scan-toolbar-row">
                            
                            {/* SSH Target Selector */}
                            <div className="scan-toolbar-field">
                                <label className="scan-toolbar-label">
                                    Target SSH Account
                                </label>
                                <select 
                                    value={selectedTarget} 
                                    onChange={(e) => setSelectedTarget(e.target.value)}
                                    className="form-control"
                                >
                                    <option value="all">All Connected SSH Users & Profiles</option>
                                    {sshTargets.map((t, idx) => (
                                        <option key={idx} value={t.ssh_user || t.credential_profile}>
                                            👤 {t.ssh_user || t.credential_profile} ({t.ssh_host || "localhost"})
                                        </option>
                                    ))}
                                </select>
                            </div>

                            {/* Search Root Input */}
                            <div className="scan-toolbar-field wide-field">
                                <label className="scan-toolbar-label">
                                    Custom Search Root Path (Optional)
                                </label>
                                <input 
                                    type="text" 
                                    placeholder="e.g. /home/username or $HOME"
                                    value={searchRoot}
                                    onChange={(e) => setSearchRoot(e.target.value)}
                                    className="form-control"
                                />
                            </div>

                            {/* Scan Button */}
                            <div className="toolbar-action">
                                <button className="md-button md-button-primary" onClick={() => loadScanData(true)} disabled={scanLoading}>
                                    <span className="material-symbols-outlined">sync</span> {scanLoading ? "Scanning Server..." : "Run Server Discovery Scan"}
                                </button>
                            </div>
                        </div>

                        {/* Search Filter Row */}
                        <div className="scan-filter-row">
                            <div className="scan-filter-group">
                                <span className="material-symbols-outlined scan-filter-icon">search</span>
                                <input 
                                    type="text" 
                                    placeholder="Filter discovered sites by name, domain, path..." 
                                    value={scanSearch}
                                    onChange={(e) => setScanSearch(e.target.value)}
                                    className="form-control"
                                />
                            </div>

                            {lastScanned && (
                                <span className="scan-status-text">
                                    {isCached ? "📁 Cached scan history: " : "⚡ Fresh scan timestamp: "}
                                    <strong>{new Date(lastScanned).toLocaleString()}</strong>
                                </span>
                            )}
                        </div>
                    </div>

                    {/* Loading State */}
                    {scanLoading && (
                        <div className="status-panel">
                            <span className="material-symbols-outlined status-panel-icon spin">progress_activity</span>
                            <p className="status-panel-copy">
                                Scanning server directories for WordPress <code>wp-config.php</code> files...
                            </p>
                        </div>
                    )}

                    {/* Empty State */}
                    {!scanLoading && groupedUserKeys.length === 0 && (
                        <div className="status-panel status-panel-empty">
                            <span className="material-symbols-outlined status-panel-empty-icon">travel_explore</span>
                            <h4 className="status-panel-empty-title">No discovered sites in scan history.</h4>
                            <p className="status-panel-empty-copy">
                                Click "Run Server Discovery Scan" above to discover WordPress installations under your SSH accounts.
                            </p>
                        </div>
                    )}

                    {/* Grouped Sites by SSH User */}
                    {!scanLoading && groupedUserKeys.map((userKey) => {
                        const group = scans[userKey];
                        if (!group) return null;

                        const allDiscovered = group.discovered || [];
                        const filteredSites = allDiscovered.filter(s => {
                            if (!scanSearch) return true;
                            const term = scanSearch.toLowerCase();
                            return (
                                (s.name && s.name.toLowerCase().includes(term)) ||
                                (s.wp_path && s.wp_path.toLowerCase().includes(term)) ||
                                (s.url && s.url.toLowerCase().includes(term))
                            );
                        });

                        if (filteredSites.length === 0 && scanSearch) return null;

                        const unimportedSites = filteredSites.filter(s => !s.already_imported);
                        const groupSelectedCount = unimportedSites.filter(s => selectedPaths.includes(s.wp_path)).length;
                        const allUnimportedSelected = unimportedSites.length > 0 && groupSelectedCount === unimportedSites.length;

                        return (
                            <div key={userKey} className="site-group-card">
                                
                                {/* Group Header */}
                                <div className="site-group-header">
                                    <div className="site-group-meta">
                                        <span className="material-symbols-outlined site-group-icon">person</span>
                                        <strong className="site-group-title">SSH User Account: <code>{group.ssh_user || userKey}</code></strong>
                                        {group.ssh_host && (
                                            <span className="site-group-subtitle">
                                                ({group.ssh_host})
                                            </span>
                                        )}
                                        {group.credential_profile && (
                                            <span className="badge badge-neutral site-group-badge">
                                                Profile: {group.credential_profile}
                                            </span>
                                        )}
                                    </div>

                                    <div className="site-group-actions">
                                        <span className="site-group-count">
                                            {filteredSites.length} site(s) total ({unimportedSites.length} unimported)
                                        </span>
                                        {unimportedSites.length > 0 && (
                                            <button 
                                                className="md-button md-button-primary compact-button"
                                                onClick={() => handleBulkImport(unimportedSites.filter(s => selectedPaths.includes(s.wp_path)).map(s => s.wp_path))}
                                                disabled={groupSelectedCount === 0 || bulkImporting}
                                            >
                                                Import Selected ({groupSelectedCount})
                                            </button>
                                        )}
                                    </div>
                                </div>

                                {/* Table */}
                                <div className="site-table-wrapper">
                                    <table className="md-table site-table">
                                        <thead>
                                            <tr>
                                                <th className="site-table-col-checkbox">
                                                    {unimportedSites.length > 0 && (
                                                        <input 
                                                            type="checkbox" 
                                                            checked={allUnimportedSelected}
                                                            onChange={() => toggleSelectGroup(filteredSites)} 
                                                            title="Select all unimported sites in this group"
                                                        />
                                                    )}
                                                </th>
                                                <th>Site Title & Domain</th>
                                                <th>WordPress Directory Path</th>
                                                <th className="site-table-col-center">Status</th>
                                                <th className="site-table-col-action">Action</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {filteredSites.map((s, idx) => (
                                                <tr key={idx} className={`site-table-row ${s.already_imported ? "site-table-row--imported" : ""}`}>
                                                    <td className="site-table-cell site-table-cell-center">
                                                        {!s.already_imported && (
                                                            <input 
                                                                type="checkbox" 
                                                                checked={selectedPaths.includes(s.wp_path)} 
                                                                onChange={() => toggleSelectSite(s.wp_path)} 
                                                            />
                                                        )}
                                                    </td>
                                                    <td className="site-table-cell">
                                                        <strong className="site-table-name">{s.name}</strong>
                                                        {s.url ? (
                                                            <a href={s.url} target="_blank" rel="noopener noreferrer" className="site-link">
                                                                {s.url}
                                                            </a>
                                                        ) : (
                                                            <span className="site-table-muted">No URL detected</span>
                                                        )}
                                                    </td>
                                                    <td className="site-table-cell site-table-code">
                                                        {s.wp_path}
                                                    </td>
                                                    <td className="site-table-cell site-table-cell-center">
                                                        {s.already_imported ? (
                                                            <span className="badge badge-success site-status-badge" title={`Configured as ${s.existing_site_name}`}>
                                                                ✓ Configured ({s.existing_site_name})
                                                            </span>
                                                        ) : (
                                                            <span className="badge badge-info site-status-badge">
                                                                Ready to Import
                                                            </span>
                                                        )}
                                                    </td>
                                                    <td className="site-table-cell site-table-cell-right">
                                                        {s.already_imported ? (
                                                            <button className="md-button md-button-outlined compact-button compact-disabled" disabled>
                                                                Imported
                                                            </button>
                                                        ) : (
                                                            <button className="md-button md-button-outlined compact-button" onClick={() => handleImportDiscovered(s)}>
                                                                Import
                                                            </button>
                                                        )}
                                                    </td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                        );
                    })}
                </div>
            )}

            {/* TAB 2: ADD SITE MANUALLY */}
            {activeTab === "add" && (
                <div className="panel-card">
                    <AddSiteForm 
                        onCancel={() => setActiveTab("configured")}
                        onSuccess={() => {
                            loadConfiguredSites();
                            setActiveTab("configured");
                        }}
                    />
                </div>
            )}

            {/* TAB 3: CONFIGURED SITES (ARCHIVE & DELETE) */}
            {activeTab === "configured" && (
                <div>
                    {/* Filter Toolbar */}
                    <div className="configured-toolbar">
                        {/* Search Input */}
                        <div className="configured-search-field">
                            <span className="material-symbols-outlined configured-search-icon">search</span>
                            <input 
                                type="text" 
                                placeholder="Search configured sites by name, domain, path, user..."
                                value={configuredSearch}
                                onChange={(e) => setConfiguredSearch(e.target.value)}
                                className="form-control"
                            />
                        </div>

                        {/* Status Filter */}
                        <div className="configured-filter-field">
                            <label className="configured-filter-label">Status:</label>
                            <select 
                                value={statusFilter}
                                onChange={(e) => setStatusFilter(e.target.value)}
                                className="form-control"
                            >
                                <option value="all">All Statuses ({configuredSites.length})</option>
                                <option value="Ready">Ready ({configuredSites.filter(s => s.status === "Ready").length})</option>
                                <option value="In Progress">In Progress ({configuredSites.filter(s => s.status === "In Progress").length})</option>
                                <option value="Archived">Archived ({configuredSites.filter(s => s.status === "Archived").length})</option>
                            </select>
                        </div>
                    </div>

                    {/* Loading State */}
                    {loadingConfigured && (
                        <div className="status-panel status-panel-loading">
                            <span className="material-symbols-outlined status-panel-icon spin">progress_activity</span>
                        </div>
                    )}

                    {/* Configured Sites Table */}
                    {!loadingConfigured && (
                        <div className="site-table-wrapper">
                            <table className="md-table site-table">
                                <thead>
                                    <tr>
                                        <th>Site Title & Slug</th>
                                        <th>Health URL / Domain</th>
                                        <th className="site-table-col-center">Status</th>
                                        <th>Connection / Directory</th>
                                        <th className="site-table-col-action">Actions</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {filteredConfiguredSites.length === 0 ? (
                                        <tr>
                                            <td colSpan="5" className="empty-table-message">
                                                No configured sites match your criteria.
                                            </td>
                                        </tr>
                                    ) : (
                                        filteredConfiguredSites.map((site) => {
                                            const isArchived = site.status === "Archived";
                                            return (
                                                <tr key={site.site_name} className={`site-table-row ${isArchived ? "site-table-row--archived" : ""}`}>
                                                    <td className="site-table-cell">
                                                        <strong className="site-table-name">{site.display_name}</strong>
                                                        <code className="site-table-meta">{site.site_name}</code>
                                                    </td>
                                                    <td className="site-table-cell">
                                                        {site.health_check_url ? (
                                                            <a href={site.health_check_url} target="_blank" rel="noopener noreferrer" className="site-link">
                                                                {site.health_check_url}
                                                            </a>
                                                        ) : (
                                                            <span className="site-table-muted">Not configured</span>
                                                        )}
                                                    </td>
                                                    <td className="site-table-cell site-table-cell-center">
                                                        <span 
                                                            className={`badge ${site.status === "Ready" ? "badge-success" : site.status === "Archived" ? "badge-neutral" : "badge-warning"} site-status-badge`}
                                                        >
                                                            {site.status || "Unknown"}
                                                        </span>
                                                    </td>
                                                    <td className="site-table-cell site-table-code">
                                                        <div>
                                                            👤 <strong>{site.ssh_user || site.credential_profile || "local"}</strong>
                                                            {site.ssh_host && <span className="site-table-muted"> ({site.ssh_host})</span>}
                                                        </div>
                                                        <div className="site-table-path">
                                                            {site.wp_path}
                                                        </div>
                                                    </td>
                                                    <td className="site-table-cell site-table-cell-right">
                                                        <div className="action-button-group">
                                                            {/* Archive / Unarchive Button */}
                                                            <button 
                                                                className="md-button md-button-outlined compact-button"
                                                                onClick={() => handleToggleArchive(site)}
                                                                title={isArchived ? "Restore site to Ready status" : "Archive site"}
                                                            >
                                                                <span className="material-symbols-outlined action-button-icon">{isArchived ? "unarchive" : "archive"}</span>
                                                                {isArchived ? "Unarchive" : "Archive"}
                                                            </button>

                                                            {/* Edit Button */}
                                                            <button 
                                                                className="md-button md-button-outlined compact-button"
                                                                onClick={() => {
                                                                    window.history.pushState({}, "", `/site/${site.site_name}/edit`);
                                                                    window.dispatchEvent(new Event("popstate"));
                                                                }}
                                                                title="Edit site details"
                                                            >
                                                                <span className="material-symbols-outlined action-button-icon">edit</span>
                                                                Edit
                                                            </button>

                                                            {/* Delete Button */}
                                                            <button 
                                                                className="md-button md-button-tonal compact-button md-button-danger"
                                                                onClick={() => handleDeleteConfiguredSite(site)}
                                                                title="Delete site configuration"
                                                            >
                                                                <span className="material-symbols-outlined action-button-icon">delete</span>
                                                                Delete
                                                            </button>
                                                        </div>
                                                    </td>
                                                </tr>
                                            );
                                        })
                                    )}
                                </tbody>
                            </table>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}
