import React, { useState, useEffect, useRef, useCallback } from "react";
import api from "../services/api";
import { showToast } from "../services/toast";
import { useTaskPolling } from "../hooks/useTaskPolling";
import { useSitesContext } from "../context/SitesContext";
import ImageLightbox from "./ImageLightbox";
import { getDisplayDomain } from "../utils/siteHelpers";
import {
    getHealthCheckedLabel,
    getHealthStatusDotClass,
    isHealthCheckStale,
} from "../utils/siteStaleness";

const STALE_CHECK_STAGGER_MS = 10000;

function goToHealthReport(siteName, checkId) {
    window.history.pushState({}, "", `/site/${siteName}/health-check/${checkId}`);
    window.dispatchEvent(new Event("popstate"));
}

function Thumbnails({ siteName, checkId, onEnlarge }) {
    const [desktopUrl, setDesktopUrl] = useState(null);
    const [mobileUrl, setMobileUrl] = useState(null);

    useEffect(() => {
        let cancelled = false;
        const urls = [];

        if (!checkId) {
            setDesktopUrl(null);
            setMobileUrl(null);
            return;
        }

        const load = async (device, setter) => {
            try {
                const blob = await api.getScreenshotBlob(siteName, checkId, device);
                if (cancelled) return;
                const url = URL.createObjectURL(blob);
                urls.push(url);
                setter(url);
            } catch (e) {
                console.debug(`No ${device} screenshot for`, siteName, e);
                if (!cancelled) setter(null);
            }
        };

        load("desktop", setDesktopUrl);
        load("mobile", setMobileUrl);

        return () => {
            cancelled = true;
            urls.forEach((u) => URL.revokeObjectURL(u));
        };
    }, [siteName, checkId]);

    if (!checkId) {
        return <span className="phd-thumbs-empty">No screenshots yet</span>;
    }

    return (
        <div className="phd-thumbs-row">
            {[["Desktop", desktopUrl], ["Mobile", mobileUrl]].map(([label, url]) => (
                <div key={label} className="phd-thumb-col">
                    {url ? (
                        <img
                            src={url}
                            alt={`${label} screenshot`}
                            onClick={() => onEnlarge(url, `${label} - ${siteName}`)}
                            className="phd-thumb-img"
                        />
                    ) : (
                        <div className="phd-thumb-placeholder">
                            n/a
                        </div>
                    )}
                    <div className="phd-thumb-label">{label}</div>
                </div>
            ))}
        </div>
    );
}

