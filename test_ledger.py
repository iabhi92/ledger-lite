from datetime import date
from decimal import Decimal

from ledger_lite import create_app
from ledger_lite.models import Account, balance_sheet, db, income_statement, post_entry, trial_balance


def make_app():
    return create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "SECRET_KEY": "test"})


def test_balanced_entry_posts_and_ties_out_trial_balance():
    app = make_app()
    with app.app_context():
        cash = Account.query.filter_by(code="1000").first()
        revenue = Account.query.filter_by(code="4000").first()
        post_entry(
            date(2026, 1, 1), "Test sale",
            [
                {"account_id": cash.id, "debit": Decimal("100"), "credit": 0},
                {"account_id": revenue.id, "debit": 0, "credit": Decimal("100")},
            ],
            source="manual", source_id=None, created_by_id=None,
        )
        db.session.commit()

        rows = dict((a.code, b) for a, b in trial_balance(date(2026, 1, 1)))
        assert rows["1000"] == Decimal("100")   # cash: net debit balance
        assert rows["4000"] == Decimal("-100")  # revenue: net credit balance (raw, unnormalized)
        total_debit = sum(b for b in rows.values() if b > 0)
        total_credit = sum(-b for b in rows.values() if b < 0)
        assert total_debit == total_credit


def test_unbalanced_entry_is_rejected():
    app = make_app()
    with app.app_context():
        cash = Account.query.filter_by(code="1000").first()
        revenue = Account.query.filter_by(code="4000").first()
        try:
            post_entry(
                date(2026, 1, 1), "Bad entry",
                [
                    {"account_id": cash.id, "debit": Decimal("100"), "credit": 0},
                    {"account_id": revenue.id, "debit": 0, "credit": Decimal("50")},
                ],
                source="manual", source_id=None, created_by_id=None,
            )
            raise AssertionError("unbalanced entry should have raised ValueError")
        except ValueError:
            pass


def test_income_statement_and_balance_sheet_tie_out():
    app = make_app()
    with app.app_context():
        cash = Account.query.filter_by(code="1000").first()
        revenue = Account.query.filter_by(code="4000").first()
        rent = Account.query.filter_by(code="5100").first()

        post_entry(
            date(2026, 1, 5), "Sale",
            [{"account_id": cash.id, "debit": Decimal("500"), "credit": 0},
             {"account_id": revenue.id, "debit": 0, "credit": Decimal("500")}],
            source="manual", source_id=None, created_by_id=None,
        )
        post_entry(
            date(2026, 1, 10), "Rent",
            [{"account_id": rent.id, "debit": Decimal("200"), "credit": 0},
             {"account_id": cash.id, "debit": 0, "credit": Decimal("200")}],
            source="manual", source_id=None, created_by_id=None,
        )
        db.session.commit()

        inc = income_statement(date(2026, 1, 1), date(2026, 1, 31))
        assert inc["net_income"] == Decimal("300")

        bs = balance_sheet(date(2026, 1, 31))
        assert bs["retained_earnings"] == Decimal("300")
        assert bs["total_assets"] == bs["total_liabilities"] + bs["total_equity"]


if __name__ == "__main__":
    test_balanced_entry_posts_and_ties_out_trial_balance()
    test_unbalanced_entry_is_rejected()
    test_income_statement_and_balance_sheet_tie_out()
    print("All checks passed.")
