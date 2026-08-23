import React, { useState, useEffect, useRef, useCallback } from "react";
import api from "../services/api";
import { showToast } from "../services/toast";
import { useTaskPolling } from "../hooks/useTaskPolling";
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
        return <span style={{ fontSize: "0.8rem", color: "var(--md-sys-color-outline)" }}>No screenshots yet</span>;
    }

    return (
        <div style={{ display: "flex", gap: "0.5rem" }}>
            {[["Desktop", desktopUrl], ["Mobile", mobileUrl]].map(([label, url]) => (
                <div key={label} style={{ textAlign: "center" }}>
                    {url ? (
                        <img
                            src={url}
                            alt={`${label} screenshot`}
                            onClick={() => onEnlarge(url, `${label} - ${siteName}`)}
                            style={{
                                width: "90px",
                                height: "60px",
                                objectFit: "cover",
                                objectPosition: "top",
                                borderRadius: "6px",
                                border: "1px solid var(--md-sys-color-outline-variant)",
                                cursor: "zoom-in",
                            }}
                        />
                    ) : (
                        <div style={{
                            width: "90px", height: "60px", borderRadius: "6px",
                            display: "flex", alignItems: "center", justifyContent: "center",
                            backgroundColor: "var(--md-sys-color-surface-variant)",
                            fontSize: "0.65rem", color: "var(--md-sys-color-outline)"
                        }}>
                            n/a
                        </div>
                    )}
                    <div style={{ fontSize: "0.65rem", color: "var(--md-sys-color-outline)", marginTop: "0.15rem" }}>{label}</div>
                </div>
            ))}
        </div>
    );
}

function HealthRow({ site, onUpdated, onEnlarge }) {
    const { pollTask } = useTaskPolling();
    const [checking, setChecking] = useState(false);
    const summary = site.health_summary;

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
            <td style={{ padding: "0.75rem" }}>
                <span
                    className={`status-circle-dot ${getHealthStatusDotClass(summary)}`}
                    title={getHealthCheckedLabel(summary)}
                    style={{ marginRight: "0.5rem" }}
                />
                <strong>{site.display_name || site.site_name}</strong>
                <div>
                    {site.health_check_url ? (
                        <a
                            href={site.health_check_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            style={{ color: "var(--md-sys-color-primary)", fontSize: "0.85rem" }}
                        >
                            {getDisplayDomain(site.health_check_url)}
                        </a>
                    ) : (
                        <span style={{ fontSize: "0.85rem", color: "var(--md-sys-color-outline)" }}>No URL configured</span>
                    )}
                </div>
            </td>
            <td style={{ padding: "0.75rem", fontSize: "0.85rem" }}>
                {getHealthCheckedLabel(summary)}
            </td>
            <td style={{ padding: "0.75rem" }}>
                {criticalCount === 0 && warningCount === 0 ? (
                    <span className="badge badge-sm badge-success">No active errors</span>
                ) : (
                    <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
                        <div style={{ display: "flex", gap: "0.4rem" }}>
                            {criticalCount > 0 && <span className="badge badge-sm badge-error">{criticalCount} critical</span>}
                            {warningCount > 0 && <span className="badge badge-sm badge-warning">{warningCount} warning</span>}
                        </div>
                        {(summary?.latest_console_errors || []).slice(0, 2).map((e, i) => (
                            <div key={i} title={e.text} style={{
                                fontSize: "0.72rem", color: "var(--md-sys-color-outline)",
                                maxWidth: "260px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap"
                            }}>
                                {e.text}
                            </div>
                        ))}
                    </div>
                )}
            </td>
            <td style={{ padding: "0.75rem" }}>
                <Thumbnails siteName={site.site_name} checkId={summary?.id} onEnlarge={onEnlarge} />
            </td>
            <td style={{ padding: "0.75rem", whiteSpace: "nowrap" }}>
                <button
                    type="button"
                    className="md-button md-button-outlined md-button-sm"
                    onClick={runCheck}
                    disabled={checking}
                    style={{ marginBottom: "0.4rem" }}
                >
                    {checking ? (
                        <span className="material-symbols-outlined" style={{ fontSize: "16px" }}>progress_activity</span>
                    ) : (
                        <span className="material-symbols-outlined" style={{ fontSize: "16px" }}>refresh</span>
                    )}
                    {" "}Check Site
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
    const [sites, setSites] = useState([]);
    const [loading, setLoading] = useState(true);
    const [lightboxImage, setLightboxImage] = useState(null);
    const staleTimeoutsRef = useRef([]);

    const loadSites = useCallback(async () => {
        setLoading(true);
        try {
            const data = await api.getSites();
            setSites(data || []);
        } catch (err) {
            showToast(`Failed to load sites: ${err.message}`, "error");
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        loadSites();
        return () => {
            staleTimeoutsRef.current.forEach(clearTimeout);
        };
    }, [loadSites]);

    const patchSiteHealthSummary = useCallback((siteName, healthSummary) => {
        setSites((prev) => prev.map((s) => (
            s.site_name === siteName ? { ...s, health_summary: healthSummary } : s
        )));
    }, []);

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
                    await api.triggerHealthCheckAsync(site.site_name);
                } catch (err) {
                    console.debug("Stale health check trigger failed for", site.site_name, err);
                }
            }, index * STALE_CHECK_STAGGER_MS);
            staleTimeoutsRef.current.push(timeoutId);
        });

        showToast(`Checking ${staleSites.length} stale site(s), staggered to avoid overload...`, "info");
    }, [sites]);

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
                <div className="site-table-wrapper" style={{ overflowX: "auto" }}>
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
