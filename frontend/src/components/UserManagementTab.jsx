import React, { useState, useEffect } from "react";
import api from "../services/api";
import { showToast } from "../services/toast";
import { useConfirm } from "../hooks/useConfirm";

export default function UserManagementTab({ siteName }) {
    const [users, setUsers] = useState([]);
    const [lastChecked, setLastChecked] = useState(null);
    const [loading, setLoading] = useState(true);
    const { confirm, confirmDialog } = useConfirm();

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

    const handleDeleteClick = async (user) => {
        const otherAdmin = users.find((otherUser) => otherUser.ID !== user.ID
            && (otherUser.roles === "administrator" || (Array.isArray(otherUser.roles) && otherUser.roles.includes("administrator"))));

        const reassignId = await confirm({
            title: `Delete User: ${user.user_login}`,
            message: "Content owned by this user must be reassigned to another user prior to deletion.",
            destructive: true,
            confirmLabel: "Confirm Delete",
            requireExtraValue: true,
            initialExtraValue: otherAdmin ? String(otherAdmin.ID) : "",
            renderExtra: (value, setValue) => (
                <>
                    <label htmlFor="umtReassignSelect">Reassign Content To (User ID):</label>
                    <select
                        id="umtReassignSelect"
                        value={value}
                        onChange={(e) => setValue(e.target.value)}
                        className="umt-modal-select"
                    >
                        <option value="">Select target user</option>
                        {users.filter((u) => u.ID !== user.ID).map((u) => (
                            <option key={u.ID} value={u.ID}>{u.user_login} (ID: {u.ID})</option>
                        ))}
                    </select>
                </>
            ),
        });
        if (!reassignId) return;

        try {
            await api.deleteUser(siteName, user.ID, reassignId);
            showToast("User deleted and content reassigned", "success");
            fetchUsers();
        } catch (err) {
            showToast(`Deletion failed: ${err.message}`, "error");
        }
    };

    if (loading) {
        return <div className="umt-loading">Loading WordPress users...</div>;
    }

    return (
        <div className="umt-root">
            <div className="umt-header">
                <div>
                    <h3 className="umt-m0">WordPress Users</h3>
                    <span className="umt-meta">
                        {lastChecked ? `Last fetched: ${new Date(lastChecked).toLocaleString()}` : "Never checked"}
                    </span>
                </div>
                <button className="md-button md-button-outlined" onClick={fetchUsers}>
                    <span className="material-symbols-outlined">refresh</span> Refresh Users
                </button>
            </div>


            <table className="md-table umt-table">
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Username</th>
                        <th>Display Name</th>
                        <th>Email</th>
                        <th>Role</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
                    {users.map((u) => (
                        <tr key={u.ID}>
                            <td>{u.ID}</td>
                            <td><strong>{u.user_login}</strong></td>
                            <td>{u.display_name}</td>
                            <td>{u.user_email}</td>
                            <td>
                                <select
                                    value={Array.isArray(u.roles) ? u.roles[0] : u.roles || "subscriber"}
                                    onChange={(e) => handleRoleChange(u.ID, e.target.value)}
                                    className="umt-role-select"
                                >
                                    <option value="administrator">administrator</option>
                                    <option value="editor">editor</option>
                                    <option value="author">author</option>
                                    <option value="contributor">contributor</option>
                                    <option value="subscriber">subscriber</option>
                                </select>
                            </td>
                            <td className="umt-actions-cell">
                                <button
                                    className="md-button md-button-outlined umt-btn-xs"
                                    onClick={() => handleDeactivate(u.ID)}
                                    title="Demote to subscriber and randomize password"
                                >
                                    Deactivate
                                </button>
                                <button
                                    className="md-button md-button-error umt-btn-xs"
                                    onClick={() => handleDeleteClick(u)}
                                >
                                    Delete
                                </button>
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>

            {confirmDialog}
        </div>
    );
}
