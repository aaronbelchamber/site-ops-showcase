import React, { useState, useEffect } from "react";
import api from "../services/api";
import { showToast } from "../services/toast";

export default function ScanSitesModal({ isOpen, onClose, onSiteAdded }) {
    const [loading, setLoading] = useState(false);
    const [scans, setScans] = useState({});
    const [flatResults, setFlatResults] = useState([]);
    const [sshTargets, setSshTargets] = useState([]);
    const [selectedTarget, setSelectedTarget] = useState("all");
    const [searchRoot, setSearchRoot] = useState("");
    const [searchTerm, setSearchTerm] = useState("");
    const [lastScanned, setLastScanned] = useState(null);
    const [isCached, setIsCached] = useState(false);
    const [selectedPaths, setSelectedPaths] = useState([]);
    const [bulkImporting, setBulkImporting] = useState(false);

    const loadScanData = async (forceRescan = false, targetUser = null) => {
        setLoading(true);
        try {
            const reqPayload = {
                search_root: searchRoot || undefined,
                force_rescan: forceRescan,
                ssh_user: targetUser || (selectedTarget !== "all" ? selectedTarget : undefined)
            };
            const resp = await api.scanSites(reqPayload, true);
            
            const returnedScans = resp.scans || {};
            setScans(returnedScans);
            setFlatResults(resp.data || []);
            setSshTargets(resp.ssh_targets || []);
            setLastScanned(resp.last_scanned || null);
            setIsCached(!!resp.cached);
            setSelectedPaths([]);

            const totalSites = resp.data ? resp.data.length : 0;
            showToast(
                forceRescan 
                    ? `Scan complete. Found ${totalSites} site(s) across accounts.` 
                    : `Loaded ${totalSites} site(s) from scan history.`, 
                "success"
            );
        } catch (err) {
            showToast(`Scan failed: ${err.message}`, "error");
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        if (isOpen) {
            loadScanData(false);
        }
    }, [isOpen]);

    const handleImport = async (site) => {
        try {
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
            showToast(`Site '${site.name}' imported successfully!`, "success");
            loadScanData(false); // Refresh scan list to update already_imported status
            if (onSiteAdded) onSiteAdded();
        } catch (err) {
            showToast(`Import failed: ${err.message}`, "error");
        }
    };

    const handleBulkImport = async (pathsToImport) => {
        if (!pathsToImport || pathsToImport.length === 0) return;
        setBulkImporting(true);
        let successCount = 0;
        for (const path of pathsToImport) {
            const site = flatResults.find(r => r.wp_path === path);
            if (site && !site.already_imported) {
                try {
                    await handleImport(site);
                    successCount++;
                } catch (e) {
                    console.error("Bulk import item error:", e);
                }
            }
        }
        setBulkImporting(false);
        showToast(`Bulk import completed. Imported ${successCount} site(s).`, "success");
        if (onSiteAdded) onSiteAdded();
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

    if (!isOpen) return null;

    // Filter scans based on target selector & search term
    const groupedUserKeys = Object.keys(scans).filter(userKey => {
        if (selectedTarget !== "all" && userKey !== selectedTarget) {
            return false;
        }
        return true;
    });

    return (
        <div className="modal-backdrop">
            <div className="modal-card">
                
                {/* Modal Header */}
                <div className="modal-header">
                    <div>
                        <div className="modal-title-row">
                            <span className="material-symbols-outlined modal-title-icon">radar</span>
                            <div>
                                <h3 className="modal-title">Discovered WordPress Sites</h3>
                                <p className="modal-subtitle">WordPress installations found on your server, organized by SSH User Account.</p>
                            </div>
                        </div>
                    </div>
                    <button className="md-button md-button-tonal modal-close-button" onClick={onClose}>
                        <span className="material-symbols-outlined">close</span>
                    </button>
                </div>

                {/* Scan Toolbar */}
                <div className="modal-toolbar-panel">
                    <div className="modal-toolbar-row">
                        {/* Target SSH User Dropdown */}
                        <div className="modal-toolbar-field">
                            <label>Target SSH User / Account</label>
                            <select 
                                value={selectedTarget} 
                                onChange={(e) => setSelectedTarget(e.target.value)}
                                className="form-control"
                            >
                                <option value="all">All SSH Users & Accounts</option>
                                {sshTargets.map((t, idx) => (
                                    <option key={idx} value={t.ssh_user || t.credential_profile}>
                                        👤 {t.ssh_user || t.credential_profile} ({t.ssh_host || "localhost"})
                                    </option>
                                ))}
                            </select>
                        </div>

                        {/* Search Root Input */}
                        <div className="modal-toolbar-field modal-toolbar-fieldwide">
                            <label>Search Root Path (Optional)</label>
                            <input 
                                type="text" 
                                placeholder="e.g. /home/username or $HOME"
                                value={searchRoot}
                                onChange={(e) => setSearchRoot(e.target.value)}
                                className="form-control"
                            />
                        </div>

                        {/* Scan Action Button */}
                        <div className="modal-toolbar-action">
                            <button className="md-button md-button-primary" onClick={() => loadScanData(true)} disabled={loading}>
                                <span className="material-symbols-outlined">sync</span> {loading ? "Scanning..." : "Scan Account(s)"}
                            </button>
                        </div>
                    </div>

                    {/* Search & Timestamp Filter Row */}
                    <div className="modal-filter-row">
                        <div className="modal-filter-group">
                            <span className="material-symbols-outlined modal-filter-icon">search</span>
                            <input 
                                type="text" 
                                placeholder="Filter discovered sites by name, domain, path..." 
                                value={searchTerm}
                                onChange={(e) => setSearchTerm(e.target.value)}
                                className="form-control"
                            />
                        </div>

                        {lastScanned && (
                            <span className="modal-filter-status">
                                {isCached ? "📁 Cached scan history: " : "⚡ Fresh scan timestamp: "}
                                <strong>{new Date(lastScanned).toLocaleString()}</strong>
                            </span>
                        )}
                    </div>
                </div>

                {/* Loading State */}
                {loading && (
                    <div className="modal-state-panel">
                        <span className="material-symbols-outlined status-panel-icon spin">progress_activity</span>
                        <p className="modal-state-copy">
                            Scanning target server directories for <code>wp-config.php</code> files...
                        </p>
                    </div>
                )}

                {/* Empty State */}
                {!loading && groupedUserKeys.length === 0 && (
                    <div className="modal-state-panel modal-state-empty">
                        <span className="material-symbols-outlined modal-state-icon">travel_explore</span>
                        <p className="modal-state-title">No scanned site data found.</p>
                        <p className="modal-state-copy">
                            Click "Scan Account(s)" above to run server site discovery for your SSH accounts.
                        </p>
                    </div>
                )}

                {/* Grouped Sites by SSH User */}
                {!loading && groupedUserKeys.map((userKey) => {
                    const group = scans[userKey];
                    if (!group) return null;

                    const allDiscovered = group.discovered || [];
                    const filteredSites = allDiscovered.filter(s => {
                        if (!searchTerm) return true;
                        const term = searchTerm.toLowerCase();
                        return (
                            (s.name && s.name.toLowerCase().includes(term)) ||
                            (s.wp_path && s.wp_path.toLowerCase().includes(term)) ||
                            (s.url && s.url.toLowerCase().includes(term))
                        );
                    });

                    if (filteredSites.length === 0 && searchTerm) return null;

                    const unimportedSites = filteredSites.filter(s => !s.already_imported);
                    const groupSelectedCount = unimportedSites.filter(s => selectedPaths.includes(s.wp_path)).length;
                    const allUnimportedSelected = unimportedSites.length > 0 && groupSelectedCount === unimportedSites.length;

                    return (
                        <div key={userKey} className="scan-group-card">
                            {/* Group Header */}
                            <div className="scan-group-header">
                                <div className="scan-group-meta">
                                    <span className="material-symbols-outlined scan-group-icon">person</span>
                                    <strong className="scan-group-title">SSH User: <code>{group.ssh_user || userKey}</code></strong>
                                    {group.ssh_host && (
                                        <span className="scan-group-subtitle">({group.ssh_host})</span>
                                    )}
                                    {group.credential_profile && (
                                        <span className="badge badge-neutral badge-neutral-profile">
                                            Profile: {group.credential_profile}
                                        </span>
                                    )}
                                </div>

                                <div className="scan-group-actions">
                                    <span className="scan-group-info">
                                        {filteredSites.length} site(s) total ({unimportedSites.length} new)
                                    </span>
                                    {unimportedSites.length > 0 && (
                                        <button 
                                            className="md-button md-button-tonal scan-group-button"
                                            onClick={() => handleBulkImport(unimportedSites.filter(s => selectedPaths.includes(s.wp_path)).map(s => s.wp_path))}
                                            disabled={groupSelectedCount === 0 || bulkImporting}
                                        >
                                            Import Selected ({groupSelectedCount})
                                        </button>
                                    )}
                                </div>
                            </div>

                            {/* Sites Table */}
                            <div className="modal-table-wrapper">
                                <table className="md-table site-table">
                                    <thead>
                                        <tr>
                                            <th className="site-table-col-checkbox">
                                                {unimportedSites.length > 0 && (
                                                    <input 
                                                        type="checkbox" 
                                                        checked={allUnimportedSelected}
                                                        onChange={() => toggleSelectGroup(filteredSites)} 
                                                        title="Select all new sites in this group"
                                                    />
                                                )}
                                            </th>
                                            <th>Site Name & URL</th>
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
                                                        <a href={s.url} target="_blank" rel="noopener noreferrer" className="site-table-link">
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
                                                        <span className="badge badge-success site-status-badge" title={`Already configured as ${s.existing_site_name}`}>
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
                                                        <button className="md-button md-button-outlined compact-button" onClick={() => handleImport(s)}>
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

                {/* Modal Footer */}
                <div className="modal-footer">
                    <button className="md-button md-button-outlined" onClick={onClose}>Close</button>
                </div>
            </div>
        </div>
    );
}
