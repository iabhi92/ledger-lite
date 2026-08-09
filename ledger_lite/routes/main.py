from datetime import date

from flask import Blueprint, redirect, render_template, session, url_for

from ..auth import login_required
from ..models import Account, Invoice, JournalEntry, account_balance

bp = Blueprint("main", __name__)


@bp.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("main.dashboard"))
    return render_template("landing.html")


@bp.route("/dashboard")
@login_required
def dashboard():
    today = date.today()
    cash_balances = [
        (a, account_balance(a.id, today))
        for a in Account.query.filter_by(type="asset").order_by(Account.code)
    ]
    total_cash = sum((b for _, b in cash_balances), 0)
    open_invoices = Invoice.query.filter(Invoice.status == "sent").all()
    ar_outstanding = sum((inv.balance_due for inv in open_invoices), 0)
    recent_entries = JournalEntry.query.order_by(JournalEntry.date.desc(), JournalEntry.id.desc()).limit(10).all()
    return render_template(
        "dashboard.html",
        cash_balances=cash_balances,
        total_cash=total_cash,
        ar_outstanding=ar_outstanding,
        open_invoices=open_invoices,
        recent_entries=recent_entries,
    )
