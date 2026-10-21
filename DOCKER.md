# Running with Docker Compose

This replaces manually installing MySQL/XAMPP and running `python app.py`
by hand. One command starts both the app and a matching database, with
the full schema (including `password_resets`) loaded automatically the
first time.

## Prerequisites

- Docker Desktop installed and running.
- A `.env` file in this folder (copy `.env.example` to `.env` if you
  haven't already, and fill in `DB_PASSWORD`, `SECRET_KEY`, and
  optionally `SMTP_*` / `ANTHROPIC_API_KEY`).

`DB_HOST` in your `.env` doesn't matter for Docker — `docker-compose.yml`
overrides it to `db` automatically, since that's the database's service
name on the Docker network, not `localhost`.

## First run

```
docker compose up --build
```

This will:
1. Build the app image from `Dockerfile`.
2. Start a MySQL 8 container and automatically run `schema.sql` against
   it (only happens once, on a fresh volume).
3. Wait for MySQL to actually be ready (healthcheck) before starting
   the Flask app — this is what fixes the classic "connection refused"
   race condition you'd otherwise hit if the app started before the
   database was ready to accept connections.
4. Start the Flask app on port 5000.

Open **http://127.0.0.1:5000** once it's up.

## Seeding demo data

With the containers running, in a second terminal:

```
docker compose exec app python seed_data.py
```

## Everyday use after the first run

```
docker compose up
```

(no `--build` needed unless you changed `requirements.txt` or the `Dockerfile`)

To stop:

```
docker compose down
```

Your database persists in a Docker volume between runs — `docker compose down`
does **not** delete your data. To wipe the database completely and start over:

```
docker compose down -v
```

## Viewing logs

```
docker compose logs -f app
```

This is where you'll see the same `mail.py` / error logs you'd normally
see in your terminal when running `python app.py` directly — useful for
debugging things like the SMTP email issue the same way as before.
