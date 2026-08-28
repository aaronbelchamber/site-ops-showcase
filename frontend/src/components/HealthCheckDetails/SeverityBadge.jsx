import React from "react";

export function SeverityBadge({ severity }) {
    const modifier = severity === "critical" || severity === "warning" ? severity : "ignored";
    return (
        <span className={`hcd-badge hcd-badge--${modifier}`}>
            {severity}
        </span>
    );
}
