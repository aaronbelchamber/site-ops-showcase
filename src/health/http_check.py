import hashlib
import re
import time
import requests
import urllib3
from typing import Any, Dict, List, Optional

# Suppress insecure request warnings for local/staging certificates when verify_ssl is False
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class ConsoleErrorClassifier:
    """Classifies browser console errors into severity tiers and fingerprints them.

    Severity tiers:
        - ``ignored``  : Known headless-browser artifact; safe to ignore automatically.
        - ``warning``  : Potentially problematic but not confirmed site-breaking.
        - ``critical`` : Unknown error; assumed site-breaking until acknowledged.

    The global suppression list only targets errors that are provably impossible to
    reproduce in a real browser (e.g. reCAPTCHA iframe sandbox rejections).
    Font-loading errors are *not* suppressed globally because they may be genuine.
    """

    # (pattern, human-readable reason) — matched against error text OR location URL
    GLOBAL_SUPPRESSION_PATTERNS: List[tuple[str, str]] = [
        (
            r"requestStorageAccess.*[Pp]ermission [Dd]enied",
            "reCAPTCHA iframe storage-access rejection — headless-only artifact",
        ),
        (
            r"Blocked.*access.*cross-origin frame",
            "Cross-origin iframe sandbox restriction — headless-only artifact",
        ),
        (
            r"Access to frame.*denied",
            "Frame access denied by sandbox — headless-only artifact",
        ),
    ]

    # Fingerprint is always computed on the full text; stored/displayed text is capped at this length.
    MAX_ERROR_TEXT_LENGTH: int = 150

    @classmethod
    def compute_fingerprint(cls, error: Dict[str, Any]) -> str:
        """Return a short, stable SHA-1 fingerprint for an error.

        Args:
            error: Raw Playwright console error dict with ``text`` and ``location``.

        Returns:
            An 8-character hex string uniquely identifying this error class.
        """
        location_url = (error.get("location") or {}).get("url", "")
        raw = f"{error.get('text', '')}|{location_url}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]

    @classmethod
    def classify(cls, error: Dict[str, Any]) -> tuple[str, Optional[str]]:
        """Classify a console error and return its severity and suppression reason.

        Args:
            error: Raw Playwright console error dict.

        Returns:
            A tuple of (severity_str, suppression_reason_or_None).
        """
        error_text = error.get("text", "")
        location_url = (error.get("location") or {}).get("url", "")
        combined = f"{error_text} {location_url}"

        for pattern, reason in cls.GLOBAL_SUPPRESSION_PATTERNS:
            if re.search(pattern, combined, re.IGNORECASE):
                return "ignored", reason

        # Third-party analytics/tracking console errors are non-critical warnings
        warning_patterns = [
            r"google-analytics", r"googletagmanager", r"analytics\.js", r"ga\.js", r"gtag",
            r"facebook\.net", r"fbevents", r"doubleclick", r"quantserve", r"connect\.facebook"
        ]
        for wp in warning_patterns:
            if re.search(wp, combined, re.IGNORECASE):
                return "warning", "Third-party analytics / tracker script error"

        return "critical", None

    @classmethod
    def enrich(cls, raw_errors: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Enrich a list of raw Playwright errors with severity, fingerprint, and suppression metadata.

        Args:
            raw_errors: List of raw console error dicts from Playwright.

        Returns:
            Enriched list with ``severity``, ``fingerprint``, and optionally
            ``suppression_source`` / ``suppression_reason`` keys added.
        """
        enriched = []
        for err in raw_errors:
            severity, reason = cls.classify(err)
            # Compute fingerprint on the FULL text before any truncation for stability.
            fingerprint = cls.compute_fingerprint(err)
            enriched_err = dict(err)
            # Truncate stored text so logs stay compact and UI never overflows.
            raw_text = enriched_err.get("text", "")
            if len(raw_text) > cls.MAX_ERROR_TEXT_LENGTH:
                enriched_err["text"] = raw_text[: cls.MAX_ERROR_TEXT_LENGTH] + "…"
            enriched_err["severity"] = severity
            enriched_err["fingerprint"] = fingerprint
            if reason:
                enriched_err["suppression_source"] = "global"
                enriched_err["suppression_reason"] = reason
            enriched.append(enriched_err)
        return enriched

class HTTPHealthCheck:
    def __init__(self, url: str, verify_ssl: bool = False):
        self.url = url
        self.verify_ssl = verify_ssl

    def check_status_code(self, expected: int = 200, timeout: int = 10) -> tuple[bool, int, Optional[str]]:
        """
        Check if URL returns the expected status code.
        Returns: (success, status_code, error_message)
        """
        try:
            response = requests.get(self.url, timeout=timeout, verify=self.verify_ssl)
            return (response.status_code == expected), response.status_code, None
        except requests.exceptions.RequestException as e:
            return False, 0, str(e)

    def check_response_time(self, max_ms: int = 5000, timeout: int = 10) -> tuple[bool, int, Optional[str]]:
        """
        Check if response time is within the threshold.
        Returns: (success, response_time_ms, error_message)
        """
        start = time.perf_counter()
        try:
            requests.get(self.url, timeout=timeout, verify=self.verify_ssl)
            duration_ms = int((time.perf_counter() - start) * 1000)
            return (duration_ms <= max_ms), duration_ms, None
        except requests.exceptions.RequestException as e:
            return False, 0, str(e)

    def check_content_contains(self, text: str, timeout: int = 10) -> tuple[bool, Optional[str]]:
        """
        Check if response text contains specific text.
        Returns: (success, error_message)
        """
        try:
            response = requests.get(self.url, timeout=timeout, verify=self.verify_ssl)
            if text in response.text:
                return True, None
            return False, f"Expected content '{text}' not found in response page."
        except requests.exceptions.RequestException as e:
            return False, str(e)

    def run_full_check(self, timeout: int = 10) -> Dict[str, Any]:
        """
        Run basic HTTP health checks and return structured result.
        """
        start = time.perf_counter()
        try:
            response = requests.get(self.url, timeout=timeout, verify=self.verify_ssl)
            duration_ms = int((time.perf_counter() - start) * 1000)
            
            # Simple content checking (look for basic HTML/WordPress clues)
            # WordPress site usually contains wp-content, wp-includes, or simply <html>
            is_wp = "wp-content" in response.text or "wp-includes" in response.text
            
            status = "pass" if response.status_code == 200 else "fail"
            
            return {
                "status_code": response.status_code,
                "response_time_ms": duration_ms,
                "status": status,
                "is_wordpress_detected": is_wp,
                "error": None
            }
        except requests.exceptions.RequestException as e:
            return {
                "status_code": 0,
                "response_time_ms": 0,
                "status": "fail",
                "is_wordpress_detected": False,
                "error": str(e)
            }
        except Exception as e:
            return {
                "status_code": 0,
                "response_time_ms": 0,
                "status": "fail",
                "is_wordpress_detected": False,
                "error": f"Unexpected error: {e}"
            }

    def run_browser_check(self, site_name: str, check_id: str, screenshots_dir: str, timeout_ms: int = 15000) -> Dict[str, Any]:
        """
        Run page check using Playwright to extract status code, console errors, and capture screenshots.
        """
        import os
        from playwright.sync_api import sync_playwright
        
        console_errors = []
        status_code = 0
        start = time.perf_counter()

        def handle_console(msg):
            if msg.type == "error":
                loc = msg.location or {}
                raw_url = str(loc.get("url", "") if isinstance(loc, dict) else getattr(loc, "url", ""))
                max_len = ConsoleErrorClassifier.MAX_ERROR_TEXT_LENGTH
                console_errors.append({
                    "text": msg.text,
                    "location": {
                        "url": raw_url if len(raw_url) <= max_len else raw_url[:max_len] + "…",
                        "lineNumber": int(loc.get("lineNumber", 0) if isinstance(loc, dict) else getattr(loc, "lineNumber", 0)),
                        "columnNumber": int(loc.get("columnNumber", 0) if isinstance(loc, dict) else getattr(loc, "columnNumber", 0)),
                    },
                })

        # Calculate YYYY-MM directory
        year_month = time.strftime("%Y-%m", time.gmtime())
        site_screenshots_dir = os.path.join(screenshots_dir, site_name, year_month)
        os.makedirs(site_screenshots_dir, exist_ok=True)
        
        desktop_filename = f"{check_id}_desktop.png"
        mobile_filename = f"{check_id}_mobile.png"
        
        desktop_path = os.path.join(site_screenshots_dir, desktop_filename)
        mobile_path = os.path.join(site_screenshots_dir, mobile_filename)

        try:
            with sync_playwright() as p:
                # 1. Desktop Screenshot & Console Logs
                browser = p.chromium.launch(headless=True)
                desktop_context = browser.new_context(
                    viewport={"width": 1280, "height": 800},
                    ignore_https_errors=not self.verify_ssl
                )
                desktop_page = desktop_context.new_page()
                desktop_page.on("console", handle_console)
                
                response = desktop_page.goto(self.url, timeout=timeout_ms, wait_until="load")
                if response:
                    status_code = response.status
                
                desktop_page.wait_for_timeout(500)
                desktop_page.screenshot(path=desktop_path)
                desktop_context.close()
                
                # 2. Mobile Screenshot (using iPhone viewport/UA)
                mobile_context = browser.new_context(
                    viewport={"width": 375, "height": 667},
                    user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
                    is_mobile=True,
                    has_touch=True,
                    ignore_https_errors=not self.verify_ssl
                )
                mobile_page = mobile_context.new_page()
                mobile_page.goto(self.url, timeout=timeout_ms, wait_until="load")
                mobile_page.wait_for_timeout(500)
                mobile_page.screenshot(path=mobile_path)
                mobile_context.close()
                
                browser.close()
                
            duration_ms = int((time.perf_counter() - start) * 1000)

            # Enrich raw errors with severity + fingerprint
            enriched_errors = ConsoleErrorClassifier.enrich(console_errors)

            # A health check fails only if there are non-ignored errors or a bad status code
            unacknowledged_errors = [e for e in enriched_errors if e["severity"] != "ignored"]
            status = "pass"
            if status_code > 302 or status_code == 0 or len(unacknowledged_errors) > 0:
                status = "fail"
                
            return {
                "status_code": status_code,
                "response_time_ms": duration_ms,
                "status": status,
                "console_errors": enriched_errors,
                "screenshots": {
                    "year_month": year_month,
                    "desktop": desktop_filename,
                    "mobile": mobile_filename,
                },
                "error": None,
            }
        except Exception as e:
            duration_ms = int((time.perf_counter() - start) * 1000)
            return {
                "status_code": status_code,
                "response_time_ms": duration_ms,
                "status": "fail",
                "console_errors": console_errors,
                "screenshots": None,
                "error": str(e)
            }


