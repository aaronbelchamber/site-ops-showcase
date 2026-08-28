import React from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, act } from "@testing-library/react";
import { useObjectUrl } from "./useObjectUrl";

function Harness({ onReady }) {
    const [url, setUrl] = useObjectUrl();
    onReady({ url, setUrl });
    return <div>{url || "empty"}</div>;
}

describe("useObjectUrl", () => {
    beforeEach(() => {
        vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
    });

    afterEach(() => {
        vi.restoreAllMocks();
    });

    it("starts with a null url", () => {
        let ref;
        render(<Harness onReady={(r) => { ref = r; }} />);
        expect(ref.url).toBeNull();
    });

    it("does not revoke on the first assignment", () => {
        let ref;
        const { rerender } = render(<Harness onReady={(r) => { ref = r; }} />);
        act(() => ref.setUrl("blob:one"));
        rerender(<Harness onReady={(r) => { ref = r; }} />);
        expect(URL.revokeObjectURL).not.toHaveBeenCalled();
    });

    it("revokes the previous url when replaced with a different one", () => {
        let ref;
        const { rerender } = render(<Harness onReady={(r) => { ref = r; }} />);
        act(() => ref.setUrl("blob:one"));
        rerender(<Harness onReady={(r) => { ref = r; }} />);

        act(() => ref.setUrl("blob:two"));
        rerender(<Harness onReady={(r) => { ref = r; }} />);

        expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:one");
        expect(URL.revokeObjectURL).not.toHaveBeenCalledWith("blob:two");
    });

    it("does not revoke when reassigned the same url", () => {
        let ref;
        const { rerender } = render(<Harness onReady={(r) => { ref = r; }} />);
        act(() => ref.setUrl("blob:one"));
        rerender(<Harness onReady={(r) => { ref = r; }} />);

        act(() => ref.setUrl("blob:one"));
        rerender(<Harness onReady={(r) => { ref = r; }} />);

        expect(URL.revokeObjectURL).not.toHaveBeenCalled();
    });

    it("revokes the current url on unmount", () => {
        let ref;
        const { rerender, unmount } = render(<Harness onReady={(r) => { ref = r; }} />);
        act(() => ref.setUrl("blob:one"));
        rerender(<Harness onReady={(r) => { ref = r; }} />);

        unmount();

        expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:one");
    });
});
