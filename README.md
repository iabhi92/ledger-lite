# Ledger Lite

Minimal double-entry bookkeeping for a small business: chart of accounts,
manual journal entries, customer invoicing, expense tracking, and Trial
Balance / Income Statement / Balance Sheet reports (CSV export + browser
print-to-PDF). Built to run for near-zero cost — Flask + SQLite, no paid
services required.

## Roles

- **owner** — full access, including managing the chart of accounts, other
  users, and voiding invoices/expenses/journal entries.
- **accountant** — day-to-day bookkeeping: journal entries, invoices,
  payments, expenses, and all reports. Can't manage users or void entries.

## Local setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

export FLASK_APP=run.py
flask create-owner yourname   # prompts for a password, first login

python run.py                 # http://localhost:5050
```

Set `SECRET_KEY` to a real random value before using this for anything but
local testing (`python -c "import secrets; print(secrets.token_hex(32))"`).

## Deploying cheaply

Any host that runs a small Flask app works (Render/Railway/Fly free or
lowest paid tier, or a $5/mo VPS). Set these environment variables:

- `SECRET_KEY` — random secret for session signing.
- `DATABASE_URL` — defaults to a local SQLite file; point it at a Postgres
  URL if the host's disk isn't persistent.
- `FLASK_ENV=production` — makes the session cookie `Secure` (HTTPS only).

Run with `gunicorn run:app` instead of the dev server in production.

## What this deliberately does not do (yet)

Kept out to stay minimal — add if the business actually needs it:

- No sales tax / VAT calculation on invoices.
- No multi-currency.
- No accounts-payable / bill tracking for unpaid vendor expenses (expenses
  assume immediate payment from a cash/bank account).
- No payroll.
- No period closing — the balance sheet shows "Retained earnings (current)"
  as cumulative net income since inception rather than closing it into
  equity at year end.
- No file/receipt attachments, just a text note field.

## Verifying it works

`python test_ledger.py` runs an assert-based self-check of the core
double-entry posting logic (balanced entries post, unbalanced entries are
rejected, income statement and balance sheet tie out) against an in-memory
database — no test framework needed.
