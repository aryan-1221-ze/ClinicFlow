"""Appointment requests: validation + persistence."""
import re
from datetime import date, datetime

from database.db import get_db

from . import clean_text, like_pattern, page_meta, utcnow

STATUSES = ("Pending", "Confirmed", "Cancelled")
EDITABLE_FIELDS = ("patient_name", "appointment_date", "appointment_time",
                   "doctor_or_specialty", "notes")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def validate(data, require_status=False):
    """Return (clean_values, errors). Never raises on bad input."""
    errors = {}
    clean = {
        "patient_name": clean_text(data.get("patient_name")),
        "appointment_date": clean_text(data.get("appointment_date")),
        "appointment_time": clean_text(data.get("appointment_time")),
        "doctor_or_specialty": clean_text(data.get("doctor_or_specialty")),
        "notes": clean_text(data.get("notes")),
    }
    if require_status:
        clean["status"] = clean_text(data.get("status"))

    if not clean["patient_name"]:
        errors["patient_name"] = "Enter a name. Use a fictional or demonstration name."
    elif len(clean["patient_name"]) > 100:
        errors["patient_name"] = "Keep the name to 100 characters or fewer."

    try:
        if not _DATE_RE.match(clean["appointment_date"]):
            raise ValueError
        d = datetime.strptime(clean["appointment_date"], "%Y-%m-%d").date()
        if not (2000 <= d.year <= 2100):
            raise ValueError
    except ValueError:
        errors["appointment_date"] = "Enter a valid date (YYYY-MM-DD)."

    try:
        if len(clean["appointment_time"]) != 5:
            raise ValueError
        datetime.strptime(clean["appointment_time"], "%H:%M")
    except ValueError:
        errors["appointment_time"] = "Enter a valid time (HH:MM, 24-hour)."

    if not clean["doctor_or_specialty"]:
        errors["doctor_or_specialty"] = "Enter the requested doctor or specialty."
    elif len(clean["doctor_or_specialty"]) > 100:
        errors["doctor_or_specialty"] = "Keep this to 100 characters or fewer."

    if len(clean["notes"]) > 500:
        errors["notes"] = "Keep notes to 500 characters or fewer."

    if require_status and clean["status"] not in STATUSES:
        errors["status"] = "Choose Pending, Confirmed or Cancelled."
    return clean, errors


def create(clean):
    db = get_db()
    now = utcnow()
    cur = db.execute(
        "INSERT INTO appointments (patient_name, appointment_date, appointment_time, "
        "doctor_or_specialty, notes, status, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, 'Pending', ?, ?)",
        (clean["patient_name"], clean["appointment_date"], clean["appointment_time"],
         clean["doctor_or_specialty"], clean["notes"], now, now),
    )
    db.commit()
    return cur.lastrowid


def get(appointment_id):
    return get_db().execute("SELECT * FROM appointments WHERE id = ?", (appointment_id,)).fetchone()


def update(appointment_id, clean):
    db = get_db()
    db.execute(
        "UPDATE appointments SET patient_name = ?, appointment_date = ?, appointment_time = ?, "
        "doctor_or_specialty = ?, notes = ?, status = ?, updated_at = ? WHERE id = ?",
        (clean["patient_name"], clean["appointment_date"], clean["appointment_time"],
         clean["doctor_or_specialty"], clean["notes"], clean["status"], utcnow(), appointment_id),
    )
    db.commit()


def set_status(appointment_id, status):
    if status not in STATUSES:
        raise ValueError("Invalid status")
    db = get_db()
    db.execute("UPDATE appointments SET status = ?, updated_at = ? WHERE id = ?",
               (status, utcnow(), appointment_id))
    db.commit()


def delete(appointment_id):
    db = get_db()
    db.execute("DELETE FROM appointments WHERE id = ?", (appointment_id,))
    db.commit()


def search(q="", status="", date_from="", date_to="", page=1, per_page=15):
    where, params = [], []
    q = clean_text(q)[:100]
    if q:
        where.append("(patient_name LIKE ? ESCAPE '\\' OR doctor_or_specialty LIKE ? ESCAPE '\\' "
                     "OR notes LIKE ? ESCAPE '\\')")
        params += [like_pattern(q)] * 3
    if status in STATUSES:
        where.append("status = ?")
        params.append(status)
    if _DATE_RE.match(date_from or ""):
        where.append("appointment_date >= ?")
        params.append(date_from)
    if _DATE_RE.match(date_to or ""):
        where.append("appointment_date <= ?")
        params.append(date_to)
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    db = get_db()
    total = db.execute(f"SELECT COUNT(*) FROM appointments{clause}", params).fetchone()[0]
    meta = page_meta(total, page, per_page)
    rows = db.execute(
        f"SELECT * FROM appointments{clause} "
        "ORDER BY appointment_date, appointment_time, id LIMIT ? OFFSET ?",
        params + [per_page, meta["offset"]],
    ).fetchall()
    return rows, meta


def count():
    return get_db().execute("SELECT COUNT(*) FROM appointments").fetchone()[0]


def stats():
    """Counts straight from the database, so they always match the records."""
    counts = {s: 0 for s in STATUSES}
    for row in get_db().execute("SELECT status, COUNT(*) AS c FROM appointments GROUP BY status"):
        counts[row["status"]] = row["c"]
    total = sum(counts.values())
    segments, x = [], 0.0
    for s in STATUSES:
        width = (counts[s] / total * 100) if total else 0.0
        segments.append({"status": s, "count": counts[s], "x": round(x, 2), "width": round(width, 2)})
        x += width
    return {"total": total, "pending": counts["Pending"], "confirmed": counts["Confirmed"],
            "cancelled": counts["Cancelled"], "segments": segments}


def upcoming(limit=6):
    return get_db().execute(
        "SELECT * FROM appointments WHERE status IN ('Pending', 'Confirmed') "
        "AND appointment_date >= ? ORDER BY appointment_date, appointment_time, id LIMIT ?",
        (date.today().isoformat(), limit),
    ).fetchall()


def confirmed_for_drafting():
    return get_db().execute(
        "SELECT * FROM appointments WHERE status = 'Confirmed' "
        "ORDER BY appointment_date, appointment_time, id"
    ).fetchall()
