import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.hash import bcrypt
from tinydb import Query
from tinydb.table import Table

from services.api.models import User, UserUpdate
from services.api.security import JWT_ALGORITHM, JWT_SECRET_KEY
from services.api.services.users import get_user_by_id, update_user


RESET_TOKEN_MINUTES = 30


class InvalidResetTokenError(Exception):
	pass


def password_matches(password: str, hashed_password: str) -> bool:
	try:
		return bcrypt.verify(password, hashed_password)
	except (ValueError, TypeError):
		return False


def digest(value: str) -> str:
	return hashlib.sha256(value.encode("utf-8")).hexdigest()


def create_reset_token(user: User, resets: Table) -> str:
	now = datetime.now(timezone.utc)
	expires_at = now + timedelta(minutes=RESET_TOKEN_MINUTES)
	token = jwt.encode(
		{
			"sub": str(user.id),
			"purpose": "password_reset",
			"jti": secrets.token_urlsafe(32),
			"iat": now,
			"exp": expires_at,
		},
		JWT_SECRET_KEY,
		algorithm=JWT_ALGORITHM,
	)
	resets.remove(Query().expires_at <= now.timestamp())
	resets.insert({
		"token_digest": digest(token),
		"user_id": user.id,
		"expires_at": expires_at.timestamp(),
		"password_digest": digest(user.hashed_password),
	})
	return token


def reset_password(users: Table, resets: Table, token: str, new_password: str) -> None:
	try:
		payload = jwt.decode(
			token,
			JWT_SECRET_KEY,
			algorithms=[JWT_ALGORITHM],
			options={"require_exp": True, "require_sub": True, "require_jti": True},
		)
		if payload.get("purpose") != "password_reset":
			raise InvalidResetTokenError()
		user_id = int(payload["sub"])
	except (JWTError, ValueError, TypeError, KeyError) as error:
		raise InvalidResetTokenError() from error

	record = resets.get(Query().token_digest == digest(token))
	user = get_user_by_id(users, user_id)
	if (
		record is None or user is None or not user.is_active
		or record["user_id"] != user_id
		or record["expires_at"] <= datetime.now(timezone.utc).timestamp()
		or not secrets.compare_digest(record["password_digest"], digest(user.hashed_password))
	):
		raise InvalidResetTokenError()
	update_user(users, user_id, UserUpdate(password=new_password))
	resets.remove(Query().user_id == user_id)


def change_password(users: Table, resets: Table, user: User, new_password: str) -> None:
	update_user(users, user.id, UserUpdate(password=new_password))
	resets.remove(Query().user_id == user.id)