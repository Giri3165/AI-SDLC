"""
Sends a weekly "here's what happened on your project" email to every
client who had real activity in the last 7 days (completed tasks,
resolved bugs, or deployments). Clients with zero activity get no
email at all — this deliberately never sends an empty/spammy digest.

Meant to be run on a schedule (cron / Windows Task Scheduler), not
manually every time — see the scheduling notes at the bottom of this
file, or WEEKLY_DIGEST.md.

Usage:
    python send_weekly_digest.py
"""

from datetime import datetime, timedelta

import mysql.connector
from flask import Flask, render_template

from config import Config
from mail import send_email

app = Flask(__name__)
app.config.from_object(Config)


def run():
    conn = mysql.connector.connect(
        host=app.config["DB_HOST"],
        user=app.config["DB_USER"],
        password=app.config["DB_PASSWORD"],
        database=app.config["DB_NAME"],
    )
    cursor = conn.cursor(dictionary=True)

    since = datetime.utcnow() - timedelta(days=7)
    since_date = since.date()

    cursor.execute("SELECT id, fullname, email FROM users WHERE role = 'Client'")
    clients = cursor.fetchall()

    sent_count = 0
    skipped_count = 0

    for client_user in clients:
        cursor.execute(
            "SELECT id, project_name FROM projects WHERE client_id = %s",
            (client_user["id"],)
        )
        client_projects = cursor.fetchall()

        digest_projects = []

        for project in client_projects:
            cursor.execute(
                """
                SELECT title FROM tasks
                WHERE project_id = %s AND status = 'Completed' AND updated_at >= %s
                """,
                (project["id"], since)
            )
            completed_tasks = [row["title"] for row in cursor.fetchall()]

            cursor.execute(
                """
                SELECT title FROM bugs
                WHERE project_id = %s AND status IN ('Resolved','Closed') AND resolved_at >= %s
                """,
                (project["id"], since)
            )
            resolved_bugs = [row["title"] for row in cursor.fetchall()]

            cursor.execute(
                """
                SELECT version, status FROM deployments
                WHERE project_id = %s AND deployment_date >= %s
                """,
                (project["id"], since_date)
            )
            deployments = cursor.fetchall()

            if completed_tasks or resolved_bugs or deployments:
                digest_projects.append({
                    "project_name": project["project_name"],
                    "completed_tasks": completed_tasks,
                    "resolved_bugs": resolved_bugs,
                    "deployments": deployments,
                })

        if not digest_projects:
            skipped_count += 1
            continue

        with app.app_context():
            login_url = f"{app.config['APP_BASE_URL']}/login"

            html_body = render_template(
                "emails/weekly_digest.html",
                client_name=client_user["fullname"],
                projects=digest_projects,
                login_url=login_url
            )

            text_lines = [f"Hi {client_user['fullname']},", "", "This week's activity:"]
            for p in digest_projects:
                text_lines.append(f"\n{p['project_name']}:")
                for t in p["completed_tasks"]:
                    text_lines.append(f"  - Completed: {t}")
                for b in p["resolved_bugs"]:
                    text_lines.append(f"  - Fixed: {b}")
                for d in p["deployments"]:
                    text_lines.append(f"  - Deployed version {d['version']} ({d['status']})")
            text_lines.append(f"\nView full details: {login_url}")
            text_body = "\n".join(text_lines)

            sent = send_email(
                client_user["email"],
                "Your Weekly Project Update",
                text_body,
                html_body=html_body
            )

            if sent:
                sent_count += 1
                print(f"  + sent digest to {client_user['email']}")
            else:
                print(f"  ! failed to send to {client_user['email']} (check SMTP config in .env)")

    cursor.close()
    conn.close()

    print(f"\nDone. Sent {sent_count} digest(s), skipped {skipped_count} client(s) with no activity.")


if __name__ == "__main__":
    run()

# ---------------------------------------------------------------------
# Scheduling this weekly (pick one):
#
# Linux/Mac cron - run every Monday at 8am:
#   crontab -e
#   0 8 * * 1 cd /path/to/ai-sdlc-new && /usr/bin/python3 send_weekly_digest.py
#
# Windows Task Scheduler:
#   Create a Basic Task -> Trigger: Weekly, Monday, 8:00 AM
#   Action: Start a program -> python.exe
#   Arguments: send_weekly_digest.py
#   Start in: (the full path to this project folder)
#
# Docker Compose users: run it inside the running app container instead:
#   docker compose exec app python send_weekly_digest.py
#   (schedule that command on the host machine with cron/Task Scheduler)
# ---------------------------------------------------------------------
