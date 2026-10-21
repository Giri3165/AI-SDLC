import json
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, abort
from db import get_cursor, get_db
from auth_utils import login_required, role_required
from health import compute_health_map

manager_bp = Blueprint("manager", __name__, url_prefix="/manager")
PAGE_SIZE = 20


def _snapshot(row):
    """Serializes a dict-cursor row (which may contain date objects) to JSON."""
    return json.dumps(row, default=str)


@manager_bp.route("/dashboard")
@login_required
@role_required("Project Manager")
def dashboard():
    cursor = get_cursor()

    cursor.execute("SELECT COUNT(*) AS c FROM projects")
    total_projects = cursor.fetchone()["c"]

    cursor.execute("SELECT COUNT(*) AS c FROM projects WHERE status='Pending'")
    pending_projects = cursor.fetchone()["c"]

    cursor.execute(
        """
        SELECT COUNT(*) AS c FROM projects
        WHERE status IN ('Approved','Planning','Development','Testing','Deployment')
        """
    )
    active_projects = cursor.fetchone()["c"]

    cursor.execute("SELECT COUNT(*) AS c FROM projects WHERE status='Completed'")
    completed_projects = cursor.fetchone()["c"]

    cursor.execute(
        """
        SELECT p.id, p.project_name, p.priority, p.status, p.progress,
               u.fullname AS client_name
        FROM projects p
        JOIN users u ON p.client_id = u.id
        ORDER BY p.id DESC
        LIMIT 5
        """
    )
    recent_projects = cursor.fetchall()

    health_map = compute_health_map(cursor, recent_projects)

    cursor.execute(
        """
        SELECT p.id, p.project_name, p.category, p.priority, p.end_date,
               u.fullname AS client_name
        FROM projects p
        JOIN users u ON p.client_id = u.id
        WHERE p.status = 'Pending'
        ORDER BY p.id ASC
        """
    )
    pending_list = cursor.fetchall()

    cursor.close()

    return render_template(
        "manager/dashboard.html",
        total_projects=total_projects,
        pending_projects=pending_projects,
        active_projects=active_projects,
        completed_projects=completed_projects,
        recent_projects=recent_projects,
        health_map=health_map,
        pending_list=pending_list
    )


@manager_bp.route("/projects")
@login_required
@role_required("Project Manager")
def projects():
    page = request.args.get("page", 1, type=int)
    if page < 1:
        page = 1
    offset = (page - 1) * PAGE_SIZE

    cursor = get_cursor()

    cursor.execute("SELECT COUNT(*) AS c FROM projects")
    total = cursor.fetchone()["c"]
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

    cursor.execute(
        """
        SELECT p.id, p.project_name, p.status, p.priority, p.progress,
               u.fullname AS client_name, m.fullname AS manager_name
        FROM projects p
        JOIN users u ON p.client_id = u.id
        LEFT JOIN users m ON p.manager_id = m.id
        ORDER BY p.id DESC
        LIMIT %s OFFSET %s
        """,
        (PAGE_SIZE, offset)
    )
    all_projects = cursor.fetchall()

    health_map = compute_health_map(cursor, all_projects)

    cursor.close()

    return render_template(
        "manager/projects.html",
        projects=all_projects,
        health_map=health_map,
        page=page,
        total_pages=total_pages,
        total=total
    )


@manager_bp.route("/projects/<int:project_id>")
@login_required
@role_required("Project Manager")
def project_details(project_id):
    cursor = get_cursor()

    cursor.execute(
        """
        SELECT p.*, u.fullname AS client_name, m.fullname AS manager_name
        FROM projects p
        JOIN users u ON p.client_id = u.id
        LEFT JOIN users m ON p.manager_id = m.id
        WHERE p.id = %s
        """,
        (project_id,)
    )
    project = cursor.fetchone()

    if not project:
        cursor.close()
        abort(404)

    # mysql-connector returns DECIMAL columns as Python Decimal objects,
    # which can't be mixed with float in arithmetic (Decimal * 0.9 raises
    # TypeError, even though Decimal > float comparisons work fine).
    # Normalizing to float here means the template never has to know or
    # care about this distinction.
    if project["hourly_rate"] is not None:
        project["hourly_rate"] = float(project["hourly_rate"])
    if project["budget_amount"] is not None:
        project["budget_amount"] = float(project["budget_amount"])

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
        "manager/project_details.html",
        project=project,
        health=health,
        requirements=requirements,
        tasks=tasks,
        bugs=bugs,
        deployments=deployments,
        total_hours=total_hours,
        total_cost=total_cost,
        requirement_count=len(requirements),
        task_count=len(tasks),
        bug_count=len(bugs),
        deployment_count=len(deployments)
    )


