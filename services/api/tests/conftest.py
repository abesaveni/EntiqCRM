"""
Test harness: in-memory SQLite (StaticPool so every session shares one connection),
ENV=test (rate limiter off), a fixed SECRET_KEY. Each test gets fresh tables.
"""
import os

os.environ["ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["SECRET_KEY"] = "test-secret-key-that-is-definitely-long-enough-0123456789"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.database import Base, engine  # noqa: E402
from app.core.tenancy import set_tenant  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402  — not `app`: `import app.models` would rebind it to the package
from app import models as _models  # noqa: E402,F401  — registers every table on Base.metadata


@pytest.fixture(autouse=True)
def _fresh_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    set_tenant(None)
    yield
    set_tenant(None)


@pytest.fixture
def client():
    with TestClient(fastapi_app) as c:
        yield c


STRONG_PW = "Correct-Horse-Battery-9!"


def signup(client: TestClient, practice="Ashfield Partners", email="priya@ashfield.example", name="Priya Nair", last4="4242"):
    r = client.post("/api/v1/auth/signup", json={
        "practice_name": practice, "abn": "62 114 887 302", "full_name": name, "email": email,
        "password": STRONG_PW, "payment_method": {"last4": last4, "brand": "visa"},
    })
    assert r.status_code == 201, r.text
    return r.json()


def auth(tokens) -> dict:
    return {"Authorization": f"Bearer {tokens['access_token']}"}
