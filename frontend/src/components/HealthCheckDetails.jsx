import React, { useState, useEffect, useCallback } from "react";
import api from "../services/api";
import ImageLightbox from "./ImageLightbox";

// --- Helper sub-components ---

function SeverityBadge({ severity }) {
    const severityStyles = {
        critical: { backgroundColor: "var(--md-sys-color-error)", color: "#fff" },
        warning:  { backgroundColor: "#f59e0b", color: "#fff" },
        ignored:  { backgroundColor: "var(--md-sys-color-outline)", color: "#fff" },
    };
    const style = severityStyles[severity] || severityStyles.ignored;
    return (
        <span style={{
            ...style,
            padding: "0.15rem 0.55rem",
            borderRadius: "100px",
            fontSize: "0.7rem",
            fontWeight: "bold",
            letterSpacing: "0.05em",
            textTransform: "uppercase",
            flexShrink: 0,
        }}>
            {severity}
        </span>
    );
}

function SuppressionLabel({ error }) {
    if (error.suppression_source === "global") {
        return (
            <span style={{ fontSize: "0.72rem", color: "var(--md-sys-color-outline)", fontStyle: "italic" }}>
                🤖 Auto-suppressed: {error.suppression_reason}
            </span>
        );
    }
    if (error.suppression_source === "acknowledged") {
        const date = error.acknowledged_at
            ? new Date(error.acknowledged_at).toLocaleDateString()
            : "";
        return (
            <span style={{ fontSize: "0.72rem", color: "var(--md-sys-color-outline)", fontStyle: "italic" }}>
                ✅ Accepted{date ? ` on ${date}` : ""}: {error.suppression_reason}
            </span>
        );
    }
    return null;
}

function AcknowledgeForm({ onSubmit, onCancel, isBusy }) {
    const [reason, setReason] = useState("");
    return (
        <div style={{
            marginTop: "0.75rem",
            padding: "0.75rem",
            backgroundColor: "rgba(0,0,0,0.1)",
            borderRadius: "6px",
            display: "flex",
            flexDirection: "column",
            gap: "0.5rem",
        }}>
            <label style={{ fontSize: "0.8rem", color: "var(--md-sys-color-outline)" }}>
                Optional reason (visible in future reports):
            </label>
            <input
                type="text"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="e.g. Third-party plugin limitation — accepted risk"
                style={{
                    padding: "0.4rem 0.75rem",
                    borderRadius: "6px",
                    border: "1px solid var(--md-sys-color-outline-variant)",
                    background: "var(--md-sys-color-surface)",
                    color: "var(--md-sys-color-on-surface)",
                    fontSize: "0.875rem",
                    width: "100%",
                    boxSizing: "border-box",
                }}
            />
            <div style={{ display: "flex", gap: "0.5rem" }}>
                <button
                    className="md-button md-button-primary"
                    onClick={() => onSubmit(reason)}
                    disabled={isBusy}
                    style={{ fontSize: "0.8rem", padding: "0.3rem 0.9rem" }}
                >
                    {isBusy ? "Saving…" : "Confirm Accept"}
                </button>
                <button
                    className="md-button"
                    onClick={onCancel}
                    disabled={isBusy}
                    style={{ fontSize: "0.8rem", padding: "0.3rem 0.9rem" }}
                >
                    Cancel
                </button>
            </div>
        </div>
    );
}

