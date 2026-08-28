import { describe, it, expect } from "vitest";
import {
    getDaysSinceLastUpdateCheck,
    getLastCheckedLabel,
    getUpdateStalenessTooltip,
    getStatusDotClass,
    getUpdateTierBadgeClass,
    getUpdateTierSuffix,
    getUpdateTier,
    isUpdateCheckStale,
    UPDATE_TIER,
    getHealthBadgeClass,
} from "./siteStaleness";
import { isSiteStale } from "./siteHelpers";

const updateInfoHoursAgo = (hours) => ({
    timestamp: new Date(Date.now() - hours * 60 * 60 * 1000).toISOString(),
});

describe("getDaysSinceLastUpdateCheck", () => {
    it("returns Infinity when updateInfo is missing", () => {
        expect(getDaysSinceLastUpdateCheck(null)).toBe(Infinity);
        expect(getDaysSinceLastUpdateCheck(undefined)).toBe(Infinity);
    });

    it("returns Infinity when timestamp is missing or unparseable", () => {
        expect(getDaysSinceLastUpdateCheck({})).toBe(Infinity);
        expect(getDaysSinceLastUpdateCheck({ timestamp: "garbage" })).toBe(Infinity);
    });

    it("returns 0 for a check within the last 24h", () => {
        expect(getDaysSinceLastUpdateCheck(updateInfoHoursAgo(5))).toBe(0);
    });

    it("returns the correct whole-day count", () => {
        expect(getDaysSinceLastUpdateCheck(updateInfoHoursAgo(50))).toBe(2);
    });
});

describe("getLastCheckedLabel", () => {
    it("reports never checked when there is no timestamp", () => {
        expect(getLastCheckedLabel(null)).toBe("Never checked");
        expect(getLastCheckedLabel({})).toBe("Never checked");
    });

    it("reports <1h for a very recent check", () => {
        expect(getLastCheckedLabel(updateInfoHoursAgo(0.5))).toBe("Checked <1h ago");
    });

    it("reports whole hours under a day", () => {
        expect(getLastCheckedLabel(updateInfoHoursAgo(5))).toBe("Checked 5h ago");
    });

    it("reports days once past 24h", () => {
        expect(getLastCheckedLabel(updateInfoHoursAgo(50))).toBe("Checked 2d ago");
    });
});

describe("getUpdateStalenessTooltip", () => {
    it("says never run when there's no data", () => {
        expect(getUpdateStalenessTooltip(null)).toContain("Never run");
    });

    it("says Fresh within 24 hours", () => {
        expect(getUpdateStalenessTooltip(updateInfoHoursAgo(5))).toContain("Fresh");
    });

    it("says Stale (>24 hours) between 1 and 7 days", () => {
        expect(getUpdateStalenessTooltip(updateInfoHoursAgo(3 * 24))).toContain("Stale (>24 hours)");
    });

    it("says Stale (>7 days) between 7 and 30 days", () => {
        expect(getUpdateStalenessTooltip(updateInfoHoursAgo(10 * 24))).toContain("Stale (>7 days)");
    });

    it("says Very Stale beyond 30 days", () => {
        expect(getUpdateStalenessTooltip(updateInfoHoursAgo(35 * 24))).toContain("Very Stale (>30 days)");
    });
});

describe("getStatusDotClass", () => {
    it("is green within 24 hours", () => {
        expect(getStatusDotClass(updateInfoHoursAgo(5))).toBe("status-circle-green");
    });

    it("is yellow between 24 hours and 7 days", () => {
        expect(getStatusDotClass(updateInfoHoursAgo(3 * 24))).toBe("status-circle-yellow");
    });

    it("is orange between 7 and 30 days", () => {
        expect(getStatusDotClass(updateInfoHoursAgo(10 * 24))).toBe("status-circle-orange");
    });

    it("is red beyond 30 days or never checked", () => {
        expect(getStatusDotClass(updateInfoHoursAgo(35 * 24))).toBe("status-circle-red");
        expect(getStatusDotClass(null)).toBe("status-circle-red");
    });
});

describe("staleness is consistent across surfaces", () => {
    // The bug this guards against: a site checked 30 hours ago was counted by
    // the dashboard chip as stale while its dot stayed green and its badges
    // said "ok" -- three surfaces disagreeing about one fact.
    const AGES_HOURS = [0.5, 5, 23, 25, 30, 3 * 24, 8 * 24, 31 * 24];

    it.each(AGES_HOURS)("at %s hours old, the chip and the dot agree", (hours) => {
        const info = updateInfoHoursAgo(hours);
        const countedStaleByChip = isSiteStale({ update_summary: info });
        const dotIsGreen = getStatusDotClass(info) === "status-circle-green";
        expect(countedStaleByChip).toBe(!dotIsGreen);
    });

    it.each(AGES_HOURS)("at %s hours old, the badge colour matches the tier", (hours) => {
        const info = updateInfoHoursAgo(hours);
        const isFresh = getUpdateTier(info) === UPDATE_TIER.FRESH;
        expect(getUpdateTierBadgeClass(info) === "badge-success").toBe(isFresh);
        expect(getUpdateTierSuffix(info) === "ok").toBe(isFresh);
    });

    it("treats a never-checked site as stale everywhere", () => {
        expect(isSiteStale({ update_summary: null })).toBe(true);
        expect(isUpdateCheckStale(null)).toBe(true);
        expect(getStatusDotClass(null)).toBe("status-circle-red");
        expect(getUpdateTier(null)).toBe(UPDATE_TIER.CRITICAL);
    });
});

describe("getHealthBadgeClass", () => {
    it.each([
        ["healthy", "badge badge-success"],
        ["HEALTHY*", "badge badge-success"],
        ["pass", "badge badge-success"],
        ["notice", "badge badge-info"],
        ["degraded", "badge badge-warning"],
        ["checking...", "badge badge-warning"],
        ["archived", "badge badge-neutral"],
        ["critical", "badge badge-error"],
        ["anything-unrecognized", "badge badge-error"],
        // Absence of data reads neutral, not as a critical failure.
        ["", "badge badge-neutral"],
        ["not checked", "badge badge-neutral"],
        ["unknown", "badge badge-neutral"],
    ])("maps %s to %s", (status, expected) => {
        expect(getHealthBadgeClass(status)).toBe(expected);
    });
});