function HealthRow({ site, onUpdated, onEnlarge, externallyChecking = false }) {
    const { pollTask } = useTaskPolling();
    const [checking, setChecking] = useState(false);
    const summary = site.health_summary;
    // A check started by "Check Stale Sites" should show on the row too.
    const isChecking = checking || externallyChecking;

    const runCheck = useCallback(async () => {
        setChecking(true);
        try {
            const res = await api.triggerHealthCheckAsync(site.site_name);
            if (res && res.task_id) {
                pollTask(res.task_id, `Health check complete for ${site.display_name || site.site_name}`, (result) => {
                    setChecking(false);
                    if (result) {
                        onUpdated(site.site_name, {
                            id: result.id,
                            timestamp: result.timestamp,
                            overall_status: result.overall_status,
                            error_summary: result.checks?.http?.error_summary || {},
                            latest_console_errors: (result.checks?.http?.console_errors || []).filter(e => e.severity !== "ignored").slice(0, 3),
                        });
                    }
                });
            } else {
                setChecking(false);
                showToast(`Could not start health check for ${site.site_name}`, "error");
            }
        } catch (err) {
            setChecking(false);
            showToast(`Health check failed: ${err.message}`, "error");
        }
    }, [site.site_name, site.display_name, onUpdated, pollTask]);

    const errorCounts = summary?.error_summary || {};
    const criticalCount = errorCounts.critical || 0;
    const warningCount = errorCounts.warning || 0;

    return (
        <tr>
            <td>
                <span
                    className={`status-circle-dot ${getHealthStatusDotClass(summary)} phd-status-dot-spacing`}
                    title={getHealthCheckedLabel(summary)}
                />
                <strong>{site.display_name || site.site_name}</strong>
                <div>
                    {site.health_check_url ? (
                        <a
                            href={site.health_check_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="phd-site-link"
                        >
                            {getDisplayDomain(site.health_check_url)}
                        </a>
                    ) : (
                        <span className="phd-text-muted-sm">No URL configured</span>
                    )}
                </div>
            </td>
            <td className="phd-td-sm-text">
                {getHealthCheckedLabel(summary)}
            </td>
            <td>
                {criticalCount === 0 && warningCount === 0 ? (
                    <span className="badge badge-sm badge-success">No active errors</span>
                ) : (
                    <div className="phd-error-col">
                        <div className="phd-badges-row">
                            {criticalCount > 0 && <span className="badge badge-sm badge-error">{criticalCount} critical</span>}
                            {warningCount > 0 && <span className="badge badge-sm badge-warning">{warningCount} warning</span>}
                        </div>
                        {(summary?.latest_console_errors || []).slice(0, 2).map((e, i) => (
                            <div key={i} title={e.text} className="phd-error-preview">
                                {e.text}
                            </div>
                        ))}
                    </div>
                )}
            </td>
            <td>
                <Thumbnails siteName={site.site_name} checkId={summary?.id} onEnlarge={onEnlarge} />
            </td>
            <td className="phd-td-nowrap">
                <button
                    type="button"
                    className="md-button md-button-outlined md-button-sm phd-check-btn-spacing"
                    onClick={runCheck}
                    disabled={isChecking}
                >
                    {isChecking ? (
                        <span className="material-symbols-outlined spin-icon phd-icon-sm">progress_activity</span>
                    ) : (
                        <span className="material-symbols-outlined phd-icon-sm">refresh</span>
                    )}
                    {" "}{isChecking ? "Checking..." : "Check Site"}
                </button>
                <br />
                {summary?.id && (
                    <button
                        type="button"
                        className="md-button md-button-tonal md-button-sm"
                        onClick={() => goToHealthReport(site.site_name, summary.id)}
                    >
                        View Report
                    </button>
                )}
            </td>
        </tr>
    );
}

export default function ProductionHealthDashboard() {
    const sitesContext = useSitesContext();
    const sites = sitesContext?.sites || [];
    const [loading, setLoading] = useState(sites.length === 0);
    const [lightboxImage, setLightboxImage] = useState(null);
    const [checkingSites, setCheckingSites] = useState(() => new Set());
    const staleTimeoutsRef = useRef([]);
    const { pollTask } = useTaskPolling();

    // GET /api/sites is already fetched app-wide (App.jsx populates
    // SitesContext right after authentication and keeps it current), so this
    // view reads from there instead of re-fetching every time it's opened --
    // it used to refetch on every mount since it's only rendered while this
    // tab is active.
    const loadSites = useCallback(async () => {
        setLoading(true);
        try {
            const data = await api.getSites();
            sitesContext?.setSites(data || []);
        } catch (err) {
            showToast(`Failed to load sites: ${err.message}`, "error");
        } finally {
            setLoading(false);
        }
    }, [sitesContext]);

    useEffect(() => {
        // Only fetch if the context hasn't been populated yet (e.g. this view
        // mounted before App.jsx's post-auth load finished); otherwise the
        // Refresh button is the only thing that should trigger a fetch here.
        if (sites.length === 0) {
            loadSites();
        } else {
            setLoading(false);
        }
        return () => {
            staleTimeoutsRef.current.forEach(clearTimeout);
        };
        // Intentionally mount-only: re-running this on every `sites` change
        // would refetch every time patchSiteHealthSummary updates the list.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const patchSiteHealthSummary = useCallback((siteName, healthSummary) => {
        sitesContext?.setSites((prev) => prev.map((s) => (
            s.site_name === siteName ? { ...s, health_summary: healthSummary } : s
        )));
    }, [sitesContext]);

    const checkStaleSites = useCallback(() => {
        staleTimeoutsRef.current.forEach(clearTimeout);
        staleTimeoutsRef.current = [];

        const staleSites = sites.filter((s) => isHealthCheckStale(s.health_summary));
        if (staleSites.length === 0) {
            showToast("No stale sites to check right now.", "info");
            return;
        }

        staleSites.forEach((site, index) => {
            const timeoutId = setTimeout(async () => {
                try {
                    const res = await api.triggerHealthCheckAsync(site.site_name);
                    // Previously the task id was discarded, so the row kept
                    // showing a stale timestamp and the button looked inert.
                    if (res && res.task_id) {
                        setCheckingSites((prev) => new Set(prev).add(site.site_name));
                        pollTask(
                            res.task_id,
                            `Health check complete for ${site.display_name || site.site_name}`,
                            (result) => {
                                setCheckingSites((prev) => {
                                    const next = new Set(prev);
                                    next.delete(site.site_name);
                                    return next;
                                });
                                if (result) {
                                    patchSiteHealthSummary(site.site_name, {
                                        id: result.id,
                                        timestamp: result.timestamp,
                                        overall_status: result.overall_status,
                                        error_summary: result.checks?.http?.error_summary || {},
                                        latest_console_errors: (result.checks?.http?.console_errors || [])
                                            .filter(e => e.severity !== "ignored").slice(0, 3),
                                    });
                                }
                            }
                        );
                    }
                } catch (err) {
                    console.debug("Stale health check trigger failed for", site.site_name, err);
                }
            }, index * STALE_CHECK_STAGGER_MS);
            staleTimeoutsRef.current.push(timeoutId);
        });

        showToast(`Checking ${staleSites.length} stale site(s), staggered to avoid overload...`, "info");
    }, [sites, pollTask, patchSiteHealthSummary]);

    const staleCount = sites.filter((s) => isHealthCheckStale(s.health_summary)).length;

    return (
        <div id="productionHealthView">
            <div className="page-title-section page-title-dashboard">
                <div>
                    <h2>Production Health</h2>
                    <div className="page-subtitle">
                        Total sites: <span>{sites.length}</span>
                        {staleCount > 0 && <span> &middot; Stale (&gt;3d): {staleCount}</span>}
                    </div>
                </div>
                <div className="page-title-actions">
                    <button type="button" className="md-button md-button-primary" onClick={checkStaleSites}>
                        <span className="material-symbols-outlined" aria-hidden="true">fact_check</span> Check Stale Sites
                    </button>
                    <button type="button" className="md-button md-button-tonal" onClick={loadSites}>
                        <span className="material-symbols-outlined" aria-hidden="true">refresh</span> Refresh
                    </button>
                </div>
            </div>

            {loading ? (
                <p>Loading sites...</p>
            ) : (
                <div className="phd-table-wrapper">
                    <table className="site-table">
                        <thead>
                            <tr>
                                <th>Site</th>
                                <th>Last Checked</th>
                                <th>Console Errors</th>
                                <th>Screenshots</th>
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {sites.map((site) => (
                                <HealthRow
                                    key={site.site_name}
                                    site={site}
                                    externallyChecking={checkingSites.has(site.site_name)}
                                    onUpdated={patchSiteHealthSummary}
                                    onEnlarge={(src, alt) => setLightboxImage({ src, alt })}
                                />
                            ))}
                        </tbody>
                    </table>
                </div>
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
