import React from "react";

export default function AdminProfilesTab({
    profiles,
    loadingProfiles,
    editingProfile,
    profileTitle,
    setProfileTitle,
    profileHost,
    setProfileHost,
    profilePort,
    setProfilePort,
    profileUser,
    setProfileUser,
    profilePassword,
    setProfilePassword,
    profilePrivateKey,
    setProfilePrivateKey,
    sshAgentActive,
    discoveredKeys,
    selectedDiscoveredKey,
    setSelectedDiscoveredKey,
    sshConfigProfiles,
    selectedSshProfile,
    loadingKeys,
    savingProfile,
    handleSaveProfile,
    handleEditProfile,
    handleDeleteProfile,
    clearProfileForm,
    handleStartSSHAgent,
    handleUseDiscoveredKeyPath,
    handleApplySshProfile,
    setEditingProfile
}) {
    return (
        <div className="md-card admin-section-card admin-profiles-grid">
            <div className="admin-panel-column admin-panel-divider">
                <h4 className="admin-panel-heading">Existing Profiles</h4>
                {loadingProfiles ? (
                    <div className="admin-status-panel">Loading profiles...</div>
                ) : profiles.length === 0 ? (
                    <div className="admin-status-panel admin-status-copy">No profiles created yet. Use the form to add one.</div>
                ) : (
                    <div className="profile-list">
                        {profiles.map((p) => (
                            <div
                                key={p.id}
                                className={`profile-card ${editingProfile?.id === p.id ? "profile-card--active" : ""}`}
                            >
                                <div className="profile-card-meta">
                                    <strong className="profile-card-title">{p.title}</strong>
                                    <span className="profile-card-copy">
                                        {p.ssh_user}@{p.ssh_host}:{p.ssh_port}
                                    </span>
                                </div>
                                <div className="profile-card-actions">
                                    <button
                                        className="md-button md-button-tonal md-button-icon profile-icon-button"
                                        onClick={() => handleEditProfile(p)}
                                        title="Edit Profile"
                                        type="button"
                                    >
                                        <span className="material-symbols-outlined">edit</span>
                                    </button>
                                    <button
                                        className="md-button md-button-outlined md-button-icon profile-icon-button profile-icon-button--danger"
                                        onClick={() => handleDeleteProfile(p.id)}
                                        title="Delete Profile"
                                        type="button"
                                    >
                                        <span className="material-symbols-outlined">delete</span>
                                    </button>
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </div>

            <div className="admin-panel-column">
                <h4 className="admin-panel-heading">{editingProfile ? "Edit Profile" : "Create New Credential Profile"}</h4>
                <form onSubmit={handleSaveProfile} className="admin-form">
                    <div className="form-group">
                        <label>Profile Title *</label>
                        <input
                            type="text"
                            className="form-control"
                            placeholder="e.g. Production Server, Staging Profile"
                            value={profileTitle}
                            onChange={(e) => setProfileTitle(e.target.value)}
                            required
                        />
                    </div>

                    <div className="admin-grid-2-columns">
                        <div className="form-group">
                            <label>SSH Host / IP</label>
                            <input
                                type="text"
                                className="form-control"
                                placeholder="e.g. 192.168.1.50 or example.com"
                                value={profileHost}
                                onChange={(e) => setProfileHost(e.target.value)}
                                required
                            />
                        </div>
                        <div className="form-group">
                            <label>SSH Port</label>
                            <input
                                type="number"
                                className="form-control"
                                value={profilePort}
                                onChange={(e) => setProfilePort(e.target.value)}
                                required
                            />
                        </div>
                    </div>

                    <div className="form-group">
                        <label>SSH Username</label>
                        <input
                            type="text"
                            className="form-control"
                            placeholder="e.g. root, ubuntu"
                            value={profileUser}
                            onChange={(e) => setProfileUser(e.target.value)}
                            required
                        />
                    </div>

                    <div className="form-group">
                        <label>SSH Password</label>
                        <input
                            type="password"
                            className="form-control"
                            placeholder={editingProfile?.has_password ? "●●●●●●●● (Unchanged)" : "Password (optional)"}
                            value={profilePassword}
                            onChange={(e) => setProfilePassword(e.target.value)}
                        />
                    </div>

                    <div className="form-group">
                        <label>SSH Private Key</label>
                        <textarea
                            className="form-control form-control-monospace"
                            placeholder={editingProfile?.has_private_key ? "📄 [Stored Private Key] (Unchanged)" : "-----BEGIN RSA PRIVATE KEY-----"}
                            value={profilePrivateKey}
                            onChange={(e) => setProfilePrivateKey(e.target.value)}
                        />
                    </div>

                    <div className="admin-help-panel">
                        <div className="admin-help-status">
                            <span className={`admin-help-indicator ${sshAgentActive ? "admin-help-indicator--active" : ""}`} />
                            <span>
                                {sshAgentActive
                                    ? "Active SSH Agent detected (agent keys will be chained)"
                                    : "No SSH Agent detected"}
                            </span>
                        </div>

                        {!sshAgentActive && (
                            <div className="admin-help-block">
                                <div className="admin-help-block-header">
                                    <strong>How to enable the agent:</strong>
                                    <button
                                        type="button"
                                        className="md-button md-button-tonal admin-help-button"
                                        onClick={handleStartSSHAgent}
                                        disabled={loadingKeys}
                                    >
                                        {loadingKeys ? "Starting..." : "Start Agent Automatically"}
                                    </button>
                                </div>
                                <ul className="admin-help-list">
                                    <li><strong>Windows:</strong> Run <code>Start-Service ssh-agent</code> in Administrator PowerShell, then add your key with <code>ssh-add</code>.</li>
                                    <li><strong>macOS / Linux:</strong> Run <code>eval $(ssh-agent -s)</code> and add your key with <code>ssh-add</code>.</li>
                                </ul>
                            </div>
                        )}

                        {discoveredKeys.length > 0 && (
                            <div className="admin-help-section">
                                <label htmlFor="discovered_key_select">Select local key from ~/.ssh:</label>
                                <div className="admin-help-row">
                                    <select
                                        id="discovered_key_select"
                                        className="form-control"
                                        value={selectedDiscoveredKey}
                                        onChange={(e) => setSelectedDiscoveredKey(e.target.value)}
                                    >
                                        <option value="">-- Choose Key --</option>
                                        {discoveredKeys.map((k) => (
                                            <option key={k.name} value={k.name}>{k.name} ({k.type})</option>
                                        ))}
                                    </select>
                                    <button
                                        type="button"
                                        className="md-button md-button-tonal admin-help-button"
                                        disabled={!selectedDiscoveredKey}
                                        onClick={handleUseDiscoveredKeyPath}
                                    >
                                        Use Path
                                    </button>
                                </div>
                            </div>
                        )}

                        {sshConfigProfiles.length > 0 && (
                            <div className="admin-help-section admin-help-top-border">
                                <label htmlFor="ssh_profile_select">Auto-fill from SSH Config profile (~/.ssh/config):</label>
                                <select
                                    id="ssh_profile_select"
                                    className="form-control"
                                    value={selectedSshProfile}
                                    onChange={(e) => handleApplySshProfile(e.target.value)}
                                >
                                    <option value="">-- Select Profile --</option>
                                    {sshConfigProfiles.map((p) => (
                                        <option key={p.host_alias} value={p.host_alias}>
                                            {p.host_alias} ({p.user || "no user"}@{p.hostname})
                                        </option>
                                    ))}
                                </select>
                            </div>
                        )}
                    </div>

                    <div className="admin-form-actions">
                        {editingProfile && (
                            <button
                                type="button"
                                className="md-button md-button-tonal"
                                onClick={() => {
                                    setEditingProfile(null);
                                    clearProfileForm();
                                }}
                            >
                                Cancel Edit
                            </button>
                        )}
                        <button type="submit" className="md-button md-button-primary" disabled={savingProfile}>
                            {savingProfile ? "Saving..." : "Save Profile"}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
}
