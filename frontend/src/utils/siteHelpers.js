// Pure helpers shared by App.jsx, extracted to their own module so App.jsx
// only exports the component (keeps Fast Refresh working) and so this logic
// is unit-testable without rendering the app.

export const STALE_THRESHOLD_HOURS = 24;

export const getHoursSinceLastCheck = (site) => {
    const timestamp = site?.update_summary?.timestamp;
    if (!timestamp) return Infinity;
    const checkDate = new Date(timestamp);
    if (isNaN(checkDate.getTime())) return Infinity;
    return (Date.now() - checkDate.getTime()) / (1000 * 60 * 60);
};

export const isSiteStale = (site) => getHoursSinceLastCheck(site) > STALE_THRESHOLD_HOURS;

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
