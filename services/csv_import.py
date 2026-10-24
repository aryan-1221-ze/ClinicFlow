"""Doctor-directory CSV import.

Design rules:
  * Parse and validate entirely in memory; nothing from the upload is written to disk.
  * Never alter supplied values. A row that fails validation is skipped and reported.
  * Missing optional values are stored as NULL and counted, never invented.
"""
import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime

from models import doctors

REQUIRED = ("name", "specialty", "practice", "city")
OPTIONAL = ("phone", "email", "source", "last_verified")
KNOWN = REQUIRED + OPTIONAL

# Accepted alternative header names (after normalisation).
ALIASES = {
    "doctor_name": "name", "professional_name": "name", "doctor": "name",
    "clinic": "practice", "clinic_name": "practice", "practice_name": "practice",
    "region": "city", "location": "city", "city_or_region": "city",
    "phone_number": "phone", "telephone": "phone", "practice_phone": "phone",
    "professional_email": "email", "email_address": "email",
    "source_url": "source", "source_description": "source", "url": "source",
    "last_verified_date": "last_verified", "date_verified": "last_verified",
}
LIMITS = {"name": 120, "specialty": 80, "practice": 120, "city": 80,
          "phone": 30, "email": 254, "source": 300}
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_RE = re.compile(r"^\+?[\d\s().\-]{6,30}$")


@dataclass
class ImportReport:
    filename: str = ""
    file_error: str = ""
    rows_read: int = 0
    blank_rows: int = 0
    imported: int = 0
    records: list = field(default_factory=list)       # validated, ready to insert
    duplicates: list = field(default_factory=list)    # {"line", "name", "reason"}
    errors: list = field(default_factory=list)        # {"line", "message"}
    missing_optional: dict = field(default_factory=dict)
    unknown_columns: list = field(default_factory=list)

    @property
    def skipped(self):
        return len(self.duplicates) + len(self.errors)


def normalise_header(raw):
    h = re.sub(r"[^a-z0-9]+", "_", (raw or "").replace("\ufeff", "").strip().lower()).strip("_")
    return ALIASES.get(h, h)


def dedupe_key(name, practice):
    collapse = lambda s: re.sub(r"\s+", " ", s).strip().lower()  # noqa: E731
    return f"{collapse(name)}|{collapse(practice)}"


def _validate_row(row):
    """Return (record, [problems])."""
    problems, rec = [], {}
    for col in KNOWN:
        value = (row.get(col) or "").strip()
        value = "".join(ch for ch in value if ch >= " " or ch == "\t").strip()
        rec[col] = value
    for col in REQUIRED:
        if not rec[col]:
            problems.append(f"missing required value: {col}")
    for col, limit in LIMITS.items():
        if len(rec[col]) > limit:
            problems.append(f"{col} is longer than {limit} characters")
    if rec["email"] and not _EMAIL_RE.match(rec["email"]):
        problems.append("email is not a valid address")
    if rec["phone"] and (not _PHONE_RE.match(rec["phone"])
                         or sum(c.isdigit() for c in rec["phone"]) < 6):
        problems.append("phone is not a valid number format")
    if rec["last_verified"]:
        try:
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", rec["last_verified"]):
                raise ValueError
            if datetime.strptime(rec["last_verified"], "%Y-%m-%d").date() > date.today():
                problems.append("last_verified is in the future")
        except ValueError:
            problems.append("last_verified must be a real date in YYYY-MM-DD format")
    return rec, problems


def parse_csv(data, filename="upload.csv", existing=frozenset(), max_rows=5000):
    """Validate CSV bytes. Pure function: touches neither the database nor the disk."""
    report = ImportReport(filename=filename)
    if not data or not data.strip():
        report.file_error = "The file is empty."
        return report
    if b"\x00" in data:
        report.file_error = "This does not look like a text CSV file."
        return report
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        report.file_error = "The file is not valid UTF-8. Re-save it as 'CSV UTF-8' and try again."
        return report

    reader = csv.reader(io.StringIO(text), strict=True)
    try:
        header = next(reader)
    except (StopIteration, csv.Error):
        report.file_error = "Could not read a header row."
        return report

    columns = [normalise_header(h) for h in header]
    dupes = sorted({c for c in columns if c and columns.count(c) > 1})
    if dupes:
        report.file_error = f"Duplicate column names after normalisation: {', '.join(dupes)}."
        return report
    missing = [c for c in REQUIRED if c not in columns]
    if missing:
        report.file_error = (f"Missing required column(s): {', '.join(missing)}. "
                             f"Required columns are: {', '.join(REQUIRED)}.")
        return report
    report.unknown_columns = [h.strip() for h, c in zip(header, columns) if c not in KNOWN]

    seen = {}  # dedupe_key -> first line number in this file
    valid = []
    try:
        for fields in reader:
            line = reader.line_num
            if not any(f.strip() for f in fields):
                report.blank_rows += 1
                continue
            report.rows_read += 1
            if report.rows_read > max_rows:
                report.file_error = f"Too many rows. The limit is {max_rows} per import."
                report.records, report.errors, report.duplicates = [], [], []
                return report
            if len(fields) > len(columns):
                report.errors.append({"line": line, "message": "row has more values than the header has columns"})
                continue
            row = dict(zip(columns, fields))
            rec, problems = _validate_row(row)
            if problems:
                report.errors.append({"line": line, "message": "; ".join(problems)})
                continue
            key = dedupe_key(rec["name"], rec["practice"])
            if key in existing:
                report.duplicates.append({"line": line, "name": rec["name"],
                                          "reason": "already in the directory"})
                continue
            if key in seen:
                report.duplicates.append({"line": line, "name": rec["name"],
                                          "reason": f"duplicate of line {seen[key]} in this file"})
                continue
            seen[key] = line
            rec["dedupe_key"] = key
            for col in OPTIONAL:
                rec[col] = rec[col] or None
            valid.append(rec)
    except csv.Error as exc:
        report.file_error = f"Malformed CSV near line {reader.line_num}: {exc}"
        report.records, report.errors, report.duplicates = [], [], []
        return report

    report.records = valid
    report.missing_optional = {c: sum(1 for r in valid if not r[c]) for c in OPTIONAL}
    return report


def apply_import(report):
    """Insert validated records; fold unique-index races into the duplicate list."""
    if report.records:
        inserted, rejected = doctors.insert_many(report.records)
        report.imported = inserted
        for r in rejected:
            report.duplicates.append({"line": 0, "name": r["name"], "reason": "already in the directory"})
    return report
