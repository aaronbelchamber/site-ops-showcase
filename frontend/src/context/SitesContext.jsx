import React, { createContext, useContext, useState, useCallback } from "react";
import api from "../services/api";

const SitesContext = createContext(null);

export function SitesProvider({ children }) {
    const [sites, setSites] = useState([]);
    const [updatesBySite, setUpdatesBySite] = useState({});
    const [healthBySite, setHealthBySite] = useState({});
    const [inFlightChecks, setInFlightChecks] = useState(() => new Set());

    const setSiteUpdates = useCallback((siteName, updatesData) => {
        if (!siteName) return;
        setUpdatesBySite((prev) => ({
            ...prev,
            [siteName]: updatesData
        }));
    }, []);

    const setSiteHealth = useCallback((siteName, healthData) => {
        if (!siteName) return;
        setHealthBySite((prev) => ({
            ...prev,
            [siteName]: healthData
        }));
    }, []);

    const setSiteCheckInFlight = useCallback((siteName, inFlight) => {
        if (!siteName) return;
        setInFlightChecks((prev) => {
            const next = new Set(prev);
            if (inFlight) {
                next.add(siteName);
            } else {
                next.delete(siteName);
            }
            return next;
        });
    }, []);

    const refreshSiteUpdates = useCallback(async (siteName) => {
        if (!siteName) return null;
        try {
            const data = await api.checkUpdates(siteName, false);
            if (data) {
                setSiteUpdates(siteName, data);
            }
            return data;
        } catch (err) {
            console.debug("Failed to fetch update status for", siteName, err);
            return null;
        }
    }, [setSiteUpdates]);

    return (
        <SitesContext.Provider
            value={{
                sites,
                setSites,
                updatesBySite,
                setSiteUpdates,
                healthBySite,
                setSiteHealth,
                inFlightChecks,
                setSiteCheckInFlight,
                refreshSiteUpdates
            }}
        >
            {children}
        </SitesContext.Provider>
    );
}

export function useSitesContext() {
    const ctx = useContext(SitesContext);
    return ctx;
}
