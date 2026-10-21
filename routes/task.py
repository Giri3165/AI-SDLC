from flask import Blueprint, render_template, request, redirect, url_for, flash, session, abort
from db import get_cursor, get_db
from auth_utils import login_required, role_required

task_bp = Blueprint("task", __name__, url_prefix="/manager/tasks")
PAGE_SIZE = 20

VALID_PRIORITIES = ["Low", "Medium", "High"]
ACTIVE_PROJECT_STATUSES = ["Approved", "Planning", "Development", "Testing", "Deployment"]


@task_bp.route("/")
@login_required
@role_required("Project Manager")
def tasks():
    page = request.args.get("page", 1, type=int)
    if page < 1:
        page = 1
    offset = (page - 1) * PAGE_SIZE

    cursor = get_cursor()

    cursor.execute("SELECT COUNT(*) AS c FROM tasks")
    total = cursor.fetchone()["c"]
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

    cursor.execute(
        """
        SELECT t.id, t.title, t.status, t.progress, t.priority, t.due_date,
               p.project_name, r.title AS requirement_title,
               u.fullname AS assignee_name
        FROM tasks t
        JOIN projects p ON t.project_id = p.id
        JOIN requirements r ON t.requirement_id = r.id
        LEFT JOIN users u ON t.assigned_to = u.id
        ORDER BY t.id DESC
        LIMIT %s OFFSET %s
        """,
        (PAGE_SIZE, offset)
    )
    all_tasks = cursor.fetchall()
    cursor.close()

    return render_template(
        "manager/tasks.html",
        tasks=all_tasks,
        page=page,
        total_pages=total_pages,
        total=total
    )


@task_bp.route("/new", methods=["GET", "POST"])
@login_required
@role_required("Project Manager")
def new_task():
    cursor = get_cursor()

    cursor.execute(
        """
        SELECT r.id, r.title, p.project_name, p.id AS project_id
        FROM requirements r
        JOIN projects p ON r.project_id = p.id
        WHERE r.status = 'Approved'
        AND p.status IN ('Approved','Planning','Development','Testing','Deployment')
        ORDER BY p.project_name, r.title
        """
    )
    eligible_requirements = cursor.fetchall()

    cursor.execute(
        "SELECT id, fullname FROM users WHERE role = 'Developer' ORDER BY fullname"
    )
    developers = cursor.fetchall()

    if request.method == "POST":
        requirement_id = request.form.get("requirement_id", "")
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        assigned_to = request.form.get("assigned_to", "")
        priority = request.form.get("priority", "Medium")
        due_date = request.form.get("due_date") or None

        errors = []

        cursor.execute(
            """
            SELECT r.id, r.project_id, p.status AS project_status
            FROM requirements r
            JOIN projects p ON r.project_id = p.id
            WHERE r.id = %s
            """,
            (requirement_id,)
        )
        requirement = cursor.fetchone()

        if not requirement:
            errors.append("Please choose a valid requirement.")

        if not title:
            errors.append("Task title is required.")

        cursor.execute(
            "SELECT id FROM users WHERE id = %s AND role = 'Developer'",
            (assigned_to,)
        )
        if not cursor.fetchone():
            errors.append("Please assign a valid developer.")

        if priority not in VALID_PRIORITIES:
            errors.append("Invalid priority.")

        if errors:
            cursor.close()
            return render_template(
                "manager/new_task.html",
                error=" ".join(errors),
                requirements=eligible_requirements,
                developers=developers,
                priorities=VALID_PRIORITIES,
                form_values=request.form
            )

        db = get_db()
        cursor.execute(
            """
            INSERT INTO tasks
                (requirement_id, project_id, title, description,
                 assigned_to, priority, status, progress, due_date)
            VALUES (%s, %s, %s, %s, %s, %s, 'Assigned', 0, %s)
            """,
            (requirement_id, requirement["project_id"], title, description,
             assigned_to, priority, due_date)
        )

        # Planning -> Development: the first task moves a project
        # from "being scoped" into active build.
        if requirement["project_status"] in ("Approved", "Planning"):
            cursor.execute(
                "UPDATE projects SET status = 'Development' WHERE id = %s",
                (requirement["project_id"],)
            )

        db.commit()
        cursor.close()

        flash("Task created and assigned.", "success")
        return redirect(url_for("task.tasks"))

    cursor.close()

    prefill = None
    if request.args.get("title"):
        prefill = {
            "requirement_id": request.args.get("requirement_id", ""),
            "title": request.args.get("title", ""),
            "description": request.args.get("description", ""),
        }

    return render_template(
        "manager/new_task.html",
        requirements=eligible_requirements,
        developers=developers,
        priorities=VALID_PRIORITIES,
        form_values=prefill
    )
