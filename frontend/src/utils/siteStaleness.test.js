import { describe, it, expect } from "vitest";
import {
    getDaysSinceLastUpdateCheck,
    getLastCheckedLabel,
    getUpdateStalenessTooltip,
    getStatusDotClass,
    getHealthBadgeClass,
} from "./siteStaleness";

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

    it("says Fresh within 7 days", () => {
        expect(getUpdateStalenessTooltip(updateInfoHoursAgo(3 * 24))).toContain("Fresh");
    });

    it("says Stale between 7 and 30 days", () => {
        expect(getUpdateStalenessTooltip(updateInfoHoursAgo(10 * 24))).toContain("Stale (>7 days)");
    });

    it("says Very Stale beyond 30 days", () => {
        expect(getUpdateStalenessTooltip(updateInfoHoursAgo(35 * 24))).toContain("Very Stale (>30 days)");
    });
});

describe("getStatusDotClass", () => {
    it("is green within 7 days", () => {
        expect(getStatusDotClass(updateInfoHoursAgo(3 * 24))).toBe("status-circle-green");
    });

    it("is yellow between 7 and 30 days", () => {
        expect(getStatusDotClass(updateInfoHoursAgo(10 * 24))).toBe("status-circle-yellow");
    });

    it("is orange beyond 30 days or never checked", () => {
        expect(getStatusDotClass(updateInfoHoursAgo(35 * 24))).toBe("status-circle-orange");
        expect(getStatusDotClass(null)).toBe("status-circle-orange");
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
        ["", "badge badge-error"],
    ])("maps %s to %s", (status, expected) => {
        expect(getHealthBadgeClass(status)).toBe(expected);
    });
});
