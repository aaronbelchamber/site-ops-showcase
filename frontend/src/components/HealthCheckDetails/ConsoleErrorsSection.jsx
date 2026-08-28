import React, { useState, useCallback } from "react";
import api from "../../services/api";
import { ConsoleErrorCard } from "./ConsoleErrorCard";

export function ConsoleErrorsSection({ errors, siteName, onErrorsChanged }) {
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
            <div className="hcd-empty-success">
                <span className="material-symbols-outlined">check_circle</span>
                <span>No console errors found. Good job!</span>
            </div>
        );
    }

    return (
        <div className="hcd-col hcd-gap-xl">
            <div className="hcd-row hcd-justify-between hcd-wrap hcd-gap-sm">
                <div className="hcd-row hcd-gap-md hcd-wrap">
                    {activeErrors.filter(e => e.severity === "critical").length > 0 && (
                        <span className="hcd-count hcd-count--critical">
                            🔴 {activeErrors.filter(e => e.severity === "critical").length} critical
                        </span>
                    )}
                    {activeErrors.filter(e => e.severity === "warning").length > 0 && (
                        <span className="hcd-count hcd-count--warning">
                            🟡 {activeErrors.filter(e => e.severity === "warning").length} warning
                        </span>
                    )}
                    {ignoredErrors.length > 0 && (
                        <span className="hcd-count hcd-count--ignored">
                            ⚫ {ignoredErrors.length} ignored
                        </span>
                    )}
                </div>
                {unacceptedActive.length > 1 && (
                    <button
                        className="md-button md-button-tonal hcd-btn-sm"
                        onClick={handleAcknowledgeAll}
                        disabled={bulkBusy}
                        title="Accept all — errors still shown but won't block health checks"
                    >
                        {bulkBusy ? "Accepting…" : `Accept all ${unacceptedActive.length} active errors`}
                    </button>
                )}
            </div>

            {activeErrors.length > 0 && (
                <div className="hcd-col hcd-gap-md">
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
                        className={`hcd-ignored-toggle ${ignoredOpen ? "hcd-ignored-toggle--open" : ""}`}
                    >
                        <span className={`material-symbols-outlined hcd-ignored-toggle__icon ${ignoredOpen ? "hcd-ignored-toggle__icon--open" : ""}`}>
                            chevron_right
                        </span>
                        {ignoredOpen ? "Hide" : "Show"} {ignoredErrors.length} ignored error{ignoredErrors.length > 1 ? "s" : ""}
                    </button>
                    {ignoredOpen && (
                        <div className="hcd-col hcd-gap-md">
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
