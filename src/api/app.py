import os
import sys
import time
import threading
from flask import Flask, jsonify

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.api.routes.sites import sites_bp
from src.api.routes.backups import backups_bp
from src.api.routes.health import health_bp
from src.api.routes.updates import updates_bp
from src.api.routes.system import system_bp
from src.api.routes.profiles import profiles_bp

_CLEANUP_INTERVAL_SECONDS = 24 * 60 * 60  # daily


def _run_cleanup_loop():
    from src.logging.cleanup import CleanupManager
    from src.logging.logger import logger

    cleanup_mgr = CleanupManager()
    while True:
        try:
            cleanup_mgr.run_scheduled_cleanup()
        except Exception as e:
            logger.error(f"Scheduled cleanup thread encountered an error: {e}")
        time.sleep(_CLEANUP_INTERVAL_SECONDS)


def start_cleanup_scheduler(debug: bool = False):
    """
    Starts a daemon thread that runs backup/log retention cleanup once a day.
    When Flask's debug reloader is active it runs the app in two processes
    (a monitor and a worker); only the worker sets WERKZEUG_RUN_MAIN=true, so
    we skip starting a duplicate thread in the monitor process.
    """
    if debug and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        return
    thread = threading.Thread(target=_run_cleanup_loop, name="cleanup-scheduler", daemon=True)
    thread.start()


class AppFactory:
    @classmethod
    def create_app(cls) -> Flask:
        # Configure project-root static folder
        api_dir = os.path.dirname(os.path.abspath(__file__))
        src_dir = os.path.dirname(api_dir)
        project_root = os.path.dirname(src_dir)
        static_dir = os.path.join(project_root, "static")
        
        app = Flask(__name__, static_folder=static_dir, static_url_path="")
        
        @app.route("/")
        @app.route("/site/add")
        @app.route("/site/<path:sitename>/edit")
        @app.route("/site/<path:sitename>/details")
        @app.route("/site/<path:sitename>/details/<path:subpath>")
        @app.route("/site/<path:sitename>/health-check/<path:check_id>")
        @app.route("/logs")
        @app.route("/admin")
        @app.route("/profiles")
        def index(**kwargs):
            return app.send_static_file("index.html")
        
        # 1. Register Blueprints
        # sites, backups, health, and updates are all nested under /api/sites prefix
        app.register_blueprint(sites_bp, url_prefix="/api/sites")
        app.register_blueprint(backups_bp, url_prefix="/api/sites")
        app.register_blueprint(health_bp, url_prefix="/api/sites")
        app.register_blueprint(updates_bp, url_prefix="/api/sites")
        
        # profiles endpoints under /api/profiles
        app.register_blueprint(profiles_bp, url_prefix="/api/profiles")
        
        # system endpoints under /api/system
        app.register_blueprint(system_bp, url_prefix="/api/system")
        
        # Also register /api/tasks/<task_id> directly on app for convenience and fallback
        from src.api.routes.system import get_task_status
        app.route("/api/tasks/<task_id>", methods=["GET"])(get_task_status)
        
        # 2. CORS Handling
        @app.after_request
        def after_request(response):
            response.headers.add("Access-Control-Allow-Origin", "*")
            response.headers.add("Access-Control-Allow-Headers", "Content-Type,Authorization")
            response.headers.add("Access-Control-Allow-Methods", "GET,PUT,POST,DELETE,OPTIONS")
            return response
    
        # 3. Global Error Handlers
        @app.errorhandler(404)
        def not_found(error):
            return jsonify({
                "success": False,
                "data": None,
                "error": "Resource not found.",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            }), 404
    
        @app.errorhandler(400)
        def bad_request(error):
            return jsonify({
                "success": False,
                "data": None,
                "error": "Bad request.",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            }), 400
    
        @app.errorhandler(500)
        def internal_server_error(error):
            import traceback
            app_debug = os.environ.get("APP_DEBUG", "false").lower() in ["true", "1"]
            resp = {
                "success": False,
                "data": None,
                "error": f"Internal server error: {error}",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            }
            if app_debug:
                resp["traceback"] = traceback.format_exc()
            return jsonify(resp), 500
    
        return app

# Backward-compatible alias
create_app = AppFactory.create_app

if __name__ == "__main__":
    start_cleanup_scheduler(debug=True)
    app = create_app()
    app.run(host="127.0.0.1", port=5000, debug=True)
