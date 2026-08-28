// Maps overall_status to the modifier suffix shared by the status badge and
// the explanation banner's border/icon colour classes.
export function statusModifier(overallStatus) {
    if (overallStatus === "critical") return "critical";
    if (overallStatus === "degraded") return "degraded";
    if (overallStatus === "notice") return "notice";
    return "healthy";
}
