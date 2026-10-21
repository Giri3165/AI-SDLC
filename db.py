import mysql.connector
from flask import g, current_app


def get_db():
    """
    Returns a per-request MySQL connection stored on flask.g.
    Reused across the whole request, closed automatically after.
    """
    if "db" not in g:
        g.db = mysql.connector.connect(
            host=current_app.config["DB_HOST"],
            user=current_app.config["DB_USER"],
            password=current_app.config["DB_PASSWORD"],
            database=current_app.config["DB_NAME"],
        )
    return g.db


def get_cursor(dictionary=True):
    """
    Returns a cursor for the current request's connection.
    dictionary=True (default) means rows come back as
    {'id': 1, 'project_name': '...'} instead of tuples,
    so templates/routes never depend on column position.
    """
    return get_db().cursor(dictionary=dictionary)


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_app(app):
    app.teardown_appcontext(close_db)
