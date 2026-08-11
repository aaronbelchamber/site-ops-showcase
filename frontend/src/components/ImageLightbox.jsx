import React, { useState, useEffect } from "react";

export default function ImageLightbox({ src, alt, onClose }) {
    const [zoom, setZoom] = useState(1);

    useEffect(() => {
        const handleKeyDown = (e) => {
            if (e.key === "Escape") {
                onClose();
            }
        };
        window.addEventListener("keydown", handleKeyDown);
        return () => window.removeEventListener("keydown", handleKeyDown);
    }, [onClose]);

    if (!src) return null;

    const zoomIn = () => setZoom((prev) => Math.min(prev + 0.3, 3));
    const zoomOut = () => setZoom((prev) => Math.max(prev - 0.3, 0.5));
    const resetZoom = () => setZoom(1);

    return (
        <div
            style={{
                position: "fixed",
                top: 0,
                left: 0,
                width: "100vw",
                height: "100vh",
                backgroundColor: "rgba(0, 0, 0, 0.85)",
                zIndex: 9999,
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                backdropFilter: "blur(5px)",
            }}
            onClick={onClose}
        >
            {/* Control Bar */}
            <div
                style={{
                    position: "absolute",
                    top: "1.25rem",
                    right: "1.5rem",
                    display: "flex",
                    alignItems: "center",
                    gap: "0.75rem",
                    zIndex: 10000,
                    backgroundColor: "rgba(20, 20, 20, 0.8)",
                    padding: "0.5rem 1rem",
                    borderRadius: "100px",
                    border: "1px solid rgba(255, 255, 255, 0.15)",
                }}
                onClick={(e) => e.stopPropagation()}
            >
                <span style={{ color: "#fff", fontSize: "0.85rem", fontWeight: "bold", marginRight: "0.5rem" }}>
                    {alt || "Image Magnifier"} ({Math.round(zoom * 100)}%)
                </span>
                <button
                    type="button"
                    className="md-button md-button-tonal md-button-sm"
                    onClick={zoomOut}
                    title="Zoom Out"
                    style={{ color: "#fff", borderColor: "rgba(255,255,255,0.3)" }}
                >
                    <span className="material-symbols-outlined" style={{ fontSize: "18px" }}>remove</span>
                </button>
                <button
                    type="button"
                    className="md-button md-button-tonal md-button-sm"
                    onClick={resetZoom}
                    title="Reset Zoom"
                    style={{ color: "#fff", borderColor: "rgba(255,255,255,0.3)" }}
                >
                    Reset
                </button>
                <button
                    type="button"
                    className="md-button md-button-tonal md-button-sm"
                    onClick={zoomIn}
                    title="Zoom In"
                    style={{ color: "#fff", borderColor: "rgba(255,255,255,0.3)" }}
                >
                    <span className="material-symbols-outlined" style={{ fontSize: "18px" }}>add</span>
                </button>
                <button
                    type="button"
                    className="md-button md-button-primary md-button-sm"
                    onClick={onClose}
                    title="Close (Esc)"
                    style={{ marginLeft: "0.5rem" }}
                >
                    <span className="material-symbols-outlined" style={{ fontSize: "18px" }}>close</span>
                </button>
            </div>

            {/* Scrollable Zoom Container */}
            <div
                style={{
                    width: "90vw",
                    height: "85vh",
                    overflow: "auto",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                }}
                onClick={(e) => e.stopPropagation()}
            >
                <img
                    src={src}
                    alt={alt || "Magnified View"}
                    style={{
                        transform: `scale(${zoom})`,
                        transformOrigin: "center center",
                        transition: "transform 0.15s ease-out",
                        maxWidth: "100%",
                        maxHeight: "100%",
                        objectFit: "contain",
                        borderRadius: "8px",
                        boxShadow: "0 8px 32px rgba(0,0,0,0.5)",
                    }}
                />
            </div>
        </div>
    );
}
