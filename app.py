from flask import Flask, render_template, request, redirect, url_for, session
from config import Config
import db
from csrf import get_csrf_token, validate_csrf


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)

    # Make csrf_token() callable from every Jinja template
    app.jinja_env.globals["csrf_token"] = get_csrf_token

    # Reject any POST request without a valid CSRF token, app-wide.
    # This covers every future route automatically — no need to
    # remember to add a check in each one individually.
    @app.before_request
    def _csrf_protect():
        validate_csrf()

    # Enforce the first-login password change. Without this, "forced"
    # would only mean "redirected once at login" — a user could simply
    # click Dashboard in the navbar and keep using the temporary password
    # forever. Only the profile pages, logout, and static files are
    # reachable until must_change_password is cleared.
    @app.before_request
    def _force_password_change():
        if session.get("user_id") and session.get("must_change_password"):
            allowed = {"profile.profile", "profile.save_profile", "auth.logout", "static"}
            if request.endpoint not in allowed:
                return redirect(url_for("profile.profile"))

    @app.errorhandler(429)
    def too_many_requests(e):
        return render_template("shared/error.html", code=429, message=e.description), 429

    from routes.auth import auth_bp
    app.register_blueprint(auth_bp)

    from routes.client import client_bp
    app.register_blueprint(client_bp)

    from routes.manager import manager_bp
    app.register_blueprint(manager_bp)

    from routes.developer import developer_bp
    app.register_blueprint(developer_bp)

    from routes.requirement import requirement_bp
    app.register_blueprint(requirement_bp)

    from routes.task import task_bp
    app.register_blueprint(task_bp)

    from routes.bug import tester_bp
    app.register_blueprint(tester_bp)

    from routes.deployment import deployment_bp
    app.register_blueprint(deployment_bp)

    from routes.admin import admin_bp
    app.register_blueprint(admin_bp)

    from routes.profile import profile_bp
    app.register_blueprint(profile_bp)

    return app


app = create_app()

if __name__ == "__main__":
    import os
    debug_mode = os.environ.get("FLASK_DEBUG", "1") == "1"
    app.run(host="0.0.0.0", port=5000, debug=debug_mode)
