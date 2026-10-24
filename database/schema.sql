CREATE TABLE IF NOT EXISTS appointments (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_name        TEXT NOT NULL,
    appointment_date    TEXT NOT NULL,            -- YYYY-MM-DD
    appointment_time    TEXT NOT NULL,            -- HH:MM (24h)
    doctor_or_specialty TEXT NOT NULL,
    notes               TEXT NOT NULL DEFAULT '',
    status              TEXT NOT NULL DEFAULT 'Pending'
                        CHECK (status IN ('Pending', 'Confirmed', 'Cancelled')),
    created_at          TEXT NOT NULL,            -- UTC
    updated_at          TEXT NOT NULL             -- UTC
);
CREATE INDEX IF NOT EXISTS idx_appointments_status ON appointments(status);
CREATE INDEX IF NOT EXISTS idx_appointments_date ON appointments(appointment_date, appointment_time);

CREATE TABLE IF NOT EXISTS doctors (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    specialty     TEXT NOT NULL,
    practice      TEXT NOT NULL,
    city          TEXT NOT NULL,
    phone         TEXT,
    email         TEXT,
    source        TEXT,
    last_verified TEXT,
    dedupe_key    TEXT NOT NULL UNIQUE,           -- lower(name)|lower(practice), whitespace-collapsed
    imported_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_doctors_specialty ON doctors(specialty);
CREATE INDEX IF NOT EXISTS idx_doctors_city ON doctors(city);

CREATE TABLE IF NOT EXISTS activity_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    action      TEXT NOT NULL,
    description TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_activity_created ON activity_log(created_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
