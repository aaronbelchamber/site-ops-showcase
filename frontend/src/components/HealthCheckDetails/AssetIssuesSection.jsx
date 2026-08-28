import React from "react";

export function AssetIssuesSection({ brokenImages, failedAssetRequests }) {
    const hasIssues = brokenImages.length > 0 || failedAssetRequests.length > 0;

    if (!hasIssues) {
        return (
            <div className="hcd-empty-success">
                <span className="material-symbols-outlined">check_circle</span>
                <span>No broken images or failed asset requests found.</span>
            </div>
        );
    }

    return (
        <div className="hcd-col hcd-gap-lg">
            {brokenImages.length > 0 && (
                <div>
                    <div className="hcd-asset-issue-heading">
                        {brokenImages.length} broken image{brokenImages.length === 1 ? "" : "s"} (loaded but rendered empty)
                    </div>
                    <div className="hcd-col hcd-gap-xs">
                        {brokenImages.map((img, i) => (
                            <div key={i} className="hcd-asset-issue-item">
                                {img.src}{img.alt ? ` (alt: "${img.alt}")` : ""}
                            </div>
                        ))}
                    </div>
                </div>
            )}
            {failedAssetRequests.length > 0 && (
                <div>
                    <div className="hcd-asset-issue-heading">
                        {failedAssetRequests.length} failed asset request{failedAssetRequests.length === 1 ? "" : "s"} (image/CSS/JS/font returned an error)
                    </div>
                    <div className="hcd-col hcd-gap-xs">
                        {failedAssetRequests.map((req, i) => (
                            <div key={i} className="hcd-asset-issue-item">
                                [{req.status}] {req.resource_type}: {req.url}
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}
