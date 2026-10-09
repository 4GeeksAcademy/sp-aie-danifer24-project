from datetime import datetime, timedelta, timezone

import pytest
from jose import jwt

from services.api.security import JWT_ALGORITHM, JWT_SECRET_KEY


def test_reset_password_changes_credentials_and_consumes_token(api, register, login, reset_token):
    client, tables, mail = api
    register(client)
    token = reset_token(client, mail)

    response = client.post(
        "/auth/reset-password",
        json={"token": token, "new_password": "replacement-password"},
    )

    assert response.status_code == 200
    assert login(client, password="replacement-password").status_code == 200
    assert login(client, password="initial-password").status_code == 401
    assert tables[3].all() == []


def test_reset_password_rejects_reuse_and_invalidates_other_reset_links(api, register, reset_token):
    client, _, mail = api
    register(client)
    first = reset_token(client, mail)
    second = reset_token(client, mail)

    assert client.post("/auth/reset-password", json={"token": first, "new_password": "replacement-password"}).status_code == 200
    assert client.post("/auth/reset-password", json={"token": first, "new_password": "another-password"}).status_code == 400
    assert client.post("/auth/reset-password", json={"token": second, "new_password": "another-password"}).status_code == 400


def test_reset_password_rejects_malformed_expired_and_session_tokens(api, register, login, reset_token):
    client, _, mail = api
    register(client)
    reset = reset_token(client, mail)
    access = login(client).json()["access_token"]
    claims = jwt.decode(reset, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    claims["exp"] = datetime.now(timezone.utc) - timedelta(minutes=1)
    expired = jwt.encode(claims, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

    for token in ("malformed", expired, access):
        response = client.post(
            "/auth/reset-password",
            json={"token": token, "new_password": "replacement-password"},
        )
        assert response.status_code == 400
        assert response.json()["code"] == "bad_request"


def test_reset_password_validates_required_and_bcrypt_boundary_fields(api):
    client, _, _ = api
    missing = client.post("/auth/reset-password", json={"token": "signed"})
    short = client.post("/auth/reset-password", json={"token": "signed", "new_password": "short"})
    too_long = client.post("/auth/reset-password", json={"token": "signed", "new_password": "x" * 73})
    unicode_too_long = client.post("/auth/reset-password", json={"token": "signed", "new_password": "é" * 37})

    assert [r.status_code for r in (missing, short, too_long, unicode_too_long)] == [422] * 4


def test_reset_password_rejects_token_after_user_becomes_inactive_or_is_deleted(api, register, reset_token):
    client, tables, mail = api
    register(client)
    token = reset_token(client, mail)
    tables[0].update({"is_active": False}, doc_ids=[1])
    inactive = client.post("/auth/reset-password", json={"token": token, "new_password": "replacement-password"})
    assert inactive.status_code == 400
    tables[0].remove(doc_ids=[1])
    deleted = client.post("/auth/reset-password", json={"token": token, "new_password": "replacement-password"})
    assert deleted.status_code == 400
