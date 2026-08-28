import React from "react";
import { describe, it, expect } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

import { useConfirm } from "./useConfirm";

function Harness({ onResolve, options }) {
    const { confirm, confirmDialog } = useConfirm();
    return (
        <div>
            <button onClick={async () => onResolve(await confirm(options))}>open</button>
            {confirmDialog}
        </div>
    );
}

describe("useConfirm", () => {
    it("resolves true on confirm and false on cancel for a plain (no renderExtra) dialog", async () => {
        let result;
        render(<Harness options={{ message: "Delete this?" }} onResolve={(r) => { result = r; }} />);

        fireEvent.click(screen.getByText("open"));
        expect(await screen.findByText("Delete this?")).toBeInTheDocument();
        fireEvent.click(screen.getByRole("button", { name: /confirm/i }));

        await waitFor(() => expect(result).toBe(true));
    });

    it("resolves false when a plain dialog is cancelled", async () => {
        let result;
        render(<Harness options={{ message: "Delete this?" }} onResolve={(r) => { result = r; }} />);

        fireEvent.click(screen.getByText("open"));
        await screen.findByText("Delete this?");
        fireEvent.click(screen.getByRole("button", { name: /cancel/i }));

        await waitFor(() => expect(result).toBe(false));
    });

    it("resolves to the renderExtra value on confirm, not a plain boolean", async () => {
        let result;
        const options = {
            title: "Reassign",
            requireExtraValue: true,
            initialExtraValue: "7",
            renderExtra: (value, setValue) => (
                <select data-testid="extra-select" value={value} onChange={(e) => setValue(e.target.value)}>
                    <option value="7">User 7</option>
                    <option value="9">User 9</option>
                </select>
            ),
        };
        render(<Harness options={options} onResolve={(r) => { result = r; }} />);

        fireEvent.click(screen.getByText("open"));
        await screen.findByText("Reassign");
        fireEvent.change(screen.getByTestId("extra-select"), { target: { value: "9" } });
        fireEvent.click(screen.getByRole("button", { name: /confirm/i }));

        await waitFor(() => expect(result).toBe("9"));
    });

    it("resolves false when a renderExtra dialog is cancelled", async () => {
        let result;
        const options = {
            title: "Reassign",
            requireExtraValue: true,
            initialExtraValue: "7",
            renderExtra: (value, setValue) => (
                <select data-testid="extra-select" value={value} onChange={(e) => setValue(e.target.value)} />
            ),
        };
        render(<Harness options={options} onResolve={(r) => { result = r; }} />);

        fireEvent.click(screen.getByText("open"));
        await screen.findByText("Reassign");
        fireEvent.click(screen.getByRole("button", { name: /cancel/i }));

        await waitFor(() => expect(result).toBe(false));
    });

    it("disables confirm until requireExtraValue is satisfied", async () => {
        const options = {
            title: "Reassign",
            requireExtraValue: true,
            initialExtraValue: "",
            renderExtra: (value, setValue) => (
                <select data-testid="extra-select" value={value} onChange={(e) => setValue(e.target.value)}>
                    <option value="">Choose one</option>
                    <option value="9">User 9</option>
                </select>
            ),
        };
        render(<Harness options={options} onResolve={() => {}} />);

        fireEvent.click(screen.getByText("open"));
        await screen.findByText("Reassign");
        expect(screen.getByRole("button", { name: /confirm/i })).toBeDisabled();

        fireEvent.change(screen.getByTestId("extra-select"), { target: { value: "9" } });
        expect(screen.getByRole("button", { name: /confirm/i })).not.toBeDisabled();
    });
});
