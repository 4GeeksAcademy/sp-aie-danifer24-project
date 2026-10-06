from datetime import datetime, timezone

from passlib.hash import bcrypt
from tinydb import Query
from tinydb.table import Table

from services.api.models import Profile, User, UserCreate, UserRole, UserUpdate


class UserAlreadyExistsError(Exception):
	pass


def _to_user(document) -> User:
	return User(**{**dict(document), "id": document.doc_id})


def create_user(
	users: Table,
	profiles: Table,
	request: UserCreate,
) -> User:
	if get_user_by_email(users, request.email) is not None:
		raise UserAlreadyExistsError(request.email)

	user_document = {
		"email": request.email,
		"hashed_password": bcrypt.hash(request.password),
		"is_active": True,
		"role": UserRole.USER.value,
		"created_at": datetime.now(timezone.utc).isoformat(),
	}
	user_id = users.insert(user_document)
	user_document["id"] = user_id
	profile_id = None
	try:
		users.update({"id": user_id}, doc_ids=[user_id])
		profile = Profile(
			user_id=user_id,
			name=request.name,
			phone=request.phone,
			address=request.address,
		)
		profile_document = profile.model_dump(mode="json")
		profile_id = profiles.insert(profile_document)
	except Exception:
		if profile_id is not None:
			profiles.remove(doc_ids=[profile_id])
		users.remove(doc_ids=[user_id])
		raise
	return User(**user_document)


def get_user_by_id(users: Table, user_id: int) -> User | None:
	document = users.get(doc_id=user_id)
	return _to_user(document) if document is not None else None


def get_user_by_email(users: Table, email: str) -> User | None:
	document = users.get(Query().email == email.strip().lower())
	return _to_user(document) if document is not None else None


def list_users(users: Table) -> list[User]:
	return [_to_user(document) for document in users.all()]


def update_user(users: Table, user_id: int, request: UserUpdate) -> User | None:
	user = get_user_by_id(users, user_id)
	if user is None:
		return None

	updates = request.model_dump(exclude_unset=True)
	if "email" in updates and updates["email"] != user.email:
		existing = get_user_by_email(users, updates["email"])
		if existing is not None and existing.id != user_id:
			raise UserAlreadyExistsError(updates["email"])
	if "password" in updates:
		updates["hashed_password"] = bcrypt.hash(updates.pop("password"))
	if "role" in updates:
		updates["role"] = updates["role"].value
	users.update(updates, doc_ids=[user_id])
	return get_user_by_id(users, user_id)


def delete_user(users: Table, profiles: Table, user_id: int) -> bool:
	if get_user_by_id(users, user_id) is None:
		return False
	profiles.remove(Query().user_id == user_id)
	users.remove(doc_ids=[user_id])
	return True