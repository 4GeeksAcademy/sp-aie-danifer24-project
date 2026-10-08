from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends
from tinydb.table import Table

from services.api.database import database_lock, get_database


def get_request_tables() -> Iterator[tuple[Table, Table, Table, Table, Table]]:
	with database_lock:
		with get_database() as database:
			yield (
				database.table("users"),
				database.table("profiles"),
				database.table("suppliers"),
				database.table("password_resets"),
				database.table("incidents"),
			)


RequestTables = Annotated[
	tuple[Table, Table, Table, Table, Table],
	Depends(get_request_tables),
]


def get_user_tables(tables: RequestTables) -> tuple[Table, Table]:
	return tables[0], tables[1]


UserTables = Annotated[tuple[Table, Table], Depends(get_user_tables)]


def get_password_tables(tables: RequestTables) -> tuple[Table, Table]:
	return tables[0], tables[3]


PasswordTables = Annotated[tuple[Table, Table], Depends(get_password_tables)]