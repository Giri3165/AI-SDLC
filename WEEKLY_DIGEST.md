# Weekly Client Digest Emails

`send_weekly_digest.py` emails every client a summary of real activity
on their projects in the last 7 days: completed tasks, resolved bugs,
and deployments. Clients with zero activity that week get nothing —
this never sends an empty or spammy digest.

## Requirements

- SMTP must be configured in `.env` (same setup as password reset emails).
- Run it manually once to confirm it works before scheduling it.

## Manual run

```
python send_weekly_digest.py
```

Docker Compose users:

```
docker compose exec app python send_weekly_digest.py
```

## Scheduling it weekly

**Linux/Mac (cron)** — edit your crontab with `crontab -e` and add:
```
0 8 * * 1 cd /path/to/ai-sdlc-new && /usr/bin/python3 send_weekly_digest.py
```
This runs every Monday at 8am.

**Windows (Task Scheduler)**:
1. Open Task Scheduler → Create Basic Task
2. Trigger: Weekly, Monday, 8:00 AM
3. Action: Start a program → Program: `python.exe`, Arguments: `send_weekly_digest.py`, "Start in": the full path to this project folder

**Docker Compose**: the script needs to run *inside* the app container (so it has the same environment/dependencies), but the *schedule* itself lives on your host machine. Set up cron or Task Scheduler on the host to run:
```
docker compose exec app python send_weekly_digest.py
```

## Notes

- This is a standalone script, not a background thread inside the Flask app — Flask's dev server isn't meant to run scheduled jobs internally, and a proper task queue (Celery, RQ) would be overkill for a weekly email. A scheduled script is the right amount of infrastructure for this.
- If you ever move to a real production host, replace cron/Task Scheduler with your platform's scheduled-job feature (e.g. a scheduled GitHub Action, a cloud provider's cron trigger, etc.) — the script itself doesn't need to change.
