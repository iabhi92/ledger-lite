from datetime import date
from decimal import Decimal

from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()

ACCOUNT_TYPES = ["asset", "liability", "equity", "income", "expense"]
DEBIT_NORMAL = {"asset", "expense"}


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # "owner" | "accountant"
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Account(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    type = db.Column(db.String(20), nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)


class JournalEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    memo = db.Column(db.String(255), nullable=False, default="")
    source = db.Column(db.String(20), nullable=False)  # manual|invoice|payment|expense|reversal
    source_id = db.Column(db.Integer, nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    lines = db.relationship("JournalLine", backref="entry", cascade="all, delete-orphan")


class JournalLine(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    entry_id = db.Column(db.Integer, db.ForeignKey("journal_entry.id"), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey("account.id"), nullable=False)
    debit = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    credit = db.Column(db.Numeric(14, 2), nullable=False, default=0)

    account = db.relationship("Account")


class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), nullable=True)


class Invoice(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.String(20), unique=True, nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"), nullable=False)
    date = db.Column(db.Date, nullable=False)
    due_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(20), nullable=False, default="draft")  # draft|sent|paid|void
    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    journal_entry_id = db.Column(db.Integer, db.ForeignKey("journal_entry.id"), nullable=True)

    customer = db.relationship("Customer")
    lines = db.relationship("InvoiceLine", backref="invoice", cascade="all, delete-orphan")
    payments = db.relationship("InvoicePayment", backref="invoice", cascade="all, delete-orphan")

    @property
    def total(self):
        return sum((l.amount for l in self.lines), Decimal("0"))

    @property
    def amount_paid(self):
        return sum((p.amount for p in self.payments), Decimal("0"))

    @property
    def balance_due(self):
        return self.total - self.amount_paid


class InvoiceLine(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey("invoice.id"), nullable=False)
    description = db.Column(db.String(255), nullable=False)
    quantity = db.Column(db.Numeric(14, 2), nullable=False, default=1)
    unit_price = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    income_account_id = db.Column(db.Integer, db.ForeignKey("account.id"), nullable=False)

    income_account = db.relationship("Account")

    @property
    def amount(self):
        return self.quantity * self.unit_price


class InvoicePayment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey("invoice.id"), nullable=False)
    date = db.Column(db.Date, nullable=False)
    amount = db.Column(db.Numeric(14, 2), nullable=False)
    method = db.Column(db.String(40), nullable=True)
    journal_entry_id = db.Column(db.Integer, db.ForeignKey("journal_entry.id"), nullable=True)


