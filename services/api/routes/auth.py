from fastapi import APIRouter, HTTPException, status
from passlib.hash import bcrypt

from services.api.dependencies import UserTables
from services.api.models import AuthMeResponse, LoginRequest, TokenResponse
from services.api.security import CurrentUser, create_access_token
from services.api.services.profiles import get_profile_by_user_id
from services.api.services.users import get_user_by_email


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(request: LoginRequest, tables: UserTables):
	user = get_user_by_email(tables[0], request.email)
	try:
		password_matches = user is not None and bcrypt.verify(
			request.password, user.hashed_password
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


@router.get("/me", response_model=AuthMeResponse)
def retrieve_authenticated_user(tables: UserTables, current_user: CurrentUser):
	profile = get_profile_by_user_id(tables[1], current_user.id)
	if profile is None:
		raise HTTPException(status_code=404, detail="Perfil no encontrado")
	return AuthMeResponse(
		email=current_user.email,
		role=current_user.role,
		profile=profile,
	)