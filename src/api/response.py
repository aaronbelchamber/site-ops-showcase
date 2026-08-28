import time
from flask import jsonify


def _timestamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def ok(data=None, status: int = 200):
    """Standard success envelope: {success, data, error: None, timestamp}."""
    return jsonify({
        "success": True,
        "data": data,
        "error": None,
        "timestamp": _timestamp()
    }), status


def err(message: str, status: int = 400, data=None):
    """Standard error envelope: {success: False, data, error, timestamp}."""
    return jsonify({
        "success": False,
        "data": data,
        "error": message,
        "timestamp": _timestamp()
    }), status
