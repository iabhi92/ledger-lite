from flask import Blueprint, flash, redirect, render_template, request, url_for

from ..auth import login_required, role_required
from ..models import ACCOUNT_TYPES, Account, account_balance, db

bp = Blueprint("accounts", __name__, url_prefix="/accounts")


@bp.route("/")
@login_required
def list_accounts():
    accounts = Account.query.order_by(Account.code).all()
    balances = {a.id: account_balance(a.id) for a in accounts}
    return render_template("accounts.html", accounts=accounts, balances=balances, account_types=ACCOUNT_TYPES)


@bp.route("/new", methods=["POST"])
@role_required("owner")
def new_account():
    code = request.form.get("code", "").strip()
    name = request.form.get("name", "").strip()
    type_ = request.form.get("type")
    if not code or not name or type_ not in ACCOUNT_TYPES:
        flash("Code, name, and a valid type are required.")
        return redirect(url_for("accounts.list_accounts"))
    if Account.query.filter_by(code=code).first():
        flash("Account code already exists.")
        return redirect(url_for("accounts.list_accounts"))
    db.session.add(Account(code=code, name=name, type=type_))
    db.session.commit()
    flash(f"Account {code} added.")
    return redirect(url_for("accounts.list_accounts"))
