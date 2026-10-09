import os
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

os.environ.setdefault("JWT_SECRET_KEY", "pytest-only-secret-not-for-production")

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from tinydb import TinyDB
from tinydb.storages import MemoryStorage

from services.api.dependencies import get_request_tables
from services.api.main import app
from services.api.security import JWT_ALGORITHM, JWT_SECRET_KEY


@pytest.fixture
def api():
    database = TinyDB(storage=MemoryStorage)
    tables = tuple(
        database.table(name)
        for name in ("users", "profiles", "suppliers", "password_resets")
    )
    app.dependency_overrides[get_request_tables] = lambda: tables
    with patch("services.api.routes.auth.send_reset_email") as mail, TestClient(app) as client:
        try:
            yield client, tables, mail
        finally:
            app.dependency_overrides.clear()
            database.close()


def register(client, email="person@example.test", password="initial-password"):
    response = client.post("/users", json={"email": email, "password": password})
    assert response.status_code == 201, response.text
    return response.json()


def login(client, email="person@example.test", password="initial-password"):
    return client.post("/auth/login", json={"email": email, "password": password})


def get_reset_token(client, mail, email="person@example.test"):
    response = client.post("/auth/forgot-password", json={"email": email})
    assert response.status_code == 200
    return mail.call_args.args[1]


