import csv
import io
from datetime import date, datetime

from flask import Blueprint, Response, render_template, request

from ..auth import login_required
from ..models import balance_sheet, income_statement, trial_balance

bp = Blueprint("reports", __name__, url_prefix="/reports")


def _parse_date(s):
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def _csv_response(filename, header, rows):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    w.writerows(rows)
    return Response(
        buf.getvalue(), mimetype="text/csv", headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@bp.route("/trial-balance")
@login_required
def trial_balance_view():
    as_of = _parse_date(request.args.get("as_of")) or date.today()
    rows = trial_balance(as_of)
    total_debit = sum((b for _, b in rows if b > 0), 0)
    total_credit = sum((-b for _, b in rows if b < 0), 0)
    if request.args.get("format") == "csv":
        return _csv_response(
            f"trial-balance-{as_of}.csv",
            ["Code", "Account", "Type", "Balance"],
            [[a.code, a.name, a.type, str(b)] for a, b in rows],
        )
    return render_template(
        "reports/trial_balance.html", rows=rows, as_of=as_of, total_debit=total_debit, total_credit=total_credit
    )


@bp.route("/income-statement")
@login_required
def income_statement_view():
    start = _parse_date(request.args.get("start")) or date(date.today().year, 1, 1)
    end = _parse_date(request.args.get("end")) or date.today()
    data = income_statement(start, end)
    if request.args.get("format") == "csv":
        rows = [["Revenue", a.name, str(b)] for a, b in data["revenue"]] + [
            ["Expense", a.name, str(b)] for a, b in data["expenses"]
        ]
        return _csv_response(f"income-statement-{start}-to-{end}.csv", ["Section", "Account", "Amount"], rows)
    return render_template("reports/income_statement.html", data=data, start=start, end=end)


@bp.route("/balance-sheet")
@login_required
def balance_sheet_view():
    as_of = _parse_date(request.args.get("as_of")) or date.today()
    data = balance_sheet(as_of)
    if request.args.get("format") == "csv":
        rows = (
            [["Asset", a.name, str(b)] for a, b in data["assets"]]
            + [["Liability", a.name, str(b)] for a, b in data["liabilities"]]
            + [["Equity", a.name, str(b)] for a, b in data["equity"]]
            + [["Equity", "Retained Earnings (current)", str(data["retained_earnings"])]]
        )
        return _csv_response(f"balance-sheet-{as_of}.csv", ["Section", "Account", "Amount"], rows)
    return render_template("reports/balance_sheet.html", data=data, as_of=as_of)
