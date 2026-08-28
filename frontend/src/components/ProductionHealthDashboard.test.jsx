import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";

import ProductionHealthDashboard from "./ProductionHealthDashboard";
import { SitesProvider, useSitesContext } from "../context/SitesContext";
import api from "../services/api";

vi.mock("../services/api", () => ({
    default: {
        getSites: vi.fn(),
        getTaskStatus: vi.fn(),
        triggerHealthCheckAsync: vi.fn(),
        getScreenshotBlob: vi.fn(),
    },
}));

vi.mock("../services/toast", () => ({
    showToast: vi.fn(),
}));

const SITE_A = { site_name: "site-a", display_name: "Site A" };
const SITE_B = { site_name: "site-b", display_name: "Site B" };

// Seeds SitesContext before the component under test mounts, the way
// App.jsx does right after authentication -- well before the user can
// navigate to this view.
function Seed({ sites }) {
    const ctx = useSitesContext();
    React.useEffect(() => {
        ctx.setSites(sites);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);
    return null;
}

function renderWithContext({ seedSites } = {}) {
    // Two render passes on the *same* <SitesProvider> instance (React
    // reconciles it as an update, not a remount, so its state persists):
    // first seed the context and let the effect flush, then swap in the
    // component under test so its mount effect sees the already-populated
    // context -- matching real timing, where SitesContext is populated long
    // before this view ever mounts.
    const utils = render(
        <SitesProvider>
            {seedSites ? <Seed sites={seedSites} /> : null}
        </SitesProvider>
    );
    utils.rerender(
        <SitesProvider>
            <ProductionHealthDashboard />
        </SitesProvider>
    );
    return utils;
}

describe("ProductionHealthDashboard", () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    it("does not re-fetch sites when SitesContext is already populated", async () => {
        renderWithContext({ seedSites: [SITE_A, SITE_B] });

        expect(await screen.findByText("Site A")).toBeInTheDocument();
        expect(screen.getByText("Site B")).toBeInTheDocument();
        expect(api.getSites).not.toHaveBeenCalled();
    });

    it("fetches sites and populates SitesContext when the context starts empty", async () => {
        api.getSites.mockResolvedValue([SITE_A]);

        renderWithContext();

        await waitFor(() => expect(api.getSites).toHaveBeenCalledTimes(1));
        expect(await screen.findByText("Site A")).toBeInTheDocument();
    });

    it("shows a loading state while the initial fetch is in flight", () => {
        api.getSites.mockReturnValue(new Promise(() => {}));

        renderWithContext();

        expect(screen.getByText(/Loading sites/i)).toBeInTheDocument();
    });

    it("shows an error toast when the initial fetch fails", async () => {
        const { showToast } = await import("../services/toast");
        api.getSites.mockRejectedValue(new Error("network down"));

        renderWithContext();

        await waitFor(() =>
            expect(showToast).toHaveBeenCalledWith(expect.stringContaining("network down"), "error")
        );
    });

    it("refetches and updates the shared context when Refresh is clicked", async () => {
        api.getSites.mockResolvedValue([SITE_A, SITE_B]);

        renderWithContext({ seedSites: [SITE_A] });
        expect(await screen.findByText("Site A")).toBeInTheDocument();
        expect(api.getSites).not.toHaveBeenCalled();

        // "Check Site" row buttons also contain a "refresh" icon glyph in
        // their accessible name; the header's Refresh button is the first.
        fireEvent.click(screen.getAllByRole("button", { name: /refresh/i })[0]);

        await waitFor(() => expect(api.getSites).toHaveBeenCalledTimes(1));
        expect(await screen.findByText("Site B")).toBeInTheDocument();
    });
});
