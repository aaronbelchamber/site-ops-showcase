import os
import time
from functools import wraps
from flask import request, jsonify

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
            expected_token = os.getenv("API_TOKEN", "secret-change-me")
            
            # Check Authorization header format
            # Supports: "Bearer token" or just "token"
            if not token:
                return jsonify({
                    "success": False,
                    "data": None,
                    "error": "Unauthorized: Missing Authorization Header",
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                }), 401
                
            valid = (token == expected_token) or (token == f"Bearer {expected_token}")
            if not valid:
                return jsonify({
                    "success": False,
                    "data": None,
                    "error": "Unauthorized: Invalid API token",
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                }), 401
                
            return f(*args, **kwargs)
        return decorated

# Backward-compatible module-level alias
require_api_key = APIAuthGuard.require_api_key
