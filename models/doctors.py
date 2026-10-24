"""Doctor directory persistence."""
import sqlite3

from database.db import get_db

from . import clean_text, like_pattern, page_meta, utcnow


def count():
    return get_db().execute("SELECT COUNT(*) FROM doctors").fetchone()[0]


def existing_keys():
    return {r["dedupe_key"] for r in get_db().execute("SELECT dedupe_key FROM doctors")}


def distinct(column):
    if column not in ("specialty", "city"):  # whitelist: column names cannot be parameterised
        raise ValueError("Unsupported column")
    return [r[0] for r in get_db().execute(
        f"SELECT DISTINCT {column} FROM doctors ORDER BY {column} COLLATE NOCASE")]


def insert_many(records):
    """Insert validated records. Returns (inserted_count, keys_rejected_by_unique_index)."""
    db = get_db()
    inserted, rejected = 0, []
    now = utcnow()
    for r in records:
        try:
            db.execute(
                "INSERT INTO doctors (name, specialty, practice, city, phone, email, source, "
                "last_verified, dedupe_key, imported_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (r["name"], r["specialty"], r["practice"], r["city"], r["phone"], r["email"],
                 r["source"], r["last_verified"], r["dedupe_key"], now),
            )
            inserted += 1
        except sqlite3.IntegrityError:
            rejected.append(r)
    db.commit()
    return inserted, rejected


def search(q="", specialty="", city="", page=1, per_page=15):
    where, params = [], []
    q = clean_text(q)[:100]
    if q:
        where.append("(name LIKE ? ESCAPE '\\' OR specialty LIKE ? ESCAPE '\\')")
        params += [like_pattern(q)] * 2
    if specialty:
        where.append("specialty = ? COLLATE NOCASE")
        params.append(specialty)
    if city:
        where.append("city = ? COLLATE NOCASE")
        params.append(city)
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    db = get_db()
    total = db.execute(f"SELECT COUNT(*) FROM doctors{clause}", params).fetchone()[0]
    meta = page_meta(total, page, per_page)
    rows = db.execute(
        f"SELECT * FROM doctors{clause} ORDER BY name COLLATE NOCASE, id LIMIT ? OFFSET ?",
        params + [per_page, meta["offset"]],
    ).fetchall()
    return rows, meta
