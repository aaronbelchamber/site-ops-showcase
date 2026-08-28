import React, { useState, useCallback } from "react";
import api from "../../services/api";
import { SeverityBadge } from "./SeverityBadge";
import { SuppressionLabel } from "./SuppressionLabel";
import { AcknowledgeForm } from "./AcknowledgeForm";

export function ConsoleErrorCard({ error, siteName, onAcknowledged, onUnacknowledged }) {
    const [showForm, setShowForm] = useState(false);
    const [busy, setBusy] = useState(false);
    const [localError, setLocalError] = useState(null);

    const isIgnored = error.severity === "ignored";
    const isAcknowledged = error.suppression_source === "acknowledged";
    const isAutoSuppressed = error.suppression_source === "global";
    const severityModifier = error.severity === "critical" || error.severity === "warning" ? error.severity : "ignored";

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
        <div className={`hcd-error-card hcd-error-card--${severityModifier} ${isIgnored ? "hcd-error-card--muted" : ""}`}>
            <div className="hcd-row-start hcd-gap-md hcd-wrap">
                <SeverityBadge severity={error.severity} />
                <div className="hcd-flex-1">
                    <div className={`hcd-error-card__message ${error.severity === "critical" ? "hcd-error-card__message--critical" : error.severity === "warning" ? "hcd-error-card__message--warning" : ""}`}>
                        {error.text}
                    </div>
                    <div className="hcd-error-card__location">
                        {(() => {
                            const url = error.location?.url || "unknown";
                            const truncatedUrl = url.length > 150 ? url.slice(0, 150) + "…" : url;
                            const line = error.location?.lineNumber ? `:${error.location.lineNumber}` : "";
                            const col = error.location?.columnNumber ? `:${error.location.columnNumber}` : "";
                            return `Location: ${truncatedUrl}${line}${col}`;
                        })()}
                    </div>
                    <div className="hcd-error-card__id">
                        ID: <code>{error.fingerprint}</code>
                    </div>
                    {isIgnored && (
                        <div className="hcd-error-card__suppression-wrap">
                            <SuppressionLabel error={error} />
                        </div>
                    )}
                </div>
                {!isAutoSuppressed && (
                    <div className="hcd-shrink-0">
                        {isAcknowledged ? (
                            <button
                                className="md-button hcd-btn-xs"
                                onClick={handleUnaccept}
                                disabled={busy}
                                title="Remove acknowledgment — this error will be flagged again"
                            >
                                {busy ? "…" : "Unaccept"}
                            </button>
                        ) : (
                            !showForm && (
                                <button
                                    className="md-button md-button-tonal hcd-btn-xs"
                                    onClick={() => setShowForm(true)}
                                    title="Accept this error — it will still be shown but won't block health checks"
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
                <div className="hcd-error-card__local-error">
                    Error: {localError}
                </div>
            )}
        </div>
    );
}
