"""CSRF protection, security headers and a redaction helper."""
import hmac
import secrets

from flask import abort, request, session

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


def init_security(app):
    app.jinja_env.globals["csrf_token"] = csrf_token

    @app.before_request
    def _check_csrf():
        if request.method in SAFE_METHODS:
            return
        sent = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token", "")
        expected = session.get("csrf_token", "")
        if not expected or not hmac.compare_digest(sent, expected):
            abort(400, description="csrf")

    @app.after_request
    def _headers(resp):
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
            "base-uri 'self'; form-action 'self'; frame-ancestors 'none'")
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "same-origin"
        resp.headers["Cache-Control"] = "no-store"
        return resp
