import React, { useState, useEffect } from "react";

export default function TopStatusContainer({ onActivityLogged }) {
    const [statusList, setStatusList] = useState([]);
    const [expandedIds, setExpandedIds] = useState(new Set());
    const [selectedDetail, setSelectedDetail] = useState(null);

    useEffect(() => {
        const handleStatusEvent = (e) => {
            const item = e.detail;
            if (!item || !item.message) return;

            // Notify parent / activity logger if callback provided
            if (onActivityLogged) {
                onActivityLogged(item);
            }

            // Add to top status list (latest on top)
            setStatusList((prev) => [item, ...prev.filter((i) => i.id !== item.id)]);
        };

        window.addEventListener("app-toast", handleStatusEvent);
        return () => window.removeEventListener("app-toast", handleStatusEvent);
    }, [onActivityLogged]);

    const handleDismiss = (id) => {
        setStatusList((prev) => prev.filter((item) => item.id !== id));
        setExpandedIds((prev) => {
            const next = new Set(prev);
            next.delete(id);
            return next;
        });
    };

    const handleClearAll = () => {
        setStatusList([]);
        setExpandedIds(new Set());
    };

    const toggleExpand = (id) => {
        setExpandedIds((prev) => {
            const next = new Set(prev);
            if (next.has(id)) {
                next.delete(id);
            } else {
                next.add(id);
            }
            return next;
        });
    };

    const getStatusStyle = (type) => {
        switch (type) {
            case "success":
                return {
                    borderColor: "var(--md-sys-color-success, #4caf50)",
                    backgroundColor: "rgba(76, 175, 80, 0.08)"
                };
            case "error":
                return {
                    borderColor: "var(--md-sys-color-error, #f44336)",
                    backgroundColor: "rgba(244, 67, 54, 0.08)"
                };
            case "warning":
                return {
                    borderColor: "var(--md-sys-color-warning, #ff9800)",
                    backgroundColor: "rgba(255, 152, 0, 0.08)"
                };
            case "process":
                return {
                    borderColor: "var(--md-sys-color-primary, #2196f3)",
                    backgroundColor: "rgba(33, 150, 243, 0.08)"
                };
            default:
                return {
                    borderColor: "var(--md-sys-color-outline-variant, #ccc)",
                    backgroundColor: "var(--md-sys-color-surface-container, #f8f9fa)"
                };
        }
    };

    const getStatusIcon = (type) => {
        switch (type) {
            case "success":
                return "check_circle";
            case "error":
                return "error";
            case "warning":
                return "warning";
            case "process":
                return "sync";
            default:
                return "info";
        }
    };

    if (statusList.length === 0) return null;

    return (
        <div className="top-status-container" id="topStatusContainer">
            <div className="top-status-header">
                <div className="top-status-title">
                    <span className="material-symbols-outlined top-status-title-icon">notifications_active</span>
                    System Status & Notifications ({statusList.length})
                </div>
                {statusList.length > 1 && (
                    <button
                        className="md-button md-button-tonal top-status-clear"
                        onClick={handleClearAll}
                    >
                        Dismiss All
                    </button>
                )}
            </div>

            <div className="top-status-list">
                {statusList.map((item) => {
                    const isExpanded = expandedIds.has(item.id);
                    const isLong = (item.message && item.message.length > 120) || item.details;
                    const displayMsg = isLong && !isExpanded 
                        ? item.message.substring(0, 120) + "..." 
                        : item.message;

                    return (
                        <div
                            key={item.id}
                            className="top-status-banner"
                            style={{ ...getStatusStyle(item.type) }}
                        >
                            <div className="top-status-banner-row">
                                <div className="top-status-banner-summary">
                                    <span className="material-symbols-outlined top-status-banner-icon">
                                        {getStatusIcon(item.type)}
                                    </span>

                                    <div className="top-status-banner-body">
                                        {item.title && (
                                            <div className="top-status-banner-title">
                                                {item.title}
                                            </div>
                                        )}
                                        <div className="top-status-banner-text">
                                            {displayMsg}
                                        </div>

                                        {isExpanded && item.details && (
                                            <pre className="top-status-banner-details">
                                                {item.details}
                                            </pre>
                                        )}

                                        {isLong && (
                                            <button
                                                type="button"
                                                onClick={() => toggleExpand(item.id)}
                                                className="top-status-banner-toggle"
                                            >
                                                <span className="material-symbols-outlined top-status-banner-toggle-icon">
                                                    {isExpanded ? "expand_less" : "expand_more"}
                                                </span>
                                                {isExpanded ? "Hide Details" : "View Full Details"}
                                            </button>
                                        )}
                                    </div>
                                </div>

                                <div className="top-status-banner-meta">
                                    <span className="top-status-banner-time">
                                        {new Date(item.timestamp || Date.now()).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                                    </span>
                                    <button
                                        type="button"
                                        onClick={() => handleDismiss(item.id)}
                                        title="Dismiss notification"
                                        className="top-status-banner-close"
                                    >
                                        <span className="material-symbols-outlined top-status-banner-close-icon">close</span>
                                    </button>
                                </div>
                            </div>
                        </div>
                    );
                })}
            </div>
        </div>
    );
}
