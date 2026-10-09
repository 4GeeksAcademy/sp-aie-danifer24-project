import pytest


@pytest.mark.parametrize("email", ["person@example.test", " PERSON@example.test "])
def test_login_returns_valid_bearer_token_for_normalized_email(api, register, login, email):
    client, _, _ = api
    register(client)

    response = login(client, email=email)

    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"
    assert response.json()["access_token"]
    me = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {response.json()['access_token']}"},
    )
    assert me.status_code == 200


def test_login_rejects_unknown_wrong_password_and_inactive_user_identically(api, register, login):
    client, tables, _ = api
    register(client)
    register(client, email="inactive@example.test")
    tables[0].update({"is_active": False}, doc_ids=[2])

    responses = [
        login(client, email="missing@example.test"),
        login(client, password="incorrect-password"),
        login(client, email="inactive@example.test"),
    ]

    assert [response.status_code for response in responses] == [401, 401, 401]
    assert len({response.json()["detail"] for response in responses}) == 1


def test_login_rejects_malformed_or_incomplete_request(api):
    client, _, _ = api
    responses = [
        client.post("/auth/login", json={"email": "invalid", "password": "secret"}),
        client.post("/auth/login", json={"email": "person@example.test"}),
        client.post(
            "/auth/login",
            json={"email": "person@example.test", "password": "secret", "extra": True},
        ),
    ]

    assert [response.status_code for response in responses] == [422, 422, 422]
