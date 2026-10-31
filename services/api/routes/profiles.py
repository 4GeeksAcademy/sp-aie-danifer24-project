from fastapi import APIRouter, HTTPException

from services.api.dependencies import UserTables
from services.api.models import Profile, ProfileResponse, ProfileUpdate
from services.api.security import CurrentUser
from services.api.services.profiles import get_profile_by_user_id, update_profile


router = APIRouter(prefix="/profiles", tags=["profiles"])


@router.get("/me", response_model=ProfileResponse)
def retrieve_my_profile(tables: UserTables, current_user: CurrentUser):
	profile = get_profile_by_user_id(tables[1], current_user.id)
	if profile is None:
		raise HTTPException(status_code=404, detail="Perfil no encontrado")
	return ProfileResponse.model_validate(profile, from_attributes=True)


@router.put("/me", response_model=ProfileResponse)
def replace_my_profile(
	request: ProfileUpdate,
	tables: UserTables,
	current_user: CurrentUser,
):
	profile = update_profile(tables[1], current_user.id, request)
	if profile is None:
		raise HTTPException(status_code=404, detail="Perfil no encontrado")
	return ProfileResponse.model_validate(profile, from_attributes=True)