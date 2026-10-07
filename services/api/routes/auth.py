from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from passlib.hash import bcrypt

from services.api.dependencies import PasswordTables, UserTables
from services.api.models import AuthMeResponse, ChangePasswordRequest, ForgotPasswordRequest, LoginRequest, ResetPasswordRequest, TokenResponse
from services.api.security import CurrentUser, create_access_token
from services.api.services.profiles import get_profile_by_user_id
from services.api.services.users import get_user_by_email
from services.api.services.email import send_reset_email
from services.api.services.passwords import InvalidResetTokenError, change_password, create_reset_token, password_matches, reset_password


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/forgot-password")
def forgot_password(request: ForgotPasswordRequest, tables: PasswordTables, background_tasks: BackgroundTasks):
	user = get_user_by_email(tables[0], request.email)
	if user is not None and user.is_active:
		token = create_reset_token(user, tables[1])
		background_tasks.add_task(send_reset_email, user.email, token)
	return {"message": "Si esa dirección está registrada, recibirás un enlace en breve."}


@router.post("/reset-password")
def replace_forgotten_password(request: ResetPasswordRequest, tables: PasswordTables):
	try:
		reset_password(tables[0], tables[1], request.token, request.new_password)
	except InvalidResetTokenError as error:
		raise HTTPException(status_code=400, detail="El enlace no es válido, ha caducado o ya se ha utilizado.") from error
	return {"message": "Contraseña restablecida correctamente."}


@router.post("/change-password")
def replace_current_password(request: ChangePasswordRequest, tables: PasswordTables, current_user: CurrentUser):
	if not password_matches(request.current_password, current_user.hashed_password):
		raise HTTPException(status_code=400, detail="La contraseña actual no es correcta.")
	change_password(tables[0], tables[1], current_user, request.new_password)
	return {"message": "Contraseña actualizada correctamente."}


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