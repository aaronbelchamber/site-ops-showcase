import React from "react";
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { SeverityBadge } from "./SeverityBadge";

describe("SeverityBadge", () => {
    it.each([
        ["critical", "hcd-badge--critical"],
        ["warning", "hcd-badge--warning"],
        ["ignored", "hcd-badge--ignored"],
        ["notice", "hcd-badge--ignored"],
    ])("renders %s with modifier class %s", (severity, expectedClass) => {
        render(<SeverityBadge severity={severity} />);
        const badge = screen.getByText(severity);
        expect(badge.className).toContain(expectedClass);
    });
});
