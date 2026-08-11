import React, { useState, useEffect } from "react";
import api from "../services/api";
import { showToast } from "../services/toast";

export default function UserManagementTab({ siteName }) {
    const [users, setUsers] = useState([]);
    const [lastChecked, setLastChecked] = useState(null);
    const [loading, setLoading] = useState(true);
    const [deleteModalUser, setDeleteModalUser] = useState(null);
    const [reassignId, setReassignId] = useState("");

    const fetchUsers = async () => {
        setLoading(true);
        try {
            const res = await api.getUsers(siteName);
            if (res && res.users) {
                setUsers(res.users);
                setLastChecked(res.last_users_checked || null);
            } else if (Array.isArray(res)) {
                setUsers(res);
            }
        } catch (err) {
            showToast(`Failed to load users: ${err.message}`, "error");
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        if (siteName) {
            fetchUsers();
        }
    }, [siteName]);

    const handleRoleChange = async (userId, newRole) => {
        try {
            await api.updateUserRole(siteName, userId, newRole);
            showToast("User role updated successfully", "success");
            fetchUsers();
        } catch (err) {
            showToast(`Role update failed: ${err.message}`, "error");
        }
    };

    const handleDeactivate = async (userId) => {
        try {
            await api.deactivateUser(siteName, userId);
            showToast("User deactivated (role set to subscriber and password reset)", "success");
            fetchUsers();
        } catch (err) {
            showToast(`Deactivation failed: ${err.message}`, "error");
        }
    };

    const handleDelete = async () => {
        if (!deleteModalUser || !reassignId) return;
        try {
            await api.deleteUser(siteName, deleteModalUser.ID, reassignId);
            showToast("User deleted and content reassigned", "success");
            setDeleteModalUser(null);
            setReassignId("");
            fetchUsers();
        } catch (err) {
            showToast(`Deletion failed: ${err.message}`, "error");
        }
    };

    if (loading) {
        return <div style={{ padding: "1rem" }}>Loading WordPress users...</div>;
    }

    return (
        <div style={{ marginTop: "1rem" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
                <div>
                    <h3 style={{ margin: 0 }}>WordPress Users</h3>
                    <span style={{ fontSize: "0.85rem", color: "var(--md-sys-color-outline)" }}>
                        {lastChecked ? `Last fetched: ${new Date(lastChecked).toLocaleString()}` : "Never checked"}
                    </span>
                </div>
                <button className="md-button md-button-outlined" onClick={fetchUsers}>
                    <span className="material-symbols-outlined">refresh</span> Refresh Users
                </button>
            </div>

            
            <table className="md-table" style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                    <tr>
                        <th style={{ textAlign: "left", padding: "0.5rem" }}>ID</th>
                        <th style={{ textAlign: "left", padding: "0.5rem" }}>Username</th>
                        <th style={{ textAlign: "left", padding: "0.5rem" }}>Display Name</th>
                        <th style={{ textAlign: "left", padding: "0.5rem" }}>Email</th>
                        <th style={{ textAlign: "left", padding: "0.5rem" }}>Role</th>
                        <th style={{ textAlign: "left", padding: "0.5rem" }}>Actions</th>
                    </tr>
                </thead>
                <tbody>
                    {users.map((u) => (
                        <tr key={u.ID} style={{ borderBottom: "1px solid var(--md-sys-color-outline-variant)" }}>
                            <td style={{ padding: "0.5rem" }}>{u.ID}</td>
                            <td style={{ padding: "0.5rem" }}><strong>{u.user_login}</strong></td>
                            <td style={{ padding: "0.5rem" }}>{u.display_name}</td>
                            <td style={{ padding: "0.5rem" }}>{u.user_email}</td>
                            <td style={{ padding: "0.5rem" }}>
                                <select 
                                    value={Array.isArray(u.roles) ? u.roles[0] : u.roles || "subscriber"}
                                    onChange={(e) => handleRoleChange(u.ID, e.target.value)}
                                    style={{ padding: "0.25rem 0.5rem", borderRadius: "4px" }}
                                >
                                    <option value="administrator">administrator</option>
                                    <option value="editor">editor</option>
                                    <option value="author">author</option>
                                    <option value="contributor">contributor</option>
                                    <option value="subscriber">subscriber</option>
                                </select>
                            </td>
                            <td style={{ padding: "0.5rem", display: "flex", gap: "0.5rem" }}>
                                <button 
                                    className="md-button md-button-outlined" 
                                    style={{ fontSize: "0.75rem", padding: "0.25rem 0.5rem" }}
                                    onClick={() => handleDeactivate(u.ID)}
                                    title="Demote to subscriber and randomize password"
                                >
                                    Deactivate
                                </button>
                                <button 
                                    className="md-button md-button-error" 
                                    style={{ fontSize: "0.75rem", padding: "0.25rem 0.5rem" }}
                                    onClick={() => {
                                        setDeleteModalUser(u);
                                        const other = users.find((otherUser) => otherUser.ID !== u.ID && (otherUser.roles === "administrator" || (Array.isArray(otherUser.roles) && otherUser.roles.includes("administrator"))));
                                        if (other) setReassignId(other.ID);
                                    }}
                                >
                                    Delete
                                </button>
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>

            {deleteModalUser && (
                <div style={{ position: "fixed", inset: 0, backgroundColor: "rgba(0,0,0,0.5)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000 }}>
                    <div style={{ backgroundColor: "var(--md-sys-color-surface)", padding: "1.5rem", borderRadius: "8px", maxWidth: "400px", width: "100%" }}>
                        <h4>Delete User: {deleteModalUser.user_login}</h4>
                        <p style={{ fontSize: "0.875rem", margin: "0.5rem 0" }}>
                            Content owned by this user must be reassigned to another user prior to deletion.
                        </p>
                        <label style={{ display: "block", fontSize: "0.875rem", marginBottom: "0.5rem" }}>Reassign Content To (User ID):</label>
                        <select 
                            value={reassignId} 
                            onChange={(e) => setReassignId(e.target.value)}
                            style={{ width: "100%", padding: "0.5rem", marginBottom: "1rem" }}
                        >
                            <option value="">Select target user</option>
                            {users.filter(u => u.ID !== deleteModalUser.ID).map(u => (
                                <option key={u.ID} value={u.ID}>{u.user_login} (ID: {u.ID})</option>
                            ))}
                        </select>
                        <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.5rem" }}>
                            <button className="md-button md-button-outlined" onClick={() => setDeleteModalUser(null)}>Cancel</button>
                            <button className="md-button md-button-error" disabled={!reassignId} onClick={handleDelete}>Confirm Delete</button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
