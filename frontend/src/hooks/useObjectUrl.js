import { useState, useEffect, useCallback, useRef } from "react";

/**
 * Holds one object URL, revoking the previous one only when it is actually
 * replaced (and the last one on unmount). A single effect over several
 * independent URLs (e.g. desktop/mobile screenshots that load sequentially)
 * would revoke every URL whenever any one of them changed, killing images
 * that were still on screen -- each call to this hook manages exactly one
 * URL's lifecycle, so callers use one instance per image.
 */
export function useObjectUrl() {
    const [url, setUrl] = useState(null);
    const currentRef = useRef(null);

    const assign = useCallback((nextUrl) => {
        if (currentRef.current && currentRef.current !== nextUrl) {
            URL.revokeObjectURL(currentRef.current);
        }
        currentRef.current = nextUrl;
        setUrl(nextUrl);
    }, []);

    useEffect(() => () => {
        if (currentRef.current) {
            URL.revokeObjectURL(currentRef.current);
            currentRef.current = null;
        }
    }, []);

    return [url, assign];
}
