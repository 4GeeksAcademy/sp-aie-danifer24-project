import os
from pathlib import Path
from threading import Lock

from tinydb import TinyDB


DEFAULT_DATABASE_PATH = Path(__file__).resolve().parents[2] / "data" / "suppliers.json"
database_lock = Lock()


def get_database() -> TinyDB:
	path = Path(os.environ.get("SUPPLIERS_DB_PATH", str(DEFAULT_DATABASE_PATH)))
	path.parent.mkdir(parents=True, exist_ok=True)
	return TinyDB(path)