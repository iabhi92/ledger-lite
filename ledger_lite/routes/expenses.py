from datetime import datetime
from decimal import Decimal, InvalidOperation

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from ..auth import login_required, role_required
from ..models import Account, Expense, JournalEntry, db, post_entry, reverse_entry

bp = Blueprint("expenses", __name__, url_prefix="/expenses")


@bp.route("/")
@login_required
def list_expenses():
    expenses = Expense.query.order_by(Expense.date.desc(), Expense.id.desc()).all()
    expense_accounts = Account.query.filter_by(type="expense").order_by(Account.code).all()
    payment_accounts = Account.query.filter_by(type="asset").order_by(Account.code).all()
    return render_template(
        "expenses.html", expenses=expenses, expense_accounts=expense_accounts, payment_accounts=payment_accounts
    )


@bp.route("/new", methods=["POST"])
@login_required
def new_expense():
    vendor = request.form.get("vendor", "").strip()
    note = request.form.get("note", "").strip()
    category_id = request.form.get("category_account_id")
    payment_id = request.form.get("payment_account_id")

    try:
        exp_date = datetime.strptime(request.form.get("date", ""), "%Y-%m-%d").date()
        amount = Decimal(request.form.get("amount") or "0")
    except (ValueError, InvalidOperation):
        flash("A valid date and amount are required.")
        return redirect(url_for("expenses.list_expenses"))

    if not category_id or not payment_id or amount <= 0:
        flash("Category, payment account, and a positive amount are required.")
        return redirect(url_for("expenses.list_expenses"))

    entry = post_entry(
        exp_date,
        f"Expense: {vendor or 'Uncategorized'}",
        [
            {"account_id": int(category_id), "debit": amount, "credit": 0},
            {"account_id": int(payment_id), "debit": 0, "credit": amount},
        ],
        source="expense",
        source_id=None,
        created_by_id=g.user.id,
    )
    expense = Expense(
        date=exp_date,
        vendor=vendor,
        category_account_id=int(category_id),
        payment_account_id=int(payment_id),
        amount=amount,
        note=note,
        created_by_id=g.user.id,
        journal_entry_id=entry.id,
    )
    db.session.add(expense)
    db.session.flush()
    entry.source_id = expense.id
    db.session.commit()
    flash("Expense recorded.")
    return redirect(url_for("expenses.list_expenses"))


@bp.route("/<int:expense_id>/void", methods=["POST"])
@role_required("owner")
def void_expense(expense_id):
    expense = Expense.query.get_or_404(expense_id)
    if expense.voided:
        flash("Already voided.")
        return redirect(url_for("expenses.list_expenses"))
    reverse_entry(
        db.session.get(JournalEntry, expense.journal_entry_id),
        memo=f"Void expense #{expense.id}",
        created_by_id=g.user.id,
    )
    expense.voided = True
    db.session.commit()
    flash("Expense voided.")
    return redirect(url_for("expenses.list_expenses"))
