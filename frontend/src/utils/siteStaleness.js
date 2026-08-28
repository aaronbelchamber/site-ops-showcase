// Pure staleness/badge helpers extracted from SiteCard.jsx so they can be
// unit tested without rendering the component. All take `updateInfo` (the
// site's cached update-check summary, or null/undefined) explicitly rather
// than closing over component state.

// ---------------------------------------------------------------------------
// One scale for update-check age.
//
// Three surfaces used to disagree about the same fact: the dashboard chip
// counted a site stale after 24h, while the card dot stayed green for 7 days
// and the component badges said "ok" alongside it. A site checked 30 hours ago
// was simultaneously "Stale (>24h): 1" and green/"core ok", which made the
// dashboard's own summary look wrong.
//
// Everything below derives from these thresholds, so the chip, the dot, the
// badges and the tooltip always agree.
// ---------------------------------------------------------------------------
export const UPDATE_FRESH_HOURS = 24;   // fresh          -> stale
export const UPDATE_STALE_DAYS = 7;     // stale          -> very stale
export const UPDATE_VERY_STALE_DAYS = 30; // very stale   -> critical

export const UPDATE_TIER = {
    FRESH: "fresh",
    STALE: "stale",
    VERY_STALE: "very-stale",
    CRITICAL: "critical",
};

export const getHoursSinceLastUpdateCheck = (updateInfo) => {
    if (!updateInfo || !updateInfo.timestamp) return Infinity;
    const checkDate = new Date(updateInfo.timestamp);
    if (isNaN(checkDate.getTime())) return Infinity;
    return Math.max(0, (Date.now() - checkDate.getTime()) / (1000 * 60 * 60));
};

/** Which tier an update-check age falls into. The single branch point. */
export const getUpdateTier = (updateInfo) => {
    const hours = getHoursSinceLastUpdateCheck(updateInfo);
    if (hours === Infinity) return UPDATE_TIER.CRITICAL;
    if (hours <= UPDATE_FRESH_HOURS) return UPDATE_TIER.FRESH;
    if (hours <= UPDATE_STALE_DAYS * 24) return UPDATE_TIER.STALE;
    if (hours <= UPDATE_VERY_STALE_DAYS * 24) return UPDATE_TIER.VERY_STALE;
    return UPDATE_TIER.CRITICAL;
};

/** True when the dashboard chip should count this site. Matches "dot is not green". */
export const isUpdateCheckStale = (updateInfo) => getUpdateTier(updateInfo) !== UPDATE_TIER.FRESH;

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
    const age = daysSinceCheck === 0 ? 'today' : `${daysSinceCheck}d ago`;
    const tier = getUpdateTier(updateInfo);
    if (tier === UPDATE_TIER.FRESH) {
        return `Last update check: ${formattedDate} (${age}) - Fresh`;
    }
    if (tier === UPDATE_TIER.STALE) {
        return `Last update check: ${formattedDate} (${age}) - Stale (>${UPDATE_FRESH_HOURS} hours)`;
    }
    if (tier === UPDATE_TIER.VERY_STALE) {
        return `Last update check: ${formattedDate} (${age}) - Stale (>${UPDATE_STALE_DAYS} days)`;
    }
    return `Last update check: ${formattedDate} (${age}) - Very Stale (>${UPDATE_VERY_STALE_DAYS} days)`;
};

const UPDATE_TIER_DOT = {
    [UPDATE_TIER.FRESH]: "status-circle-green",
    [UPDATE_TIER.STALE]: "status-circle-yellow",
    [UPDATE_TIER.VERY_STALE]: "status-circle-orange",
    [UPDATE_TIER.CRITICAL]: "status-circle-red",
};

export const getStatusDotClass = (updateInfo) => UPDATE_TIER_DOT[getUpdateTier(updateInfo)];

/** Badge colour for a per-component (core/plugins/themes) staleness chip. */
const UPDATE_TIER_BADGE = {
    [UPDATE_TIER.FRESH]: "badge-success",
    [UPDATE_TIER.STALE]: "badge-stale-yellow",
    [UPDATE_TIER.VERY_STALE]: "badge-stale-orange",
    [UPDATE_TIER.CRITICAL]: "badge-error",
};

export const getUpdateTierBadgeClass = (updateInfo) => UPDATE_TIER_BADGE[getUpdateTier(updateInfo)];

/** Short suffix describing the tier, e.g. "stale (>7d)". */
const UPDATE_TIER_SUFFIX = {
    [UPDATE_TIER.FRESH]: "ok",
    [UPDATE_TIER.STALE]: `stale (>${UPDATE_FRESH_HOURS}h)`,
    [UPDATE_TIER.VERY_STALE]: `stale (>${UPDATE_STALE_DAYS}d)`,
    [UPDATE_TIER.CRITICAL]: `stale (>${UPDATE_VERY_STALE_DAYS}d)`,
};

export const getUpdateTierSuffix = (updateInfo) => UPDATE_TIER_SUFFIX[getUpdateTier(updateInfo)];

// Health-check staleness (Production Health dashboard): a separate, shorter
// scale from the update-check staleness above, since a stale health check
// means "we haven't looked at the live site/console errors recently" rather
// than "we haven't checked for WP updates recently".
export const getDaysSinceHealthCheck = (healthSummary) => {
    if (!healthSummary || !healthSummary.timestamp) return Infinity;
    const checkDate = new Date(healthSummary.timestamp);
    if (isNaN(checkDate.getTime())) return Infinity;
    const diffMs = Date.now() - checkDate.getTime();
    return Math.max(0, Math.floor(diffMs / (1000 * 60 * 60 * 24)));
};

export const getHealthCheckedLabel = (healthSummary) => {
    if (!healthSummary || !healthSummary.timestamp) return "Never checked";
    const checkDate = new Date(healthSummary.timestamp);
    if (isNaN(checkDate.getTime())) return "Never checked";
    const diffHours = (Date.now() - checkDate.getTime()) / (1000 * 60 * 60);
    if (diffHours < 1) return "Checked <1h ago";
    if (diffHours < 24) return `Checked ${Math.floor(diffHours)}h ago`;
    return `Checked ${getDaysSinceHealthCheck(healthSummary)}d ago`;
};

// green <3d, yellow 3-7d, red >7d (or never checked)
export const getHealthStatusDotClass = (healthSummary) => {
    const daysSinceCheck = getDaysSinceHealthCheck(healthSummary);
    if (daysSinceCheck === Infinity) return "status-circle-red";
    if (daysSinceCheck < 3) return "status-circle-green";
    if (daysSinceCheck <= 7) return "status-circle-yellow";
    return "status-circle-red";
};

export const isHealthCheckStale = (healthSummary) => getDaysSinceHealthCheck(healthSummary) >= 3;

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
        // "not checked" is an absence of data, not a failure -- it used to fall
        // through to the default and render as a red error badge.
        case "not checked":
        case "unknown":
        case "":
            return "badge badge-neutral";
        case "error":
        case "failed":
        case "critical":
        default:
            return "badge badge-error";
    }
};
