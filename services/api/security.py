import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from services.api.dependencies import UserTables
from services.api.models import User
from services.api.services.users import get_user_by_id


JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY") or secrets.token_urlsafe(32)
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
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