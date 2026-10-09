def test_register_creates_user_with_normalized_email_and_profile(api, register):
    client, tables, _ = api

    response = client.post(
        "/users",
        json={"email": " Person@Example.Test ", "password": "initial-password", "name": "Person"},
    )

    assert response.status_code == 201
    assert response.json()["email"] == "person@example.test"
    assert tables[0].all()[0]["email"] == "person@example.test"
    assert tables[1].all()[0]["name"] == "Person"


def test_register_rejects_duplicate_email(api, register):
    client, _, _ = api
    register(client)

    response = client.post(
        "/users", json={"email": "PERSON@example.test", "password": "another-password"}
    )

    assert response.status_code == 409
    assert response.json()["code"] == "conflict"


def test_register_rejects_invalid_email_short_or_overlong_password(api):
    client, _, _ = api
    responses = [
        client.post("/users", json={"email": "not-an-email", "password": "initial-password"}),
        client.post("/users", json={"email": "ok@example.test", "password": "short"}),
        client.post("/users", json={"email": "ok@example.test", "password": "é" * 37}),
    ]

    assert [response.status_code for response in responses] == [422, 422, 422]
