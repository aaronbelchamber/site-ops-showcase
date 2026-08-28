import React, { useState, useEffect } from "react";
import api from "../services/api";
import { showToast } from "../services/toast";
import { useSitesContext } from "../context/SitesContext";
import {
    getLastCheckedLabel as getLastCheckedLabelFor,
    getUpdateStalenessTooltip as getUpdateStalenessTooltipFor,
    getStatusDotClass as getStatusDotClassFor,
    getUpdateTierBadgeClass,
    getUpdateTierSuffix,
    getHealthBadgeClass,
} from "../utils/siteStaleness";

export default function SiteCard({ site, viewMode = "grid", onViewDetails, onRequestCheck }) {
    const sitesContext = useSitesContext();
    const contextUpdates = sitesContext?.updatesBySite?.[site.site_name];
    const isCheckingUpdates = Boolean(sitesContext?.inFlightChecks?.has(site.site_name));

    // GET /api/sites already returns `health_summary` (id, timestamp,
    // overall_status) and `update_summary` for every site, so the card renders
    // from props alone.
    //
    // This card used to fire three requests per site on mount -- health history,
    // latest snapshot and an update check -- and two of those fell back to
    // api.runHealthCheck(), the *synchronous* endpoint that opens SSH and drives
    // a headless browser. A dashboard of N sites launched up to 2N live checks
    // at once, which saturated the backend (cascading 409s, then SSH banner
    // timeouts). The only per-card request left is the screenshot image itself,
    // which needs an authenticated blob fetch.
    const healthSummary = site.health_summary || null;
    const latestCheckId = healthSummary?.id || null;
    const [updateInfo, setUpdateInfo] = useState(contextUpdates || site.update_summary || null);
    const [screenshotUrl, setScreenshotUrl] = useState(null);

    // Sync from context when a background update check reports back
    useEffect(() => {
        if (contextUpdates) {
            setUpdateInfo(contextUpdates);
        }
    }, [contextUpdates]);

    // Keep local state in step when the parent reloads the site list
    useEffect(() => {
        if (site.update_summary) {
            setUpdateInfo((prev) => prev || site.update_summary);
        }
    }, [site.update_summary]);

    // Load the screenshot for the most recent check via an authenticated request
    useEffect(() => {
        let cancelled = false;
        let createdUrl = null;

        if (!latestCheckId) {
            setScreenshotUrl(null);
            return undefined;
        }

        (async () => {
            try {
                const blob = await api.getScreenshotBlob(site.site_name, latestCheckId, "desktop");
                if (!cancelled) {
                    createdUrl = URL.createObjectURL(blob);
                    setScreenshotUrl(createdUrl);
                }
            } catch (e) {
                console.debug("No screenshot for", site.site_name, e);
                if (!cancelled) setScreenshotUrl(null);
            }
        })();

        return () => {
            cancelled = true;
            if (createdUrl) URL.revokeObjectURL(createdUrl);
        };
    }, [site.site_name, latestCheckId]);

    // Staleness calculations
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

        if (!updateInfo || !updateInfo.timestamp) {
            return (
                <span className="badge badge-sm badge-lowercase badge-error" title={tooltipText}>updates unchecked</span>
            );
        }

        const coreAvailable = updateInfo.core?.update_available;
        const pluginsCount = updateInfo.plugins?.plugins?.length ?? 0;
        const themesCount = updateInfo.themes?.themes?.length ?? 0;

        // An available update is a warning regardless of age; otherwise the
        // badge reflects how old the check itself is, on the shared scale that
        // also drives the status dot and the dashboard chip.
        const staleBadgeClass = getUpdateTierBadgeClass(updateInfo);
        const staleSuffix = getUpdateTierSuffix(updateInfo);
        const getBadgeClassForComponent = (hasUpdate) => (hasUpdate ? "badge-warning" : staleBadgeClass);

        const getLabel = (type, countOrAvail) => {
            if (type === "Core") {
                return countOrAvail ? "core update" : `core ${staleSuffix}`;
            }
            if (type === "Plugins") {
                return countOrAvail > 0 ? `plugins (${countOrAvail})` : `plugins ${staleSuffix}`;
            }
            if (type === "Themes") {
                return countOrAvail > 0 ? `themes (${countOrAvail})` : `themes ${staleSuffix}`;
            }
            return "";
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

    const rawStatus = healthSummary?.overall_status || "";
    const healthDisplay = rawStatus
        ? (rawStatus.toLowerCase() === "healthy with exception" ? "HEALTHY*" : rawStatus.toUpperCase())
        : "NOT CHECKED";
    const healthBadgeClass = getHealthBadgeClass(healthDisplay);
    const healthTitle = healthDisplay === "HEALTHY*"
        ? "Healthy with Exceptions: All functional checks passed, but visual diffs or console errors were accepted by an admin."
        : latestCheckId
            ? "Click to view latest health check details"
            : "No health check has been run for this site yet. Click to open site details.";

    const openLatestReport = () => {
        if (latestCheckId) {
            window.history.pushState({}, "", `/site/${site.site_name}/health-check/${latestCheckId}`);
            window.dispatchEvent(new Event("popstate"));
        } else {
            onViewDetails(site.site_name);
        }
    };

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
                            <span className="material-symbols-outlined">language</span>
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
                    <button
                        type="button"
                        className={`${healthBadgeClass} site-health-badge badge-micro badge-clickable`}
                        onClick={openLatestReport}
                        title={healthTitle}
                    >
                        {healthDisplay}
                    </button>
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
                <button
                    type="button"
                    className={`${healthBadgeClass} site-health-badge badge-clickable`}
                    onClick={openLatestReport}
                    title={healthTitle}
                >
                    {healthDisplay}
                </button>
            </div>

            {/* Thumbnail below header for default grid view */}
            {defaultView && (
                <div className="site-card-thumb">
                    {screenshotUrl ? (
                        <img src={screenshotUrl} alt={`${site.display_name} snapshot`} />
                    ) : (
                        <div className="thumb-loading-placeholder">
                            {latestCheckId ? (
                                <span className="material-symbols-outlined">language</span>
                            ) : (
                                <div className="thumb-capturing-msg">
                                    <span className="material-symbols-outlined">photo_camera</span>
                                    <span>No snapshot yet</span>
                                    {onRequestCheck && (
                                        <button
                                            type="button"
                                            className="md-button md-button-tonal md-button-sm"
                                            onClick={() => onRequestCheck(site.site_name)}
                                            title="Run a health check now and capture a screenshot"
                                        >
                                            Run check
                                        </button>
                                    )}
                                </div>
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
