"""ClinicFlow application factory.  Run with:  python app.py   or   flask --app app run"""
import logging
from datetime import datetime

import click
from flask import Flask, jsonify, render_template, request

from config import Config
from database.db import close_db, init_db
from services.security import init_security


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)

    app.teardown_appcontext(close_db)
    init_security(app)
    _register_filters(app)
    _register_errors(app)

    from routes import bp
    app.register_blueprint(bp)

    with app.app_context():
        init_db()
        if app.config["AUTO_SEED"]:
            from models.seed import seed_demo_data
            seed_demo_data()

    if app.config.get("SECRET_KEY_IS_TEMPORARY") and not app.testing:
        app.logger.warning("SECRET_KEY is not set: using a temporary key. "
                           "Sessions reset on restart. See .env.example.")

    @app.cli.command("init-db")
    @click.option("--seed", is_flag=True, help="Also load fictional demo data.")
    def init_db_command(seed):
        """Create the database tables."""
        init_db()
        if seed:
            from models.seed import seed_demo_data
            click.echo("Demo data loaded." if seed_demo_data() else "Skipped: database is not empty.")
        click.echo("Database ready.")

    return app


def _register_filters(app):
    @app.template_filter("ts")
    def fmt_ts(value):
        try:
            return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").strftime("%d %b %Y, %H:%M UTC")
        except (TypeError, ValueError):
            return value or "-"

    @app.template_filter("day")
    def fmt_day(value):
        try:
            d = datetime.strptime(value, "%Y-%m-%d")
            return f"{d.strftime('%a')} {d.day} {d.strftime('%b %Y')}"
        except (TypeError, ValueError):
            return value or "-"


def _register_errors(app):
    messages = {
        400: "The request could not be processed. If you were filling in a form, reload the page and try again.",
        404: "That page or record does not exist.",
        405: "That action is not allowed here.",
        413: "The upload is too large. The limit is set by MAX_UPLOAD_BYTES (default 1 MB).",
        500: "Something went wrong on our side. Nothing was lost; please try again.",
    }

    def handle(err):
        code = getattr(err, "code", None)
        if not isinstance(code, int):
            code = 500
        if code == 500:
            app.logger.error("Unhandled error on %s %s", request.method, request.path, exc_info=err)
        message = messages.get(code, "Something went wrong.")
        if code == 400 and getattr(err, "description", "") == "csrf":
            message = "Your session expired or the form is out of date. Reload the page and try again."
        if request.path.startswith("/assistant/"):
            return jsonify(error=message), code
        return render_template("error.html", code=code, message=message), code

    for code in messages:
        app.register_error_handler(code, handle)
    app.register_error_handler(Exception, handle)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    create_app().run(host="127.0.0.1", port=5000, debug=False)
