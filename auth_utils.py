from functools import wraps
from flask import session, redirect, url_for, abort


def login_required(view_func):
    """
    Blocks access unless a user is logged in.
    Use on every protected route in every future stage.
    """
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("auth.login"))
        return view_func(*args, **kwargs)
    return wrapped


def role_required(*allowed_roles):
    """
    Blocks access unless the logged-in user's role is in allowed_roles.
    This is what stops a Client from reaching a Manager URL by typing it
    in manually — every protected route in later stages will use this.

    Usage:
        @manager_bp.route("/approve_project/<int:project_id>", methods=["POST"])
        @login_required
        @role_required("Project Manager", "Admin")
        def approve_project(project_id):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            if not session.get("user_id"):
                return redirect(url_for("auth.login"))
            if session.get("role") not in allowed_roles:
                abort(403)
            return view_func(*args, **kwargs)
        return wrapped
    return decorator
