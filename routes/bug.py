from flask import Blueprint, render_template, request, redirect, url_for, flash, session, abort
from db import get_cursor, get_db
from auth_utils import login_required, role_required

tester_bp = Blueprint("tester", __name__, url_prefix="/tester")
PAGE_SIZE = 20

VALID_BUG_STATUSES = ["Open", "In Progress", "Resolved", "Closed", "Reopened"]
VALID_SEVERITIES = ["Low", "Medium", "High", "Critical"]


@tester_bp.route("/dashboard")
@login_required
@role_required("Tester")
def dashboard():
    cursor = get_cursor()

    cursor.execute("SELECT COUNT(*) AS c FROM projects WHERE status = 'Testing'")
    testing_projects = cursor.fetchone()["c"]

    cursor.execute("SELECT COUNT(*) AS c FROM bugs WHERE status NOT IN ('Resolved','Closed')")
    open_bugs = cursor.fetchone()["c"]

    cursor.execute("SELECT COUNT(*) AS c FROM bugs WHERE assigned_to IS NULL")
    unassigned_bugs = cursor.fetchone()["c"]

    cursor.execute(
        """
        SELECT id, project_name, progress
        FROM projects
        WHERE status = 'Testing'
        ORDER BY id DESC
        """
    )
    testing_list = cursor.fetchall()

    cursor.close()

    return render_template(
        "tester/dashboard.html",
        testing_projects=testing_projects,
        open_bugs=open_bugs,
        unassigned_bugs=unassigned_bugs,
        testing_list=testing_list
    )


@tester_bp.route("/projects/<int:project_id>/tasks")
@login_required
@role_required("Tester")
def project_tasks(project_id):
    cursor = get_cursor()

    cursor.execute("SELECT id, project_name, status FROM projects WHERE id = %s", (project_id,))
    project = cursor.fetchone()

    if not project:
        cursor.close()
        abort(404)

    cursor.execute(
        """
        SELECT t.*, u.fullname AS assignee_name
        FROM tasks t
        LEFT JOIN users u ON t.assigned_to = u.id
        WHERE t.project_id = %s AND t.status = 'Completed'
        ORDER BY t.id DESC
        """,
        (project_id,)
    )
    completed_tasks = cursor.fetchall()

    cursor.execute(
        "SELECT COUNT(*) AS c FROM bugs WHERE project_id = %s AND status NOT IN ('Resolved','Closed')",
        (project_id,)
    )
    open_bug_count = cursor.fetchone()["c"]

    cursor.close()

    return render_template(
        "tester/project_tasks.html",
        project=project,
        tasks=completed_tasks,
        open_bug_count=open_bug_count
    )


@tester_bp.route("/tasks/<int:task_id>/report_bug", methods=["GET", "POST"])
@login_required
@role_required("Tester")
def report_bug(task_id):
    cursor = get_cursor()
    cursor.execute(
        "SELECT id, project_id, title FROM tasks WHERE id = %s",
        (task_id,)
    )
    task = cursor.fetchone()

    if not task:
        cursor.close()
        abort(404)

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        severity = request.form.get("severity", "Medium")

        errors = []
        if not title:
            errors.append("Bug title is required.")
        if severity not in VALID_SEVERITIES:
            errors.append("Invalid severity.")

        if errors:
            cursor.close()
            return render_template(
                "tester/report_bug.html",
                task=task,
                error=" ".join(errors),
                severities=VALID_SEVERITIES
            )

        db = get_db()
        cursor.execute(
            """
            INSERT INTO bugs (project_id, task_id, title, description, severity, status, reported_by)
            VALUES (%s, %s, %s, %s, %s, 'Open', %s)
            """,
            (task["project_id"], task_id, title, description, severity, session["user_id"])
        )
        db.commit()
        cursor.close()

        flash("Bug reported.", "success")
        return redirect(url_for("tester.project_tasks", project_id=task["project_id"]))

    cursor.close()
    return render_template("tester/report_bug.html", task=task, severities=VALID_SEVERITIES)


