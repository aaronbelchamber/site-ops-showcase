export function showToast(message, type = "info", options = {}) {
    let opts = typeof options === "object" && options !== null ? options : {};
    let isProcess = opts.isProcess || type === "process";
    let details = opts.details || null;
    let title = opts.title || null;

    const detailObj = {
        id: Date.now() + Math.random().toString(36).substr(2, 9),
        message: typeof message === "string" ? message : JSON.stringify(message),
        type,
        isProcess,
        details,
        title,
        timestamp: new Date().toISOString()
    };

    const event = new CustomEvent("app-toast", {
        detail: detailObj
    });
    window.dispatchEvent(event);
}

