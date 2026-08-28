import os
import sys
import time
import threading
from flask import Flask, jsonify, request

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.api.routes.sites import sites_bp
from src.api.routes.backups import backups_bp
from src.api.routes.health import health_bp
from src.api.routes.updates import updates_bp
from src.api.routes.users import users_bp
from src.api.routes.vulnerability import vulnerability_bp
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
        app.config["MAX_CONTENT_LENGTH"] = int(os.environ.get("MAX_UPLOAD_MB", "25")) * 1024 * 1024


        @app.route("/health")
        def health():
            """This application's own liveness, distinct from /api/sites health.

            The blueprint under /api/sites reports on the WordPress sites this
            tool manages; this reports on the tool. A monitor asking "is the
            site manager up" must not be answered with a remote site's status.

            Kept cheap deliberately: it is polled on a timer, and reaching out
            over SSH to prove liveness would make the check heavier than the
            thing it checks.
            """
            return {"status": "ok", "service": "site-manager"}

        @app.route("/")
        def index(**kwargs):
            return app.send_static_file("index.html")
        
        # 1. Register Blueprints
        # sites, backups, health, updates, users, and vulnerability are all
        # nested under the /api/sites prefix
        app.register_blueprint(sites_bp, url_prefix="/api/sites")
        app.register_blueprint(backups_bp, url_prefix="/api/sites")
        app.register_blueprint(health_bp, url_prefix="/api/sites")
        app.register_blueprint(updates_bp, url_prefix="/api/sites")
        app.register_blueprint(users_bp, url_prefix="/api/sites")
        app.register_blueprint(vulnerability_bp, url_prefix="/api/sites")
        
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
            """
            Unmatched paths fall through to the single-page app so that deep
            links and refreshes work on client-side routes.

            This replaced a hand-maintained list of @app.route entries that had
            drifted from the frontend router: /manage-sites and its sub-routes
            were never added, so refreshing there returned this JSON 404 in
            production (dev worked only because Vite serves the SPA itself).
            Routing through the 404 handler means new client routes need no
            server change.

            API paths and asset-looking paths still 404 properly -- returning
            index.html for a missing bundle would turn a build error into a
            blank page.
            """
            path = request.path
            is_api = path.startswith("/api/")
            looks_like_file = "." in os.path.basename(path)
            wants_html = "text/html" in (request.headers.get("Accept") or "")

            if request.method == "GET" and not is_api and not looks_like_file and wants_html:
                try:
                    return app.send_static_file("index.html")
                except Exception:
                    # Static bundle not built or unreadable; fall through to JSON 404 response. Best-effort SPA routing.
                    pass

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

        @app.errorhandler(413)
        def payload_too_large(error):
            return jsonify({
                "success": False,
                "data": None,
                "error": "The uploaded file is too large.",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            }), 413

        @app.errorhandler(500)
        def internal_server_error(error):
            import traceback
            from src.logging.logger import logger as app_logger
            app_debug = os.environ.get("APP_DEBUG", "false").lower() in ["true", "1"]
            app_logger.error(f"Unhandled exception: {error}", exc_info=True)
            resp = {
                "success": False,
                "data": None,
                # Detail is logged server-side above; never echo exception text to
                # the client regardless of APP_DEBUG (which only gates the traceback).
                "error": "Internal server error.",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            }
            if app_debug:
                resp["traceback"] = traceback.format_exc()
            return jsonify(resp), 500
    
        return app

# Backward-compatible alias
create_app = AppFactory.create_app


def serve_app(app: Flask, host: str, port: int, debug: bool, threads: int = 8) -> None:
    """
    Serve the app appropriately for the requested mode.

    debug=True uses Flask's own dev server, since only it supports the
    auto-reloader development relies on. debug=False uses waitress -- the
    Werkzeug dev server is single-threaded by default and was serializing
    every request behind whichever one is slowest, which is what turned
    the pre-remediation perf issues into outright timeouts under load.
    """
    if debug:
        app.run(host=host, port=port, debug=True)
        return

    from waitress import serve
    print(f"Serving via waitress (production WSGI server, {threads} threads) on {host}:{port}...")
    serve(app, host=host, port=port, threads=threads)


if __name__ == "__main__":
    start_cleanup_scheduler(debug=True)
    app = create_app()
    app.run(host="127.0.0.1", port=63010, debug=True)
