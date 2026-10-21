"""
Seed script — creates demo accounts and sample projects covering every
stage of the workflow (Pending, Development, Testing, Deployment, Completed)
so you can explore every dashboard without manually walking the whole
Client -> Manager -> Developer -> Tester -> Deployment loop yourself.

Safe to re-run: existing users (matched by username) are skipped rather
than duplicated. Projects are NOT deduplicated, so re-running will add
another batch of demo projects — delete them via the Manager UI if you
run this more than once and don't want duplicates.

Usage:
    python seed_data.py
"""

import os
from datetime import date, timedelta

import mysql.connector
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash

load_dotenv()

conn = mysql.connector.connect(
    host=os.environ.get("DB_HOST", "localhost"),
    user=os.environ.get("DB_USER", "root"),
    password=os.environ.get("DB_PASSWORD", ""),
    database=os.environ.get("DB_NAME", "ai_sdlc"),
)
cursor = conn.cursor()

DEMO_PASSWORD = "Password123"


def create_user(fullname, email, username, role):
    cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
    existing = cursor.fetchone()
    if existing:
        print(f"  - {username} already exists, skipping")
        return existing[0]

    cursor.execute(
        """
        INSERT INTO users (fullname, email, username, password_hash, role)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (fullname, email, username, generate_password_hash(DEMO_PASSWORD), role)
    )
    conn.commit()
    print(f"  + created {username} ({role})")
    return cursor.lastrowid


def create_project(name, description, category, priority, status, progress,
                    manager_id=None, start_offset=0, end_offset=30):
    cursor.execute(
        """
        INSERT INTO projects
            (project_name, description, category, priority, status, progress,
             client_id, manager_id, start_date, end_date)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (name, description, category, priority, status, progress,
         client_id, manager_id,
         date.today() - timedelta(days=start_offset),
         date.today() + timedelta(days=end_offset))
    )
    conn.commit()
    return cursor.lastrowid


def create_requirement(project_id, title, description, priority="Medium"):
    cursor.execute(
        """
        INSERT INTO requirements (project_id, title, description, priority, status, created_by)
        VALUES (%s, %s, %s, %s, 'Approved', %s)
        """,
        (project_id, title, description, priority, pm_id)
    )
    conn.commit()
    return cursor.lastrowid


def create_task(requirement_id, project_id, title, description,
                 assigned_to, priority, status, progress, due_offset=14):
    cursor.execute(
        """
        INSERT INTO tasks
            (requirement_id, project_id, title, description,
             assigned_to, priority, status, progress, due_date)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (requirement_id, project_id, title, description, assigned_to,
         priority, status, progress, date.today() + timedelta(days=due_offset))
    )
    conn.commit()
    return cursor.lastrowid


def create_bug(project_id, task_id, title, description, severity,
                status, reported_by, assigned_to=None):
    cursor.execute(
        """
        INSERT INTO bugs
            (project_id, task_id, title, description, severity, status, reported_by, assigned_to)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (project_id, task_id, title, description, severity, status, reported_by, assigned_to)
    )
    conn.commit()
    return cursor.lastrowid


print("Creating demo users (all use password: Password123)...")
admin_id = create_user("Ava Admin", "admin@demo.com", "admin", "Admin")
pm_id = create_user("Priya Manager", "pm@demo.com", "pm", "Project Manager")
dev1_id = create_user("Dev One", "dev1@demo.com", "dev1", "Developer")
dev2_id = create_user("Dev Two", "dev2@demo.com", "dev2", "Developer")
tester_id = create_user("Tara Tester", "tester@demo.com", "tester", "Tester")
client_id = create_user("Casey Client", "client@demo.com", "client", "Client")

print("\nCreating demo projects across every lifecycle stage...")

p_pending = create_project(
    "Inventory Tracker",
    "A simple inventory tracking web app for small warehouses.",
    "Web Application", "Medium", "Pending", 0
)
print("  + Inventory Tracker (Pending — try approving/rejecting as PM)")

p_dev = create_project(
    "Customer Portal",
    "Self-service portal for customers to manage their accounts.",
    "Web Application", "High", "Development", 35,
    manager_id=pm_id, start_offset=20
)
r1 = create_requirement(p_dev, "User authentication", "Allow customers to log in securely.")
create_task(r1, p_dev, "Build login form", "Frontend login form with validation.",
            dev1_id, "High", "In Progress", 60)
r2 = create_requirement(p_dev, "Account settings page", "Let customers update their profile.")
create_task(r2, p_dev, "Design settings UI", "Wireframe and build settings page.",
            dev2_id, "Medium", "Assigned", 10)
print("  + Customer Portal (Development — log in as dev1/dev2 to see tasks)")

p_testing = create_project(
    "Mobile Expense App",
    "Track and categorize business expenses on the go.",
    "Mobile Application", "Medium", "Testing", 70,
    manager_id=pm_id, start_offset=40
)
r3 = create_requirement(p_testing, "Expense entry form", "Capture amount, category, and receipt photo.")
t3 = create_task(r3, p_testing, "Build expense entry screen", "Mobile form for logging expenses.",
                  dev1_id, "High", "Completed", 100)
create_bug(p_testing, t3, "Receipt photo upload fails on Android",
           "Upload crashes on Android 12+.", "High", "Open", tester_id)
print("  + Mobile Expense App (Testing, with 1 open bug blocking deployment)")

p_deploy = create_project(
    "Internal HR System",
    "Employee records and leave management.",
    "Management System", "High", "Deployment", 90,
    manager_id=pm_id, start_offset=60
)
r4 = create_requirement(p_deploy, "Leave request workflow", "Employees submit leave requests for approval.")
t4 = create_task(r4, p_deploy, "Build leave request form", "Form plus approval routing.",
                  dev2_id, "High", "Completed", 100)
create_bug(p_deploy, t4, "Date picker allows past dates",
           "Should block requesting leave in the past.", "Low", "Resolved", tester_id, dev2_id)
print("  + Internal HR System (Deployment-ready — try recording a deployment as PM)")

p_done = create_project(
    "Marketing Website",
    "Public marketing site redesign.",
    "Web Application", "Low", "Completed", 100,
    manager_id=pm_id, start_offset=90
)
r5 = create_requirement(p_done, "Homepage redesign", "New hero section and layout.")
create_task(r5, p_done, "Implement new homepage", "Responsive homepage build.",
            dev1_id, "Medium", "Completed", 100)
cursor.execute(
    """
    INSERT INTO deployments
        (project_id, version, environment, deployment_date, status, notes, deployed_by)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    """,
    (p_done, "v1.0.0", "Production", date.today() - timedelta(days=5),
     "Deployed", "Initial launch.", pm_id)
)
conn.commit()
print("  + Marketing Website (Completed, with deployment history)")

cursor.close()
conn.close()

print("\nDone. Log in with any of these (password: Password123):")
print("  admin    - Admin")
print("  pm       - Project Manager")
print("  dev1     - Developer")
print("  dev2     - Developer")
print("  tester   - Tester")
print("  client   - Client")