class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    vendor = db.Column(db.String(120), nullable=True)
    category_account_id = db.Column(db.Integer, db.ForeignKey("account.id"), nullable=False)
    payment_account_id = db.Column(db.Integer, db.ForeignKey("account.id"), nullable=False)
    amount = db.Column(db.Numeric(14, 2), nullable=False)
    note = db.Column(db.String(255), nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    journal_entry_id = db.Column(db.Integer, db.ForeignKey("journal_entry.id"), nullable=True)
    voided = db.Column(db.Boolean, nullable=False, default=False)

    category_account = db.relationship("Account", foreign_keys=[category_account_id])
    payment_account = db.relationship("Account", foreign_keys=[payment_account_id])


# --- core double-entry posting -------------------------------------------------

def post_entry(entry_date, memo, lines, source, source_id, created_by_id):
    """lines: [{account_id, debit, credit}, ...] using Decimal amounts. Must balance."""
    total_debit = sum((Decimal(l.get("debit") or 0) for l in lines), Decimal("0"))
    total_credit = sum((Decimal(l.get("credit") or 0) for l in lines), Decimal("0"))
    if total_debit != total_credit:
        raise ValueError(f"Journal entry does not balance: debits {total_debit} != credits {total_credit}")
    if total_debit == 0:
        raise ValueError("Journal entry has no amount")

    entry = JournalEntry(date=entry_date, memo=memo, source=source, source_id=source_id, created_by_id=created_by_id)
    db.session.add(entry)
    db.session.flush()
    for l in lines:
        db.session.add(JournalLine(
            entry_id=entry.id,
            account_id=l["account_id"],
            debit=Decimal(l.get("debit") or 0),
            credit=Decimal(l.get("credit") or 0),
        ))
    return entry


def reverse_entry(entry, memo=None, created_by_id=None):
    lines = [{"account_id": l.account_id, "debit": l.credit, "credit": l.debit} for l in entry.lines]
    return post_entry(
        date.today(), memo or f"Reversal of entry #{entry.id}", lines,
        source="reversal", source_id=entry.id, created_by_id=created_by_id,
    )


# --- balances and reports -------------------------------------------------

def _sum_lines(account_id, start=None, end=None):
    q = db.session.query(
        db.func.coalesce(db.func.sum(JournalLine.debit), 0),
        db.func.coalesce(db.func.sum(JournalLine.credit), 0),
    ).join(JournalEntry).filter(JournalLine.account_id == account_id)
    if start:
        q = q.filter(JournalEntry.date >= start)
    if end:
        q = q.filter(JournalEntry.date <= end)
    debit, credit = q.one()
    return Decimal(debit), Decimal(credit)


def account_balance(account_id, as_of=None):
    """Cumulative balance from inception through as_of (or all time)."""
    debit, credit = _sum_lines(account_id, end=as_of)
    account = db.session.get(Account, account_id)
    return debit - credit if account.type in DEBIT_NORMAL else credit - debit


def period_balance(account_id, start, end):
    """Balance for a single date range, for income-statement accounts."""
    debit, credit = _sum_lines(account_id, start=start, end=end)
    account = db.session.get(Account, account_id)
    return debit - credit if account.type in DEBIT_NORMAL else credit - debit


def trial_balance(as_of=None):
    """Raw debit-minus-credit balance per account (not normalized by account
    type) — a positive number sits in the Debit column, negative in Credit,
    so the two columns always tie out regardless of which accounts moved."""
    rows = []
    for acct in Account.query.order_by(Account.code).all():
        debit, credit = _sum_lines(acct.id, end=as_of)
        rows.append((acct, debit - credit))
    return rows


def income_statement(start, end):
    revenue = [(a, period_balance(a.id, start, end)) for a in Account.query.filter_by(type="income").order_by(Account.code)]
    expenses = [(a, period_balance(a.id, start, end)) for a in Account.query.filter_by(type="expense").order_by(Account.code)]
    total_revenue = sum((b for _, b in revenue), Decimal("0"))
    total_expense = sum((b for _, b in expenses), Decimal("0"))
    return {
        "revenue": revenue,
        "expenses": expenses,
        "total_revenue": total_revenue,
        "total_expense": total_expense,
        "net_income": total_revenue - total_expense,
    }


def balance_sheet(as_of):
    assets = [(a, account_balance(a.id, as_of)) for a in Account.query.filter_by(type="asset").order_by(Account.code)]
    liabilities = [(a, account_balance(a.id, as_of)) for a in Account.query.filter_by(type="liability").order_by(Account.code)]
    equity = [(a, account_balance(a.id, as_of)) for a in Account.query.filter_by(type="equity").order_by(Account.code)]
    total_assets = sum((b for _, b in assets), Decimal("0"))
    total_liabilities = sum((b for _, b in liabilities), Decimal("0"))
    total_equity_accounts = sum((b for _, b in equity), Decimal("0"))
    # Retained earnings: cumulative net income since inception, not yet closed into an equity account.
    retained_earnings = income_statement(date(1970, 1, 1), as_of)["net_income"]
    return {
        "assets": assets,
        "liabilities": liabilities,
        "equity": equity,
        "total_assets": total_assets,
        "total_liabilities": total_liabilities,
        "total_equity_accounts": total_equity_accounts,
        "retained_earnings": retained_earnings,
        "total_equity": total_equity_accounts + retained_earnings,
    }


DEFAULT_ACCOUNTS = [
    ("1000", "Cash", "asset"),
    ("1010", "Bank Account", "asset"),
    ("1200", "Accounts Receivable", "asset"),
    ("2000", "Accounts Payable", "liability"),
    ("3000", "Owner's Equity", "equity"),
    ("4000", "Sales Revenue", "income"),
    ("4900", "Other Income", "income"),
    ("5000", "Cost of Goods Sold", "expense"),
    ("5100", "Rent", "expense"),
    ("5200", "Utilities", "expense"),
    ("5300", "Office Supplies", "expense"),
    ("5400", "Software & Subscriptions", "expense"),
    ("5900", "Other Expense", "expense"),
]
