import React from "react";

export default function AdminMaintenanceTab({ sites, handlePurgeHealthData }) {
    return (
        <div className="md-card admin-section-card">
            <div>
                <h3 className="admin-section-title">Disk Data & Screenshot Purging</h3>
                <span className="admin-section-copy">
                    Purge health checks history (JSONL files) and Playwright screenshots to reclaim server disk space.
                </span>
            </div>

            {sites.length === 0 ? (
                <div className="admin-status-panel">
                    No sites configured yet.
                </div>
            ) : (
                <div className="admin-list">
                    {sites.map((site) => (
                        <div key={site.site_name} className="admin-item">
                            <div className="admin-item-meta">
                                <strong>{site.display_name}</strong>
                                <span>
                                    Slug: {site.site_name} • Health Check URL: {site.health_check_url || "Not configured"}
                                </span>
                            </div>
                            <button
                                className="md-button md-button-outlined md-button-destructive"
                                onClick={() => handlePurgeHealthData(site.site_name, site.display_name)}
                            >
                                <span className="material-symbols-outlined">delete_sweep</span> Purge Health History
                            </button>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}
