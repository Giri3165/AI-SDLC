from flask import Blueprint, render_template, request, redirect, url_for, flash, session, abort
from db import get_cursor, get_db
from auth_utils import login_required, role_required

developer_bp = Blueprint("developer", __name__, url_prefix="/developer")
PAGE_SIZE = 20

VALID_TASK_STATUSES = ["Pending", "Assigned", "In Progress", "Testing", "Completed"]
VALID_BUG_STATUSES = ["Open", "In Progress", "Resolved", "Closed", "Reopened"]
VALID_SEVERITIES = ["Low", "Medium", "High", "Critical"]


@developer_bp.route("/dashboard")
@login_required
@role_required("Developer")
def dashboard():
    user_id = session["user_id"]
    cursor = get_cursor()

    cursor.execute("SELECT COUNT(*) AS c FROM tasks WHERE assigned_to = %s", (user_id,))
    total_tasks = cursor.fetchone()["c"]

    cursor.execute(
        "SELECT COUNT(*) AS c FROM tasks WHERE assigned_to = %s AND status IN ('Pending','Assigned')",
        (user_id,)
    )
    pending_tasks = cursor.fetchone()["c"]

    cursor.execute(
        "SELECT COUNT(*) AS c FROM tasks WHERE assigned_to = %s AND status = 'In Progress'",
        (user_id,)
    )
    in_progress_tasks = cursor.fetchone()["c"]

    cursor.execute(
        "SELECT COUNT(*) AS c FROM tasks WHERE assigned_to = %s AND status = 'Completed'",
        (user_id,)
    )
    completed_tasks = cursor.fetchone()["c"]

    cursor.execute(
        "SELECT COUNT(*) AS c FROM bugs WHERE assigned_to = %s AND status NOT IN ('Resolved','Closed')",
        (user_id,)
    )
    open_bugs = cursor.fetchone()["c"]

    cursor.execute(
        """
        SELECT t.id, t.title, t.status, t.progress, t.due_date, p.project_name
        FROM tasks t
        JOIN projects p ON t.project_id = p.id
        WHERE t.assigned_to = %s
        ORDER BY t.id DESC
        LIMIT 5
        """,
        (user_id,)
    )
    recent_tasks = cursor.fetchall()

    cursor.close()

    return render_template(
        "developer/dashboard.html",
        total_tasks=total_tasks,
        pending_tasks=pending_tasks,
        in_progress_tasks=in_progress_tasks,
        completed_tasks=completed_tasks,
        open_bugs=open_bugs,
        recent_tasks=recent_tasks
    )


@developer_bp.route("/tasks")
@login_required
@role_required("Developer")
def tasks():
    page = request.args.get("page", 1, type=int)
    if page < 1:
        page = 1
    offset = (page - 1) * PAGE_SIZE

    cursor = get_cursor()

    cursor.execute(
        "SELECT COUNT(*) AS c FROM tasks WHERE assigned_to = %s",
        (session["user_id"],)
    )
    total = cursor.fetchone()["c"]
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

    cursor.execute(
        """
        SELECT t.id, t.title, t.status, t.progress, t.priority, t.due_date, p.project_name
        FROM tasks t
        JOIN projects p ON t.project_id = p.id
        WHERE t.assigned_to = %s
        ORDER BY t.id DESC
        LIMIT %s OFFSET %s
        """,
        (session["user_id"], PAGE_SIZE, offset)
    )
    my_tasks = cursor.fetchall()
    cursor.close()

    return render_template(
        "developer/tasks.html",
        tasks=my_tasks,
        page=page,
        total_pages=total_pages,
        total=total
    )


@developer_bp.route("/tasks/<int:task_id>")
@login_required
@role_required("Developer")
def task_details(task_id):
    cursor = get_cursor()
    cursor.execute(
        """
        SELECT t.*, p.project_name, r.title AS requirement_title
        FROM tasks t
        JOIN projects p ON t.project_id = p.id
        JOIN requirements r ON t.requirement_id = r.id
        WHERE t.id = %s
        """,
        (task_id,)
    )
    task = cursor.fetchone()

    if not task:
        cursor.close()
        abort(404)

    # Server-side ownership check — a developer cannot view/act on a
    # task assigned to someone else, even by guessing the URL.
    if task["assigned_to"] != session["user_id"]:
        cursor.close()
        abort(403)

    cursor.execute(
        "SELECT * FROM bugs WHERE task_id = %s ORDER BY id DESC",
        (task_id,)
    )
    bugs = cursor.fetchall()

    cursor.execute(
        "SELECT COALESCE(SUM(hours), 0) AS total_hours FROM time_logs WHERE task_id = %s",
        (task_id,)
    )
    total_hours = cursor.fetchone()["total_hours"]

    cursor.execute(
        "SELECT * FROM time_logs WHERE task_id = %s ORDER BY log_date DESC, id DESC",
        (task_id,)
    )
    time_logs = cursor.fetchall()

    cursor.close()

    return render_template(
        "developer/task_details.html",
        task=task,
        bugs=bugs,
        time_logs=time_logs,
        total_hours=total_hours,
        statuses=VALID_TASK_STATUSES
    )


