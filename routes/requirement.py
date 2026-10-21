from flask import Blueprint, render_template, request, redirect, url_for, flash, session, abort
from db import get_cursor, get_db
from auth_utils import login_required, role_required
from ai_helper import suggest_tasks_for_requirement

requirement_bp = Blueprint("requirement", __name__, url_prefix="/manager/requirements")
PAGE_SIZE = 20

VALID_PRIORITIES = ["Low", "Medium", "High"]

# A requirement can only be added to a project that's been approved and
# hasn't already finished/died — not Pending (not reviewed yet) and not
# Rejected/Completed.
ACTIVE_PROJECT_STATUSES = ["Approved", "Planning", "Development", "Testing", "Deployment"]


@requirement_bp.route("/")
@login_required
@role_required("Project Manager")
def requirements():
    page = request.args.get("page", 1, type=int)
    if page < 1:
        page = 1
    offset = (page - 1) * PAGE_SIZE

    cursor = get_cursor()

    cursor.execute("SELECT COUNT(*) AS c FROM requirements")
    total = cursor.fetchone()["c"]
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

    cursor.execute(
        """
        SELECT r.id, r.title, r.priority, r.status, r.created_at,
               p.project_name, p.id AS project_id
        FROM requirements r
        JOIN projects p ON r.project_id = p.id
        ORDER BY r.id DESC
        LIMIT %s OFFSET %s
        """,
        (PAGE_SIZE, offset)
    )
    all_requirements = cursor.fetchall()
    cursor.close()

    return render_template(
        "manager/requirements.html",
        requirements=all_requirements,
        page=page,
        total_pages=total_pages,
        total=total
    )


@requirement_bp.route("/new", methods=["GET", "POST"])
@login_required
@role_required("Project Manager")
def new_requirement():
    cursor = get_cursor()
    cursor.execute(
        """
        SELECT id, project_name, status FROM projects
        WHERE status IN ('Approved','Planning','Development','Testing','Deployment')
        ORDER BY project_name
        """
    )
    eligible_projects = cursor.fetchall()

    if request.method == "POST":
        project_id = request.form.get("project_id", "")
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        priority = request.form.get("priority", "Medium")

        errors = []

        cursor.execute("SELECT id, status FROM projects WHERE id = %s", (project_id,))
        project = cursor.fetchone()

        if not project:
            errors.append("Please choose a valid project.")
        elif project["status"] not in ACTIVE_PROJECT_STATUSES:
            errors.append("Requirements can only be added to approved/active projects.")

        if not title:
            errors.append("Title is required.")
        if priority not in VALID_PRIORITIES:
            errors.append("Invalid priority.")

        if errors:
            cursor.close()
            return render_template(
                "manager/new_requirement.html",
                error=" ".join(errors),
                projects=eligible_projects,
                priorities=VALID_PRIORITIES,
                form_values=request.form
            )

        db = get_db()
        cursor.execute(
            """
            INSERT INTO requirements (project_id, title, description, priority, status, created_by)
            VALUES (%s, %s, %s, %s, 'Approved', %s)
            """,
            (project_id, title, description, priority, session["user_id"])
        )

        # Approved -> Planning: the first requirement moves a project
        # from "waiting to start" into active planning.
        if project["status"] == "Approved":
            cursor.execute("UPDATE projects SET status = 'Planning' WHERE id = %s", (project_id,))

        db.commit()
        cursor.close()

        flash("Requirement added.", "success")
        return redirect(url_for("requirement.requirements"))

    cursor.close()
    return render_template(
        "manager/new_requirement.html",
        projects=eligible_projects,
        priorities=VALID_PRIORITIES
    )


@requirement_bp.route("/<int:requirement_id>/reject", methods=["POST"])
@login_required
@role_required("Project Manager")
def reject_requirement(requirement_id):
    db = get_db()
    cursor = get_cursor()

    cursor.execute("SELECT id FROM requirements WHERE id = %s", (requirement_id,))
    if not cursor.fetchone():
        cursor.close()
        abort(404)

    cursor.execute("UPDATE requirements SET status = 'Rejected' WHERE id = %s", (requirement_id,))
    db.commit()
    cursor.close()

    flash("Requirement rejected.", "info")
    return redirect(url_for("requirement.requirements"))


@requirement_bp.route("/<int:requirement_id>/suggest_tasks")
@login_required
@role_required("Project Manager")
def suggest_tasks(requirement_id):
    """
    Asks Claude to break this requirement into candidate tasks and shows
    them for review. Nothing is created here — each suggestion links to
    the normal "Create Task" form, prefilled, so the manager still picks
    a real developer and priority before anything is written to the DB.
    """
    cursor = get_cursor()
    cursor.execute(
        """
        SELECT r.id, r.title, r.description, p.project_name
        FROM requirements r
        JOIN projects p ON r.project_id = p.id
        WHERE r.id = %s
        """,
        (requirement_id,)
    )
    requirement = cursor.fetchone()
    cursor.close()

    if not requirement:
        abort(404)

    suggestions = suggest_tasks_for_requirement(
        requirement["title"], requirement["description"]
    )

    if suggestions is None:
        flash(
            "AI task suggestions aren't available right now — check "
            "ANTHROPIC_API_KEY in your .env, or just create tasks manually.",
            "warning"
        )
        return redirect(url_for("requirement.requirements"))

    return render_template(
        "manager/suggest_tasks.html",
        requirement=requirement,
        suggestions=suggestions
    )
