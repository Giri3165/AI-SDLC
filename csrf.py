import secrets
from flask import session, request, abort


def get_csrf_token():
    """
    Returns the current session's CSRF token, generating one if needed.
    Exposed to Jinja as csrf_token() — use in every form:
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
    """
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)
    return session["csrf_token"]


def validate_csrf():
    """
    Call at the top of every POST route (or globally via before_request,
    see app.py) to reject requests with a missing/incorrect token.
    """
    if request.method == "POST":
        submitted = request.form.get("csrf_token")
        expected = session.get("csrf_token")
        if not submitted or not expected or submitted != expected:
            abort(400, description="Invalid or missing CSRF token.")
