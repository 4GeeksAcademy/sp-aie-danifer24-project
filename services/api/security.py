import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated

from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from services.api.dependencies import UserTables
from services.api.models import User
from services.api.services.users import get_user_by_id


load_dotenv(Path(__file__).resolve().parents[2] / ".env")

JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY")
if not JWT_SECRET_KEY:
	raise RuntimeError("JWT_SECRET_KEY must be configured in .env or the environment")

JWT_ALGORITHM = "HS256"
try:
	ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
except ValueError as error:
	raise RuntimeError("ACCESS_TOKEN_EXPIRE_MINUTES must be a positive integer") from error
if ACCESS_TOKEN_EXPIRE_MINUTES <= 0:
	raise RuntimeError("ACCESS_TOKEN_EXPIRE_MINUTES must be a positive integer")

bearer_scheme = HTTPBearer(auto_error=False)


def create_access_token(user_id: int) -> str:
	expires_at = datetime.now(timezone.utc) + timedelta(
		minutes=ACCESS_TOKEN_EXPIRE_MINUTES
	)
	return jwt.encode(
		{"sub": str(user_id), "exp": expires_at},
		JWT_SECRET_KEY,
		algorithm=JWT_ALGORITHM,
	)


def get_current_user(
	credentials: Annotated[
		HTTPAuthorizationCredentials | None,
		Depends(bearer_scheme),
	],
	tables: UserTables,
) -> User:
	unauthorized = HTTPException(
		status_code=status.HTTP_401_UNAUTHORIZED,
		detail="Credenciales no válidas",
		headers={"WWW-Authenticate": "Bearer"},
	)
	if credentials is None:
		raise unauthorized
	try:
		payload = jwt.decode(
			credentials.credentials,
			JWT_SECRET_KEY,
			algorithms=[JWT_ALGORITHM],
		)
		user_id = int(payload.get("sub", ""))
	except (JWTError, TypeError, ValueError) as error:
		raise unauthorized from error

	user = get_user_by_id(tables[0], user_id)
	if user is None or not user.is_active:
		raise unauthorized
	return user


CurrentUser = Annotated[User, Depends(get_current_user)]