from datetime import datetime

TERMINAL_STATUSES = ("Completed", "Rejected")

STALE_DAYS = 14


def compute_health_map(cursor, projects):
    """
    Given a cursor and a list of project dicts (each needs at least
    "id" and "status"), returns {project_id: {"level", "reason"}}.

    Uses a small, fixed number of aggregate queries across ALL the given
    projects at once — never one query per project — so this stays cheap
    even on a page listing 20+ projects.

    Completed/Rejected projects always get level "neutral": health
    monitoring stops being meaningful once a project is finished or dead.
    """
    active_ids = [p["id"] for p in projects if p["status"] not in TERMINAL_STATUSES]

    result = {}
    for p in projects:
        if p["status"] in TERMINAL_STATUSES:
            result[p["id"]] = {"level": "neutral", "reason": p["status"]}

    if not active_ids:
        return result

    placeholders = ",".join(["%s"] * len(active_ids))

    cursor.execute(
        f"""
        SELECT project_id, COUNT(*) AS c
        FROM tasks
        WHERE project_id IN ({placeholders})
        AND status != 'Completed'
        AND due_date IS NOT NULL
        AND due_date < CURDATE()
        GROUP BY project_id
        """,
        active_ids
    )
    overdue = {row["project_id"]: row["c"] for row in cursor.fetchall()}

    cursor.execute(
        f"""
        SELECT project_id, COUNT(*) AS c
        FROM bugs
        WHERE project_id IN ({placeholders})
        AND status NOT IN ('Resolved','Closed')
        AND severity IN ('High','Critical')
        GROUP BY project_id
        """,
        active_ids
    )
    critical_bugs = {row["project_id"]: row["c"] for row in cursor.fetchall()}

    cursor.execute(
        f"""
        SELECT project_id, COUNT(*) AS c
        FROM bugs
        WHERE project_id IN ({placeholders})
        AND status NOT IN ('Resolved','Closed')
        GROUP BY project_id
        """,
        active_ids
    )
    open_bugs = {row["project_id"]: row["c"] for row in cursor.fetchall()}

    cursor.execute(
        f"""
        SELECT project_id, MAX(updated_at) AS last_activity
        FROM tasks
        WHERE project_id IN ({placeholders})
        GROUP BY project_id
        """,
        active_ids
    )
    last_activity = {row["project_id"]: row["last_activity"] for row in cursor.fetchall()}

    now = datetime.utcnow()

    for pid in active_ids:
        od = overdue.get(pid, 0)
        cb = critical_bugs.get(pid, 0)
        ob = open_bugs.get(pid, 0)
        la = last_activity.get(pid)
        stale = (now - la).days > STALE_DAYS if la else False

        if od > 0 or cb > 0:
            level = "red"
            if od > 0 and cb > 0:
                reason = f"{od} overdue task(s) and {cb} critical/high-severity bug(s)"
            elif od > 0:
                reason = f"{od} overdue task(s)"
            else:
                reason = f"{cb} critical/high-severity bug(s) open"
        elif ob > 0 or stale:
            level = "yellow"
            if ob > 0 and stale:
                reason = f"{ob} open bug(s), no activity in over {STALE_DAYS} days"
            elif ob > 0:
                reason = f"{ob} open bug(s)"
            else:
                reason = f"No activity in over {STALE_DAYS} days"
        else:
            level = "green"
            reason = "On track"

        result[pid] = {"level": level, "reason": reason}

    return result
