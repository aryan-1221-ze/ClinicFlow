from database.db import get_db

DEFAULT_CLINIC_NAME = "ClinicFlow Demo Clinic"


def get(key, default=None):
    row = get_db().execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_value(key, value):
    db = get_db()
    db.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    db.commit()


def clinic_name():
    return get("clinic_name", DEFAULT_CLINIC_NAME)
