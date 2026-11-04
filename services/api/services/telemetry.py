"""Privacy-preserving identifiers used by telemetry consumers."""

import hashlib
import hmac
import os


def telemetry_user_id(user_id: int) -> str | None:
	key = os.environ.get("TELEMETRY_PSEUDONYM_KEY")
	if key is None or len(key.encode("utf-8")) < 32:
		return None

	environment = os.environ.get("TELEMETRY_ENVIRONMENT", "development")
	message = f"nexova:telemetry:user:v1:{environment}:{user_id}".encode("utf-8")
	digest = hmac.new(key.encode("utf-8"), message, hashlib.sha256).hexdigest()
	return f"u1_{digest}"