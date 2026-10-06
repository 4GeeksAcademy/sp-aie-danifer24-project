from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Response, status

from services.api.dependencies import UserTables
from services.api.models import User, UserCreate, UserResponse, UserRole, UserUpdate
from services.api.security import CurrentUser
from services.api.services.users import (
	UserAlreadyExistsError,
	create_user,
	delete_user,
	get_user_by_id,
	list_users,
	update_user,
)


router = APIRouter(prefix="/users", tags=["users"])
UserId = Annotated[int, Path(gt=0)]


def _require_owner_or_admin(current_user: User, target_id: int) -> None:
	if current_user.id != target_id and current_user.role is not UserRole.ADMIN:
		raise HTTPException(status_code=403, detail="Permisos insuficientes")


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register_user(request: UserCreate, tables: UserTables):
	try:
		return create_user(tables[0], tables[1], request)
	except UserAlreadyExistsError as error:
		raise HTTPException(status_code=409, detail="El email ya está registrado") from error


@router.get("", response_model=list[UserResponse])
def retrieve_users(tables: UserTables, current_user: CurrentUser):
	return list_users(tables[0])


@router.get("/{user_id}", response_model=UserResponse)
def retrieve_user(user_id: UserId, tables: UserTables, current_user: CurrentUser):
	_require_owner_or_admin(current_user, user_id)
	user = get_user_by_id(tables[0], user_id)
	if user is None:
		raise HTTPException(status_code=404, detail="Usuario no encontrado")
	return user


@router.put("/{user_id}", response_model=UserResponse)
def replace_user(
	user_id: UserId,
	request: UserUpdate,
	tables: UserTables,
	current_user: CurrentUser,
):
	_require_owner_or_admin(current_user, user_id)
	if "role" in request.model_fields_set and current_user.role is not UserRole.ADMIN:
		raise HTTPException(status_code=403, detail="Solo admin puede cambiar roles")
	if "is_active" in request.model_fields_set and current_user.role is not UserRole.ADMIN:
		raise HTTPException(status_code=403, detail="Solo admin puede cambiar el estado")
	try:
		user = update_user(tables[0], user_id, request)
	except UserAlreadyExistsError as error:
		raise HTTPException(status_code=409, detail="El email ya está registrado") from error
	if user is None:
		raise HTTPException(status_code=404, detail="Usuario no encontrado")
	return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_user(
	user_id: UserId,
	tables: UserTables,
	current_user: CurrentUser,
):
	_require_owner_or_admin(current_user, user_id)
	if not delete_user(tables[0], tables[1], user_id):
		raise HTTPException(status_code=404, detail="Usuario no encontrado")
	return Response(status_code=status.HTTP_204_NO_CONTENT)