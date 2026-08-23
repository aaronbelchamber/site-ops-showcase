// Pure staleness/badge helpers extracted from SiteCard.jsx so they can be
// unit tested without rendering the component. All take `updateInfo` (the
// site's cached update-check summary, or null/undefined) explicitly rather
// than closing over component state.

export const getDaysSinceLastUpdateCheck = (updateInfo) => {
    if (!updateInfo || !updateInfo.timestamp) return Infinity;
    const checkDate = new Date(updateInfo.timestamp);
    if (isNaN(checkDate.getTime())) return Infinity;
    const diffMs = Date.now() - checkDate.getTime();
    return Math.max(0, Math.floor(diffMs / (1000 * 60 * 60 * 24)));
};

// Compact, always-visible "last checked" label (the tooltip only shows on hover,
// which isn't enough for at-a-glance staleness scanning across many cards).
export const getLastCheckedLabel = (updateInfo) => {
    if (!updateInfo || !updateInfo.timestamp) return "Never checked";
    const checkDate = new Date(updateInfo.timestamp);
    if (isNaN(checkDate.getTime())) return "Never checked";
    const diffHours = (Date.now() - checkDate.getTime()) / (1000 * 60 * 60);
    if (diffHours < 1) return "Checked <1h ago";
    if (diffHours < 24) return `Checked ${Math.floor(diffHours)}h ago`;
    return `Checked ${getDaysSinceLastUpdateCheck(updateInfo)}d ago`;
};

export const getUpdateStalenessTooltip = (updateInfo) => {
    const daysSinceCheck = getDaysSinceLastUpdateCheck(updateInfo);
    if (!updateInfo || !updateInfo.timestamp || daysSinceCheck === Infinity) {
        return "Last update check: Never run. Update status is unverified.";
    }
    const formattedDate = new Date(updateInfo.timestamp).toLocaleDateString(undefined, {
        month: 'short', day: 'numeric', year: 'numeric'
    });
    if (daysSinceCheck <= 7) {
        return `Last update check: ${formattedDate} (${daysSinceCheck === 0 ? 'today' : daysSinceCheck + 'd ago'}) - Fresh`;
    }
    if (daysSinceCheck <= 30) {
        return `Last update check: ${formattedDate} (${daysSinceCheck}d ago) - Stale (>7 days)`;
    }
    return `Last update check: ${formattedDate} (${daysSinceCheck}d ago) - Very Stale (>30 days)`;
};

export const getStatusDotClass = (updateInfo) => {
    const daysSinceCheck = getDaysSinceLastUpdateCheck(updateInfo);
    if (daysSinceCheck <= 7) return "status-circle-green";
    if (daysSinceCheck <= 30) return "status-circle-yellow";
    return "status-circle-orange";
};

// Health badge keeps UPPERCASE
export const getHealthBadgeClass = (status) => {
    switch ((status || "").toLowerCase()) {
        case "healthy":
        case "healthy*":
        case "healthy with exception":
        case "ok":
        case "success":
        case "pass":
            return "badge badge-success";
        case "notice":
        case "minor issues":
        case "info":
            return "badge badge-info";
        case "checking...":
        case "loading":
        case "warning":
        case "degraded":
        case "in progress":
            return "badge badge-warning";
        case "archived":
        case "neutral":
            return "badge badge-neutral";
        case "error":
        case "failed":
        case "critical":
        default:
            return "badge badge-error";
    }
};
