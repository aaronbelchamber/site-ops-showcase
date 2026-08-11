import React from "react";
import api from "../../services/api";

export default function AdminBackupsTab({
    systemBackups,
    loadingSystemBackups,
    creatingSystemBackup,
    restoringSystemBackup,
    uploadingSystemBackup,
    handleCreateSystemBackup,
    handleRestoreSystemBackup,
    handleDeleteSystemBackup,
    handleUploadSystemBackup
}) {
    return (
        <div className="md-card admin-section-card">
            <div className="admin-section-header">
                <div>
                    <h3 className="admin-section-title">System Configuration Backups</h3>
                    <span className="admin-section-copy">
                        Backup/restore your configurations, credential profiles, and encrypted credentials.
                    </span>
                </div>
                <div className="admin-section-actions">
                    <label className="md-button md-button-tonal admin-file-upload-label">
                        <span className="material-symbols-outlined">upload</span>
                        {uploadingSystemBackup ? "Uploading..." : "Upload ZIP to Restore"}
                        <input
                            type="file"
                            accept=".zip"
                            className="sr-only"
                            onChange={handleUploadSystemBackup}
                            disabled={uploadingSystemBackup || restoringSystemBackup}
                        />
                    </label>
                    <button
                        className="md-button md-button-primary"
                        onClick={handleCreateSystemBackup}
                        disabled={creatingSystemBackup}
                    >
                        <span className="material-symbols-outlined">add</span> Create Backup
                    </button>
                </div>
            </div>

            {loadingSystemBackups ? (
                <div className="admin-status-panel">Loading system backups...</div>
            ) : systemBackups.length === 0 ? (
                <div className="admin-empty-state">
                    No backups found. Click "Create Backup" or upload a ZIP config file.
                </div>
            ) : (
                <div className="backup-list">
                    {systemBackups.map((backup) => (
                        <div key={backup.filename} className="backup-item">
                            <div className="backup-item-meta">
                                <strong>{backup.filename}</strong>
                                <span>
                                    Created: {new Date(backup.created_at).toLocaleString()} • Size: {(backup.size_bytes / 1024).toFixed(2)} KB
                                </span>
                            </div>
                            <div className="backup-item-actions">
                                <button
                                    className="md-button md-button-tonal"
                                    onClick={() => handleRestoreSystemBackup(backup.filename)}
                                    disabled={restoringSystemBackup || uploadingSystemBackup}
                                    title="Restore configuration from this backup"
                                >
                                    <span className="material-symbols-outlined">restore</span> Restore
                                </button>
                                <button
                                    className="md-button md-button-outlined"
                                    onClick={() => api.downloadSystemBackup(backup.filename)}
                                    title="Download backup file"
                                >
                                    <span className="material-symbols-outlined">download</span> Download
                                </button>
                                <button
                                    className="md-button md-button-outlined md-button-destructive"
                                    onClick={() => handleDeleteSystemBackup(backup.filename)}
                                    title="Delete backup file"
                                >
                                    <span className="material-symbols-outlined">delete</span>
                                </button>
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}
