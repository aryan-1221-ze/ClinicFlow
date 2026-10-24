import io

import pytest

from app import create_app


@pytest.fixture(autouse=True)
def no_ai_keys(monkeypatch):
    for var in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "AI_PROVIDER"):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def app(tmp_path):
    return create_app({"TESTING": True, "DATABASE_PATH": str(tmp_path / "test.db"),
                       "AUTO_SEED": False, "SECRET_KEY": "test-secret", "PER_PAGE": 5})


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def token(client):
    client.get("/")
    with client.session_transaction() as sess:
        return sess["csrf_token"]


@pytest.fixture
def post(client, token):
    def _post(url, data=None, **kwargs):
        data = dict(data or {})
        data.setdefault("csrf_token", token)
        return client.post(url, data=data, **kwargs)
    return _post


@pytest.fixture
def post_json(client, token):
    def _post(url, payload):
        return client.post(url, json=payload, headers={"X-CSRF-Token": token})
    return _post


VALID_APPT = {"patient_name": "Demo Patient", "appointment_date": "2030-05-20",
              "appointment_time": "10:30", "doctor_or_specialty": "Cardiology", "notes": "demo"}


@pytest.fixture
def make_appt(post):
    def _make(**overrides):
        resp = post("/appointments/new", {**VALID_APPT, **overrides})
        assert resp.status_code == 302, resp.data
        return int(resp.headers["Location"].rstrip("/").split("/")[-1])
    return _make


def csv_file(text, name="doctors.csv"):
    return {"file": (io.BytesIO(text.encode("utf-8") if isinstance(text, str) else text), name)}


HEADER = "name,specialty,practice,city,phone,email,source,last_verified\n"
