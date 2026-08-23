import React, { useState, useEffect } from "react";
import api from "../services/api";
import { showToast } from "../services/toast";
import { useSitesContext } from "../context/SitesContext";
import {
    getDaysSinceLastUpdateCheck,
    getLastCheckedLabel as getLastCheckedLabelFor,
    getUpdateStalenessTooltip as getUpdateStalenessTooltipFor,
    getStatusDotClass as getStatusDotClassFor,
    getHealthBadgeClass,
} from "../utils/siteStaleness";

export default function SiteCard({ site, viewMode = "grid", onViewDetails }) {
    const sitesContext = useSitesContext();
    const contextUpdates = sitesContext?.updatesBySite?.[site.site_name];
    const isCheckingUpdates = Boolean(sitesContext?.inFlightChecks?.has(site.site_name));

    const [healthStatus, setHealthStatus] = useState("Loading");
    const [loadingHealth, setLoadingHealth] = useState(false);
    const [latestCheckId, setLatestCheckId] = useState(null);
    const [latestSnapshot, setLatestSnapshot] = useState(null);
    const [updateInfo, setUpdateInfo] = useState(contextUpdates || site.update_summary || null);
    const [screenshotUrl, setScreenshotUrl] = useState(null);
    const [capturingSnapshot, setCapturingSnapshot] = useState(false);

    // Sync from context when context updates
    useEffect(() => {
        if (contextUpdates) {
            setUpdateInfo(contextUpdates);
        }
    }, [contextUpdates]);

    const fetchHealth = async (forceCheck = false) => {
        setLoadingHealth(true);
        if (forceCheck) {
            setHealthStatus("CHECKING...");
        }
        try {
            let report;
            if (forceCheck) {
                report = await api.runHealthCheck(site.site_name);
                if (report && report.id) {
                    setLatestCheckId(report.id);
                }
                showToast(`Health check complete for ${site.display_name}`, "success");
            } else {
                const history = await api.getHealthHistory(site.site_name);
                if (history && history.length > 0) {
                    report = history[0];
                } else {
                    report = await api.runHealthCheck(site.site_name);
                }
            }

            const statusVal = report ? (report.overall_status || report.status) : null;
            if (statusVal) {
                const lower = statusVal.toLowerCase();
                if (lower === "healthy with exception") {
                    setHealthStatus("HEALTHY*");
                } else {
                    setHealthStatus(statusVal.toUpperCase());
                }
            } else {
                setHealthStatus("UNKNOWN");
            }
        } catch (error) {
            console.error("Health check failed:", error);
            setHealthStatus("ERROR");
        } finally {
            setLoadingHealth(false);
        }
    };

    useEffect(() => {
        fetchHealth(false);
    }, [site.site_name, site.status]);

    // Auto-backfill screenshot flow if snapshot or screenshot missing
    useEffect(() => {
        let cancelled = false;
        const fetchSnapshot = async () => {
            try {
                let snapshot = await api.getLatestSnapshot(site.site_name);
                const hasDesktopScreenshot = snapshot?.checks?.http?.screenshots?.desktop && snapshot?.id;

                if (!snapshot || !hasDesktopScreenshot) {
                    if (!cancelled) setCapturingSnapshot(true);
                    try {
                        const report = await api.runHealthCheck(site.site_name);
                        if (report && report.id) {
                            snapshot = report;
                        } else {
                            snapshot = await api.getLatestSnapshot(site.site_name);
                        }
                    } catch (e) {
                        console.debug("Auto backfill health check failed for", site.site_name, e);
                    } finally {
                        if (!cancelled) setCapturingSnapshot(false);
                    }
                }

                if (!cancelled && snapshot) {
                    setLatestSnapshot(snapshot);
                }
            } catch (error) {
                console.debug("No snapshot available for", site.site_name, error);
            }
        };
        fetchSnapshot();
        return () => { cancelled = true; };
    }, [site.site_name]);

    useEffect(() => {
        if (site.update_summary) {
            setUpdateInfo(site.update_summary);
            if (sitesContext?.setSiteUpdates) {
                sitesContext.setSiteUpdates(site.site_name, site.update_summary);
            }
        }
        const fetchUpdatesInfo = async () => {
            try {
                const data = await api.checkUpdates(site.site_name, false);
                if (data) {
                    setUpdateInfo(data);
                    if (sitesContext?.setSiteUpdates) {
                        sitesContext.setSiteUpdates(site.site_name, data);
                    }
                }
            } catch (error) {
                console.debug("No cached update info available for", site.site_name, error);
            }
        };
        if (!contextUpdates) {
            fetchUpdatesInfo();
        }
    }, [site.site_name, site.update_summary]);

    // Load screenshot via authenticated blob request
    useEffect(() => {
        let cancelled = false;
        let createdUrl = null;

        const loadScreenshotBlob = async () => {
            if (latestSnapshot?.checks?.http?.screenshots?.desktop && latestSnapshot?.id) {
                try {
                    const blob = await api.getScreenshotBlob(site.site_name, latestSnapshot.id, "desktop");
                    if (!cancelled) {
                        createdUrl = URL.createObjectURL(blob);
                        setScreenshotUrl(createdUrl);
                    }
                } catch (e) {
                    console.debug("Failed to load screenshot blob for", site.site_name, e);
                    if (!cancelled) setScreenshotUrl(null);
                }
            } else {
                if (!cancelled) setScreenshotUrl(null);
            }
        };

        loadScreenshotBlob();

        return () => {
            cancelled = true;
            if (createdUrl) {
                URL.revokeObjectURL(createdUrl);
            }
        };
    }, [latestSnapshot, site.site_name]);

    // Staleness calculations
    const daysSinceCheck = getDaysSinceLastUpdateCheck(updateInfo);
    const getLastCheckedLabel = () => getLastCheckedLabelFor(updateInfo);
    const getUpdateStalenessTooltip = () => getUpdateStalenessTooltipFor(updateInfo);
    const getStatusDotClass = () => getStatusDotClassFor(updateInfo);

    // All other tags are smaller & lowercase
    const renderVulnerabilityStatus = () => {
        const status = site.vulnerability_status;
        if (!status) {
            return <span className="badge badge-sm badge-lowercase badge-neutral" title="No vulnerability scan history">no scan</span>;
        }
        if (status === "green") {
            return <span className="badge badge-sm badge-lowercase badge-success" title="Clean - No vulnerabilities detected">clean</span>;
        }
        if (status === "yellow") {
            return <span className="badge badge-sm badge-lowercase badge-warning" title="WP-CLI Vulnerability extension missing or check incomplete">vuln pkg missing</span>;
        }
        if (status === "red") {
            return <span className="badge badge-sm badge-lowercase badge-error" title="Security vulnerabilities detected!">vulnerable</span>;
        }
        return <span className="badge badge-sm badge-lowercase badge-neutral">{status.toLowerCase()}</span>;
    };

    const renderUpdateStatus = () => {
        if (isCheckingUpdates) {
            return (
                <span className="badge badge-sm badge-lowercase badge-info" title="Background update check in progress">
                    <span className="material-symbols-outlined spin-icon" style={{ fontSize: "12px", marginRight: "4px", verticalAlign: "middle" }}>sync</span>
                    checking...
                </span>
            );
        }

        const tooltipText = getUpdateStalenessTooltip();

        if (!updateInfo || daysSinceCheck === Infinity) {
            return (
                <span className="badge badge-sm badge-lowercase badge-stale-orange" title={tooltipText}>updates unchecked</span>
            );
        }

        const coreAvailable = updateInfo.core?.update_available;
        const pluginsCount = updateInfo.plugins?.plugins?.length ?? 0;
        const themesCount = updateInfo.themes?.themes?.length ?? 0;

        const getBadgeClassForComponent = (hasUpdate) => {
            if (hasUpdate) return "badge-warning";
            if (daysSinceCheck > 30) return "badge-stale-orange";
            if (daysSinceCheck > 7) return "badge-stale-yellow";
            return "badge-success";
        };

        const getLabel = (type, countOrAvail) => {
            if (type === "Core") {
                if (countOrAvail) return "core update";
                if (daysSinceCheck > 30) return "core stale (>30d)";
                if (daysSinceCheck > 7) return "core stale (>7d)";
                return "core ok";
            }
            if (type === "Plugins") {
                if (countOrAvail > 0) return `plugins (${countOrAvail})`;
                if (daysSinceCheck > 30) return "plugins stale (>30d)";
                if (daysSinceCheck > 7) return "plugins stale (>7d)";
                return "plugins ok";
            }
            if (type === "Themes") {
                if (countOrAvail > 0) return `themes (${countOrAvail})`;
                if (daysSinceCheck > 30) return "themes stale (>30d)";
                if (daysSinceCheck > 7) return "themes stale (>7d)";
                return "themes ok";
            }
        };

        return (
            <React.Fragment>
                <span className={`badge badge-sm badge-lowercase ${getBadgeClassForComponent(coreAvailable)}`} title={tooltipText}>
                    {getLabel("Core", coreAvailable)}
                </span>
                <span className={`badge badge-sm badge-lowercase ${getBadgeClassForComponent(pluginsCount > 0)}`} title={tooltipText}>
                    {getLabel("Plugins", pluginsCount)}
                </span>
                <span className={`badge badge-sm badge-lowercase ${getBadgeClassForComponent(themesCount > 0)}`} title={tooltipText}>
                    {getLabel("Themes", themesCount)}
                </span>
            </React.Fragment>
        );
    };

    const healthDisplay = latestSnapshot?.overall_status ? latestSnapshot.overall_status.toUpperCase() : healthStatus;
    const healthBadgeClass = getHealthBadgeClass(healthDisplay);

    const rowView = viewMode === "details";
    const compactView = viewMode === "compact";
    const defaultView = viewMode === "grid";

    // Row / Details view rendering - Sleek 34px Micro Row
    if (rowView) {
        return (
            <article className="md-card site-card site-card-row" aria-labelledby={`${site.site_name}-title`}>
                <div className="row-col-thumb">
                    {screenshotUrl ? (
                        <img src={screenshotUrl} alt={`${site.display_name}`} className="detail-thumb-small" />
                    ) : (
                        <div className="detail-thumb-placeholder">
                            {capturingSnapshot ? (
                                <span className="material-symbols-outlined spin-icon">sync</span>
                            ) : (
                                <span className="material-symbols-outlined">language</span>
                            )}
                        </div>
                    )}
                </div>

                <div className="row-col-title" title={getUpdateStalenessTooltip()}>
                    <div className="card-title-group">
                        <span className={`status-circle-dot ${getStatusDotClass()}`} />
                        <h3 id={`${site.site_name}-title`} className="row-title-text">{site.display_name}</h3>
                    </div>
                    <span className="row-slug-text">{site.site_name}</span>
                    <span className="last-checked-label">{getLastCheckedLabel()}</span>
                </div>

                <div className="row-col-health">
                    <span 
                        className={`${healthBadgeClass} site-health-badge badge-micro`} 
                        style={{ cursor: "pointer" }}
                        onClick={() => {
                            if (latestSnapshot?.id) {
                                window.history.pushState({}, "", `/site/${site.site_name}/health-check/${latestSnapshot.id}`);
                                window.dispatchEvent(new Event("popstate"));
                            } else {
                                onViewDetails(site.site_name);
                            }
                        }}
                        title={
                            healthDisplay === "HEALTHY*"
                                ? "Healthy with Exceptions: All functional checks passed, but visual diffs or console errors were accepted by an admin."
                                : latestSnapshot?.id ? "Click to view latest health check details" : "Click to view site details"
                        }
                    >
                        {healthDisplay}
                    </span>
                </div>

                <div className="row-col-badges">
                    {renderUpdateStatus()}
                    {renderVulnerabilityStatus()}
                </div>

                <div className="row-col-actions">
                    <button type="button" className="md-button md-button-primary btn-micro" onClick={() => onViewDetails(site.site_name)} title="Details">
                        Details <span className="material-symbols-outlined" aria-hidden="true" style={{ fontSize: "11px" }}>arrow_forward</span>
                    </button>
                </div>
            </article>
        );
    }

    // Default / Grid view or Compact view rendering - Clean single CTA
    return (
        <article className={`md-card site-card ${compactView ? "site-card-compact" : "site-card-default"}`} aria-labelledby={`${site.site_name}-title`}>
            {/* Header sits on top above thumbnail */}
            <div className="card-header">
                <div className="card-title">
                    <div className="card-title-group" title={getUpdateStalenessTooltip()}>
                        <span className={`status-circle-dot ${getStatusDotClass()}`} />
                        <h3 id={`${site.site_name}-title`}>{site.display_name}</h3>
                    </div>
                    <span className="site-slug">{site.site_name}</span>
                    <span className="last-checked-label" title={getUpdateStalenessTooltip()}>{getLastCheckedLabel()}</span>
                </div>
                <span 
                    className={`${healthBadgeClass} site-health-badge`} 
                    style={{ cursor: "pointer" }}
                    onClick={() => {
                        if (latestSnapshot?.id) {
                            window.history.pushState({}, "", `/site/${site.site_name}/health-check/${latestSnapshot.id}`);
                            window.dispatchEvent(new Event("popstate"));
                        } else {
                            onViewDetails(site.site_name);
                        }
                    }}
                    title={
                        healthDisplay === "HEALTHY*"
                            ? "Healthy with Exceptions: All functional checks passed, but visual diffs or console errors were accepted by an admin."
                            : latestSnapshot?.id ? "Click to view latest health check details" : "Click to view site details"
                    }
                >
                    {healthDisplay}
                </span>
            </div>

            {/* Thumbnail below header for default grid view */}
            {defaultView && (
                <div className="site-card-thumb" aria-hidden="true">
                    {screenshotUrl ? (
                        <img src={screenshotUrl} alt={`${site.display_name} snapshot`} />
                    ) : (
                        <div className="thumb-loading-placeholder">
                            {capturingSnapshot ? (
                                <div className="thumb-capturing-msg">
                                    <span className="material-symbols-outlined spin-icon">sync</span>
                                    <span>Capturing snapshot...</span>
                                </div>
                            ) : (
                                <span className="material-symbols-outlined">language</span>
                            )}
                        </div>
                    )}
                </div>
            )}

            <div className="site-card-main">
                <div className="site-card-tags">
                    {renderUpdateStatus()}
                    {renderVulnerabilityStatus()}
                </div>
            </div>

            <div className="card-actions site-card-actions">
                <button type="button" className="md-button md-button-primary btn-sm view-details" onClick={() => onViewDetails(site.site_name)}>
                    Details <span className="material-symbols-outlined" aria-hidden="true">arrow_forward</span>
                </button>
            </div>
        </article>
    );
}
