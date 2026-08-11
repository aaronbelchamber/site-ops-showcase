import React, { useState, useEffect } from "react";

export default function ToastContainer() {
    const [toasts, setToasts] = useState([]);

    useEffect(() => {
        const handleToast = (e) => {
            const { id, message, type, isProcess } = e.detail;
            
            // Lower-right toasts are restricted ONLY to process starting or ending indicators
            if (!isProcess && type !== "process") {
                return;
            }

            setToasts((prev) => [...prev, { id, message, type }]);

            // Automatically remove toast after 4 seconds
            setTimeout(() => {
                setToasts((prev) => prev.filter((t) => t.id !== id));
            }, 4000);
        };

        window.addEventListener("app-toast", handleToast);
        return () => window.removeEventListener("app-toast", handleToast);
    }, []);

    const getToastStyle = (type) => {
        switch (type) {
            case "success":
                return { borderLeft: "4px solid var(--md-sys-color-success)" };
            case "error":
                return { borderLeft: "4px solid var(--md-sys-color-error)" };
            case "warning":
                return { borderLeft: "4px solid var(--md-sys-color-warning)" };
            default:
                return {};
        }
    };

    const getToastIcon = (type) => {
        switch (type) {
            case "success":
                return "check_circle";
            case "error":
                return "error";
            case "warning":
                return "warning";
            default:
                return "info";
        }
    };

    return (
        <div className="toast-container" id="toastContainer">
            {toasts.map((toast) => (
                <div
                    key={toast.id}
                    className="toast"
                    style={getToastStyle(toast.type)}
                >
                    <span className="material-symbols-outlined">
                        {getToastIcon(toast.type)}
                    </span>
                    <span>{toast.message}</span>
                </div>
            ))}
        </div>
    );
}
