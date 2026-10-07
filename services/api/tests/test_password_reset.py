import json
import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from urllib.error import HTTPError

os.environ.setdefault("JWT_SECRET_KEY", "test-only-signing-key-not-for-production")

from fastapi.testclient import TestClient
from jose import jwt
from tinydb import TinyDB
from tinydb.storages import MemoryStorage

from services.api.dependencies import get_request_tables
from services.api.main import app
from services.api.security import JWT_ALGORITHM, JWT_SECRET_KEY
from services.api.services.email import send_reset_email
from services.api.services.passwords import digest


class PasswordResetTests(unittest.TestCase):
	def setUp(self):
		self.database = TinyDB(storage=MemoryStorage)
		self.tables = tuple(self.database.table(name) for name in ("users", "profiles", "suppliers", "password_resets"))
		app.dependency_overrides[get_request_tables] = lambda: self.tables
		self.client = TestClient(app)
		self.client.__enter__()
		self.mail_patch = patch("services.api.routes.auth.send_reset_email")
		self.mail = self.mail_patch.start()
		response = self.client.post("/users", json={"email": "test@example.test", "password": "initial-password"})
		self.assertEqual(response.status_code, 201)

	def tearDown(self):
		self.mail_patch.stop()
		self.client.__exit__(None, None, None)
		app.dependency_overrides.clear()
		self.database.close()

	def request_token(self):
		response = self.client.post("/auth/forgot-password", json={"email": " TEST@example.test "})
		self.assertEqual(response.status_code, 200)
		return self.mail.call_args.args[1]

	def session_headers(self):
		response = self.client.post("/auth/login", json={"email": "test@example.test", "password": "initial-password"})
		return {"Authorization": f"Bearer {response.json()['access_token']}"}

	def reset(self, token, password="replacement-password"):
		return self.client.post("/auth/reset-password", json={"token": token, "new_password": password})

	def test_forgot_response_does_not_reveal_account(self):
		known = self.client.post("/auth/forgot-password", json={"email": "test@example.test"})
		unknown = self.client.post("/auth/forgot-password", json={"email": "missing@example.test"})
		self.assertEqual(known.status_code, 200)
		self.assertEqual(unknown.status_code, 200)
		self.assertEqual(known.json(), unknown.json())
		self.assertEqual(self.mail.call_count, 1)

	def test_token_is_hashed_and_valid_for_thirty_minutes(self):
		token = self.request_token()
		record = self.tables[3].all()[0]
		self.assertEqual(record["token_digest"], digest(token))
		self.assertNotIn(token, json.dumps(record))
		claims = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
		self.assertEqual(claims["exp"] - claims["iat"], 1800)

	def test_reset_is_single_use_and_updates_password_hash(self):
		token = self.request_token()
		previous_hash = self.tables[0].all()[0]["hashed_password"]
		self.assertEqual(self.reset(token).status_code, 200)
		self.assertEqual(self.reset(token).status_code, 400)
		self.assertNotEqual(self.tables[0].all()[0]["hashed_password"], previous_hash)
		self.assertEqual(self.tables[3].all(), [])
		self.assertEqual(self.client.post("/auth/login", json={"email": "test@example.test", "password": "replacement-password"}).status_code, 200)
		self.assertEqual(self.client.post("/auth/login", json={"email": "test@example.test", "password": "initial-password"}).status_code, 401)

	def test_invalid_expired_tampered_and_session_tokens_rejected(self):
		token = self.request_token()
		claims = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
		claims["exp"] = datetime.now(timezone.utc) - timedelta(minutes=1)
		expired = jwt.encode(claims, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
		parts = token.split(".")
		parts[2] = ("A" if parts[2][0] != "A" else "B") + parts[2][1:]
		access = self.session_headers()["Authorization"].split(" ")[1]
		for invalid in ("", "bad-token", expired, ".".join(parts), access):
			with self.subTest(token_type=invalid[:5]):
				self.assertEqual(self.reset(invalid).status_code, 400)
		self.assertEqual(self.reset(token).status_code, 200)

	def test_reset_token_cannot_authenticate_session(self):
		token = self.request_token()
		self.assertEqual(self.client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code, 401)

	def test_changing_password_requires_session_and_current_password(self):
		token = self.request_token()
		headers = self.session_headers()
		body = {"current_password": "wrong-password", "new_password": "changed-password"}
		self.assertEqual(self.client.post("/auth/change-password", json=body).status_code, 401)
		self.assertEqual(self.client.post("/auth/change-password", headers=headers, json=body).status_code, 400)
		body["current_password"] = "initial-password"
		self.assertEqual(self.client.post("/auth/change-password", headers=headers, json=body).status_code, 200)
		self.assertEqual(self.reset(token).status_code, 400)
		self.assertEqual(self.client.post("/auth/login", json={"email": "test@example.test", "password": "changed-password"}).status_code, 200)

	def test_other_reset_links_are_invalidated(self):
		first = self.request_token()
		second = self.request_token()
		self.assertEqual(self.reset(first).status_code, 200)
		self.assertEqual(self.reset(second).status_code, 400)

	def test_new_password_obeys_bcrypt_limits(self):
		token = self.request_token()
		for password in ("short", "a" * 73, "é" * 37):
			self.assertEqual(self.reset(token, password).status_code, 422)
		self.assertEqual(self.reset(token).status_code, 200)

	def test_disabled_user_and_deleted_user_cannot_reset(self):
		token = self.request_token()
		self.tables[0].update({"is_active": False}, doc_ids=[1])
		self.assertEqual(self.reset(token).status_code, 400)
		self.mail.reset_mock()
		self.assertEqual(self.client.post("/auth/forgot-password", json={"email": "test@example.test"}).status_code, 200)
		self.mail.assert_not_called()
		self.tables[0].remove(doc_ids=[1])
		self.assertEqual(self.reset(token).status_code, 400)

	def test_forgot_survives_email_service_failure(self):
		with patch.dict(os.environ, {"RESEND_API_KEY": ""}), patch("services.api.services.email.logger.error") as log:
			self.mail.side_effect = send_reset_email
			response = self.client.post("/auth/forgot-password", json={"email": "test@example.test"})
			self.assertEqual(response.status_code, 200)
			log.assert_called_once()


class ResetEmailTests(unittest.TestCase):
	def test_resend_payload_and_mobile_template(self):
		settings = {"RESEND_API_KEY": "test-key", "RESEND_FROM_EMAIL": "Nexova <noreply@example.test>", "PASSWORD_RESET_URL": "https://app.example.test/reset-password"}
		with patch.dict(os.environ, settings), patch("services.api.services.email.urlopen") as transport:
			send_reset_email("recipient@example.test", "signed-test-token")
			request = transport.call_args.args[0]
			self.assertEqual(request.full_url, "https://api.resend.com/emails")
			self.assertEqual(request.get_header("Authorization"), "Bearer test-key")
			payload = json.loads(request.data)
			self.assertEqual(payload["to"], ["recipient@example.test"])
			self.assertIn("https://app.example.test/reset-password?token=signed-test-token", payload["text"])
			self.assertIn('name="viewport"', payload["html"])
			self.assertIn("30 minutos", payload["text"])

	def test_provider_failure_does_not_log_secrets(self):
		settings = {"RESEND_API_KEY": "test-key", "RESEND_FROM_EMAIL": "noreply@example.test", "PASSWORD_RESET_URL": "https://app.example.test/reset-password"}
		with patch.dict(os.environ, settings), patch("services.api.services.email.urlopen", side_effect=HTTPError("https://api.resend.com/emails", 429, "rate limited", {}, None)), patch("services.api.services.email.logger.error") as log:
			send_reset_email("recipient@example.test", "signed-test-token")
			log.assert_called_once()
			self.assertNotIn("test-key", str(log.call_args))
			self.assertNotIn("signed-test-token", str(log.call_args))


if __name__ == "__main__":
	unittest.main()