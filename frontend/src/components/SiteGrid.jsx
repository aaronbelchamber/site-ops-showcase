import React from "react";
import SiteCard from "./SiteCard";

export default function SiteGrid({ sites, loading, onViewDetails, onAddSiteClick, onRequestCheck, viewMode = "grid" }) {
    if (loading) {
        return (
            <div style={{ display: "grid", gridColumn: "1/-1", textAlign: "center", color: "var(--md-sys-color-outline)", padding: "3rem 0" }}>
                <span className="material-symbols-outlined animate-spin" style={{ fontSize: "2.5rem" }}>
                    sync
                </span>
                <p style={{ marginTop: "0.5rem" }}>Loading monitored sites...</p>
            </div>
        );
    }

    if (sites.length === 0) {
        return (
            <div style={{
                textAlign: "center",
                padding: "4rem 2rem",
                border: "1px dashed var(--md-sys-color-outline)",
                borderRadius: "var(--md-sys-shape-corner-medium)",
                marginTop: "1rem"
            }}>
                <span className="material-symbols-outlined" style={{ fontSize: "3.5rem", color: "var(--md-sys-color-outline)" }}>
                    explore_off
                </span>
                <h3 style={{ marginTop: "1rem", fontWeight: 500 }}>No sites configured yet</h3>
                <p style={{ color: "var(--md-sys-color-on-surface-variant)", fontSize: "0.875rem", marginTop: "0.25rem", marginBottom: "1.5rem" }}>
                    Add a WordPress site using the button in the top right to start monitoring.
                </p>
                <button className="md-button md-button-primary" onClick={onAddSiteClick}>
                    <span className="material-symbols-outlined">add</span> Add Your First Site
                </button>
            </div>
        );
    }

    return (
        <div className={`sites-grid ${viewMode}-view`}>
            {sites.map((site) => (
                <SiteCard
                    key={site.site_name}
                    site={site}
                    viewMode={viewMode}
                    onViewDetails={onViewDetails}
                    onRequestCheck={onRequestCheck}
                />
            ))}
        </div>
    );
}
