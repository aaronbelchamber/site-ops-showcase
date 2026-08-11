import React, { useState } from "react";
import api from "../services/api";
import { showToast } from "../services/toast";

export default function AuthOverlay({ isOpen, onAuthenticated }) {
    const [token, setToken] = useState("");
    const [loading, setLoading] = useState(false);

    const handleAuthenticate = async (e) => {
        e.preventDefault();
        if (!token.trim()) {
            showToast("Please enter an API token.", "warning");
            return;
        }

        setLoading(true);
        // Temporarily store the token in the API client to verify it
        api.setToken(token);

        try {
            // Verify token by calling getSites
            await api.getSites();
            showToast("Authenticated successfully!", "success");
            onAuthenticated(token);
        } catch (error) {
            api.clearToken();
            showToast("Invalid API token. Access denied.", "error");
        } finally {
            setLoading(false);
        }
    };

    return (
        <div id="authOverlay" className={`modal-overlay ${isOpen ? "active" : ""}`}>
            <div className="modal-content" style={{ maxWidth: "400px", textAlign: "center" }}>
                <div className="brand" style={{ justifyContent: "center", marginBottom: "1.5rem" }}>
                    <span className="material-symbols-outlined logo-icon" style={{ fontSize: "3rem" }}>
                        admin_panel_settings
                    </span>
                    <h1 style={{ fontSize: "1.5rem" }}>WordPress Manager</h1>
                </div>
                <p style={{ fontSize: "0.875rem", color: "var(--md-sys-color-on-surface-variant)", marginBottom: "1.5rem" }}>
                    Please enter your master API Token to manage your WordPress sites.
                </p>
                <form onSubmit={handleAuthenticate}>
                    <div className="form-group" style={{ textAlign: "left" }}>
                        <label htmlFor="tokenInput">API Token</label>
                        <input
                            type="password"
                            id="tokenInput"
                            className="form-control"
                            placeholder="Enter API Token"
                            value={token}
                            onChange={(e) => setToken(e.target.value)}
                            disabled={loading}
                        />
                    </div>
                    <button
                        type="submit"
                        id="authBtn"
                        className="md-button md-button-primary"
                        style={{ width: "100%", justifyContent: "center", marginTop: "1rem" }}
                        disabled={loading}
                    >
                        {loading ? "Authenticating..." : "Authenticate"}
                    </button>
                </form>
            </div>
        </div>
    );
}
