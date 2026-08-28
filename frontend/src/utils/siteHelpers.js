// Pure helpers shared by App.jsx, extracted to their own module so App.jsx
// only exports the component (keeps Fast Refresh working) and so this logic
// is unit-testable without rendering the app.

// Staleness thresholds live in siteStaleness.js so the dashboard chip, the card
// dot and the component badges cannot drift apart. These wrappers just adapt a
// whole `site` to the `updateInfo` shape those helpers take.
import {
    UPDATE_FRESH_HOURS,
    getHoursSinceLastUpdateCheck,
    isUpdateCheckStale,
} from "./siteStaleness";

export const STALE_THRESHOLD_HOURS = UPDATE_FRESH_HOURS;

export const getHoursSinceLastCheck = (site) => getHoursSinceLastUpdateCheck(site?.update_summary);

export const isSiteStale = (site) => isUpdateCheckStale(site?.update_summary);

// Strips scheme/www for a compact display label while callers keep the
// full URL as the link href (mirrors SiteConfigManager.get_site_domain()).
export const getDisplayDomain = (url) => {
    if (!url) return "";
    return url.replace(/^https?:\/\//i, "").replace(/^www\./i, "").replace(/\/$/, "");
};

export const arePathsEqual = (pathA, pathB, homeDir) => {
    if (!pathA || !pathB) return false;

    const norm = (p) => {
        let res = p.replace(/\\/g, "/").trim();
        if (homeDir) {
            if (res.startsWith("~/")) {
                res = homeDir.replace(/\\/g, "/") + res.substring(1);
            }
        }
        if (res.endsWith("/")) {
            res = res.slice(0, -1);
        }
        return res.toLowerCase();
    };

    return norm(pathA) === norm(pathB);
};
