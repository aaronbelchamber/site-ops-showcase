import React from "react";
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { SuppressionLabel } from "./SuppressionLabel";

describe("SuppressionLabel", () => {
    it("renders nothing when the error is not suppressed", () => {
        const { container } = render(<SuppressionLabel error={{}} />);
        expect(container).toBeEmptyDOMElement();
    });

    it("renders the auto-suppressed label for global suppression", () => {
        render(<SuppressionLabel error={{ suppression_source: "global", suppression_reason: "known false positive" }} />);
        expect(screen.getByText(/Auto-suppressed: known false positive/)).toBeInTheDocument();
    });

    it("renders the accepted label with a date for acknowledged suppression", () => {
        render(<SuppressionLabel error={{
            suppression_source: "acknowledged",
            suppression_reason: "third-party plugin",
            acknowledged_at: "2026-01-15T00:00:00Z",
        }} />);
        expect(screen.getByText(/Accepted on/)).toBeInTheDocument();
        expect(screen.getByText(/third-party plugin/)).toBeInTheDocument();
    });

    it("renders the accepted label without a date when acknowledged_at is missing", () => {
        render(<SuppressionLabel error={{ suppression_source: "acknowledged", suppression_reason: "manual review" }} />);
        const label = screen.getByText(/Accepted: manual review/);
        expect(label).toBeInTheDocument();
    });
});
