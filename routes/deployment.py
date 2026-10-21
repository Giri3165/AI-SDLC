from flask import Blueprint, render_template, request, redirect, url_for, flash, session, abort
from db import get_cursor, get_db
from auth_utils import login_required, role_required
from ai_helper import generate_release_notes

deployment_bp = Blueprint("deployment", __name__, url_prefix="/manager/deployments")
PAGE_SIZE = 20

VALID_ENVIRONMENTS = ["Production", "Staging", "QA"]
VALID_STATUSES = ["Pending", "Deployed", "Failed", "Rolled Back"]


@deployment_bp.route("/")
@login_required
@role_required("Project Manager")
def deployments():
    page = request.args.get("page", 1, type=int)
    if page < 1:
        page = 1
    offset = (page - 1) * PAGE_SIZE

    cursor = get_cursor()

    cursor.execute("SELECT COUNT(*) AS c FROM deployments")
    total = cursor.fetchone()["c"]
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

    cursor.execute(
        """
        SELECT d.*, p.project_name
        FROM deployments d
        JOIN projects p ON d.project_id = p.id
        ORDER BY d.deployment_date DESC, d.id DESC
        LIMIT %s OFFSET %s
        """,
        (PAGE_SIZE, offset)
    )
    all_deployments = cursor.fetchall()
    cursor.close()

    return render_template(
        "manager/deployments.html",
        deployments=all_deployments,
        page=page,
        total_pages=total_pages,
        total=total
    )


@deployment_bp.route("/new", methods=["GET", "POST"])
@login_required
@role_required("Project Manager")
def new_deployment():
    cursor = get_cursor()
    cursor.execute(
        "SELECT id, project_name FROM projects WHERE status = 'Deployment' ORDER BY project_name"
    )
    eligible_projects = cursor.fetchall()

    if request.method == "POST":
        project_id = request.form.get("project_id", "")
        version = request.form.get("version", "").strip()
        environment = request.form.get("environment", "Production")
        deployment_date = request.form.get("deployment_date") or None
        status = request.form.get("status", "Pending")
        notes = request.form.get("notes", "").strip()

        errors = []

        cursor.execute("SELECT id, project_name, status FROM projects WHERE id = %s", (project_id,))
        project = cursor.fetchone()

        if not project:
            errors.append("Please choose a valid project.")
        elif project["status"] != "Deployment":
            errors.append("This project is not ready for deployment.")

        if not version:
            errors.append("Version is required.")
        if not deployment_date:
            errors.append("Deployment date is required.")
        if environment not in VALID_ENVIRONMENTS:
            errors.append("Invalid environment.")
        if status not in VALID_STATUSES:
            errors.append("Invalid status.")

        if errors:
            cursor.close()
            return render_template(
                "manager/new_deployment.html",
                error=" ".join(errors),
                projects=eligible_projects,
                environments=VALID_ENVIRONMENTS,
                statuses=VALID_STATUSES,
                form_values=request.form
            )

        db = get_db()

        ai_generated = False
        if status == "Deployed" and not notes:
            cursor.execute(
                "SELECT title, description FROM tasks WHERE project_id = %s AND status = 'Completed'",
                (project_id,)
            )
            completed_tasks = cursor.fetchall()
            ai_notes = generate_release_notes(project["project_name"], completed_tasks)
            if ai_notes:
                notes = ai_notes
                ai_generated = True

        cursor.execute(
            """
            INSERT INTO deployments
                (project_id, version, environment, deployment_date, status, notes, deployed_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (project_id, version, environment, deployment_date, status, notes, session["user_id"])
        )

        # A successfully Deployed record completes the project.
        # Failed / Rolled Back / Pending leave it in Deployment status
        # so another attempt can be recorded without losing history.
        if status == "Deployed":
            cursor.execute(
                "UPDATE projects SET status = 'Completed', progress = 100 WHERE id = %s",
                (project_id,)
            )

        db.commit()
        cursor.close()

        if ai_generated:
            flash("Deployment recorded. Since you left notes blank, AI wrote a client-friendly summary from the completed tasks — check the deployment history to see it.", "success")
        else:
            flash("Deployment recorded.", "success")
        return redirect(url_for("deployment.deployments"))

    cursor.close()
    return render_template(
        "manager/new_deployment.html",
        projects=eligible_projects,
        environments=VALID_ENVIRONMENTS,
        statuses=VALID_STATUSES
    )
