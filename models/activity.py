"""Activity log. Descriptions must never contain secrets or free-text personal data."""
from database.db import get_db

from . import page_meta, utcnow


def log(action, description):
    db = get_db()
    db.execute(
        "INSERT INTO activity_log (action, description, created_at) VALUES (?, ?, ?)",
        (action, description[:300], utcnow()),
    )
    db.commit()


def recent(limit=8):
    return get_db().execute(
        "SELECT * FROM activity_log ORDER BY created_at DESC, id DESC LIMIT ?", (limit,)
    ).fetchall()


def page(page_number, per_page=25):
    db = get_db()
    total = db.execute("SELECT COUNT(*) FROM activity_log").fetchone()[0]
    meta = page_meta(total, page_number, per_page)
    rows = db.execute(
        "SELECT * FROM activity_log ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
        (per_page, meta["offset"]),
    ).fetchall()
    return rows, meta
