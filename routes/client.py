from flask import Blueprint, render_template, request, redirect, url_for, flash, session, abort
from db import get_cursor, get_db
from auth_utils import login_required, role_required
from health import compute_health_map

client_bp = Blueprint("client", __name__, url_prefix="/client")
PAGE_SIZE = 20

VALID_CATEGORIES = [
    "Web Application", "Desktop Application", "Mobile Application",
    "AI Application", "Management System", "E-Commerce", "Other"
]
VALID_PRIORITIES = ["Low", "Medium", "High"]


@client_bp.route("/dashboard")
@login_required
@role_required("Client")
def dashboard():
    user_id = session["user_id"]
    cursor = get_cursor()

    cursor.execute(
        "SELECT COUNT(*) AS c FROM projects WHERE client_id = %s",
        (user_id,)
    )
    total_projects = cursor.fetchone()["c"]

    cursor.execute(
        "SELECT COUNT(*) AS c FROM projects WHERE client_id = %s AND status = 'Pending'",
        (user_id,)
    )
    pending = cursor.fetchone()["c"]

    cursor.execute(
        """
        SELECT COUNT(*) AS c FROM projects
        WHERE client_id = %s
        AND status IN ('Approved','Planning','Development','Testing','Deployment')
        """,
        (user_id,)
    )
    active = cursor.fetchone()["c"]

    cursor.execute(
        "SELECT COUNT(*) AS c FROM projects WHERE client_id = %s AND status = 'Completed'",
        (user_id,)
    )
    completed = cursor.fetchone()["c"]

    cursor.execute(
        """
        SELECT id, project_name, status, progress
        FROM projects
        WHERE client_id = %s
        ORDER BY id DESC
        LIMIT 5
        """,
        (user_id,)
    )
    recent_projects = cursor.fetchall()

    health_map = compute_health_map(cursor, recent_projects)

    cursor.close()

    return render_template(
        "client/dashboard.html",
        total_projects=total_projects,
        pending=pending,
        active=active,
        completed=completed,
        recent_projects=recent_projects,
        health_map=health_map
    )


@client_bp.route("/projects")
@login_required
@role_required("Client")
def my_projects():
    page = request.args.get("page", 1, type=int)
    if page < 1:
        page = 1
    offset = (page - 1) * PAGE_SIZE

    cursor = get_cursor()

    cursor.execute(
        "SELECT COUNT(*) AS c FROM projects WHERE client_id = %s",
        (session["user_id"],)
    )
    total = cursor.fetchone()["c"]
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

    cursor.execute(
        """
        SELECT id, project_name, category, priority, status, progress, end_date
        FROM projects
        WHERE client_id = %s
        ORDER BY id DESC
        LIMIT %s OFFSET %s
        """,
        (session["user_id"], PAGE_SIZE, offset)
    )
    projects = cursor.fetchall()

    health_map = compute_health_map(cursor, projects)

    cursor.close()

    return render_template(
        "client/my_projects.html",
        projects=projects,
        health_map=health_map,
        page=page,
        total_pages=total_pages,
        total=total
    )


@client_bp.route("/projects/new", methods=["GET", "POST"])
@login_required
@role_required("Client")
def new_project():
    if request.method == "POST":
        project_name = request.form.get("project_name", "").strip()
        description = request.form.get("description", "").strip()
        category = request.form.get("category", "").strip()
        priority = request.form.get("priority", "Medium")
        start_date = request.form.get("start_date") or None
        end_date = request.form.get("end_date") or None

        errors = []

        if not project_name:
            errors.append("Project name is required.")
        if not description:
            errors.append("Description is required.")
        if category not in VALID_CATEGORIES:
            errors.append("Please choose a valid category.")
        if priority not in VALID_PRIORITIES:
            errors.append("Please choose a valid priority.")
        if not end_date:
            errors.append("Expected delivery date is required.")

        if errors:
            return render_template(
                "client/new_project.html",
                error=" ".join(errors),
                categories=VALID_CATEGORIES,
                form_values=request.form
            )

        db = get_db()
        cursor = get_cursor()
        cursor.execute(
            """
            INSERT INTO projects
                (project_name, description, category, priority,
                 status, progress, client_id, start_date, end_date)
            VALUES (%s, %s, %s, %s, 'Pending', 0, %s, %s, %s)
            """,
            (project_name, description, category, priority,
             session["user_id"], start_date, end_date)
        )
        db.commit()
        cursor.close()

        flash("Project submitted for review.", "success")
        return redirect(url_for("client.dashboard"))

    return render_template("client/new_project.html", categories=VALID_CATEGORIES)


@client_bp.route("/projects/<int:project_id>")
@login_required
@role_required("Client")
def project_details(project_id):
    cursor = get_cursor()

    cursor.execute(
        """
        SELECT p.*, m.fullname AS manager_name
        FROM projects p
        LEFT JOIN users m ON p.manager_id = m.id
        WHERE p.id = %s
        """,
        (project_id,)
    )
    project = cursor.fetchone()

    if not project:
        cursor.close()
        abort(404)

    # Normalize DECIMAL -> float (see same fix in manager.py's
    # project_details for why this matters: Decimal * float literal
    # raises TypeError in Jinja, even though comparisons don't).
    if project["hourly_rate"] is not None:
        project["hourly_rate"] = float(project["hourly_rate"])
    if project["budget_amount"] is not None:
        project["budget_amount"] = float(project["budget_amount"])

    # Server-side ownership check — a client cannot view another
    # client's project by guessing/editing the ID in the URL.
    if project["client_id"] != session["user_id"]:
        cursor.close()
        abort(403)

    health = compute_health_map(cursor, [project])[project["id"]]

    cursor.execute(
        "SELECT * FROM requirements WHERE project_id = %s ORDER BY id DESC",
        (project_id,)
    )
    requirements = cursor.fetchall()

    cursor.execute(
        """
        SELECT t.*, u.fullname AS assignee_name
        FROM tasks t
        LEFT JOIN users u ON t.assigned_to = u.id
        WHERE t.project_id = %s
        ORDER BY t.id DESC
        """,
        (project_id,)
    )
    tasks = cursor.fetchall()

    cursor.execute(
        "SELECT * FROM bugs WHERE project_id = %s ORDER BY id DESC",
        (project_id,)
    )
    bugs = cursor.fetchall()

    cursor.execute(
        "SELECT * FROM deployments WHERE project_id = %s ORDER BY deployment_date DESC",
        (project_id,)
    )
    deployments = cursor.fetchall()

    cursor.execute(
        """
        SELECT COALESCE(SUM(tl.hours), 0) AS total_hours
        FROM time_logs tl
        JOIN tasks t ON tl.task_id = t.id
        WHERE t.project_id = %s
        """,
        (project_id,)
    )
    total_hours = cursor.fetchone()["total_hours"]

    total_cost = None
    if project["hourly_rate"] is not None:
        total_cost = float(total_hours) * float(project["hourly_rate"])

    cursor.close()

    return render_template(
        "client/project_details.html",
        project=project,
        health=health,
        requirements=requirements,
        tasks=tasks,
        bugs=bugs,
        deployments=deployments,
        total_cost=total_cost,
        requirement_count=len(requirements),
        task_count=len(tasks),
        bug_count=len(bugs),
        deployment_count=len(deployments)
    )
