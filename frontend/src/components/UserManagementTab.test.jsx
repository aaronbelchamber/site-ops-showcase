import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within, fireEvent } from "@testing-library/react";

import UserManagementTab from "./UserManagementTab";
import api from "../services/api";
import { showToast } from "../services/toast";

vi.mock("../services/api", () => ({
    default: {
        getUsers: vi.fn(),
        updateUserRole: vi.fn(),
        deactivateUser: vi.fn(),
        deleteUser: vi.fn(),
    },
}));

vi.mock("../services/toast", () => ({
    showToast: vi.fn(),
}));

const SAMPLE_USERS = [
    { ID: 1, user_login: "admin", display_name: "Admin", user_email: "admin@example.com", roles: ["administrator"] },
    { ID: 2, user_login: "jdoe", display_name: "Jane Doe", user_email: "jdoe@example.com", roles: ["subscriber"] },
];

describe("UserManagementTab", () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    it("shows a loading state before users resolve", () => {
        api.getUsers.mockReturnValue(new Promise(() => {}));
        render(<UserManagementTab siteName="my-site" />);
        expect(screen.getByText(/Loading WordPress users/i)).toBeInTheDocument();
    });

    it("loads and renders users in the table on mount", async () => {
        api.getUsers.mockResolvedValue({ users: SAMPLE_USERS, last_users_checked: "2026-08-25T00:00:00Z" });

        render(<UserManagementTab siteName="my-site" />);

        await waitFor(() => expect(api.getUsers).toHaveBeenCalledWith("my-site"));
        expect(await screen.findByText("admin")).toBeInTheDocument();
        expect(screen.getByText("jdoe")).toBeInTheDocument();
        expect(screen.getByText("jdoe@example.com")).toBeInTheDocument();
    });

    it("shows an error toast when loading users fails", async () => {
        api.getUsers.mockRejectedValue(new Error("network down"));

        render(<UserManagementTab siteName="my-site" />);

        await waitFor(() =>
            expect(showToast).toHaveBeenCalledWith(expect.stringContaining("network down"), "error")
        );
    });

    it("updates a user's role when the dropdown changes", async () => {
        api.getUsers.mockResolvedValue({ users: SAMPLE_USERS });
        api.updateUserRole.mockResolvedValue({ success: true });

        render(<UserManagementTab siteName="my-site" />);
        await screen.findByText("admin");

        const row = screen.getByText("jdoe").closest("tr");
        const select = within(row).getByRole("combobox");
        fireEvent.change(select, { target: { value: "editor" } });

        await waitFor(() => expect(api.updateUserRole).toHaveBeenCalledWith("my-site", 2, "editor"));
        expect(showToast).toHaveBeenCalledWith(expect.stringContaining("updated"), "success");
    });

    it("deactivates a user when Deactivate is clicked", async () => {
        api.getUsers.mockResolvedValue({ users: SAMPLE_USERS });
        api.deactivateUser.mockResolvedValue({ success: true });

        render(<UserManagementTab siteName="my-site" />);
        await screen.findByText("admin");

        const row = screen.getByText("jdoe").closest("tr");
        fireEvent.click(within(row).getByRole("button", { name: /deactivate/i }));

        await waitFor(() => expect(api.deactivateUser).toHaveBeenCalledWith("my-site", 2));
        expect(showToast).toHaveBeenCalledWith(expect.stringContaining("deactivated"), "success");
    });

    it("opens a confirmation modal and deletes a user with reassignment", async () => {
        api.getUsers.mockResolvedValue({ users: SAMPLE_USERS });
        api.deleteUser.mockResolvedValue({ success: true });

        render(<UserManagementTab siteName="my-site" />);
        await screen.findByText("admin");

        const row = screen.getByText("jdoe").closest("tr");
        fireEvent.click(within(row).getByRole("button", { name: /delete/i }));

        expect(await screen.findByText(/Delete User: jdoe/i)).toBeInTheDocument();

        fireEvent.click(screen.getByRole("button", { name: /confirm delete/i }));

        await waitFor(() => expect(api.deleteUser).toHaveBeenCalledWith("my-site", 2, "1"));
        expect(showToast).toHaveBeenCalledWith(expect.stringContaining("deleted"), "success");
    });

    it("cancels the delete modal without calling the API", async () => {
        api.getUsers.mockResolvedValue({ users: SAMPLE_USERS });

        render(<UserManagementTab siteName="my-site" />);
        await screen.findByText("admin");

        const row = screen.getByText("jdoe").closest("tr");
        fireEvent.click(within(row).getByRole("button", { name: /delete/i }));
        expect(await screen.findByText(/Delete User: jdoe/i)).toBeInTheDocument();

        fireEvent.click(screen.getByRole("button", { name: /cancel/i }));

        expect(screen.queryByText(/Delete User: jdoe/i)).not.toBeInTheDocument();
        expect(api.deleteUser).not.toHaveBeenCalled();
    });

    it("shows an error toast when deleting a user fails", async () => {
        api.getUsers.mockResolvedValue({ users: SAMPLE_USERS });
        api.deleteUser.mockRejectedValue(new Error("cannot delete"));

        render(<UserManagementTab siteName="my-site" />);
        await screen.findByText("admin");

        const row = screen.getByText("jdoe").closest("tr");
        fireEvent.click(within(row).getByRole("button", { name: /delete/i }));
        fireEvent.click(screen.getByRole("button", { name: /confirm delete/i }));

        await waitFor(() =>
            expect(showToast).toHaveBeenCalledWith(expect.stringContaining("cannot delete"), "error")
        );
    });
});
