import { describe, it, expect } from "vitest";
import { statusModifier } from "./statusModifier";

describe("statusModifier", () => {
    it.each([
        ["critical", "critical"],
        ["degraded", "degraded"],
        ["notice", "notice"],
        ["healthy", "healthy"],
        ["unknown", "healthy"],
        [undefined, "healthy"],
    ])("maps %s to %s", (input, expected) => {
        expect(statusModifier(input)).toBe(expected);
    });
});
