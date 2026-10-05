# Nexova Incidents API

FastAPI service exposing the shared incident validation and analysis logic. It also serves the static backoffice at `/`.

## Run

From the repository root:

```bash
python -m pip install -r services/api/requirements.txt
uvicorn services.api.main:app --reload
```

Open `http://127.0.0.1:8000/`. The API documentation is available at `http://127.0.0.1:8000/docs`.

## Endpoints

- `POST /api/incidents/analyze`: upload a `.csv` file using the multipart field `file`; returns aggregate JSON only.
- `GET /api/incidents/results/report`: download the most recent aggregate report as `results.csv`.

The latest aggregate report is held in process memory. Raw rows, descriptions, and customer emails are not retained or returned.

## Supplier Seeder

With uv installed, run from the repository root:

```bash
uv run seed
```

This loads the 15 suppliers defined in `09-lightweight-storage/CONTEXT-nexova.md`
into the `suppliers` table in `data/suppliers.json`. Each record is validated with
Pydantic and receives a system-generated UTC `updated_at`. Existing suppliers
are matched by name and country and are neither duplicated nor overwritten.
The command prints the number of inserted records, including zero on a repeat run.

To use a different database file without changing code:

```bash
SUPPLIERS_DB_PATH=/tmp/nexova-suppliers.json uv run seed
```