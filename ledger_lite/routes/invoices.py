from datetime import datetime
from decimal import Decimal, InvalidOperation

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from ..auth import login_required, role_required
from ..models import Account, Customer, Invoice, InvoiceLine, InvoicePayment, JournalEntry, db, post_entry, reverse_entry

bp = Blueprint("invoices", __name__, url_prefix="/invoices")


def _ar_account():
    return Account.query.filter_by(code="1200").first()


@bp.route("/")
@login_required
def list_invoices():
    invoices = Invoice.query.order_by(Invoice.date.desc(), Invoice.id.desc()).all()
    customers = Customer.query.order_by(Customer.name).all()
    income_accounts = Account.query.filter_by(type="income").order_by(Account.code).all()
    return render_template("invoices.html", invoices=invoices, customers=customers, income_accounts=income_accounts)


@bp.route("/customers/new", methods=["POST"])
@login_required
def new_customer():
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip()
    if not name:
        flash("Customer name is required.")
        return redirect(url_for("invoices.list_invoices"))
    db.session.add(Customer(name=name, email=email))
    db.session.commit()
    flash("Customer added.")
    return redirect(url_for("invoices.list_invoices"))


def _next_invoice_number():
    last = Invoice.query.order_by(Invoice.id.desc()).first()
    return f"INV-{(last.id if last else 0) + 1:04d}"


@bp.route("/new", methods=["POST"])
@login_required
def new_invoice():
    customer_id = request.form.get("customer_id")
    if not customer_id:
        flash("Customer is required.")
        return redirect(url_for("invoices.list_invoices"))

    try:
        inv_date = datetime.strptime(request.form.get("date", ""), "%Y-%m-%d").date()
        due_date_str = request.form.get("due_date", "")
        due_date = datetime.strptime(due_date_str, "%Y-%m-%d").date() if due_date_str else None
    except ValueError:
        flash("A valid invoice date is required.")
        return redirect(url_for("invoices.list_invoices"))

    invoice = Invoice(
        number=_next_invoice_number(), customer_id=int(customer_id), date=inv_date, due_date=due_date,
        status="draft", created_by_id=g.user.id,
    )
    db.session.add(invoice)
    db.session.flush()

    descriptions = request.form.getlist("description")
    quantities = request.form.getlist("quantity")
    prices = request.form.getlist("unit_price")
    account_ids = request.form.getlist("income_account_id")

    any_line = False
    try:
        for desc, qty, price, acc_id in zip(descriptions, quantities, prices, account_ids):
            if not desc.strip() or not acc_id:
                continue
            db.session.add(InvoiceLine(
                invoice_id=invoice.id, description=desc.strip(),
                quantity=Decimal(qty or "1"), unit_price=Decimal(price or "0"),
                income_account_id=int(acc_id),
            ))
            any_line = True
    except InvalidOperation:
        db.session.rollback()
        flash("Quantity and unit price must be numbers.")
        return redirect(url_for("invoices.list_invoices"))

    if not any_line:
        db.session.rollback()
        flash("Invoice needs at least one line item.")
        return redirect(url_for("invoices.list_invoices"))

    db.session.commit()
    return redirect(url_for("invoices.detail", invoice_id=invoice.id))


@bp.route("/<int:invoice_id>")
@login_required
def detail(invoice_id):
    invoice = Invoice.query.get_or_404(invoice_id)
    payment_accounts = Account.query.filter_by(type="asset").order_by(Account.code).all()
    return render_template("invoice_detail.html", invoice=invoice, payment_accounts=payment_accounts)


@bp.route("/<int:invoice_id>/send", methods=["POST"])
@login_required
def send_invoice(invoice_id):
    invoice = Invoice.query.get_or_404(invoice_id)
    if invoice.status != "draft":
        flash("Only draft invoices can be sent.")
        return redirect(url_for("invoices.detail", invoice_id=invoice_id))

    lines = [{"account_id": _ar_account().id, "debit": invoice.total, "credit": 0}]
    for line in invoice.lines:
        lines.append({"account_id": line.income_account_id, "debit": 0, "credit": line.amount})

    entry = post_entry(
        invoice.date, f"Invoice {invoice.number}", lines,
        source="invoice", source_id=invoice.id, created_by_id=g.user.id,
    )
    invoice.journal_entry_id = entry.id
    invoice.status = "sent"
    db.session.commit()
    flash(f"Invoice {invoice.number} sent.")
    return redirect(url_for("invoices.detail", invoice_id=invoice_id))


@bp.route("/<int:invoice_id>/payments/new", methods=["POST"])
@login_required
def new_payment(invoice_id):
    invoice = Invoice.query.get_or_404(invoice_id)
    if invoice.status != "sent":
        flash("Invoice must be sent before recording a payment.")
        return redirect(url_for("invoices.detail", invoice_id=invoice_id))

    try:
        amount = Decimal(request.form.get("amount") or "0")
        pay_date = datetime.strptime(request.form.get("date", ""), "%Y-%m-%d").date()
    except (InvalidOperation, ValueError):
        flash("A valid date and amount are required.")
        return redirect(url_for("invoices.detail", invoice_id=invoice_id))

    account_id = request.form.get("account_id")
    if not account_id or amount <= 0 or amount > invoice.balance_due:
        flash("Invalid payment amount.")
        return redirect(url_for("invoices.detail", invoice_id=invoice_id))

    entry = post_entry(
        pay_date, f"Payment for {invoice.number}",
        [
            {"account_id": int(account_id), "debit": amount, "credit": 0},
            {"account_id": _ar_account().id, "debit": 0, "credit": amount},
        ],
        source="payment", source_id=invoice.id, created_by_id=g.user.id,
    )
    db.session.add(InvoicePayment(
        invoice_id=invoice.id, date=pay_date, amount=amount,
        method=request.form.get("method", "").strip(), journal_entry_id=entry.id,
    ))
    if invoice.balance_due - amount <= 0:
        invoice.status = "paid"
    db.session.commit()
    flash("Payment recorded.")
    return redirect(url_for("invoices.detail", invoice_id=invoice_id))


@bp.route("/<int:invoice_id>/void", methods=["POST"])
@role_required("owner")
def void_invoice(invoice_id):
    invoice = Invoice.query.get_or_404(invoice_id)
    if invoice.status == "draft":
        invoice.status = "void"
    elif invoice.status in ("sent", "paid"):
        for payment in invoice.payments:
            reverse_entry(
                db.session.get(JournalEntry, payment.journal_entry_id),
                memo=f"Void payment for {invoice.number}", created_by_id=g.user.id,
            )
        reverse_entry(
            db.session.get(JournalEntry, invoice.journal_entry_id),
            memo=f"Void invoice {invoice.number}", created_by_id=g.user.id,
        )
        invoice.status = "void"
    db.session.commit()
    flash(f"Invoice {invoice.number} voided.")
    return redirect(url_for("invoices.detail", invoice_id=invoice_id))
