import { useEffect, useCallback } from "react";

export function useNavigation() {
    const navigateTo = useCallback((path) => {
        if (window.location.pathname !== path) {
            window.history.pushState({}, "", path);
            window.dispatchEvent(new Event("popstate"));
        }
    }, []);

    const navigateBack = useCallback(() => {
        window.history.pushState({}, "", "/");
        window.dispatchEvent(new Event("popstate"));
    }, []);

    return {
        navigateTo,
        navigateBack
    };
}
