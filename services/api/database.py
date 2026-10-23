import os
from pathlib import Path
from threading import Lock

from dotenv import load_dotenv
from sqlalchemy.engine import make_url
from sqlmodel import create_engine
from tinydb import TinyDB


DEFAULT_DATABASE_PATH = Path(__file__).resolve().parents[2] / "data" / "suppliers.json"
database_lock = Lock()
load_dotenv(Path(__file__).resolve().parents[2] / ".env")
DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
	raise RuntimeError("DATABASE_URL must be set to initialize the Supabase engine.")

database_url = make_url(DATABASE_URL)
if database_url.get_backend_name() != "postgresql":
	raise RuntimeError("DATABASE_URL must use PostgreSQL for the Supabase engine.")

engine = create_engine(
	database_url.set(drivername="postgresql+psycopg2"),
	pool_pre_ping=True,
)


def get_database() -> TinyDB:
	path = Path(os.environ.get("SUPPLIERS_DB_PATH", str(DEFAULT_DATABASE_PATH)))
	path.parent.mkdir(parents=True, exist_ok=True)
	return TinyDB(path)