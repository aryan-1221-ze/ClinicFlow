import re

from models import appointments
from tests.conftest import VALID_APPT


def _count(client, snippet):
    return client.get("/").get_data(as_text=True).count(snippet)


def test_key_routes_start_and_render(client):
    for path in ["/", "/appointments", "/appointments/new", "/doctors", "/assistant",
                 "/activity", "/settings"]:
        assert client.get(path).status_code == 200, path
    assert client.get("/appointments/9999").status_code == 404
    assert "Page not found" in client.get("/nope").get_data(as_text=True)


def test_security_headers_present(client):
    resp = client.get("/")
    assert "default-src 'self'" in resp.headers["Content-Security-Policy"]
    assert resp.headers["X-Content-Type-Options"] == "nosniff"


def test_post_without_csrf_token_is_rejected(client):
    resp = client.post("/appointments/new", data=VALID_APPT)
    assert resp.status_code == 400
    assert "out of date" in resp.get_data(as_text=True)
    with client.application.app_context():
        assert appointments.count() == 0


def test_create_appointment_persists_and_logs(client, post, make_appt):
    appt_id = make_appt()
    page = client.get(f"/appointments/{appt_id}").get_data(as_text=True)
    assert "Demo Patient" in page and "Pending" in page
    assert "Appointment request #1 created." in client.get("/activity").get_data(as_text=True)


def test_create_appointment_validation_errors(client, post):
    bad = {"patient_name": "", "appointment_date": "2030-02-31", "appointment_time": "25:99",
           "doctor_or_specialty": "", "notes": "x" * 501}
    resp = post("/appointments/new", bad)
    assert resp.status_code == 422
    html = resp.get_data(as_text=True)
    for field in ("patient_name", "appointment_date", "appointment_time",
                  "doctor_or_specialty", "notes"):
        assert f'id="{field}-error"' in html
    with client.application.app_context():
        assert appointments.count() == 0


def test_html_in_input_is_escaped(client, make_appt):
    appt_id = make_appt(patient_name="<script>alert(1)</script>")
    html = client.get(f"/appointments/{appt_id}").get_data(as_text=True)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_sql_metacharacters_are_stored_literally(client, make_appt):
    appt_id = make_appt(patient_name="Robert'); DROP TABLE appointments;--")
    assert client.get(f"/appointments/{appt_id}").status_code == 200
    assert client.get("/appointments").status_code == 200


def test_edit_appointment_and_status_change_logged(client, post, make_appt):
    appt_id = make_appt()
    resp = post(f"/appointments/{appt_id}/edit",
                {**VALID_APPT, "doctor_or_specialty": "Dermatology", "status": "Confirmed"})
    assert resp.status_code == 302
    with client.application.app_context():
        row = appointments.get(appt_id)
        assert row["doctor_or_specialty"] == "Dermatology" and row["status"] == "Confirmed"
    log = client.get("/activity").get_data(as_text=True)
    assert "from Pending to Confirmed" in log and "doctor or specialty" in log


def test_edit_rejects_invalid_status(post, make_appt):
    appt_id = make_appt()
    resp = post(f"/appointments/{appt_id}/edit", {**VALID_APPT, "status": "Booked"})
    assert resp.status_code == 422


def test_quick_confirm_and_invalid_quick_status(client, post, make_appt):
    appt_id = make_appt()
    assert post(f"/appointments/{appt_id}/status", {"status": "Confirmed"}).status_code == 302
    with client.application.app_context():
        assert appointments.get(appt_id)["status"] == "Confirmed"
    assert post(f"/appointments/{appt_id}/status", {"status": "Cancelled"}).status_code == 400
    assert post(f"/appointments/{appt_id}/status", {"status": "nonsense"}).status_code == 400


def test_open_redirect_target_is_ignored(post, make_appt):
    appt_id = make_appt()
    resp = post(f"/appointments/{appt_id}/status", {"status": "Confirmed", "next": "//evil.example"})
    assert resp.headers["Location"].endswith("/appointments")