@manager_bp.route("/projects/<int:project_id>/set_budget", methods=["POST"])
@login_required
@role_required("Project Manager")
def set_budget(project_id):
    db = get_db()
    cursor = get_cursor()

    cursor.execute("SELECT id FROM projects WHERE id = %s", (project_id,))
    if not cursor.fetchone():
        cursor.close()
        abort(404)

    hourly_rate_raw = request.form.get("hourly_rate", "").strip()
    budget_amount_raw = request.form.get("budget_amount", "").strip()

    try:
        hourly_rate = float(hourly_rate_raw) if hourly_rate_raw else None
        budget_amount = float(budget_amount_raw) if budget_amount_raw else None
        if (hourly_rate is not None and hourly_rate < 0) or (budget_amount is not None and budget_amount < 0):
            raise ValueError
    except ValueError:
        cursor.close()
        flash("Please enter valid, non-negative numbers.", "danger")
        return redirect(url_for("manager.project_details", project_id=project_id))

    cursor.execute(
        "UPDATE projects SET hourly_rate = %s, budget_amount = %s WHERE id = %s",
        (hourly_rate, budget_amount, project_id)
    )
    db.commit()
    cursor.close()

    flash("Budget updated.", "success")
    return redirect(url_for("manager.project_details", project_id=project_id))


@manager_bp.route("/projects/<int:project_id>/approve", methods=["POST"])
@login_required
@role_required("Project Manager")
def approve_project(project_id):
    db = get_db()
    cursor = get_cursor()

    cursor.execute("SELECT id, status FROM projects WHERE id = %s", (project_id,))
    project = cursor.fetchone()

    if not project:
        cursor.close()
        abort(404)

    # Server-side status-transition guard — approving is only valid
    # from Pending, regardless of what the client sends.
    if project["status"] != "Pending":
        cursor.close()
        flash("Only pending projects can be approved.", "warning")
        return redirect(url_for("manager.dashboard"))

    cursor.execute(
        "UPDATE projects SET status='Approved', manager_id=%s WHERE id=%s",
        (session["user_id"], project_id)
    )
    db.commit()
    cursor.close()

    flash("Project approved. You are now assigned as its manager.", "success")
    return redirect(url_for("manager.dashboard"))


@manager_bp.route("/projects/<int:project_id>/reject", methods=["POST"])
@login_required
@role_required("Project Manager")
def reject_project(project_id):
    db = get_db()
    cursor = get_cursor()

    cursor.execute("SELECT id, status FROM projects WHERE id = %s", (project_id,))
    project = cursor.fetchone()

    if not project:
        cursor.close()
        abort(404)

    if project["status"] != "Pending":
        cursor.close()
        flash("Only pending projects can be rejected.", "warning")
        return redirect(url_for("manager.dashboard"))

    cursor.execute("UPDATE projects SET status='Rejected' WHERE id = %s", (project_id,))
    db.commit()
    cursor.close()

    flash("Project rejected.", "info")
    return redirect(url_for("manager.dashboard"))


@manager_bp.route("/projects/<int:project_id>/delete", methods=["POST"])
@login_required
@role_required("Project Manager")
def delete_project(project_id):
    db = get_db()
    cursor = get_cursor()

    cursor.execute("SELECT * FROM projects WHERE id = %s", (project_id,))
    project = cursor.fetchone()

    if not project:
        cursor.close()
        abort(404)

    reason = request.form.get("reason", "").strip() or None

    try:
        cursor.execute(
            """
            INSERT INTO deleted_projects (project_id, project_snapshot, deleted_by, reason)
            VALUES (%s, %s, %s, %s)
            """,
            (project_id, _snapshot(project), session["user_id"], reason)
        )

        # requirements/tasks/bugs/deployments all have
        # ON DELETE CASCADE back to projects.id in the schema,
        # so this single statement cleans up everything related.
        cursor.execute("DELETE FROM projects WHERE id = %s", (project_id,))

        db.commit()
        flash("Project deleted. A snapshot was saved to the deletion history.", "success")

    except Exception as e:
        db.rollback()
        flash(f"Delete failed — nothing was changed. ({e})", "danger")

    finally:
        cursor.close()

    return redirect(url_for("manager.projects"))


@manager_bp.route("/projects/deleted")
@login_required
@role_required("Project Manager")
def deleted_projects():
    cursor = get_cursor()
    cursor.execute(
        """
        SELECT dp.id, dp.project_id, dp.project_snapshot, dp.deleted_at, dp.reason,
               u.fullname AS deleted_by_name
        FROM deleted_projects dp
        JOIN users u ON dp.deleted_by = u.id
        ORDER BY dp.deleted_at DESC
        """
    )
    rows = cursor.fetchall()
    cursor.close()

    history = []
    for row in rows:
        snapshot = json.loads(row["project_snapshot"])
        history.append({
            "project_id": row["project_id"],
            "project_name": snapshot.get("project_name", "Unknown"),
            "client_id": snapshot.get("client_id"),
            "deleted_by_name": row["deleted_by_name"],
            "deleted_at": row["deleted_at"],
            "reason": row["reason"],
        })

    return render_template("manager/deleted_projects.html", history=history)
