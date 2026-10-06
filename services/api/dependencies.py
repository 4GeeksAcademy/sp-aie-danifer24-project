from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends
from tinydb.table import Table

from services.api.database import database_lock, get_database


def get_user_tables() -> Iterator[tuple[Table, Table]]:
	with database_lock:
		with get_database() as database:
			yield database.table("users"), database.table("profiles")


UserTables = Annotated[tuple[Table, Table], Depends(get_user_tables)]