import React from "react";
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { AssetIssuesSection } from "./AssetIssuesSection";

describe("AssetIssuesSection", () => {
    it("shows the success state when there are no issues", () => {
        render(<AssetIssuesSection brokenImages={[]} failedAssetRequests={[]} />);
        expect(screen.getByText(/No broken images or failed asset requests found/)).toBeInTheDocument();
    });

    it("lists broken images", () => {
        render(<AssetIssuesSection
            brokenImages={[{ src: "https://example.com/logo.png", alt: "Logo" }]}
            failedAssetRequests={[]}
        />);
        expect(screen.getByText(/1 broken image \(loaded but rendered empty\)/)).toBeInTheDocument();
        expect(screen.getByText(/https:\/\/example\.com\/logo\.png \(alt: "Logo"\)/)).toBeInTheDocument();
    });

    it("lists failed asset requests", () => {
        render(<AssetIssuesSection
            brokenImages={[]}
            failedAssetRequests={[{ status: 404, resource_type: "script", url: "https://example.com/app.js" }]}
        />);
        expect(screen.getByText(/1 failed asset request/)).toBeInTheDocument();
        expect(screen.getByText(/\[404\] script: https:\/\/example\.com\/app\.js/)).toBeInTheDocument();
    });

    it("pluralizes counts correctly for multiple issues", () => {
        render(<AssetIssuesSection
            brokenImages={[{ src: "a.png" }, { src: "b.png" }]}
            failedAssetRequests={[]}
        />);
        expect(screen.getByText(/2 broken images/)).toBeInTheDocument();
    });
});
