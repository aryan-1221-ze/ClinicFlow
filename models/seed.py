"""Fictional demonstration data. Nothing here describes a real person or clinic."""
import csv
from datetime import date, timedelta
from pathlib import Path

from database.db import get_db
from services import csv_import

from . import activity, appointments, doctors, settings

SAMPLE_CSV = Path(__file__).resolve().parent.parent / "sample_data" / "doctors_sample.csv"

# (name, day offset, time, doctor/specialty, notes, status)
DEMO_APPOINTMENTS = [
    ("Demo Patient A", 1, "09:30", "General Practice", "Demo request: routine check-in.", "Pending"),
    ("Demo Patient B", 2, "11:00", "Dermatology", "Demo request: first visit.", "Confirmed"),
    ("Demo Patient C", 3, "14:15", "Dr. Mira Okafor (Sample)", "Demo request: follow-up slot.", "Confirmed"),
    ("Demo Patient D", 4, "10:00", "Paediatrics", "Demo request: prefers mornings.", "Pending"),
    ("Demo Patient E", 5, "16:30", "Orthopaedics", "", "Pending"),
    ("Demo Patient F", 7, "09:00", "Cardiology", "Demo request: rescheduled once.", "Confirmed"),
    ("Demo Patient G", -2, "13:00", "General Practice", "Demo request: cancelled by operator.", "Cancelled"),
    ("Demo Patient H", 9, "15:45", "Ophthalmology", "", "Pending"),
]


def seed_demo_data():
    """Load demo data once, and only into an empty database. Returns True if anything loaded."""
    if settings.get("demo_seeded") or appointments.count() or doctors.count():
        return False
    db = get_db()
    today = date.today()
    for name, offset, time, who, notes, status in DEMO_APPOINTMENTS:
        clean = {"patient_name": name, "appointment_date": (today + timedelta(days=offset)).isoformat(),
                 "appointment_time": time, "doctor_or_specialty": who, "notes": notes}
        appt_id = appointments.create(clean)
        if status != "Pending":
            appointments.set_status(appt_id, status)
    if SAMPLE_CSV.exists():
        report = csv_import.parse_csv(SAMPLE_CSV.read_bytes(), SAMPLE_CSV.name, doctors.existing_keys())
        csv_import.apply_import(report)
    settings.set_value("demo_seeded", "1")
    activity.log("demo_data", "Fictional demonstration data loaded.")
    db.commit()
    return True
