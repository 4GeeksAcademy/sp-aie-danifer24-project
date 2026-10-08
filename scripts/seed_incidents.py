"""Import historical support tickets into the incidents TinyDB table."""

from datetime import date, datetime, time, timezone
from pathlib import Path
import sys

# Allow running this file directly from the repository root.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.api.database import get_database
from packages.shared.incidents_csv import (
    REQUIRED_COLUMNS,
    CsvInputError,
    load_records,
    validate_row,
    value_of,
)
from services.api.models import (
    IncidentBranch,
    IncidentCategory,
    IncidentCreate,
    IncidentOrigin,
    IncidentStatus,
)


DEFAULT_CSV_PATH = ROOT / "scripts" / "incidents-nexova.csv"
STATUS_MAP = {
    "OPEN": IncidentStatus.OPEN,
    "CLOSED": IncidentStatus.RESOLVED,
    "DISCARDED": IncidentStatus.DISCARDED,
}
CATEGORY_MAP = {
    "TECHNICAL": IncidentCategory.TECHNICAL_FAILURE,
    "BILLING": IncidentCategory.PROCESS_ERROR,
    "ACCESS": IncidentCategory.TECHNICAL_FAILURE,
    "HR_QUERY": IncidentCategory.PROCESS_ERROR,
    "COMPLAINT": IncidentCategory.CLIENT_COMPLAINT,
}


def transform_record(row: dict[str, str], inserted_at: datetime) -> tuple[dict, str]:
    """Validate and map one analyzer CSV row to the incident model fields."""
    description = row.get("description", "")
    if not isinstance(description, str):
        description = ""
    title = description[:120].strip()
    if not title:
        raise ValueError("title vacío tras transformar description")

    raw_status = value_of(row, "status")
    raw_category = value_of(row, "category")
    if raw_status not in STATUS_MAP:
        raise ValueError("status no mapeable")
    if raw_category not in CATEGORY_MAP:
        raise ValueError("category no mapeable")

    csv_date = date.fromisoformat(value_of(row, "date"))
    created_at = datetime.combine(csv_date, time.min, tzinfo=timezone.utc)
    request = IncidentCreate(
        title=title,
        description=description,
        category=CATEGORY_MAP[raw_category],
        status=STATUS_MAP[raw_status],
        origin=IncidentOrigin.CUSTOMER,
        branch=IncidentBranch.CENTRAL,
    )
    incident_data = request.model_dump(mode="json")
    incident_data.update(
        created_at=created_at.isoformat(),
        updated_at=inserted_at.isoformat(),
    )
    return incident_data, created_at.isoformat()


def seed_incidents(csv_path: Path = DEFAULT_CSV_PATH) -> dict:
    """Validate, transform and insert records once; return an import summary."""
    # If the identifier is absent, use title + created_at as the idempotency key.
    required_columns = tuple(
        column for column in REQUIRED_COLUMNS if column != "ticket_id"
    )
    rows = load_records(csv_path, required_columns=required_columns)
    seen_ticket_ids: set[str] = set()
    invalid_rows: list[tuple[int, list[str]]] = []
    inserted = 0
    duplicates = 0

    with get_database() as database:
        incidents_table = database.table("incidents")
        seed_keys_table = database.table("incident_seed_keys")
        existing_keys = {
            document["key"] for document in seed_keys_table.all() if "key" in document
        }
        inserted_at = datetime.now(timezone.utc)

        for row_number, row in enumerate(rows, start=2):
            ticket_id = value_of(row, "ticket_id")
            problems, _ = validate_row(
                row,
                seen_ticket_ids,
                allow_missing_ticket_id="ticket_id" not in row or not ticket_id,
            )
            try:
                incident_data, created_at = transform_record(row, inserted_at)
            except (ValueError, TypeError):
                problems.append("mapping_error: registro no válido")
                incident_data = None
                created_at = ""

            if problems or incident_data is None:
                if not problems:
                    problems.append("mapping_error: registro incompleto")
                invalid_rows.append((row_number, problems))
                continue

            dedupe_value = (
                f"ticket:{ticket_id}"
                if ticket_id and "missing_ticket_id" not in problems
                else f"title-date:{incident_data['title']}|{created_at}"
            )
            if dedupe_value in existing_keys:
                duplicates += 1
                continue

            incidents_table.insert(incident_data)
            seed_keys_table.insert({"key": dedupe_value})
            existing_keys.add(dedupe_value)
            inserted += 1

    return {
        "total": len(rows),
        "inserted": inserted,
        "duplicates": duplicates,
        "invalid": invalid_rows,
    }


def main() -> int:
    try:
        summary = seed_incidents()
    except CsvInputError as error:
        print(f"Error al cargar el CSV: {error}", file=sys.stderr)
        return 1
    except Exception as error:
        print(f"Error crítico durante la importación ({type(error).__name__}).", file=sys.stderr)
        return 1

    print("Importación histórica de incidencias finalizada" if not summary["invalid"] else "Importación finalizada con errores")
    print(f"Filas leídas: {summary['total']}")
    print(f"Incidencias insertadas: {summary['inserted']}")
    print(f"Duplicados ya existentes: {summary['duplicates']}")
    print(f"Filas inválidas descartadas: {len(summary['invalid'])}")
    if summary["invalid"]:
        print("Error: se descartaron filas inválidas; revisa los detalles por fila:", file=sys.stderr)
        for row_number, problems in summary["invalid"]:
            print(f"  Fila {row_number}: {', '.join(problems)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
