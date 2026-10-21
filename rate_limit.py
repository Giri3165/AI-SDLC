import time
from collections import defaultdict
from functools import wraps
from flask import request, abort

_attempts = defaultdict(list)


def rate_limit(max_requests, window_seconds):
    """
    Limits how many POST requests a single IP can make to a given route
    within a time window. Used on public, unauthenticated forms that
    could otherwise be spammed (registration, password-reset requests).

    NOTE: this is in-memory and keyed per Flask process. That's accurate
    for how this app actually runs — `python app.py` directly, or the
    single `app` container in docker-compose.yml here. If this were ever
    run with multiple worker processes (e.g. `gunicorn -w 4`), each
    worker has separate memory and the count would be wrong — a shared
    store like Redis would be needed at that point instead.
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            if request.method == "POST":
                key = (request.endpoint, request.remote_addr)
                now = time.time()

                _attempts[key] = [t for t in _attempts[key] if now - t < window_seconds]

                if len(_attempts[key]) >= max_requests:
                    abort(429, description="Too many requests. Please wait a few minutes and try again.")

                _attempts[key].append(now)

            return view_func(*args, **kwargs)
        return wrapped
    return decorator