@tester_bp.route("/bugs")
@login_required
@role_required("Tester")
def bugs():
    page = request.args.get("page", 1, type=int)
    if page < 1:
        page = 1
    offset = (page - 1) * PAGE_SIZE

    cursor = get_cursor()

    cursor.execute("SELECT COUNT(*) AS c FROM bugs")
    total = cursor.fetchone()["c"]
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

    cursor.execute(
        """
        SELECT b.*, p.project_name, u.fullname AS assignee_name
        FROM bugs b
        JOIN projects p ON b.project_id = p.id
        LEFT JOIN users u ON b.assigned_to = u.id
        ORDER BY b.id DESC
        LIMIT %s OFFSET %s
        """,
        (PAGE_SIZE, offset)
    )
    all_bugs = cursor.fetchall()

    cursor.execute("SELECT id, fullname FROM users WHERE role = 'Developer' ORDER BY fullname")
    developers = cursor.fetchall()

    cursor.close()

    return render_template(
        "tester/bugs.html",
        bugs=all_bugs,
        developers=developers,
        statuses=VALID_BUG_STATUSES,
        page=page,
        total_pages=total_pages,
        total=total
    )


@tester_bp.route("/bugs/<int:bug_id>/assign", methods=["POST"])
@login_required
@role_required("Tester")
def assign_bug(bug_id):
    db = get_db()
    cursor = get_cursor()

    cursor.execute("SELECT id FROM bugs WHERE id = %s", (bug_id,))
    if not cursor.fetchone():
        cursor.close()
        abort(404)

    developer_id = request.form.get("developer_id", "")

    cursor.execute("SELECT id FROM users WHERE id = %s AND role = 'Developer'", (developer_id,))
    if not cursor.fetchone():
        cursor.close()
        flash("Please choose a valid developer.", "danger")
        return redirect(url_for("tester.bugs"))

    cursor.execute(
        "UPDATE bugs SET assigned_to = %s, status = 'In Progress' WHERE id = %s",
        (developer_id, bug_id)
    )
    db.commit()
    cursor.close()

    flash("Bug assigned.", "success")
    return redirect(url_for("tester.bugs"))


@tester_bp.route("/bugs/<int:bug_id>/update_status", methods=["POST"])
@login_required
@role_required("Tester")
def update_bug_status(bug_id):
    db = get_db()
    cursor = get_cursor()

    cursor.execute("SELECT id FROM bugs WHERE id = %s", (bug_id,))
    if not cursor.fetchone():
        cursor.close()
        abort(404)

    status = request.form.get("status", "")
    if status not in VALID_BUG_STATUSES:
        cursor.close()
        flash("Invalid status.", "danger")
        return redirect(url_for("tester.bugs"))

    if status in ("Resolved", "Closed"):
        cursor.execute(
            "UPDATE bugs SET status = %s, resolved_at = NOW() WHERE id = %s",
            (status, bug_id)
        )
    else:
        cursor.execute(
            "UPDATE bugs SET status = %s, resolved_at = NULL WHERE id = %s",
            (status, bug_id)
        )

    db.commit()
    cursor.close()

    flash("Bug status updated.", "success")
    return redirect(url_for("tester.bugs"))


@tester_bp.route("/projects/<int:project_id>/advance", methods=["POST"])
@login_required
@role_required("Tester")
def advance_project(project_id):
    """
    Testing -> Deployment. Only allowed when no unresolved bugs remain
    on the project — enforced here, server-side, not just hidden in the UI.
    """
    db = get_db()
    cursor = get_cursor()

    cursor.execute("SELECT id, status FROM projects WHERE id = %s", (project_id,))
    project = cursor.fetchone()

    if not project:
        cursor.close()
        abort(404)

    if project["status"] != "Testing":
        cursor.close()
        flash("Only projects currently in Testing can be advanced.", "warning")
        return redirect(url_for("tester.dashboard"))

    cursor.execute(
        "SELECT COUNT(*) AS c FROM bugs WHERE project_id = %s AND status NOT IN ('Resolved','Closed')",
        (project_id,)
    )
    open_count = cursor.fetchone()["c"]

    if open_count > 0:
        cursor.close()
        flash(f"Cannot advance — {open_count} unresolved bug(s) remain.", "danger")
        return redirect(url_for("tester.project_tasks", project_id=project_id))

    cursor.execute("UPDATE projects SET status = 'Deployment' WHERE id = %s", (project_id,))
    db.commit()
    cursor.close()

    flash("Project marked ready for deployment.", "success")
    return redirect(url_for("tester.dashboard"))