@developer_bp.route("/tasks/<int:task_id>/update", methods=["POST"])
@login_required
@role_required("Developer")
def update_task(task_id):
    db = get_db()
    cursor = get_cursor()

    cursor.execute("SELECT id, assigned_to, project_id FROM tasks WHERE id = %s", (task_id,))
    task = cursor.fetchone()

    if not task:
        cursor.close()
        abort(404)

    if task["assigned_to"] != session["user_id"]:
        cursor.close()
        abort(403)

    status = request.form.get("status", "")
    progress_raw = request.form.get("progress", "0")

    if status not in VALID_TASK_STATUSES:
        cursor.close()
        flash("Invalid status.", "danger")
        return redirect(url_for("developer.task_details", task_id=task_id))

    try:
        progress = int(progress_raw)
    except ValueError:
        progress = 0
    progress = max(0, min(100, progress))

    cursor.execute(
        "UPDATE tasks SET status = %s, progress = %s WHERE id = %s",
        (status, progress, task_id)
    )

    # Development -> Testing: once every task on this project is
    # Completed, the project is ready for QA. This is the backend
    # controlling the transition automatically rather than leaving
    # it to be forgotten by a human.
    if status == "Completed":
        cursor.execute(
            "SELECT COUNT(*) AS c FROM tasks WHERE project_id = %s AND status != 'Completed'",
            (task["project_id"],)
        )
        remaining = cursor.fetchone()["c"]

        if remaining == 0:
            cursor.execute(
                "UPDATE projects SET status = 'Testing' WHERE id = %s AND status = 'Development'",
                (task["project_id"],)
            )

    db.commit()
    cursor.close()

    flash("Task updated.", "success")
    return redirect(url_for("developer.task_details", task_id=task_id))


@developer_bp.route("/tasks/<int:task_id>/log_time", methods=["POST"])
@login_required
@role_required("Developer")
def log_time(task_id):
    db = get_db()
    cursor = get_cursor()

    cursor.execute("SELECT id, assigned_to FROM tasks WHERE id = %s", (task_id,))
    task = cursor.fetchone()

    if not task:
        cursor.close()
        abort(404)

    if task["assigned_to"] != session["user_id"]:
        cursor.close()
        abort(403)

    hours_raw = request.form.get("hours", "").strip()
    log_date = request.form.get("log_date") or None
    notes = request.form.get("notes", "").strip()

    try:
        hours = float(hours_raw)
        if hours <= 0 or hours > 24:
            raise ValueError
    except ValueError:
        cursor.close()
        flash("Please enter a valid number of hours (greater than 0, up to 24).", "danger")
        return redirect(url_for("developer.task_details", task_id=task_id))

    if not log_date:
        cursor.close()
        flash("Please choose a date for the logged time.", "danger")
        return redirect(url_for("developer.task_details", task_id=task_id))

    cursor.execute(
        """
        INSERT INTO time_logs (task_id, user_id, hours, log_date, notes)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (task_id, session["user_id"], hours, log_date, notes or None)
    )
    db.commit()
    cursor.close()

    flash("Time logged.", "success")
    return redirect(url_for("developer.task_details", task_id=task_id))


@developer_bp.route("/tasks/<int:task_id>/report_bug", methods=["GET", "POST"])
@login_required
@role_required("Developer")
def report_bug(task_id):
    cursor = get_cursor()
    cursor.execute(
        "SELECT id, assigned_to, project_id, title FROM tasks WHERE id = %s",
        (task_id,)
    )
    task = cursor.fetchone()

    if not task:
        cursor.close()
        abort(404)

    if task["assigned_to"] != session["user_id"]:
        cursor.close()
        abort(403)

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
                "developer/report_bug.html",
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
        return redirect(url_for("developer.task_details", task_id=task_id))

    cursor.close()
    return render_template("developer/report_bug.html", task=task, severities=VALID_SEVERITIES)


@developer_bp.route("/bugs")
@login_required
@role_required("Developer")
def bugs():
    user_id = session["user_id"]

    page = request.args.get("page", 1, type=int)
    if page < 1:
        page = 1
    offset = (page - 1) * PAGE_SIZE

    cursor = get_cursor()

    cursor.execute(
        "SELECT COUNT(*) AS c FROM bugs WHERE assigned_to = %s OR reported_by = %s",
        (user_id, user_id)
    )
    total = cursor.fetchone()["c"]
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

    cursor.execute(
        """
        SELECT b.*, p.project_name
        FROM bugs b
        JOIN projects p ON b.project_id = p.id
        WHERE b.assigned_to = %s OR b.reported_by = %s
        ORDER BY b.id DESC
        LIMIT %s OFFSET %s
        """,
        (user_id, user_id, PAGE_SIZE, offset)
    )
    my_bugs = cursor.fetchall()
    cursor.close()

    return render_template(
        "developer/bugs.html",
        bugs=my_bugs,
        user_id=user_id,
        statuses=VALID_BUG_STATUSES,
        page=page,
        total_pages=total_pages,
        total=total
    )


@developer_bp.route("/bugs/<int:bug_id>/update", methods=["POST"])
@login_required
@role_required("Developer")
def update_bug(bug_id):
    db = get_db()
    cursor = get_cursor()

    cursor.execute("SELECT id, assigned_to FROM bugs WHERE id = %s", (bug_id,))
    bug = cursor.fetchone()

    if not bug:
        cursor.close()
        abort(404)

    # Only the developer this bug is assigned to may change its status —
    # reporting a bug does not by itself grant update rights.
    if bug["assigned_to"] != session["user_id"]:
        cursor.close()
        abort(403)

    status = request.form.get("status", "")
    if status not in VALID_BUG_STATUSES:
        cursor.close()
        flash("Invalid status.", "danger")
        return redirect(url_for("developer.bugs"))

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

    flash("Bug updated.", "success")
    return redirect(url_for("developer.bugs"))
