import os
from unittest.mock import patch

from services.api.services.email import send_reset_email


def test_forgot_password_sends_token_for_active_user_and_generic_response(api, register):
    client, _, mail = api
    register(client)

    response = client.post("/auth/forgot-password", json={"email": " PERSON@example.test "})

    assert response.status_code == 200
    assert response.json() == {"message": "Si esa dirección está registrada, recibirás un enlace en breve."}
    assert mail.call_count == 1
    assert mail.call_args.args[0] == "person@example.test"
    assert mail.call_args.args[1]


def test_forgot_password_does_not_reveal_unknown_or_inactive_accounts(api, register):
    client, tables, mail = api
    register(client)
    register(client, email="inactive@example.test")
    tables[0].update({"is_active": False}, doc_ids=[2])

    known = client.post("/auth/forgot-password", json={"email": "person@example.test"})
    unknown = client.post("/auth/forgot-password", json={"email": "unknown@example.test"})
    inactive = client.post("/auth/forgot-password", json={"email": "inactive@example.test"})

    assert known.status_code == unknown.status_code == inactive.status_code == 200
    assert known.json() == unknown.json() == inactive.json()
    assert mail.call_count == 1


def test_forgot_password_validates_required_email(api):
    client, _, _ = api

    response = client.post("/auth/forgot-password", json={})

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_forgot_password_keeps_generic_response_if_email_provider_fails(api, register):
    client, _, mail = api
    register(client)
    with patch.dict(os.environ, {"RESEND_API_KEY": ""}), patch("services.api.services.email.logger.error") as log:
        mail.side_effect = send_reset_email
        response = client.post("/auth/forgot-password", json={"email": "person@example.test"})

    assert response.status_code == 200
    log.assert_called_once()
    assert "person@example.test" not in str(log.call_args)
