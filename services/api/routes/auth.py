from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from passlib.hash import bcrypt

from services.api.dependencies import UserTables
from services.api.models import TokenResponse
from services.api.security import create_access_token
from services.api.services.users import get_user_by_email


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/token", response_model=TokenResponse)
def issue_token(
	form: Annotated[OAuth2PasswordRequestForm, Depends()],
	tables: UserTables,
):
	user = get_user_by_email(tables[0], form.username)
	try:
		password_matches = user is not None and bcrypt.verify(
			form.password, user.hashed_password
		)
	except (ValueError, TypeError):
		password_matches = False
	if not password_matches or not user.is_active:
		raise HTTPException(
			status_code=status.HTTP_401_UNAUTHORIZED,
			detail="Email o contraseña incorrectos",
			headers={"WWW-Authenticate": "Bearer"},
		)
	return TokenResponse(access_token=create_access_token(user.id))