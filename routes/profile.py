from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
)

from werkzeug.security import (
    generate_password_hash,
    check_password_hash,
)

from db import get_cursor, get_db
from auth_utils import login_required


profile_bp = Blueprint(
    "profile",
    __name__,
    url_prefix="/profile"
)


# ============================================================
# PROFILE PAGE
# ============================================================

@profile_bp.route("/", methods=["GET"])
@login_required
def profile():

    user_id = session.get("user_id")

    cursor = get_cursor()

    cursor.execute(
        """
        SELECT
            id,
            fullname,
            email,
            username,
            role,
            must_change_password
        FROM users
        WHERE id = %s
        """,
        (user_id,)
    )

    user = cursor.fetchone()

    cursor.close()

    if not user:

        session.clear()

        flash(
            "User account not found.",
            "danger"
        )

        return redirect(
            url_for("auth.login")
        )

    return render_template(
        "shared/profile.html",
        user=user
    )


# ============================================================
# SAVE PROFILE + CHANGE PASSWORD
# ============================================================

@profile_bp.route(
    "/save",
    methods=["POST"]
)
@login_required
def save_profile():

    user_id = session.get("user_id")

    # --------------------------------------------------------
    # Read submitted values
    # --------------------------------------------------------

    username = request.form.get(
        "username",
        ""
    ).strip()

    current_password = request.form.get(
        "current_password",
        ""
    )

    new_password = request.form.get(
        "new_password",
        ""
    )

    confirm_password = request.form.get(
        "confirm_password",
        ""
    )


    # --------------------------------------------------------
    # Validate username
    # --------------------------------------------------------

    if not username:

        flash(
            "Username cannot be empty.",
            "danger"
        )

        return redirect(
            url_for("profile.profile")
        )


    # --------------------------------------------------------
    # Validate current password
    # --------------------------------------------------------

    if not current_password:

        flash(
            "Current password is required.",
            "danger"
        )

        return redirect(
            url_for("profile.profile")
        )


    # --------------------------------------------------------
    # Validate new password
    # --------------------------------------------------------

    if not new_password:

        flash(
            "New password is required.",
            "danger"
        )

        return redirect(
            url_for("profile.profile")
        )


    if len(new_password) < 8:

        flash(
            "New password must be at least 8 characters.",
            "danger"
        )

        return redirect(
            url_for("profile.profile")
        )


    if not confirm_password:

        flash(
            "Please confirm your new password.",
            "danger"
        )

        return redirect(
            url_for("profile.profile")
        )


    if new_password != confirm_password:

        flash(
            "New passwords do not match.",
            "danger"
        )

        return redirect(
            url_for("profile.profile")
        )


    if current_password == new_password:

        flash(
            "New password must be different from your current password.",
            "danger"
        )

        return redirect(
            url_for("profile.profile")
        )


    # --------------------------------------------------------
    # Get current user
    # --------------------------------------------------------

    cursor = get_cursor()

    cursor.execute(
        """
        SELECT
            id,
            fullname,
            email,
            username,
            role,
            password_hash
        FROM users
        WHERE id = %s
        """,
        (user_id,)
    )

    user = cursor.fetchone()

    if not user:

        cursor.close()

        session.clear()

        flash(
            "User account not found.",
            "danger"
        )

        return redirect(
            url_for("auth.login")
        )


    # --------------------------------------------------------
    # Verify current password
    # --------------------------------------------------------

    if not check_password_hash(
        user["password_hash"],
        current_password
    ):

        cursor.close()

        flash(
            "Current password is incorrect.",
            "danger"
        )

        return redirect(
            url_for("profile.profile")
        )


    # --------------------------------------------------------
    # Check username uniqueness
    # --------------------------------------------------------

    cursor.execute(
        """
        SELECT id
        FROM users
        WHERE username = %s
          AND id <> %s
        """,
        (
            username,
            user_id
        )
    )

    existing_user = cursor.fetchone()

    if existing_user:

        cursor.close()

        flash(
            "Username already exists. Please choose another username.",
            "danger"
        )

        return redirect(
            url_for("profile.profile")
        )


    # --------------------------------------------------------
    # Hash new password
    # --------------------------------------------------------

    new_password_hash = generate_password_hash(
        new_password
    )


    # --------------------------------------------------------
    # Save username + password together
    #
    # Full name, email and role are deliberately NOT updated.
    # --------------------------------------------------------

    db = get_db()

    cursor.execute(
        """
        UPDATE users
        SET
            username = %s,
            password_hash = %s,
            must_change_password = FALSE
        WHERE id = %s
        """,
        (
            username,
            new_password_hash,
            user_id
        )
    )

    db.commit()

    cursor.close()


    # --------------------------------------------------------
    # Update current session
    # --------------------------------------------------------

    session["username"] = username
    session["must_change_password"] = False


    # --------------------------------------------------------
    # Success
    # --------------------------------------------------------

    flash(
        "Profile and password saved successfully.",
        "success"
    )

    return redirect(
        url_for("auth.dashboard")
    )