def test_login_returns_bearer_jwt_and_auth_me_profile(api):
    client, _, _ = api
    register(client)

    response = login(client, " PERSON@example.test ")

    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"
    token = response.json()["access_token"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "person@example.test"
    assert me.json()["role"] == "user"
    assert me.json()["profile"]["user_id"] == 1


def test_login_rejects_unknown_wrong_password_and_inactive_user_identically(api):
    client, tables, _ = api
    register(client)
    inactive = client.post("/users", json={"email": "inactive@example.test", "password": "initial-password"})
    assert inactive.status_code == 201
    tables[0].update({"is_active": False}, doc_ids=[2])

    responses = [
        login(client, "missing@example.test"),
        login(client, password="incorrect-password"),
        login(client, "inactive@example.test"),
    ]
    assert [response.status_code for response in responses] == [401, 401, 401]
    assert len({response.json()["detail"] for response in responses}) == 1


@pytest.mark.parametrize(
    "payload",
    [
        {"email": "invalid", "password": "secret"},
        {"email": "person@example.test"},
        {"email": "person@example.test", "password": "secret", "extra": True},
    ],
)
def test_login_invalid_or_extra_fields_return_422(api, payload):
    client, _, _ = api
    assert client.post("/auth/login", json=payload).status_code == 422


def test_auth_me_rejects_missing_bad_expired_tampered_reset_and_revoked_tokens(api):
    client, tables, mail = api
    register(client)
    session = login(client).json()["access_token"]
    reset_token = get_reset_token(client, mail)
    expired_claims = jwt.decode(session, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    expired_claims["exp"] = datetime.now(timezone.utc) - timedelta(minutes=1)
    expired = jwt.encode(expired_claims, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    parts = session.split(".")
    parts[2] = ("A" if parts[2][0] != "A" else "B") + parts[2][1:]

    responses = [
        client.get("/auth/me"),
        client.get("/auth/me", headers={"Authorization": "Bearer bad-token"}),
        client.get("/auth/me", headers={"Authorization": f"Bearer {expired}"}),
        client.get("/auth/me", headers={"Authorization": f"Bearer {'.'.join(parts)}"}),
        client.get("/auth/me", headers={"Authorization": f"Bearer {reset_token}"}),
    ]
    assert [response.status_code for response in responses] == [401] * 5

    tables[0].update({"is_active": False}, doc_ids=[1])
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {session}"}).status_code == 401


def test_auth_me_returns_not_found_if_profile_is_missing(api):
    client, tables, _ = api
    register(client)
    token = login(client).json()["access_token"]
    tables[1].truncate()

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_forgot_password_has_generic_response_and_emails_only_active_users(api):
    client, tables, mail = api
    register(client)
    client.post("/users", json={"email": "inactive@example.test", "password": "initial-password"})
    tables[0].update({"is_active": False}, doc_ids=[2])

    known = client.post("/auth/forgot-password", json={"email": " PERSON@example.test "})
    unknown = client.post("/auth/forgot-password", json={"email": "unknown@example.test"})
    inactive = client.post("/auth/forgot-password", json={"email": "inactive@example.test"})

    assert known.status_code == unknown.status_code == inactive.status_code == 200
    assert known.json() == unknown.json() == inactive.json()
    assert mail.call_count == 1
    assert mail.call_args.args[0] == "person@example.test"


def test_forgot_password_email_failure_does_not_change_public_response_or_log_secrets(api):
    client, _, mail = api
    register(client)
    mail.side_effect = None
    with patch.dict(os.environ, {"RESEND_API_KEY": ""}), patch("services.api.services.email.logger.error") as log:
        from services.api.services.email import send_reset_email

        mail.side_effect = send_reset_email
        response = client.post("/auth/forgot-password", json={"email": "person@example.test"})

    assert response.status_code == 200
    assert "person@example.test" not in str(log.call_args)


def test_reset_password_is_single_use_changes_credentials_and_invalidates_other_links(api):
    client, tables, mail = api
    register(client)
    first = get_reset_token(client, mail)
    second = get_reset_token(client, mail)

    reset = client.post("/auth/reset-password", json={"token": first, "new_password": "replacement-password"})

    assert reset.status_code == 200
    assert client.post("/auth/reset-password", json={"token": first, "new_password": "another-password"}).status_code == 400
    assert client.post("/auth/reset-password", json={"token": second, "new_password": "another-password"}).status_code == 400
    assert login(client, password="replacement-password").status_code == 200
    assert login(client, password="initial-password").status_code == 401
    assert tables[3].all() == []


def test_reset_tokens_expire_after_thirty_minutes_and_are_not_stored_in_plaintext(api):
    client, tables, mail = api
    register(client)
    token = get_reset_token(client, mail)
    record = tables[3].all()[0]
    claims = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])

    assert claims["exp"] - claims["iat"] == 1800
    assert token not in str(record)

    claims["exp"] = datetime.now(timezone.utc) - timedelta(minutes=1)
    expired = jwt.encode(claims, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    response = client.post("/auth/reset-password", json={"token": expired, "new_password": "replacement-password"})
    assert response.status_code == 400


@pytest.mark.parametrize("token", ["", "invalid"])
def test_reset_password_rejects_invalid_tokens(api, token):
    client, _, _ = api
    response = client.post("/auth/reset-password", json={"token": token, "new_password": "replacement-password"})
    assert response.status_code == 400
    assert response.json()["code"] == "bad_request"


def test_reset_password_rejects_session_tokens_and_password_outside_bcrypt_limits(api):
    client, _, mail = api
    register(client)
    reset_token = get_reset_token(client, mail)
    access_token = login(client).json()["access_token"]

    for token in (access_token, reset_token):
        for password in ("short", "x" * 73, "é" * 37):
            response = client.post("/auth/reset-password", json={"token": token, "new_password": password})
            assert response.status_code in (400, 422)

    valid = client.post("/auth/reset-password", json={"token": reset_token, "new_password": "replacement-password"})
    assert valid.status_code == 200


def test_reset_token_is_invalidated_by_password_change_and_inactive_or_deleted_user(api):
    client, tables, mail = api
    register(client)
    reset_token = get_reset_token(client, mail)
    access_token = login(client).json()["access_token"]
    changed = client.post(
        "/auth/change-password",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"current_password": "initial-password", "new_password": "changed-password"},
    )
    assert changed.status_code == 200
    assert client.post("/auth/reset-password", json={"token": reset_token, "new_password": "replacement-password"}).status_code == 400

    inactive_reset = get_reset_token(client, mail)
    tables[0].update({"is_active": False}, doc_ids=[1])
    assert client.post("/auth/reset-password", json={"token": inactive_reset, "new_password": "replacement-password"}).status_code == 400
    tables[0].remove(doc_ids=[1])
    assert client.post("/auth/reset-password", json={"token": inactive_reset, "new_password": "replacement-password"}).status_code == 400


def test_change_password_requires_bearer_and_current_password(api):
    client, _, _ = api
    register(client)
    body = {"current_password": "initial-password", "new_password": "changed-password"}

    assert client.post("/auth/change-password", json=body).status_code == 401
    token = login(client).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    wrong = client.post("/auth/change-password", headers=headers, json={**body, "current_password": "wrong-password"})
    assert wrong.status_code == 400
    assert wrong.json()["code"] == "bad_request"

    success = client.post("/auth/change-password", headers=headers, json=body)
    assert success.status_code == 200
    assert login(client, password="changed-password").status_code == 200
    assert login(client).status_code == 401


@pytest.mark.parametrize("endpoint,body", [
    ("/auth/forgot-password", {}),
    ("/auth/reset-password", {"token": "x"}),
])
def test_public_password_endpoints_validate_required_fields(api, endpoint, body):
    client, _, _ = api
    assert client.post(endpoint, json=body).status_code == 422


def test_change_password_validates_required_fields_after_authentication(api):
    client, _, _ = api
    register(client)
    token = login(client).json()["access_token"]
    response = client.post(
        "/auth/change-password",
        headers={"Authorization": f"Bearer {token}"},
        json={"new_password": "changed-password"},
    )
    assert response.status_code == 422
