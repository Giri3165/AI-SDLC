import secrets
import mysql.connector
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, abort, current_app
from werkzeug.security import generate_password_hash
from db import get_cursor, get_db
from auth_utils import login_required, role_required
from mail import send_email

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

VALID_ROLES = ["Client", "Project Manager", "Developer", "Tester", "Admin"]
PAGE_SIZE = 20


@admin_bp.route("/dashboard")
@login_required
@role_required("Admin")
def dashboard():
    cursor = get_cursor()

    cursor.execute("SELECT COUNT(*) AS c FROM users")
    total_users = cursor.fetchone()["c"]

    cursor.execute("SELECT COUNT(*) AS c FROM projects")
    total_projects = cursor.fetchone()["c"]

    cursor.execute("SELECT COUNT(*) AS c FROM requirements")
    total_requirements = cursor.fetchone()["c"]

    cursor.execute("SELECT COUNT(*) AS c FROM tasks")
    total_tasks = cursor.fetchone()["c"]

    cursor.execute("SELECT COUNT(*) AS c FROM bugs")
    total_bugs = cursor.fetchone()["c"]

    cursor.execute("SELECT COUNT(*) AS c FROM deployments")
    total_deployments = cursor.fetchone()["c"]

    cursor.execute("SELECT role, COUNT(*) AS c FROM users GROUP BY role ORDER BY role")
    role_breakdown = cursor.fetchall()

    cursor.execute("SELECT status, COUNT(*) AS c FROM projects GROUP BY status ORDER BY status")
    project_status_breakdown = cursor.fetchall()

    cursor.close()

    return render_template(
        "admin/dashboard.html",
        total_users=total_users,
        total_projects=total_projects,
        total_requirements=total_requirements,
        total_tasks=total_tasks,
        total_bugs=total_bugs,
        total_deployments=total_deployments,
        role_breakdown=role_breakdown,
        project_status_breakdown=project_status_breakdown
    )


@admin_bp.route("/users/create", methods=["GET", "POST"])
@login_required
@role_required("Admin")
def create_user():
    """
    Admin-provisioned account creation. Generates a random temporary
    password, stores only its hash (never the plaintext), emails the
    credentials to the new user, and sets must_change_password so they
    are forced into the profile/password-change flow on first login.

    If email sending fails (e.g. SMTP not configured), the temporary
    password is shown to the admin in a flash message instead, so the
    account isn't created with no way for anyone to know the password.
    """
    if request.method == "POST":
        fullname = request.form.get("fullname", "").strip()
        email = request.form.get("email", "").strip()
        username = request.form.get("username", "").strip()
        role = request.form.get("role", "")

        errors = []
        if not fullname or not email or not username:
            errors.append("Full name, email, and username are required.")
        if role not in VALID_ROLES:
            errors.append("Please choose a valid role.")

        if not errors:
            cursor = get_cursor()
            cursor.execute(
                "SELECT id FROM users WHERE username = %s OR email = %s",
                (username, email)
            )
            if cursor.fetchone():
                errors.append("Username or email is already registered.")
            cursor.close()

        if errors:
            return render_template(
                "admin/create_user.html",
                error=" ".join(errors),
                roles=VALID_ROLES,
                form_values=request.form
            )

        temporary_password = secrets.token_urlsafe(9)
        password_hash = generate_password_hash(temporary_password)

        db = get_db()
        cursor = get_cursor()
        cursor.execute(
            """
            INSERT INTO users
                (fullname, email, username, password_hash, role, must_change_password)
            VALUES (%s, %s, %s, %s, %s, TRUE)
            """,
            (fullname, email, username, password_hash, role)
        )
        db.commit()
        cursor.close()

        login_url = f"{current_app.config['APP_BASE_URL']}/login"

        html_body = render_template(
            "emails/account_created.html",
            fullname=fullname,
            username=username,
            role=role,
            temporary_password=temporary_password,
            login_url=login_url
        )
        text_body = (
            f"Welcome to AI-SDLC, {fullname}!\n\n"
            f"Username: {username}\n"
            f"Role: {role}\n"
            f"Temporary Password: {temporary_password}\n\n"
            f"Log in at: {login_url}\n\n"
            "For security, please log in and change your temporary password."
        )

        email_sent = send_email(
            email, "Your AI-SDLC Account", text_body, html_body=html_body
        )

        if email_sent:
            flash(f"Account created for {fullname}. Credentials emailed to {email}.", "success")
        else:
            flash(
                f"Account created for {fullname}, but the email could not be sent "
                f"(check SMTP config in .env). Temporary password: {temporary_password} "
                "— share this with them securely yourself.",
                "warning"
            )

        return redirect(url_for("admin.users"))

    return render_template("admin/create_user.html", roles=VALID_ROLES)


