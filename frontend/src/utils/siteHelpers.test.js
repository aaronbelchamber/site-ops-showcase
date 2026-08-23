import { describe, it, expect } from "vitest";
import { STALE_THRESHOLD_HOURS, getHoursSinceLastCheck, isSiteStale, arePathsEqual } from "./siteHelpers";

const siteWithTimestamp = (hoursAgo) => ({
    site_name: "test-site",
    update_summary: {
        timestamp: new Date(Date.now() - hoursAgo * 60 * 60 * 1000).toISOString(),
    },
});

describe("getHoursSinceLastCheck", () => {
    it("returns Infinity when there is no update_summary", () => {
        expect(getHoursSinceLastCheck({ site_name: "x" })).toBe(Infinity);
    });

    it("returns Infinity when the timestamp is missing", () => {
        expect(getHoursSinceLastCheck({ update_summary: {} })).toBe(Infinity);
    });

    it("returns Infinity when the timestamp is unparseable", () => {
        expect(getHoursSinceLastCheck({ update_summary: { timestamp: "not-a-date" } })).toBe(Infinity);
    });

    it("returns roughly the number of hours since the timestamp", () => {
        const hours = getHoursSinceLastCheck(siteWithTimestamp(5));
        expect(hours).toBeGreaterThan(4.9);
        expect(hours).toBeLessThan(5.1);
    });
});

describe("isSiteStale", () => {
    it("is false just under the threshold", () => {
        expect(isSiteStale(siteWithTimestamp(STALE_THRESHOLD_HOURS - 1))).toBe(false);
    });

    it("is true just over the threshold", () => {
        expect(isSiteStale(siteWithTimestamp(STALE_THRESHOLD_HOURS + 1))).toBe(true);
    });

    it("treats a never-checked site as stale", () => {
        expect(isSiteStale({ site_name: "never-checked" })).toBe(true);
    });
});

describe("arePathsEqual", () => {
    it("returns false when either path is missing", () => {
        expect(arePathsEqual(null, "/var/www")).toBe(false);
        expect(arePathsEqual("/var/www", undefined)).toBe(false);
    });

    it("normalizes backslashes and trailing slashes", () => {
        expect(arePathsEqual("C:\\sites\\example\\", "C:/sites/example")).toBe(true);
    });

    it("is case-insensitive", () => {
        expect(arePathsEqual("/var/WWW/Example", "/var/www/example")).toBe(true);
    });

    it("expands a leading ~/ against the provided home directory", () => {
        expect(arePathsEqual("~/sites/example", "/home/user/sites/example", "/home/user")).toBe(true);
    });

    it("returns false for genuinely different paths", () => {
        expect(arePathsEqual("/var/www/site-a", "/var/www/site-b")).toBe(false);
    });
});
