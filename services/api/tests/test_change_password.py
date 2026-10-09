def test_change_password_updates_current_users_password(api, register, login):
    client, _, _ = api
    register(client)
    token = login(client).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    response = client.post(
        "/auth/change-password",
        headers=headers,
        json={"current_password": "initial-password", "new_password": "changed-password"},
    )

    assert response.status_code == 200
    assert login(client, password="changed-password").status_code == 200
    assert login(client).status_code == 401


def test_change_password_rejects_missing_session_and_wrong_current_password(api, register, login):
    client, _, _ = api
    register(client)
    body = {"current_password": "wrong-password", "new_password": "changed-password"}
    assert client.post("/auth/change-password", json=body).status_code == 401

    token = login(client).json()["access_token"]
    response = client.post(
        "/auth/change-password",
        headers={"Authorization": f"Bearer {token}"},
        json=body,
    )

    assert response.status_code == 400
    assert response.json()["code"] == "bad_request"


def test_change_password_requires_fields_and_valid_new_password(api, register, login):
    client, _, _ = api
    register(client)
    token = login(client).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    responses = [
        client.post("/auth/change-password", headers=headers, json={"new_password": "changed-password"}),
        client.post("/auth/change-password", headers=headers, json={"current_password": "initial-password", "new_password": "short"}),
        client.post("/auth/change-password", headers=headers, json={"current_password": "initial-password", "new_password": "x" * 73}),
    ]

    assert [response.status_code for response in responses] == [422, 422, 422]