@admin_bp.route("/users")
@login_required
@role_required("Admin")
def users():
    page = request.args.get("page", 1, type=int)
    if page < 1:
        page = 1
    offset = (page - 1) * PAGE_SIZE

    cursor = get_cursor()

    cursor.execute("SELECT COUNT(*) AS c FROM users")
    total = cursor.fetchone()["c"]
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

    cursor.execute(
        """
        SELECT id, fullname, email, username, role, created_at
        FROM users
        ORDER BY id DESC
        LIMIT %s OFFSET %s
        """,
        (PAGE_SIZE, offset)
    )
    all_users = cursor.fetchall()
    cursor.close()

    return render_template(
        "admin/users.html",
        users=all_users,
        page=page,
        total_pages=total_pages,
        total=total
    )


@admin_bp.route("/users/<int:user_id>/edit", methods=["GET", "POST"])
@login_required
@role_required("Admin")
def edit_user(user_id):
    cursor = get_cursor()
    cursor.execute(
        "SELECT id, fullname, email, username, role FROM users WHERE id = %s",
        (user_id,)
    )
    user = cursor.fetchone()

    if not user:
        cursor.close()
        abort(404)

    if request.method == "POST":
        fullname = request.form.get("fullname", "").strip()
        email = request.form.get("email", "").strip()
        role = request.form.get("role", "")

        errors = []
        if not fullname or not email:
            errors.append("Full name and email are required.")
        if role not in VALID_ROLES:
            errors.append("Invalid role.")
        if user_id == session["user_id"] and user["role"] == "Admin" and role != "Admin":
            errors.append("You cannot remove your own Admin role while logged in.")

        if errors:
            cursor.close()
            return render_template(
                "admin/edit_user.html",
                user=user,
                error=" ".join(errors),
                roles=VALID_ROLES
            )

        db = get_db()
        try:
            cursor.execute(
                "UPDATE users SET fullname = %s, email = %s, role = %s WHERE id = %s",
                (fullname, email, role, user_id)
            )
            db.commit()
            flash("User updated.", "success")
        except mysql.connector.IntegrityError:
            db.rollback()
            flash("That email is already used by another account.", "danger")

        cursor.close()
        return redirect(url_for("admin.users"))

    cursor.close()
    return render_template("admin/edit_user.html", user=user, roles=VALID_ROLES)


@admin_bp.route("/users/<int:user_id>/delete", methods=["POST"])
@login_required
@role_required("Admin")
def delete_user(user_id):
    if user_id == session["user_id"]:
        flash("You cannot delete your own account while logged in.", "warning")
        return redirect(url_for("admin.users"))

    db = get_db()
    cursor = get_cursor()

    cursor.execute("SELECT id FROM users WHERE id = %s", (user_id,))
    if not cursor.fetchone():
        cursor.close()
        abort(404)

    try:
        # Deliberately NOT wrapped in a blanket "delete everything they
        # touched" cascade — a user who owns projects, wrote requirements,
        # or reported bugs should be reassigned or handled deliberately,
        # not silently erased along with their history. The FK RESTRICT
        # constraints on those columns enforce that; this just turns the
        # resulting database error into a readable message instead of a 500.
        cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
        db.commit()
        flash("User deleted.", "success")
    except mysql.connector.IntegrityError:
        db.rollback()
        flash(
            "Cannot delete this user — they still own projects, requirements, "
            "or bug reports. Reassign or remove those first.",
            "danger"
        )

    cursor.close()
    return redirect(url_for("admin.users"))
