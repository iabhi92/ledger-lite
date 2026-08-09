from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from ..models import User

bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first()
        if user and user.is_active and user.check_password(password):
            session.clear()
            session["user_id"] = user.id
            return redirect(request.args.get("next") or url_for("main.dashboard"))
        flash("Invalid username or password.")
    return render_template("login.html")


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
