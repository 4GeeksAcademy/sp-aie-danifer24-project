import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from tinydb import TinyDB
from tinydb.storages import MemoryStorage

os.environ.setdefault("JWT_SECRET_KEY", "pytest-only-secret-not-for-production")

from services.api.dependencies import get_request_tables
from services.api.main import app


@pytest.fixture
def api():
    database = TinyDB(storage=MemoryStorage)
    tables = tuple(
        database.table(name)
        for name in ("users", "profiles", "suppliers", "password_resets")
    )
    app.dependency_overrides[get_request_tables] = lambda: tables
    with patch("services.api.routes.auth.send_reset_email") as mail:
        with TestClient(app) as client:
            try:
                yield client, tables, mail
            finally:
                app.dependency_overrides.clear()
                database.close()


@pytest.fixture
def register():
    def _register(client, email="person@example.test", password="initial-password"):
        response = client.post("/users", json={"email": email, "password": password})
        assert response.status_code == 201, response.text
        return response.json()

    return _register


@pytest.fixture
def login():
    def _login(client, email="person@example.test", password="initial-password"):
        return client.post("/auth/login", json={"email": email, "password": password})

    return _login


@pytest.fixture
def reset_token():
    def _reset_token(client, mail, email="person@example.test"):
        response = client.post("/auth/forgot-password", json={"email": email})
        assert response.status_code == 200
        return mail.call_args.args[1]

    return _reset_token
