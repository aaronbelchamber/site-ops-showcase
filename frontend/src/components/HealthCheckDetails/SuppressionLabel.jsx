import React from "react";

export function SuppressionLabel({ error }) {
    if (error.suppression_source === "global") {
        return (
            <span className="hcd-suppression-label">
                🤖 Auto-suppressed: {error.suppression_reason}
            </span>
        );
    }
    if (error.suppression_source === "acknowledged") {
        const date = error.acknowledged_at
            ? new Date(error.acknowledged_at).toLocaleDateString()
            : "";
        return (
            <span className="hcd-suppression-label">
                ✅ Accepted{date ? ` on ${date}` : ""}: {error.suppression_reason}
            </span>
        );
    }
    return null;
}
