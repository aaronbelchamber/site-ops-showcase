import React from "react";

/**
 * Catches render/lifecycle errors from any descendant so a single broken view
 * (a bad prop, a malformed API record) degrades to a recoverable panel instead
 * of unmounting the whole app into a blank page.
 *
 * To clear a caught error on navigation, give the boundary a `key` that encodes
 * the current route: changing it remounts the boundary with fresh state, which
 * is React's idiom for this and avoids a setState-in-componentDidUpdate loop.
 */
export default class ErrorBoundary extends React.Component {
    constructor(props) {
        super(props);
        this.state = { error: null };
    }

    static getDerivedStateFromError(error) {
        return { error };
    }

    componentDidCatch(error, info) {
        console.error("Unhandled UI error:", error, info?.componentStack);
    }

    handleReload = () => {
        window.location.reload();
    };

    handleGoHome = () => {
        window.history.pushState({}, "", "/");
        window.dispatchEvent(new Event("popstate"));
        this.setState({ error: null });
    };

    render() {
        if (!this.state.error) {
            return this.props.children;
        }

        return (
            <div className="error-boundary-panel" role="alert">
                <span className="material-symbols-outlined error-boundary-icon">report</span>
                <h3 className="error-boundary-title">Something went wrong in this view</h3>
                <p className="error-boundary-copy">
                    The rest of the app is still running. You can return to the dashboard or reload
                    the page.
                </p>
                <pre className="error-boundary-details">{String(this.state.error?.message || this.state.error)}</pre>
                <div className="error-boundary-actions">
                    <button type="button" className="md-button md-button-primary" onClick={this.handleGoHome}>
                        <span className="material-symbols-outlined">home</span> Back to Dashboard
                    </button>
                    <button type="button" className="md-button md-button-tonal" onClick={this.handleReload}>
                        <span className="material-symbols-outlined">refresh</span> Reload Page
                    </button>
                </div>
            </div>
        );
    }
}
