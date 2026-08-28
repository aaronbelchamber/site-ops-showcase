import React, { useCallback, useRef, useState } from "react";

/**
 * Promise-based replacement for window.confirm().
 *
 * Native confirm() was used for every destructive action (delete a site, purge
 * health data, restore a backup over the live config). It cannot be styled or
 * branded, renders inconsistently across platforms, and some browsers suppress
 * it entirely -- which would silently skip the guard on an irreversible action.
 *
 * Usage keeps the same shape as the call it replaces:
 *
 *     const { confirm, confirmDialog } = useConfirm();
 *     if (!(await confirm({ message: "Delete this?", destructive: true }))) return;
 *     ...
 *     return (<>{confirmDialog}<Rest /></>);
 *
 * A confirmation that needs to collect one extra value first (e.g. "which
 * user should this content reassign to?") can pass `renderExtra`: the dialog
 * then resolves to that value (or `false` if cancelled) instead of a plain
 * boolean, and the confirm button stays disabled until `requireExtraValue`
 * is satisfied.
 *
 *     const reassignId = await confirm({
 *         title: "Delete User: jdoe", destructive: true, requireExtraValue: true,
 *         renderExtra: (value, setValue) => <select value={value} onChange={...}>...</select>,
 *     });
 *     if (!reassignId) return;
 */
export function useConfirm() {
    const [state, setState] = useState(null);
    const resolverRef = useRef(null);

    const confirm = useCallback((options) => {
        const opts = typeof options === "string" ? { message: options } : (options || {});
        return new Promise((resolve) => {
            resolverRef.current = resolve;
            setState({
                title: opts.title || "Are you sure?",
                message: opts.message || "",
                details: opts.details || null,
                confirmLabel: opts.confirmLabel || (opts.destructive ? "Delete" : "Confirm"),
                cancelLabel: opts.cancelLabel || "Cancel",
                destructive: Boolean(opts.destructive),
                // For the most dangerous actions, require the exact name typed.
                requireTyped: opts.requireTyped || null,
                // For confirmations that need one extra piece of input (e.g. a
                // reassign-to user) rather than a plain yes/no.
                renderExtra: opts.renderExtra || null,
                initialExtraValue: opts.initialExtraValue ?? "",
                requireExtraValue: Boolean(opts.requireExtraValue),
            });
        });
    }, []);

    const settle = useCallback((result) => {
        setState(null);
        const resolve = resolverRef.current;
        resolverRef.current = null;
        if (resolve) resolve(result);
    }, []);

    const confirmDialog = state ? (
        <ConfirmDialog
            {...state}
            onConfirm={(extraValue) => settle(state.renderExtra ? extraValue : true)}
            onCancel={() => settle(false)}
        />
    ) : null;

    return { confirm, confirmDialog };
}

function ConfirmDialog({
    title, message, details, confirmLabel, cancelLabel, destructive, requireTyped,
    renderExtra, initialExtraValue, requireExtraValue, onConfirm, onCancel,
}) {
    const [typed, setTyped] = useState("");
    const [extraValue, setExtraValue] = useState(initialExtraValue);
    const canConfirm = (!requireTyped || typed.trim() === requireTyped)
        && (!requireExtraValue || Boolean(extraValue));

    React.useEffect(() => {
        const onKeyDown = (e) => {
            if (e.key === "Escape") onCancel();
            if (e.key === "Enter" && canConfirm && !requireTyped && !renderExtra) onConfirm(extraValue);
        };
        window.addEventListener("keydown", onKeyDown);
        return () => window.removeEventListener("keydown", onKeyDown);
    }, [onCancel, onConfirm, canConfirm, requireTyped, renderExtra, extraValue]);

    return (
        <div className="confirm-overlay" onClick={onCancel}>
            <div
                className={`confirm-dialog ${destructive ? "confirm-dialog--destructive" : ""}`}
                role="alertdialog"
                aria-modal="true"
                aria-labelledby="confirmDialogTitle"
                onClick={(e) => e.stopPropagation()}
            >
                <div className="confirm-dialog-header">
                    <span className="material-symbols-outlined confirm-dialog-icon" aria-hidden="true">
                        {destructive ? "warning" : "help"}
                    </span>
                    <h3 id="confirmDialogTitle" className="confirm-dialog-title">{title}</h3>
                </div>

                {message && <p className="confirm-dialog-message">{message}</p>}
                {details && <pre className="confirm-dialog-details">{details}</pre>}

                {requireTyped && (
                    <div className="confirm-dialog-typed">
                        <label htmlFor="confirmTypedInput">
                            Type <code>{requireTyped}</code> to confirm:
                        </label>
                        <input
                            id="confirmTypedInput"
                            className="form-control"
                            value={typed}
                            onChange={(e) => setTyped(e.target.value)}
                            autoComplete="off"
                            autoFocus
                        />
                    </div>
                )}

                {renderExtra && (
                    <div className="confirm-dialog-extra">
                        {renderExtra(extraValue, setExtraValue)}
                    </div>
                )}

                <div className="confirm-dialog-actions">
                    <button type="button" className="md-button md-button-tonal" onClick={onCancel}>
                        {cancelLabel}
                    </button>
                    <button
                        type="button"
                        className={`md-button ${destructive ? "md-button-error" : "md-button-primary"}`}
                        onClick={() => onConfirm(extraValue)}
                        disabled={!canConfirm}
                        autoFocus={!requireTyped && !renderExtra}
                    >
                        {confirmLabel}
                    </button>
                </div>
            </div>
        </div>
    );
}