function ConsoleErrorCard({ error, siteName, onAcknowledged, onUnacknowledged }) {
    const [showForm, setShowForm] = useState(false);
    const [busy, setBusy] = useState(false);
    const [localError, setLocalError] = useState(null);

    const isIgnored = error.severity === "ignored";
    const isAcknowledged = error.suppression_source === "acknowledged";
    const isAutoSuppressed = error.suppression_source === "global";

    const borderColors = {
        critical: "var(--md-sys-color-error)",
        warning:  "#f59e0b",
        ignored:  "var(--md-sys-color-outline-variant)",
    };
    const bgColors = {
        critical: "rgba(255, 0, 0, 0.04)",
        warning:  "rgba(245, 158, 11, 0.04)",
        ignored:  "rgba(0, 0, 0, 0.02)",
    };

    const handleAccept = useCallback(async (reason) => {
        setBusy(true);
        setLocalError(null);
        try {
            await api.acknowledgeConsoleError(siteName, error.fingerprint, reason);
            onAcknowledged(error.fingerprint, reason);
            setShowForm(false);
        } catch (e) {
            setLocalError(e.message);
        } finally {
            setBusy(false);
        }
    }, [siteName, error.fingerprint, onAcknowledged]);

    const handleUnaccept = useCallback(async () => {
        setBusy(true);
        setLocalError(null);
        try {
            await api.unacknowledgeConsoleError(siteName, error.fingerprint);
            onUnacknowledged(error.fingerprint);
        } catch (e) {
            setLocalError(e.message);
        } finally {
            setBusy(false);
        }
    }, [siteName, error.fingerprint, onUnacknowledged]);

    return (
        <div style={{
            backgroundColor: bgColors[error.severity] || bgColors.ignored,
            borderLeft: `4px solid ${borderColors[error.severity] || borderColors.ignored}`,
            borderRadius: "4px",
            padding: "1rem",
            opacity: isIgnored ? 0.75 : 1,
            overflow: "hidden",
        }}>
            <div style={{ display: "flex", alignItems: "flex-start", gap: "0.75rem", flexWrap: "wrap" }}>
                <SeverityBadge severity={error.severity} />
                <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{
                        fontFamily: "monospace",
                        fontWeight: "bold",
                        color: error.severity === "critical"
                            ? "var(--md-sys-color-error)"
                            : error.severity === "warning"
                            ? "#d97706"
                            : "var(--md-sys-color-on-surface-variant)",
                        wordBreak: "break-word",
                        overflowWrap: "anywhere",
                    }}>
                        {error.text}
                    </div>
                    <div style={{ marginTop: "0.35rem", fontSize: "0.75rem", color: "var(--md-sys-color-outline)", fontFamily: "monospace", wordBreak: "break-all", overflowWrap: "anywhere" }}>
                        {(() => {
                            const url = error.location?.url || "unknown";
                            const truncatedUrl = url.length > 150 ? url.slice(0, 150) + "…" : url;
                            const line = error.location?.lineNumber ? `:${error.location.lineNumber}` : "";
                            const col = error.location?.columnNumber ? `:${error.location.columnNumber}` : "";
                            return `Location: ${truncatedUrl}${line}${col}`;
                        })()}
                    </div>
                    <div style={{ marginTop: "0.25rem", fontSize: "0.72rem", color: "var(--md-sys-color-outline)", fontFamily: "monospace" }}>
                        ID: <code>{error.fingerprint}</code>
                    </div>
                    {isIgnored && (
                        <div style={{ marginTop: "0.35rem" }}>
                            <SuppressionLabel error={error} />
                        </div>
                    )}
                </div>
                {!isAutoSuppressed && (
                    <div style={{ flexShrink: 0 }}>
                        {isAcknowledged ? (
                            <button
                                className="md-button"
                                onClick={handleUnaccept}
                                disabled={busy}
                                title="Remove acknowledgment — this error will be flagged again"
                                style={{ fontSize: "0.78rem", padding: "0.25rem 0.75rem" }}
                            >
                                {busy ? "…" : "Unaccept"}
                            </button>
                        ) : (
                            !showForm && (
                                <button
                                    className="md-button md-button-tonal"
                                    onClick={() => setShowForm(true)}
                                    title="Accept this error — it will still be shown but won't block health checks"
                                    style={{ fontSize: "0.78rem", padding: "0.25rem 0.75rem" }}
                                >
                                    Accept risk
                                </button>
                            )
                        )}
                    </div>
                )}
            </div>

            {showForm && !isAcknowledged && (
                <AcknowledgeForm
                    onSubmit={handleAccept}
                    onCancel={() => setShowForm(false)}
                    isBusy={busy}
                />
            )}
            {localError && (
                <div style={{ marginTop: "0.5rem", fontSize: "0.8rem", color: "var(--md-sys-color-error)" }}>
                    Error: {localError}
                </div>
            )}
        </div>
    );
}

