from tinydb import Query
from tinydb.table import Table

from services.api.models import Profile, ProfileUpdate


def _to_profile(document) -> Profile:
	return Profile(**{**dict(document), "id": document.doc_id})


def get_profile_by_user_id(profiles: Table, user_id: int) -> Profile | None:
	document = profiles.get(Query().user_id == user_id)
	return _to_profile(document) if document is not None else None


def update_profile(
	profiles: Table,
	user_id: int,
	request: ProfileUpdate,
) -> Profile | None:
	profile = get_profile_by_user_id(profiles, user_id)
	if profile is None:
		return None
	profiles.update(request.model_dump(exclude_unset=True), doc_ids=[profile.id])
	return get_profile_by_user_id(profiles, user_id)