from datetime import datetime
from decimal import Decimal, InvalidOperation

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from ..auth import login_required, role_required
from ..models import Account, JournalEntry, db, post_entry, reverse_entry

bp = Blueprint("journal", __name__, url_prefix="/journal")


@bp.route("/")
@login_required
def list_entries():
    entries = JournalEntry.query.order_by(JournalEntry.date.desc(), JournalEntry.id.desc()).limit(200).all()
    accounts = Account.query.order_by(Account.code).all()
    return render_template("journal.html", entries=entries, accounts=accounts)


@bp.route("/new", methods=["POST"])
@login_required
def new_entry():
    entry_date_str = request.form.get("date", "")
    memo = request.form.get("memo", "").strip()
    account_ids = request.form.getlist("account_id")
    debits = request.form.getlist("debit")
    credits = request.form.getlist("credit")

    try:
        entry_date = datetime.strptime(entry_date_str, "%Y-%m-%d").date()
    except ValueError:
        flash("A valid date is required.")
        return redirect(url_for("journal.list_entries"))

    lines = []
    try:
        for acc_id, d, c in zip(account_ids, debits, credits):
            if not acc_id:
                continue
            d = Decimal(d or "0")
            c = Decimal(c or "0")
            if d == 0 and c == 0:
                continue
            lines.append({"account_id": int(acc_id), "debit": d, "credit": c})
    except (InvalidOperation, ValueError):
        flash("Debit/credit amounts must be numbers.")
        return redirect(url_for("journal.list_entries"))

    try:
        post_entry(entry_date, memo, lines, source="manual", source_id=None, created_by_id=g.user.id)
        db.session.commit()
        flash("Journal entry posted.")
    except ValueError as e:
        db.session.rollback()
        flash(str(e))
    return redirect(url_for("journal.list_entries"))


@bp.route("/<int:entry_id>/void", methods=["POST"])
@role_required("owner")
def void_entry(entry_id):
    entry = JournalEntry.query.get_or_404(entry_id)
    if entry.source != "manual":
        flash("Only manual entries can be voided directly; void the related invoice/expense instead.")
        return redirect(url_for("journal.list_entries"))
    reverse_entry(entry, memo=f"Void of entry #{entry.id}", created_by_id=g.user.id)
    db.session.commit()
    flash("Entry voided.")
    return redirect(url_for("journal.list_entries"))