function ConsoleErrorsSection({ errors, siteName, onErrorsChanged }) {
    const [ignoredOpen, setIgnoredOpen] = useState(false);
    const [bulkBusy, setBulkBusy] = useState(false);

    const activeErrors = errors.filter((e) => e.severity !== "ignored");
    const ignoredErrors = errors.filter((e) => e.severity === "ignored");
    const unacceptedActive = activeErrors.filter(
        (e) => e.suppression_source !== "acknowledged" && e.suppression_source !== "global"
    );

    const handleAcknowledged = useCallback((fingerprint, reason) => {
        onErrorsChanged((prev) =>
            prev.map((e) =>
                e.fingerprint === fingerprint
                    ? {
                          ...e,
                          severity: "ignored",
                          suppression_source: "acknowledged",
                          suppression_reason: reason || "Acknowledged by operator",
                          acknowledged_at: new Date().toISOString(),
                      }
                    : e
            )
        );
    }, [onErrorsChanged]);

    const handleUnacknowledged = useCallback((fingerprint) => {
        onErrorsChanged((prev) =>
            prev.map((e) =>
                e.fingerprint === fingerprint
                    ? { ...e, severity: "critical", suppression_source: undefined, suppression_reason: undefined, acknowledged_at: undefined }
                    : e
            )
        );
    }, [onErrorsChanged]);

    const handleAcknowledgeAll = useCallback(async () => {
        setBulkBusy(true);
        try {
            for (const err of unacceptedActive) {
                await api.acknowledgeConsoleError(siteName, err.fingerprint, "Bulk accepted");
            }
            onErrorsChanged((prev) =>
                prev.map((e) =>
                    unacceptedActive.some((u) => u.fingerprint === e.fingerprint)
                        ? { ...e, severity: "ignored", suppression_source: "acknowledged", suppression_reason: "Bulk accepted", acknowledged_at: new Date().toISOString() }
                        : e
                )
            );
        } finally {
            setBulkBusy(false);
        }
    }, [siteName, unacceptedActive, onErrorsChanged]);

    if (errors.length === 0) {
        return (
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", color: "var(--md-sys-color-success)" }}>
                <span className="material-symbols-outlined">check_circle</span>
                <span>No console errors found. Good job!</span>
            </div>
        );
    }

    return (
        <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "0.5rem" }}>
                <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap" }}>
                    {activeErrors.filter(e => e.severity === "critical").length > 0 && (
                        <span style={{ color: "var(--md-sys-color-error)", fontWeight: 600, fontSize: "0.875rem" }}>
                            🔴 {activeErrors.filter(e => e.severity === "critical").length} critical
                        </span>
                    )}
                    {activeErrors.filter(e => e.severity === "warning").length > 0 && (
                        <span style={{ color: "#d97706", fontWeight: 600, fontSize: "0.875rem" }}>
                            🟡 {activeErrors.filter(e => e.severity === "warning").length} warning
                        </span>
                    )}
                    {ignoredErrors.length > 0 && (
                        <span style={{ color: "var(--md-sys-color-outline)", fontWeight: 600, fontSize: "0.875rem" }}>
                            ⚫ {ignoredErrors.length} ignored
                        </span>
                    )}
                </div>
                {unacceptedActive.length > 1 && (
                    <button
                        className="md-button md-button-tonal"
                        onClick={handleAcknowledgeAll}
                        disabled={bulkBusy}
                        style={{ fontSize: "0.8rem", padding: "0.3rem 0.9rem" }}
                        title="Accept all — errors still shown but won't block health checks"
                    >
                        {bulkBusy ? "Accepting…" : `Accept all ${unacceptedActive.length} active errors`}
                    </button>
                )}
            </div>

            {activeErrors.length > 0 && (
                <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                    {activeErrors.map((err) => (
                        <ConsoleErrorCard
                            key={err.fingerprint || err.text}
                            error={err}
                            siteName={siteName}
                            onAcknowledged={handleAcknowledged}
                            onUnacknowledged={handleUnacknowledged}
                        />
                    ))}
                </div>
            )}

            {ignoredErrors.length > 0 && (
                <div>
                    <button
                        onClick={() => setIgnoredOpen((o) => !o)}
                        style={{
                            display: "flex",
                            alignItems: "center",
                            gap: "0.4rem",
                            fontSize: "0.85rem",
                            color: "var(--md-sys-color-outline)",
                            background: "none",
                            border: "none",
                            cursor: "pointer",
                            padding: "0.25rem 0",
                            marginBottom: ignoredOpen ? "0.75rem" : 0,
                        }}
                    >
                        <span className="material-symbols-outlined" style={{ fontSize: "1.1rem", transition: "transform 0.2s", transform: ignoredOpen ? "rotate(90deg)" : "rotate(0deg)" }}>
                            chevron_right
                        </span>
                        {ignoredOpen ? "Hide" : "Show"} {ignoredErrors.length} ignored error{ignoredErrors.length > 1 ? "s" : ""}
                    </button>
                    {ignoredOpen && (
                        <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                            {ignoredErrors.map((err) => (
                                <ConsoleErrorCard
                                    key={err.fingerprint || err.text}
                                    error={err}
                                    siteName={siteName}
                                    onAcknowledged={handleAcknowledged}
                                    onUnacknowledged={handleUnacknowledged}
                                />
                            ))}
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}

// --- Main component ---

export default function HealthCheckDetails({ siteName, healthCheckId, onBack }) {
    const [check, setCheck] = useState(null);
    const [errors, setErrors] = useState([]);
    const [loading, setLoading] = useState(true);
    const [fetchError, setFetchError] = useState(null);
    const [desktopImgUrl, setDesktopImgUrl] = useState(null);
    const [mobileImgUrl, setMobileImgUrl] = useState(null);
    const [desktopDiffUrl, setDesktopDiffUrl] = useState(null);
    const [mobileDiffUrl, setMobileDiffUrl] = useState(null);
    const [isDiffAccepted, setIsDiffAccepted] = useState(false);
    const [acceptingDiff, setAcceptingDiff] = useState(false);
    const [diffReason, setDiffReason] = useState("");
    const [lightboxImage, setLightboxImage] = useState(null);

    useEffect(() => {
        let isMounted = true;

        async function fetchDetails() {
            setLoading(true);
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
    }, [siteName, healthCheckId]);

    useEffect(() => {
        return () => {
            if (desktopImgUrl) URL.revokeObjectURL(desktopImgUrl);
            if (mobileImgUrl) URL.revokeObjectURL(mobileImgUrl);
            if (desktopDiffUrl) URL.revokeObjectURL(desktopDiffUrl);
            if (mobileDiffUrl) URL.revokeObjectURL(mobileDiffUrl);
        };
    }, [desktopImgUrl, mobileImgUrl, desktopDiffUrl, mobileDiffUrl]);

    if (loading) {
        return (
            <div style={{ padding: "2rem", textAlign: "center" }}>
                <h2>Loading Health Check Details...</h2>
                <div style={{ marginTop: "1rem", color: "var(--md-sys-color-outline)" }}>Retrieving report data...</div>
            </div>
        );
    }

    if (fetchError) {
        return (
            <div className="md-card" style={{ padding: "2rem", margin: "2rem auto", maxWidth: "600px" }}>
                <h3 style={{ color: "var(--md-sys-color-error)" }}>Error Loading Health Check</h3>
                <p>{fetchError}</p>
                <button className="md-button md-button-primary" onClick={onBack} style={{ marginTop: "1rem" }}>
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

    let statusBadgeColor = "var(--md-sys-color-success)";
    if (overallStatus === "critical") statusBadgeColor = "var(--md-sys-color-error)";
    if (overallStatus === "degraded") statusBadgeColor = "var(--md-sys-color-warning)";
    if (overallStatus === "notice") statusBadgeColor = "var(--md-sys-color-primary)";

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
        <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem", paddingBottom: "3rem" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
                    <button className="md-button md-button-tonal md-button-icon" onClick={onBack}>
                        <span className="material-symbols-outlined">arrow_back</span>
                    </button>
                    <div>
                        <h2 style={{ margin: 0 }}>Health Check Report</h2>
                        <span style={{ fontSize: "0.875rem", color: "var(--md-sys-color-outline)" }}>
                            ID: {healthCheckId} • Checked: {new Date(check.timestamp).toLocaleString()}
                        </span>
                    </div>
                </div>
                <span 
                    onClick={scrollToRootCause}
                    title="Click to jump to root cause of this health status"
                    style={{
                        backgroundColor: statusBadgeColor,
                        color: "#fff",
                        padding: "0.5rem 1rem",
                        borderRadius: "100px",
                        fontWeight: "bold",
                        fontSize: "0.875rem",
                        textTransform: "uppercase",
                        cursor: "pointer",
                        userSelect: "none",
                        display: "inline-flex",
                        alignItems: "center",
                        gap: "0.35rem",
                        boxShadow: "0 2px 6px rgba(0,0,0,0.25)"
                    }}
                >
                    {overallStatus}
                    {(overallStatus === "critical" || overallStatus === "degraded" || activeErrorCount > 0) && (
                        <span className="material-symbols-outlined" style={{ fontSize: "16px" }}>south</span>
                    )}
                </span>
            </div>

            {/* Status Breakdown & Explanation Banner */}
            <div className="md-card" style={{ padding: "1.25rem 1.5rem", borderLeft: `5px solid ${statusBadgeColor}`, backgroundColor: "var(--md-sys-color-surface-variant)" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.5rem" }}>
                    <span className="material-symbols-outlined" style={{ color: statusBadgeColor }}>info</span>
                    <strong style={{ fontSize: "1rem" }}>Status Summary & Explanation</strong>
                </div>
                {check.status_reasons && check.status_reasons.length > 0 ? (
                    <ul style={{ margin: 0, paddingLeft: "1.25rem", color: "var(--md-sys-color-on-surface-variant)", fontSize: "0.9rem" }}>
                        {check.status_reasons.map((reason, idx) => (
                            <li key={idx} style={{ marginBottom: "0.25rem" }}>{reason}</li>
                        ))}
                    </ul>
                ) : (
                    <p style={{ margin: 0, fontSize: "0.9rem", color: "var(--md-sys-color-on-surface-variant)" }}>
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

            <div className="md-card" style={{ padding: "1.5rem" }}>
                <h3>Captured Screenshots</h3>
                <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: "1.5rem", marginTop: "1rem" }}>
                    <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                        <strong style={{ fontSize: "0.875rem", color: "var(--md-sys-color-outline)" }}>Desktop View (1280x800)</strong>
                        <div style={{ border: "1px solid var(--md-sys-color-outline-variant)", borderRadius: "8px", overflow: "hidden", backgroundColor: "#000", minHeight: "200px", display: "flex", alignItems: "center", justifyContent: "center" }}>
                            {desktopImgUrl
                                ? <img src={desktopImgUrl} alt="Desktop View" onClick={() => setLightboxImage({ src: desktopImgUrl, alt: "Desktop View (1280x800)" })} style={{ width: "100%", height: "auto", display: "block", cursor: "zoom-in" }} title="Click to enlarge & magnify" />
                                : <div style={{ color: "#aaa" }}>No screenshot available</div>
                            }
                        </div>
                    </div>
                    <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                        <strong style={{ fontSize: "0.875rem", color: "var(--md-sys-color-outline)" }}>Mobile View (375x667)</strong>
                        <div style={{ border: "1px solid var(--md-sys-color-outline-variant)", borderRadius: "8px", overflow: "hidden", backgroundColor: "#000", minHeight: "200px", display: "flex", alignItems: "center", justifyContent: "center" }}>
                            {mobileImgUrl
                                ? <img src={mobileImgUrl} alt="Mobile View" onClick={() => setLightboxImage({ src: mobileImgUrl, alt: "Mobile View (375x667)" })} style={{ width: "100%", height: "auto", display: "block", cursor: "zoom-in" }} title="Click to enlarge & magnify" />
                                : <div style={{ color: "#aaa" }}>No screenshot available</div>
                            }
                        </div>
                    </div>
                </div>
            </div>

            {check.checks?.http?.screenshot_diffs && !check.checks.http.screenshot_diffs.matched && (
                <div id="visualDiffCard" className="md-card" style={{ padding: "1.5rem", border: isDiffAccepted ? "1px solid var(--md-sys-color-primary)" : "1px solid var(--md-sys-color-error)", backgroundColor: isDiffAccepted ? "rgba(0, 160, 255, 0.02)" : "rgba(255, 0, 128, 0.02)" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "1rem", marginBottom: "1rem" }}>
                        <div>
                            <h3 style={{ color: isDiffAccepted ? "var(--md-sys-color-primary)" : "var(--md-sys-color-error)", display: "flex", alignItems: "center", gap: "0.5rem", margin: 0 }}>
                                <span className="material-symbols-outlined">difference</span>
                                Visual Differences Detected (Pre vs Post Update)
                            </h3>
                            <p style={{ fontSize: "0.875rem", color: "var(--md-sys-color-outline)", margin: "0.35rem 0 0 0" }}>
                                {isDiffAccepted 
                                    ? "Visual difference has been accepted by an admin and will not block site updates or health status." 
                                    : "The layout changed after applying the update. Differences are highlighted in magenta below."
                                }
                            </p>
                        </div>
                        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                            {isDiffAccepted ? (
                                <button
                                    className="md-button md-button-outlined"
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
                                    style={{ borderColor: "var(--md-sys-color-error)", color: "var(--md-sys-color-error)" }}
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

                    <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: "1.5rem" }}>
                        <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                            <strong style={{ fontSize: "0.875rem", color: "var(--md-sys-color-outline)" }}>Desktop Visual Diff (1280x800)</strong>
                            <div style={{ border: "1px solid var(--md-sys-color-outline-variant)", borderRadius: "8px", overflow: "hidden", backgroundColor: "#000", minHeight: "200px", display: "flex", alignItems: "center", justifyContent: "center" }}>
                                {desktopDiffUrl
                                    ? <img src={desktopDiffUrl} alt="Desktop Visual Diff" onClick={() => setLightboxImage({ src: desktopDiffUrl, alt: "Desktop Visual Diff (1280x800)" })} style={{ width: "100%", height: "auto", display: "block", cursor: "zoom-in" }} title="Click to enlarge & magnify" />
                                    : <div style={{ color: "#aaa" }}>No diff image available</div>
                                }
                            </div>
                        </div>
                        <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                            <strong style={{ fontSize: "0.875rem", color: "var(--md-sys-color-outline)" }}>Mobile Visual Diff (375x667)</strong>
                            <div style={{ border: "1px solid var(--md-sys-color-outline-variant)", borderRadius: "8px", overflow: "hidden", backgroundColor: "#000", minHeight: "200px", display: "flex", alignItems: "center", justifyContent: "center" }}>
                                {mobileDiffUrl
                                    ? <img src={mobileDiffUrl} alt="Mobile Visual Diff" onClick={() => setLightboxImage({ src: mobileDiffUrl, alt: "Mobile Visual Diff (375x667)" })} style={{ width: "100%", height: "auto", display: "block", cursor: "zoom-in" }} title="Click to enlarge & magnify" />
                                    : <div style={{ color: "#aaa" }}>No diff image available</div>
                                }
                            </div>
                        </div>
                    </div>
                </div>
            )}

            <div id="httpMetricsCard" className="md-card" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: "1.5rem", padding: "1.5rem" }}>
                <div>
                    <div style={{ color: "var(--md-sys-color-outline)", fontSize: "0.875rem" }}>HTTP Response Code</div>
                    <div style={{ fontSize: "2rem", fontWeight: "bold", color: http.status_code <= 302 ? "var(--md-sys-color-success)" : "var(--md-sys-color-error)" }}>
                        {http.status_code || "N/A"}
                    </div>
                </div>
                <div>
                    <div style={{ color: "var(--md-sys-color-outline)", fontSize: "0.875rem" }}>Response Time</div>
                    <div style={{ fontSize: "2rem", fontWeight: "bold" }}>
                        {http.response_time_ms ? `${http.response_time_ms} ms` : "N/A"}
                    </div>
                </div>
                <div>
                    <div style={{ color: "var(--md-sys-color-outline)", fontSize: "0.875rem" }}>Active Errors</div>
                    <div style={{ fontSize: "2rem", fontWeight: "bold", color: activeErrorCount > 0 ? "var(--md-sys-color-error)" : "var(--md-sys-color-success)" }}>
                        {activeErrorCount}
                    </div>
                </div>
                {ignoredErrorCount > 0 && (
                    <div>
                        <div style={{ color: "var(--md-sys-color-outline)", fontSize: "0.875rem" }}>Ignored / Accepted</div>
                        <div style={{ fontSize: "2rem", fontWeight: "bold", color: "var(--md-sys-color-outline)" }}>
                            {ignoredErrorCount}
                        </div>
                    </div>
                )}
            </div>

            <div id="consoleErrorsCard" className="md-card" style={{ padding: "1.5rem" }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1rem", flexWrap: "wrap", gap: "0.5rem" }}>
                    <h3 style={{ margin: 0 }}>Console Errors</h3>
                    {ignoredErrorCount > 0 && activeErrorCount === 0 && (
                        <span style={{ fontSize: "0.8rem", color: "var(--md-sys-color-outline)", fontStyle: "italic" }}>
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
