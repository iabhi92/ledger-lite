import secrets
from functools import wraps

from flask import abort, g, redirect, request, session, url_for

from .models import User, db


def generate_csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(16)
    return session["csrf_token"]


def csrf_protect():
    if request.method == "POST":
        token = session.get("csrf_token")
        if not token or not secrets.compare_digest(token, request.form.get("csrf_token", "")):
            abort(400, description="Invalid or missing CSRF token")


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("auth.login", next=request.path))
        user = db.session.get(User, session["user_id"])
        if not user or not user.is_active:
            session.clear()
            return redirect(url_for("auth.login"))
        g.user = user
        return view(*args, **kwargs)

    return wrapped


def role_required(role):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if g.user.role != role:
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator
