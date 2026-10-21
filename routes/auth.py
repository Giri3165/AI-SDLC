from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    jsonify,
    current_app,
)
from werkzeug.security import generate_password_hash, check_password_hash
from db import get_cursor, get_db
from auth_utils import login_required
from mail import send_email
from rate_limit import rate_limit
import secrets
from datetime import datetime, timedelta


auth_bp = Blueprint("auth", __name__)


# Kept available for other parts of the application that may import it.
VALID_ROLES = [
    "Client",
    "Project Manager",
    "Developer",
    "Tester",
    "Admin",
]


@auth_bp.route("/")
def home():
    if session.get("user_id"):
        return redirect(url_for("auth.dashboard"))

    return redirect(url_for("auth.login"))


@auth_bp.route("/check_username")
def check_username():
    username = request.args.get("username", "").strip()

    if not username:
        return jsonify({"available": False})

    cursor = get_cursor()

    cursor.execute(
        "SELECT id FROM users WHERE username = %s",
        (username,)
    )

    exists = cursor.fetchone()

    cursor.close()

    return jsonify({"available": exists is None})


MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15


@auth_bp.route("/login", methods=["GET", "POST"])
def login():

    if session.get("user_id"):
        return redirect(url_for("auth.dashboard"))

    if request.method == "POST":

        identifier = request.form.get(
            "identifier",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        cursor = get_cursor()

        cursor.execute(
            """
            SELECT
                id,
                fullname,
                username,
                password_hash,
                role,
                failed_login_attempts,
                locked_until,
                must_change_password
            FROM users
            WHERE username = %s
               OR email = %s
            """,
            (
                identifier,
                identifier
            )
        )

        user = cursor.fetchone()

        # ----------------------------------------
        # Account locked
        # ----------------------------------------

        if (
            user
            and user["locked_until"]
            and user["locked_until"] > datetime.utcnow()
        ):

            remaining_minutes = int(
                (
                    user["locked_until"]
                    - datetime.utcnow()
                ).total_seconds() // 60
            ) + 1

            cursor.close()

            return render_template(
                "auth/login.html",
                error=(
                    "Too many failed attempts. "
                    f"Try again in {remaining_minutes} minute(s)."
                )
            )

        # ----------------------------------------
        # Correct password
        # ----------------------------------------

        if (
            user
            and check_password_hash(
                user["password_hash"],
                password
            )
        ):

            db = get_db()

            cursor.execute(
                """
                UPDATE users
                SET
                    failed_login_attempts = 0,
                    locked_until = NULL
                WHERE id = %s
                """,
                (user["id"],)
            )

            db.commit()
            cursor.close()

            session.clear()

            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["fullname"] = user["fullname"]
            session["role"] = user["role"]
            session["must_change_password"] = bool(
                user["must_change_password"]
            )

            # ------------------------------------
            # Force first-time password change
            # ------------------------------------

            if user["must_change_password"]:

                return redirect(
                    url_for("profile.profile")
                )

            return redirect(
                url_for("auth.dashboard")
            )

        # ----------------------------------------
        # Wrong password
        # ----------------------------------------

        if user:

            attempts = (
                user["failed_login_attempts"] + 1
            )

            db = get_db()

            if attempts >= MAX_FAILED_ATTEMPTS:

                locked_until = (
                    datetime.utcnow()
                    + timedelta(
                        minutes=LOCKOUT_MINUTES
                    )
                )

                cursor.execute(
                    """
                    UPDATE users
                    SET
                        failed_login_attempts = %s,
                        locked_until = %s
                    WHERE id = %s
                    """,
                    (
                        attempts,
                        locked_until,
                        user["id"]
                    )
                )

            else:

                cursor.execute(
                    """
                    UPDATE users
                    SET failed_login_attempts = %s
                    WHERE id = %s
                    """,
                    (
                        attempts,
                        user["id"]
                    )
                )

            db.commit()

        cursor.close()

        return render_template(
            "auth/login.html",
            error="Invalid username or password."
        )

    return render_template(
        "auth/login.html"
    )

@auth_bp.route("/register", methods=["GET", "POST"])
@rate_limit(max_requests=10, window_seconds=3600)
def register():

    if session.get("user_id"):
        return redirect(url_for("auth.dashboard"))

    if request.method == "POST":

        fullname = request.form.get("fullname", "").strip()
        email = request.form.get("email", "").strip()
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        errors = []

        if not fullname or not email or not username or not password:
            errors.append("All fields are required.")

        if password != confirm_password:
            errors.append("Passwords do not match.")

        if len(password) < 8:
            errors.append("Password must be at least 8 characters.")

        # ---------------------------------------------------------
        # IMPORTANT SECURITY RULE:
        # Public registration can ONLY create Client accounts.
        #
        # Do NOT trust a role submitted by the browser.
        # ---------------------------------------------------------
        role = "Client"

        if not errors:

            cursor = get_cursor()

            cursor.execute(
                """
                SELECT id
                FROM users
                WHERE username = %s OR email = %s
                """,
                (username, email)
            )

            if cursor.fetchone():

                errors.append(
                    "Username or email is already registered."
                )

            cursor.close()

        if errors:

            return render_template(
                "auth/register.html",
                error=" ".join(errors),
                form_values={
                    "fullname": fullname,
                    "email": email,
                    "username": username,
                }
            )

        password_hash = generate_password_hash(password)

        db = get_db()
        cursor = get_cursor()

        cursor.execute(
            """
            INSERT INTO users (
                fullname,
                email,
                username,
                password_hash,
                role
            )
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                fullname,
                email,
                username,
                password_hash,
                role
            )
        )

        db.commit()
        cursor.close()

        flash(
            "Account created successfully. Please log in.",
            "success"
        )

        return redirect(url_for("auth.login"))

    return render_template("auth/register.html")


@auth_bp.route("/dashboard")
@login_required
def dashboard():

    role = session.get("role")

    if role == "Client":
        return redirect(url_for("client.dashboard"))

    if role == "Project Manager":
        return redirect(url_for("manager.dashboard"))

    if role == "Developer":
        return redirect(url_for("developer.dashboard"))

    if role == "Tester":
        return redirect(url_for("tester.dashboard"))

    if role == "Admin":
        return redirect(url_for("admin.dashboard"))

    return render_template("shared/dashboard_stub.html")


@auth_bp.route("/forgot_password", methods=["GET", "POST"])
@rate_limit(max_requests=3, window_seconds=600)
def forgot_password():

    if request.method == "POST":

        identifier = request.form.get("identifier", "").strip()

        cursor = get_cursor()

        cursor.execute(
            """
            SELECT id, email
            FROM users
            WHERE username = %s OR email = %s
            """,
            (identifier, identifier)
        )

        user = cursor.fetchone()

        if user:

            token = secrets.token_urlsafe(32)

            expires_at = (
                datetime.utcnow()
                + timedelta(hours=1)
            )

            db = get_db()

            cursor.execute(
                """
                INSERT INTO password_resets
                (user_id, token, expires_at)
                VALUES (%s, %s, %s)
                """,
                (
                    user["id"],
                    token,
                    expires_at
                )
            )

            db.commit()

            reset_link = url_for(
                "auth.reset_password",
                token=token,
                _external=True
            )

            html_body = render_template(
                "emails/reset_password.html",
                reset_link=reset_link
            )

            text_body = (
                "You requested a password reset.\n\n"
                f"Click the link below to choose a new password. "
                f"It expires in 1 hour:\n\n"
                f"{reset_link}\n\n"
                "If you didn't request this, you can safely ignore "
                "this email."
            )

            email_sent = send_email(
                user["email"],
                "Reset your AI-SDLC password",
                text_body,
                html_body=html_body
            )

            if not email_sent and current_app.debug:

                flash(
                    "[DEV MODE — email not sent, no SMTP configured] "
                    f"Reset link: {reset_link}",
                    "info"
                )

        cursor.close()

        # Same response regardless of whether the account exists.
        return render_template(
            "auth/forgot_password_sent.html"
        )

    return render_template(
        "auth/forgot_password.html"
    )


@auth_bp.route(
    "/reset_password/<token>",
    methods=["GET", "POST"]
)
def reset_password(token):

    cursor = get_cursor()

    cursor.execute(
        """
        SELECT
            id,
            user_id,
            expires_at,
            used
        FROM password_resets
        WHERE token = %s
        """,
        (token,)
    )

    reset_row = cursor.fetchone()

    cursor.close()

    valid = (
        reset_row is not None
        and not reset_row["used"]
        and reset_row["expires_at"] > datetime.utcnow()
    )

    if not valid:

        flash(
            "This reset link is invalid or has expired.",
            "danger"
        )

        return redirect(
            url_for("auth.forgot_password")
        )

    if request.method == "POST":

        password = request.form.get("password", "")
        confirm_password = request.form.get(
            "confirm_password",
            ""
        )

        errors = []

        if len(password) < 8:
            errors.append(
                "Password must be at least 8 characters."
            )

        if password != confirm_password:
            errors.append(
                "Passwords do not match."
            )

        if errors:

            return render_template(
                "auth/reset_password.html",
                token=token,
                error=" ".join(errors)
            )

        password_hash = generate_password_hash(password)

        db = get_db()
        cursor = get_cursor()

        cursor.execute(
            """
            UPDATE users
            SET password_hash = %s
            WHERE id = %s
            """,
            (
                password_hash,
                reset_row["user_id"]
            )
        )

        cursor.execute(
            """
            UPDATE password_resets
            SET used = 1
            WHERE id = %s
            """,
            (reset_row["id"],)
        )

        db.commit()
        cursor.close()

        flash(
            "Password reset successful. Please log in.",
            "success"
        )

        return redirect(
            url_for("auth.login")
        )

    return render_template(
        "auth/reset_password.html",
        token=token
    )


@auth_bp.route("/logout")
def logout():

    session.clear()

    return redirect(
        url_for("auth.login")
    )
