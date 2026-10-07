"""Shared CSV parsing and validation for Nexova incident exports."""

import csv
import io
import re
from datetime import date
from pathlib import Path


CATEGORIES = ("TECHNICAL", "BILLING", "ACCESS", "HR_QUERY", "COMPLAINT")
STATUSES = ("OPEN", "CLOSED", "DISCARDED")
SCORE_LABELS = {
    1: "Muy insatisfecho",
    2: "Insatisfecho",
    3: "Neutral",
    4: "Satisfecho",
    5: "Muy satisfecho",
}
REQUIRED_COLUMNS = (
    "ticket_id",
    "date",
    "client_company",
    "category",
    "description",
    "agent_id",
    "status",
    "customer_email",
    "satisfaction_score",
)
INVALID_RULES = (
    ("missing_ticket_id", "Falta ticket_id"),
    ("invalid_ticket_id", "ticket_id inválido"),
    ("duplicate_ticket_id", "ticket_id duplicado"),
    ("missing_date", "Falta la fecha"),
    ("invalid_date", "Fecha inválida"),
    ("missing_client_company", "Falta client_company"),
    ("invalid_category", "Categoría inválida o faltante"),
    ("invalid_description", "Descripción inválida o faltante"),
    ("invalid_agent_id", "agent_id inválido o faltante"),
    ("invalid_status", "Estado inválido o faltante"),
    ("invalid_email", "Email inválido o faltante"),
    ("closed_without_score", "Ticket cerrado sin puntuación"),
    ("score_out_of_range", "Puntuación fuera del rango 1-5"),
    ("malformed_csv_row", "Fila CSV mal formada"),
)


class CsvInputError(ValueError):
    """Raised when an input file is not a readable incidents CSV."""


def value_of(row, column):
    value = row.get(column, "")
    return value.strip() if isinstance(value, str) else ""


def validate_row(row, seen_ticket_ids, *, allow_missing_ticket_id=False):
    problems = []
    ticket_id = value_of(row, "ticket_id")

    if None in row:
        problems.append("malformed_csv_row")
    if not ticket_id and not allow_missing_ticket_id:
        problems.append("missing_ticket_id")
    elif ticket_id and not re.fullmatch(r"NXV-\d{6}", ticket_id):
        problems.append("invalid_ticket_id")
    elif ticket_id and ticket_id in seen_ticket_ids:
        problems.append("duplicate_ticket_id")
    if ticket_id:
        seen_ticket_ids.add(ticket_id)

    date_value = value_of(row, "date")
    if not date_value:
        problems.append("missing_date")
    else:
        try:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_value):
                raise ValueError
            date.fromisoformat(date_value)
        except ValueError:
            problems.append("invalid_date")

    if not value_of(row, "client_company"):
        problems.append("missing_client_company")
    if value_of(row, "category") not in CATEGORIES:
        problems.append("invalid_category")
    if len(value_of(row, "description")) < 5:
        problems.append("invalid_description")
    if not re.fullmatch(r"AGT-\d{2}", value_of(row, "agent_id")):
        problems.append("invalid_agent_id")

    status = value_of(row, "status")
    if status not in STATUSES:
        problems.append("invalid_status")

    email = value_of(row, "customer_email")
    if not email or "@" not in email:
        problems.append("invalid_email")

    score_text = value_of(row, "satisfaction_score")
    score = None
    if status == "CLOSED" and not score_text:
        problems.append("closed_without_score")
    if score_text:
        try:
            score = int(score_text)
            if not 1 <= score <= 5:
                problems.append("score_out_of_range")
                score = None
        except ValueError:
            problems.append("score_out_of_range")

    return problems, score


def load_records_from_text(contents, *, required_columns=REQUIRED_COLUMNS):
    try:
        text = contents.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise CsvInputError("El archivo debe estar codificado en UTF-8.") from error
    if not text.strip():
        raise CsvInputError("El archivo CSV está vacío.")

    try:
        reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
        if reader.fieldnames is None:
            raise CsvInputError("El CSV no contiene una fila de encabezados.")
        missing_columns = [
            column for column in required_columns if column not in reader.fieldnames
        ]
        if missing_columns:
            raise CsvInputError(
                "Faltan columnas obligatorias: " + ", ".join(missing_columns)
            )
        rows = list(reader)
    except csv.Error as error:
        raise CsvInputError("El formato CSV no es válido.") from error
    if not rows:
        raise CsvInputError("El CSV no contiene registros para analizar.")
    return rows


def load_records(csv_path, *, required_columns=REQUIRED_COLUMNS):
    try:
        return load_records_from_text(
            Path(csv_path).read_bytes(), required_columns=required_columns
        )
    except OSError as error:
        raise CsvInputError("No se pudo leer el archivo CSV indicado.") from error