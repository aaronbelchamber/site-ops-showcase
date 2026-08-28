import React, { useState, useEffect } from "react";
import api from "../../services/api";
import { showToast } from "../../services/toast";
import ImageLightbox from "../ImageLightbox";
import { getDisplayDomain } from "../../utils/siteHelpers";
import { useObjectUrl } from "../../hooks/useObjectUrl";
import { statusModifier } from "./statusModifier";
import { ConsoleErrorsSection } from "./ConsoleErrorsSection";
import { AssetIssuesSection } from "./AssetIssuesSection";

export default function HealthCheckDetails({ siteName, healthCheckId, onBack }) {
    const [check, setCheck] = useState(null);
    const [errors, setErrors] = useState([]);
    const [loading, setLoading] = useState(true);
    const [fetchError, setFetchError] = useState(null);
    const [desktopImgUrl, setDesktopImgUrl] = useObjectUrl();
    const [mobileImgUrl, setMobileImgUrl] = useObjectUrl();
    const [desktopDiffUrl, setDesktopDiffUrl] = useObjectUrl();
    const [mobileDiffUrl, setMobileDiffUrl] = useObjectUrl();
    const [isDiffAccepted, setIsDiffAccepted] = useState(false);
    const [acceptingDiff, setAcceptingDiff] = useState(false);
    const [diffReason, setDiffReason] = useState("");
    const [lightboxImage, setLightboxImage] = useState(null);
    const [site, setSite] = useState(null);

    useEffect(() => {
        let isMounted = true;
        api.getSite(siteName)
            .then((data) => { if (isMounted) setSite(data); })
            .catch((e) => console.error("Failed to load site details", e));
        return () => { isMounted = false; };
    }, [siteName]);

    useEffect(() => {
        let isMounted = true;

        async function fetchDetails() {
            setLoading(true);
            // Clear the previous report's images so a check that lacks, say, a
            // mobile screenshot doesn't keep showing the last one.
            setDesktopImgUrl(null);
            setMobileImgUrl(null);
            setDesktopDiffUrl(null);
            setMobileDiffUrl(null);
            try {
                const data = await api.getHealthCheck(siteName, healthCheckId);
                if (isMounted) {
                    setCheck(data);
                    setErrors(data.checks?.http?.console_errors || []);
                }

                try {
                    const acceptedDiffs = await api.getAcceptedVisualDiffs(siteName);
                    if (isMounted) {
                        const accepted = (acceptedDiffs || []).some(d => d.check_id === healthCheckId);
                        setIsDiffAccepted(accepted);
                    }
                } catch (e) {
                    console.error("Failed to load accepted visual diffs", e);
                }

                try {
                    const desktopBlob = await api.getScreenshotBlob(siteName, healthCheckId, "desktop");
                    if (isMounted) setDesktopImgUrl(URL.createObjectURL(desktopBlob));
                } catch (e) {
                    console.error("Failed to load desktop screenshot", e);
                }

                try {
                    const mobileBlob = await api.getScreenshotBlob(siteName, healthCheckId, "mobile");
                    if (isMounted) setMobileImgUrl(URL.createObjectURL(mobileBlob));
                } catch (e) {
                    console.error("Failed to load mobile screenshot", e);
                }

                const diffs = data.checks?.http?.screenshot_diffs || {};
                if (diffs.desktop_diff) {
                    try {
                        const blob = await api.getScreenshotBlob(siteName, healthCheckId, "desktop_diff");
                        if (isMounted) setDesktopDiffUrl(URL.createObjectURL(blob));
                    } catch (e) {
                        console.error("Failed to load desktop diff screenshot", e);
                    }
                }
                if (diffs.mobile_diff) {
                    try {
                        const blob = await api.getScreenshotBlob(siteName, healthCheckId, "mobile_diff");
                        if (isMounted) setMobileDiffUrl(URL.createObjectURL(blob));
                    } catch (e) {
                        console.error("Failed to load mobile diff screenshot", e);
                    }
                }
            } catch (err) {
                if (isMounted) setFetchError(err.message);
            } finally {
                if (isMounted) setLoading(false);
            }
        }

        fetchDetails();
        return () => { isMounted = false; };
    }, [siteName, healthCheckId, setDesktopImgUrl, setMobileImgUrl, setDesktopDiffUrl, setMobileDiffUrl]);

    if (loading) {
        return (
            <div className="hcd-loading">
                <h2>Loading Health Check Details...</h2>
                <div className="hcd-loading__subtext">Retrieving report data...</div>
            </div>
        );
    }

    if (fetchError) {
        return (
            <div className="md-card hcd-fetch-error-card">
                <h3 className="hcd-text-error">Error Loading Health Check</h3>
                <p>{fetchError}</p>
                <button className="md-button md-button-primary hcd-mt-1r" onClick={onBack}>
                    Back to Site Details
                </button>
            </div>
        );
    }

    const http = check.checks?.http || {};
    const overallStatus = check.overall_status || "unknown";
    const errorSummary = http.error_summary || {};
    const activeErrorCount = (errorSummary.critical || 0) + (errorSummary.warning || 0);
    const ignoredErrorCount = errorSummary.ignored || 0;
    const statusMod = statusModifier(overallStatus);

    const scrollToRootCause = () => {
        if (activeErrorCount > 0) {
            const el = document.getElementById("consoleErrorsCard");
            if (el) {
                el.scrollIntoView({ behavior: "smooth", block: "start" });
                return;
            }
        }
        if (check.checks?.http?.screenshot_diffs && !check.checks.http.screenshot_diffs.matched) {
            const el = document.getElementById("visualDiffCard");
            if (el) {
                el.scrollIntoView({ behavior: "smooth", block: "start" });
                return;
            }
        }
        if (http.status_code > 302 || http.status_code === 0) {
            const el = document.getElementById("httpMetricsCard");
            if (el) {
                el.scrollIntoView({ behavior: "smooth", block: "start" });
                return;
            }
        }
        const firstCard = document.querySelector(".md-card");
        if (firstCard) {
            firstCard.scrollIntoView({ behavior: "smooth", block: "start" });
        }
    };

    return (
        <div className="stack-column hcd-page-pad">
            <div className="hcd-row hcd-justify-between">
                <div className="hcd-row hcd-gap-lg">
                    <button className="md-button md-button-tonal md-button-icon" onClick={onBack}>
                        <span className="material-symbols-outlined">arrow_back</span>
                    </button>
                    <div>
                        <h2 className="hcd-m0">Health Check Report</h2>
                        {site?.health_check_url && (
                            <div>
                                <a
                                    href={site.health_check_url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="hcd-domain-link"
                                >
                                    {getDisplayDomain(site.health_check_url)}
                                </a>
                            </div>
                        )}
                        <span className="hcd-text-muted">
                            ID: {healthCheckId} • Checked: {new Date(check.timestamp).toLocaleString()}
                        </span>
                    </div>
                </div>
                <span
                    onClick={scrollToRootCause}
                    title="Click to jump to root cause of this health status"
                    className={`hcd-status-badge hcd-status-badge--${statusMod}`}
                >
                    {overallStatus}
                    {(overallStatus === "critical" || overallStatus === "degraded" || activeErrorCount > 0) && (
                        <span className="material-symbols-outlined hcd-status-badge__arrow">south</span>
                    )}
                </span>
            </div>

            {/* Status Breakdown & Explanation Banner */}
            <div className={`md-card hcd-explain-card hcd-explain-card--${statusMod}`}>
                <div className="hcd-explain-card__header">
                    <span className={`material-symbols-outlined hcd-explain-card__icon--${statusMod}`}>info</span>
                    <strong className="hcd-explain-card__title">Status Summary & Explanation</strong>
                </div>
                {check.status_reasons && check.status_reasons.length > 0 ? (
                    <ul className="hcd-explain-card__list">
                        {check.status_reasons.map((reason, idx) => (
                            <li key={idx} className="hcd-explain-card__list-item">{reason}</li>
                        ))}
                    </ul>
                ) : (
                    <p className="hcd-explain-card__text">
                        {overallStatus === "healthy" && "All automated checks, response times, and baseline visual comparisons passed cleanly."}
                        {overallStatus === "degraded" && `Response time was ${http.response_time_ms || 0} ms (exceeding standard performance threshold).`}
                        {overallStatus === "notice" && "Site is fully functional, but browser console emitted active JavaScript errors."}
                        {overallStatus === "critical" && (
                            http.status_code >= 400
                                ? `HTTP response status error ${http.status_code}.`
                                : http.status_code === 0
                                    ? "Site connection failed (unreachable)."
                                    : activeErrorCount > 0
                                        ? "Active critical errors detected."
                                        : "Critical site issue detected."
                        )}
                    </p>
                )}
            </div>

            <div className="md-card hcd-card-pad">
                <h3>Captured Screenshots</h3>
                <div className="split-2-1 hcd-mt-1r">
                    <div className="hcd-col hcd-gap-sm">
                        <strong className="hcd-text-muted">Desktop View (1280x800)</strong>
                        <div className="hcd-screenshot-frame">
                            {desktopImgUrl
                                ? <img src={desktopImgUrl} alt="Desktop View" onClick={() => setLightboxImage({ src: desktopImgUrl, alt: "Desktop View (1280x800)" })} title="Click to enlarge & magnify" />
                                : <div className="hcd-screenshot-frame__empty">No screenshot available</div>
                            }
                        </div>
                    </div>
                    <div className="hcd-col hcd-gap-sm">
                        <strong className="hcd-text-muted">Mobile View (375x667)</strong>
                        <div className="hcd-screenshot-frame">
                            {mobileImgUrl
                                ? <img src={mobileImgUrl} alt="Mobile View" onClick={() => setLightboxImage({ src: mobileImgUrl, alt: "Mobile View (375x667)" })} title="Click to enlarge & magnify" />
                                : <div className="hcd-screenshot-frame__empty">No screenshot available</div>
                            }
                        </div>
                    </div>
                </div>
            </div>

            {check.checks?.http?.screenshot_diffs && !check.checks.http.screenshot_diffs.matched && (
                <div id="visualDiffCard" className={`md-card hcd-card-pad ${isDiffAccepted ? "hcd-diff-card--accepted" : "hcd-diff-card--rejected"}`}>
                    <div className="hcd-diff-card__header">
                        <div>
                            <h3 className={`hcd-diff-card__title ${isDiffAccepted ? "hcd-diff-card__title--accepted" : "hcd-diff-card__title--rejected"}`}>
                                <span className="material-symbols-outlined">difference</span>
                                Visual Differences Detected (Pre vs Post Update)
                            </h3>
                            <p className="hcd-diff-card__subtitle">
                                {isDiffAccepted
                                    ? "Visual difference has been accepted by an admin and will not block site updates or health status."
                                    : "The layout changed after applying the update. Differences are highlighted in magenta below."
                                }
                            </p>
                        </div>
                        <div className="hcd-diff-card__actions">
                            {isDiffAccepted ? (
                                <button
                                    className="md-button md-button-outlined hcd-diff-card__reject-btn"
                                    disabled={acceptingDiff}
                                    onClick={async () => {
                                        setAcceptingDiff(true);
                                        try {
                                            await api.unacceptVisualDiff(siteName, healthCheckId);
                                            setIsDiffAccepted(false);
                                            const updated = await api.getHealthCheck(siteName, healthCheckId);
                                            if (updated) setCheck(updated);
                                            showToast("Visual diff re-rejected.", "info");
                                        } catch (e) {
                                            showToast(`Failed to re-reject diff: ${e.message}`, "error");
                                        } finally {
                                            setAcceptingDiff(false);
                                        }
                                    }}
                                >
                                    <span className="material-symbols-outlined">cancel</span> Re-reject Difference
                                </button>
                            ) : (
                                <button
                                    className="md-button md-button-primary"
                                    disabled={acceptingDiff}
                                    onClick={async () => {
                                        setAcceptingDiff(true);
                                        try {
                                            await api.acceptVisualDiff(siteName, healthCheckId, diffReason || "Accepted design update");
                                            setIsDiffAccepted(true);
                                            const updated = await api.getHealthCheck(siteName, healthCheckId);
                                            if (updated) setCheck(updated);
                                            showToast("Visual diff accepted by admin!", "success");
                                        } catch (e) {
                                            showToast(`Failed to accept diff: ${e.message}`, "error");
                                        } finally {
                                            setAcceptingDiff(false);
                                        }
                                    }}
                                >
                                    <span className="material-symbols-outlined">check_circle</span> Accept Difference
                                </button>
                            )}
                        </div>
                    </div>

                    <div className="split-2-1">
                        <div className="hcd-col hcd-gap-sm">
                            <strong className="hcd-text-muted">Desktop Visual Diff (1280x800)</strong>
                            <div className="hcd-screenshot-frame">
                                {desktopDiffUrl
                                    ? <img src={desktopDiffUrl} alt="Desktop Visual Diff" onClick={() => setLightboxImage({ src: desktopDiffUrl, alt: "Desktop Visual Diff (1280x800)" })} title="Click to enlarge & magnify" />
                                    : <div className="hcd-screenshot-frame__empty">No diff image available</div>
                                }
                            </div>
                        </div>
                        <div className="hcd-col hcd-gap-sm">
                            <strong className="hcd-text-muted">Mobile Visual Diff (375x667)</strong>
                            <div className="hcd-screenshot-frame">
                                {mobileDiffUrl
                                    ? <img src={mobileDiffUrl} alt="Mobile Visual Diff" onClick={() => setLightboxImage({ src: mobileDiffUrl, alt: "Mobile Visual Diff (375x667)" })} title="Click to enlarge & magnify" />
                                    : <div className="hcd-screenshot-frame__empty">No diff image available</div>
                                }
                            </div>
                        </div>
                    </div>
                </div>
            )}

            <div id="httpMetricsCard" className="md-card hcd-metrics-grid">
                <div>
                    <div className="hcd-metric-label">HTTP Response Code</div>
                    <div className={`hcd-metric-value ${http.status_code <= 302 ? "hcd-metric-value--good" : "hcd-metric-value--bad"}`}>
                        {http.status_code || "N/A"}
                    </div>
                </div>
                <div>
                    <div className="hcd-metric-label">Response Time</div>
                    <div className="hcd-metric-value">
                        {http.response_time_ms ? `${http.response_time_ms} ms` : "N/A"}
                    </div>
                </div>
                <div>
                    <div className="hcd-metric-label">Active Errors</div>
                    <div className={`hcd-metric-value ${activeErrorCount > 0 ? "hcd-metric-value--bad" : "hcd-metric-value--good"}`}>
                        {activeErrorCount}
                    </div>
                </div>
                {ignoredErrorCount > 0 && (
                    <div>
                        <div className="hcd-metric-label">Ignored / Accepted</div>
                        <div className="hcd-metric-value hcd-metric-value--muted">
                            {ignoredErrorCount}
                        </div>
                    </div>
                )}
            </div>

            <div id="consoleErrorsCard" className="md-card hcd-card-pad">
                <div className="hcd-console-errors-header">
                    <h3 className="hcd-m0">Console Errors</h3>
                    {ignoredErrorCount > 0 && activeErrorCount === 0 && (
                        <span className="hcd-console-errors-suppressed-note">
                            All errors are suppressed — site is healthy
                        </span>
                    )}
                </div>
                <ConsoleErrorsSection
                    errors={errors}
                    siteName={siteName}
                    onErrorsChanged={setErrors}
                />
            </div>

            <div id="assetIssuesCard" className="md-card hcd-card-pad">
                <h3 className="hcd-mb-4">Broken Images & Assets</h3>
                <AssetIssuesSection
                    brokenImages={check?.checks?.http?.broken_images || []}
                    failedAssetRequests={check?.checks?.http?.failed_asset_requests || []}
                />
            </div>

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
