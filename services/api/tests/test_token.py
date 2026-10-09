from datetime import datetime, timedelta, timezone

from jose import jwt

from services.api.security import JWT_ALGORITHM, JWT_SECRET_KEY


def test_token_endpoint_returns_authenticated_user_and_profile(api, register, login):
    client, _, _ = api
    register(client, email="user@example.test")
    token = login(client, email="user@example.test").json()["access_token"]

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["email"] == "user@example.test"
    assert response.json()["profile"]["user_id"] == 1


def test_token_endpoint_returns_not_found_for_missing_profile(api, register, login):
    client, tables, _ = api
    register(client)
    token = login(client).json()["access_token"]
    tables[1].truncate()

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_token_endpoint_rejects_missing_expired_tampered_and_reset_tokens(api, register, login, reset_token):
    client, _, mail = api
    register(client)
    session = login(client).json()["access_token"]
    reset = reset_token(client, mail)
    claims = jwt.decode(session, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    claims["exp"] = datetime.now(timezone.utc) - timedelta(minutes=1)
    expired = jwt.encode(claims, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    parts = session.split(".")
    parts[2] = ("A" if parts[2][0] != "A" else "B") + parts[2][1:]
    headers = [
        {},
        {"Authorization": "Bearer malformed"},
        {"Authorization": f"Bearer {expired}"},
        {"Authorization": f"Bearer {'.'.join(parts)}"},
        {"Authorization": f"Bearer {reset}"},
    ]

    assert [client.get("/auth/me", headers=header).status_code for header in headers] == [401] * len(headers)
