import getpass
import os

import click
from flask import Flask, session

from .auth import csrf_protect, generate_csrf_token
from .models import DEFAULT_ACCOUNTS, Account, User, db


def create_app(config_overrides=None):
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
        "DATABASE_URL", "sqlite:///" + os.path.join(app.instance_path, "ledger.db")
    )
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = os.environ.get("FLASK_ENV") == "production"
    if config_overrides:
        app.config.update(config_overrides)

    os.makedirs(app.instance_path, exist_ok=True)
    db.init_app(app)
    app.jinja_env.globals["csrf_token"] = generate_csrf_token

    @app.before_request
    def _csrf():
        csrf_protect()

    @app.context_processor
    def inject_user():
        user = None
        if "user_id" in session:
            user = db.session.get(User, session["user_id"])
        return {"current_user": user}

    from .routes.accounts import bp as accounts_bp
    from .routes.auth import bp as auth_bp
    from .routes.expenses import bp as expenses_bp
    from .routes.invoices import bp as invoices_bp
    from .routes.journal import bp as journal_bp
    from .routes.main import bp as main_bp
    from .routes.reports import bp as reports_bp
    from .routes.users import bp as users_bp

    for bp in (auth_bp, main_bp, accounts_bp, journal_bp, invoices_bp, expenses_bp, reports_bp, users_bp):
        app.register_blueprint(bp)

    with app.app_context():
        db.create_all()
        if Account.query.count() == 0:
            for code, name, type_ in DEFAULT_ACCOUNTS:
                db.session.add(Account(code=code, name=name, type=type_))
            db.session.commit()

    @app.cli.command("create-owner")
    @click.argument("username")
    def create_owner(username):
        """Create the first owner-role login. Prompts for a password (never stored in code)."""
        if User.query.filter_by(username=username).first():
            click.echo(f"User {username!r} already exists.")
            return
        password = getpass.getpass("Password (min 8 chars): ")
        if len(password) < 8:
            click.echo("Password must be at least 8 characters.")
            return
        if password != getpass.getpass("Confirm password: "):
            click.echo("Passwords did not match.")
            return
        user = User(username=username, role="owner")
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        click.echo(f"Owner {username!r} created.")

    return app
