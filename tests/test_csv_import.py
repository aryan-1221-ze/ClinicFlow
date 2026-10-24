import io

from models import doctors
from services import csv_import
from tests.conftest import HEADER, csv_file

GOOD = HEADER + (
    "Dr. A (Sample),Cardiology,Demo Clinic,Northvale,(555) 010-0001,a@example.org,FICTIONAL,2025-01-01\n"
    "Dr. B (Sample),Dermatology,Demo Clinic,Eastmere,,,,\n")


def _import(post, text, name="doctors.csv"):
    return post("/doctors/import", {**csv_file(text, name)}, content_type="multipart/form-data")


def test_valid_import_and_search(client, post):
    resp = _import(post, GOOD)
    html = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert "Imported 2 record(s)." in html or "<dd>2</dd>" in html
    with client.application.app_context():
        assert doctors.count() == 2
        rows, _ = doctors.search(q="cardio")
        assert [r["name"] for r in rows] == ["Dr. A (Sample)"]
        rows, _ = doctors.search(city="eastmere")  # case-insensitive filter
        assert [r["name"] for r in rows] == ["Dr. B (Sample)"]
        rows, _ = doctors.search(specialty="Cardiology", city="Eastmere")
        assert rows == []
    assert "Missing optional values" in html  # phone/email gaps are reported, not invented
    assert "CSV import of doctors.csv: 2 imported" in client.get("/activity").get_data(as_text=True)


def test_missing_optional_values_stay_empty(client, post):
    _import(post, GOOD)
    with client.application.app_context():
        row = doctors.search(q="Dr. B")[0][0]
        assert row["phone"] is None and row["email"] is None and row["last_verified"] is None


def test_missing_required_column_rejected_with_message(client, post):
    resp = _import(post, "name,specialty,city\nDr. X,Cardiology,Northvale\n")
    assert resp.status_code == 422
    assert "Missing required column(s): practice" in resp.get_data(as_text=True)
    with client.application.app_context():
        assert doctors.count() == 0


def test_row_level_problems_are_reported_and_valid_rows_still_import(client, post):
    text = HEADER + (
        "Dr. Good,Cardiology,Clinic,City,,,,\n"
        ",Cardiology,Clinic,City,,,,\n"                       # missing name
        "Dr. BadEmail,Cardiology,Clinic,City,,nope,,\n"       # bad email
        "Dr. BadPhone,Cardiology,Clinic,City,abc,,,\n"        # bad phone
        "Dr. BadDate,Cardiology,Clinic,City,,,,31/12/2025\n"  # bad date
        "Dr. Future,Cardiology,Clinic,City,,,,2999-01-01\n"   # future date
        "Dr. Extra,Cardiology,Clinic,City,,,,,x,y\n")         # too many values
    report = csv_import.parse_csv(text.encode(), "t.csv")
    assert [r["name"] for r in report.records] == ["Dr. Good"]
    assert len(report.errors) == 6
    messages = " | ".join(e["message"] for e in report.errors)
    for expected in ("missing required value: name", "email is not a valid", "phone is not a valid",
                     "real date", "in the future", "more values than the header"):
        assert expected in messages
    resp = _import(post, text)
    assert resp.status_code == 200 and "Rejected rows" in resp.get_data(as_text=True)
    with client.application.app_context():
        assert doctors.count() == 1


def test_duplicates_within_file_and_against_database(client, post):
    text = HEADER + ("Dr. Dup,Cardiology,Clinic One,City,,,,\n"
                     "  dr.  dup ,Neurology,CLINIC ONE,Other,,,,\n"      # same after normalising
                     "Dr. Dup,Cardiology,Clinic Two,City,,,,\n")          # different practice: allowed
    report = csv_import.parse_csv(text.encode(), "t.csv")
    assert len(report.records) == 2
    assert report.duplicates[0]["reason"] == "duplicate of line 2 in this file"
    _import(post, text)
    resp = _import(post, text)  # second upload: everything already exists
    html = resp.get_data(as_text=True)
    assert "already in the directory" in html
    with client.application.app_context():
        assert doctors.count() == 2


def test_header_aliases_and_bom_and_unknown_columns():
    text = "\ufeffDoctor Name,Specialty,Clinic,Region,Notes\nDr. Z,Neurology,C,R,ignore me\n"
    report = csv_import.parse_csv(text.encode("utf-8"), "t.csv")
    assert report.file_error == "" and len(report.records) == 1
    assert report.unknown_columns == ["Notes"]


def test_file_level_failures():
    assert "empty" in csv_import.parse_csv(b"", "t.csv").file_error
    assert "UTF-8" in csv_import.parse_csv("é".encode("latin-1") + b",x\n", "t.csv").file_error
    assert "text CSV" in csv_import.parse_csv(b"name,specialty\x00\n", "t.csv").file_error
    assert "Duplicate column" in csv_import.parse_csv(b"name,name,specialty,practice,city\n", "t.csv").file_error
    assert "Malformed" in csv_import.parse_csv((HEADER + '"Dr. Q,x\n').encode(), "t.csv").file_error
    many = HEADER + "".join(f"Dr {i},S,P{i},C,,,,\n" for i in range(6))
    assert "Too many rows" in csv_import.parse_csv(many.encode(), "t.csv", max_rows=5).file_error


def test_upload_type_and_size_restrictions(app, client, post):
    assert post("/doctors/import", {}, content_type="multipart/form-data").status_code == 400
    assert _import(post, GOOD, "doctors.txt").status_code == 400
    assert _import(post, GOOD, "../../evil.csv").status_code == 200  # path stripped, still valid
    app.config["MAX_CONTENT_LENGTH"] = 200
    resp = _import(post, HEADER + "Dr. Big,Cardiology,Clinic,City,,,," + "x" * 500 + "\n")
    assert resp.status_code == 413
    assert "too large" in resp.get_data(as_text=True)


def test_bundled_sample_files(client, post):
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent / "sample_data"
    clean = csv_import.parse_csv((root / "doctors_sample.csv").read_bytes(), "s.csv")
    assert clean.file_error == "" and len(clean.records) == 12 and not clean.errors
    assert all("Sample" in r["name"] for r in clean.records)
    messy = csv_import.parse_csv((root / "doctors_sample_with_errors.csv").read_bytes(), "e.csv")
    assert len(messy.records) == 2 and len(messy.errors) == 5 and len(messy.duplicates) == 1
    resp = _import(post, (root / "doctors_sample.csv").read_bytes(), "doctors_sample.csv")
    assert resp.status_code == 200
    with client.application.app_context():
        assert doctors.count() == 12
