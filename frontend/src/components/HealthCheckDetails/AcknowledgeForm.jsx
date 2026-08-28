import React, { useState } from "react";

export function AcknowledgeForm({ onSubmit, onCancel, isBusy }) {
    const [reason, setReason] = useState("");
    return (
        <div className="hcd-ack-form">
            <label className="hcd-ack-form__label">
                Optional reason (visible in future reports):
            </label>
            <input
                type="text"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="e.g. Third-party plugin limitation — accepted risk"
                className="hcd-ack-form__input"
            />
            <div className="hcd-row hcd-gap-sm">
                <button
                    className="md-button md-button-primary hcd-btn-sm"
                    onClick={() => onSubmit(reason)}
                    disabled={isBusy}
                >
                    {isBusy ? "Saving…" : "Confirm Accept"}
                </button>
                <button
                    className="md-button hcd-btn-sm"
                    onClick={onCancel}
                    disabled={isBusy}
                >
                    Cancel
                </button>
            </div>
        </div>
    );
}