def test_cancel_requires_confirmation_then_keeps_record(client, post, make_appt):
    appt_id = make_appt()
    page = client.get(f"/appointments/{appt_id}/cancel")
    assert page.status_code == 200 and "Cancel request" in page.get_data(as_text=True)
    with client.application.app_context():
        assert appointments.get(appt_id)["status"] == "Pending"  # GET changed nothing
    assert post(f"/appointments/{appt_id}/cancel").status_code == 302
    with client.application.app_context():
        assert appointments.get(appt_id)["status"] == "Cancelled"


def test_delete_requires_confirmation_then_removes(client, post, make_appt):
    appt_id = make_appt()
    assert client.get(f"/appointments/{appt_id}/delete").status_code == 200
    with client.application.app_context():
        assert appointments.get(appt_id) is not None
    assert post(f"/appointments/{appt_id}/delete").status_code == 302
    assert client.get(f"/appointments/{appt_id}").status_code == 404
    assert "deleted" in client.get("/activity").get_data(as_text=True)


def test_dashboard_stats_follow_database(client, post, make_appt):
    page = client.get("/").get_data(as_text=True)
    assert "0 appointment requests in total" in page
    a, b, c = make_appt(), make_appt(patient_name="B"), make_appt(patient_name="C")
    post(f"/appointments/{b}/status", {"status": "Confirmed"})
    post(f"/appointments/{c}/cancel")
    with client.application.app_context():
        s = appointments.stats()
    assert (s["total"], s["pending"], s["confirmed"], s["cancelled"]) == (3, 1, 1, 1)
    page = client.get("/").get_data(as_text=True)
    assert "3 appointment requests in total" in page
    assert "1 pending, 1 confirmed, 1 cancelled" in page
    post(f"/appointments/{a}/delete")
    with client.application.app_context():
        assert appointments.stats()["total"] == 2


def test_upcoming_excludes_cancelled_and_past(client, post, make_appt):
    make_appt(patient_name="FutureOne")
    make_appt(patient_name="PastOne", appointment_date="2001-01-01")
    cancelled = make_appt(patient_name="CancelledOne")
    post(f"/appointments/{cancelled}/cancel")
    with client.application.app_context():
        names = [r["patient_name"] for r in appointments.upcoming()]
    assert names == ["FutureOne"]


def test_search_and_filter_appointments(client, post, make_appt):
    make_appt(patient_name="Alice Demo", doctor_or_specialty="Cardiology")
    b = make_appt(patient_name="Bob Demo", doctor_or_specialty="Dermatology", appointment_date="2030-06-01")
    post(f"/appointments/{b}/status", {"status": "Confirmed"})
    with client.application.app_context():
        rows, meta = appointments.search(q="alice")
        assert [r["patient_name"] for r in rows] == ["Alice Demo"]
        rows, _ = appointments.search(status="Confirmed")
        assert [r["patient_name"] for r in rows] == ["Bob Demo"]
        rows, _ = appointments.search(date_from="2030-05-25")
        assert [r["patient_name"] for r in rows] == ["Bob Demo"]
        rows, _ = appointments.search(q="derm", status="Pending")
        assert rows == []
        rows, _ = appointments.search(status="not-a-status")  # ignored, not an error
        assert len(rows) == 2
        rows, _ = appointments.search(q="%")  # wildcard is literal
        assert rows == []
    assert "No requests match these filters" in client.get("/appointments?q=zzz").get_data(as_text=True)


def test_pagination(client, make_appt):
    for i in range(7):
        make_appt(patient_name=f"P{i}")
    page2 = client.get("/appointments?page=2").get_data(as_text=True)
    assert "Page 2 of 2" in page2
    assert client.get("/appointments?page=abc").status_code == 200
    assert client.get("/appointments?page=999").status_code == 200


def test_settings_validation_and_update(client, post):
    assert post("/settings", {"clinic_name": "  "}).status_code == 422
    assert post("/settings", {"clinic_name": "x" * 81}).status_code == 422
    assert post("/settings", {"clinic_name": "Riverside Demo"}).status_code == 302
    assert "Riverside Demo" in client.get("/settings").get_data(as_text=True)
