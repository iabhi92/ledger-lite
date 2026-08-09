from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from ..auth import role_required
from ..models import User, db

bp = Blueprint("users", __name__, url_prefix="/users")


@bp.route("/")
@role_required("owner")
def list_users():
    users = User.query.order_by(User.username).all()
    return render_template("users.html", users=users)


@bp.route("/new", methods=["POST"])
@role_required("owner")
def new_user():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    role = request.form.get("role")
    if not username or len(password) < 8 or role not in ("owner", "accountant"):
        flash("Username, an 8+ character password, and a valid role are required.")
        return redirect(url_for("users.list_users"))
    if User.query.filter_by(username=username).first():
        flash("Username already taken.")
        return redirect(url_for("users.list_users"))
    user = User(username=username, role=role)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    flash(f"User {username} created.")
    return redirect(url_for("users.list_users"))


@bp.route("/<int:user_id>/deactivate", methods=["POST"])
@role_required("owner")
def deactivate_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == g.user.id:
        flash("You can't deactivate your own account.")
        return redirect(url_for("users.list_users"))
    user.is_active = False
    db.session.commit()
    flash(f"{user.username} deactivated.")
    return redirect(url_for("users.list_users"))
