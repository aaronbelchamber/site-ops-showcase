import hmac
import os
import time
from functools import wraps
from flask import request, jsonify

from src.logging.logger import logger

# Historical fallback token. Kept only so we can recognise and refuse it: an
# install that never set API_TOKEN would otherwise authenticate anyone who read
# this file in the public source.
_INSECURE_DEFAULT_TOKEN = "secret-change-me"


def _unauthorized(message: str):
    return jsonify({
        "success": False,
        "data": None,
        "error": f"Unauthorized: {message}",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }), 401


def _misconfigured(message: str):
    return jsonify({
        "success": False,
        "data": None,
        "error": f"Server misconfigured: {message}",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }), 500


class APIAuthGuard:
    @staticmethod
    def require_api_key(f):
        """Decorator to secure API endpoints with API token authentication."""
        @wraps(f)
        def decorated(*args, **kwargs):
            # Allow preflight CORS requests without auth
            if request.method == "OPTIONS":
                return f(*args, **kwargs)

            token = request.headers.get("Authorization")
            expected_token = os.getenv("API_TOKEN")

            # Refuse to serve rather than fall back to a token published in the
            # source tree.
            if not expected_token or expected_token == _INSECURE_DEFAULT_TOKEN:
                logger.error(
                    "API_TOKEN is unset or still set to the insecure default; refusing all API requests. "
                    "Set a strong API_TOKEN in config/.env."
                )
                return _misconfigured(
                    "API_TOKEN is not configured. Set a strong API_TOKEN in config/.env and restart."
                )

            if not token:
                return _unauthorized("Missing Authorization Header")

            # Constant-time comparison so a wrong token cannot be recovered by
            # timing the response. Both accepted forms are compared.
            bearer = f"Bearer {expected_token}"
            valid = hmac.compare_digest(token, expected_token) or hmac.compare_digest(token, bearer)
            if not valid:
                return _unauthorized("Invalid API token")

            return f(*args, **kwargs)
        return decorated


# Backward-compatible module-level alias
require_api_key = APIAuthGuard.require_api_key
