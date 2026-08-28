import React, { useState } from "react";
import api from "../services/api";
import { showToast } from "../services/toast";
import { useConfirm } from "../hooks/useConfirm";

export default function SecurityScanTab({ site, onScanComplete }) {
    const [scanning, setScanning] = useState(false);
    const [installing, setInstalling] = useState(false);
    const { confirm, confirmDialog } = useConfirm();

    // Rendered from the parent's already-loaded site record; guard so a missing
    // or not-yet-loaded site degrades to an empty state instead of crashing.
    if (!site) {
        return (
            <div className="security-empty-state">
                <span className="material-symbols-outlined security-empty-state-icon">security</span>
                <p>Site configuration is not available yet.</p>
            </div>
        );
    }

    const vulnDetails = site.last_vulnerability_details;

    const handleRunScan = async () => {
        setScanning(true);
        try {
            showToast(`Running security scan for ${site.display_name}...`, "info");
            await api.runVulnerabilityScan(site.site_name);
            showToast(`Security scan complete!`, "success");
            if (onScanComplete) onScanComplete();
        } catch (err) {
            showToast(`Scan failed: ${err.message}`, "error");
        } finally {
            setScanning(false);
        }
    };

    const handleInstallPackage = async () => {
        const ok = await confirm({
            title: "Install vulnerability scanner?",
            message: `The WP-CLI vulnerability scanner package will be installed on ${site.display_name}.`,
            confirmLabel: "Install",
        });
        if (!ok) {
            return;
        }

        setInstalling(true);
        try {
            showToast(`Installing WP-CLI vulnerability extension for ${site.display_name}...`, "info");
            await api.installVulnerabilityPackage(site.site_name);
            showToast(`WP-CLI vulnerability extension installed successfully!`, "success");
            if (onScanComplete) onScanComplete();
        } catch (err) {
            showToast(`Installation failed: ${err.message}`, "error");
        } finally {
            setInstalling(false);
        }
    };

    const getStatusBadge = () => {
        const status = site.vulnerability_status;
        if (status === "green") return <span className="badge badge-success">CLEAN / NO VULNERABILITIES</span>;
        if (status === "red") return <span className="badge badge-error">VULNERABILITIES DETECTED</span>;
        if (status === "yellow") return <span className="badge badge-warning">DIAGNOSTIC NOTICE / AUDIT COMPLETED</span>;
        return <span className="badge badge-neutral">NOT YET SCANNED</span>;
    };

    return (
        <div className="security-scan-root">
            {confirmDialog}
            <div className="md-card security-status-card">
                <div className="security-status-row">
                    <div>
                        <h3 className="security-status-title">Security Scan Status</h3>
                        <p className="security-status-copy">
                            {site.last_vulnerability_scan ? `Last scanned: ${new Date(site.last_vulnerability_scan).toLocaleString()}` : "No scan recorded yet."}
                        </p>
                    </div>
                    <div className="security-status-controls">
                        {getStatusBadge()}
                        <button className="md-button md-button-primary security-action-button" onClick={handleRunScan} disabled={scanning || installing}>
                            <span className="material-symbols-outlined">security</span>
                            {scanning ? "Scanning..." : "Run Security Scan"}
                        </button>
                    </div>
                </div>
            </div>

            {vulnDetails ? (
                <div className="md-card">
                    <h4>Security Audit Details</h4>
                    {vulnDetails.package_installed ? (
                        <div className="security-data-section">
                            <p className="security-data-heading">WP-CLI Vulnerability Extension Scan Results:</p>
                            <pre className="code-block">{JSON.stringify(vulnDetails.data, null, 2)}</pre>
                        </div>
                    ) : (
                        <div className="security-data-section">
                            <div className="security-alert">
                                <div className="security-alert-row">
                                    <div>
                                        <strong>WP-CLI Vulnerability Extension Not Installed</strong>
                                        <p className="security-alert-copy">
                                            {vulnDetails.message || "Run 'wp package install wp-cli/vulnerability-command' on the remote server to enable automated package checks."}
                                        </p>
                                    </div>
                                    <button
                                        className="md-button md-button-primary security-action-button"
                                        onClick={handleInstallPackage}
                                        disabled={installing || scanning}
                                    >
                                        <span className="material-symbols-outlined">download</span>
                                        {installing ? "Installing..." : "Install Extension"}
                                    </button>
                                </div>
                            </div>

                            {vulnDetails.audit_data && (
                                <div className="security-data-section">
                                    <h5>Discovered Component Versions</h5>
                                    <div className="security-data-list">
                                        <div className="security-data-row">
                                            <span>WordPress Core Version</span>
                                            <strong>{vulnDetails.audit_data.core_version}</strong>
                                        </div>
                                        <div className="security-data-row">
                                            <span>Installed Plugins</span>
                                            <strong>{Array.isArray(vulnDetails.audit_data.plugins) ? vulnDetails.audit_data.plugins.length : 0}</strong>
                                        </div>
                                        <div className="security-data-group">
                                            {Array.isArray(vulnDetails.audit_data.plugins) ? vulnDetails.audit_data.plugins.map((p, idx) => (
                                                <div key={idx} className="security-data-item">
                                                    <span><strong>{p.name}</strong> (v{p.version})</span>
                                                    <span>{p.status}</span>
                                                </div>
                                            )) : <span className="security-empty-state">No plugin data available</span>}
                                        </div>
                                        <div className="security-data-row">
                                            <span>Installed Themes</span>
                                            <strong>{Array.isArray(vulnDetails.audit_data.themes) ? vulnDetails.audit_data.themes.length : 0}</strong>
                                        </div>
                                        <div className="security-data-group">
                                            {Array.isArray(vulnDetails.audit_data.themes) ? vulnDetails.audit_data.themes.map((t, idx) => (
                                                <div key={idx} className="security-data-item">
                                                    <span><strong>{t.name}</strong> (v{t.version})</span>
                                                    <span>{t.status}</span>
                                                </div>
                                            )) : <span className="security-empty-state">No theme data available</span>}
                                        </div>
                                    </div>
                                </div>
                            )}
                        </div>
                    )}
                </div>
            ) : (
                <div className="security-empty-state">
                    <span className="material-symbols-outlined security-empty-state-icon">security</span>
                    <p>No vulnerability audit data found. Click "Run Security Scan" to audit this site.</p>
                </div>
            )}
        </div>
    );
}
