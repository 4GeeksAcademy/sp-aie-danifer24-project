import csv
import io
import re
from collections import Counter
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


def validate_row(row, seen_ticket_ids):
    problems = []
    ticket_id = value_of(row, "ticket_id")

    if None in row:
        problems.append("malformed_csv_row")
    if not ticket_id:
        problems.append("missing_ticket_id")
    elif not re.fullmatch(r"NXV-\d{6}", ticket_id):
        problems.append("invalid_ticket_id")
    elif ticket_id in seen_ticket_ids:
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


def load_records_from_text(contents):
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
            column for column in REQUIRED_COLUMNS if column not in reader.fieldnames
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


def load_records(csv_path):
    try:
        return load_records_from_text(csv_path.read_bytes())
    except OSError as error:
        raise CsvInputError("No se pudo leer el archivo CSV indicado.") from error


def analyze(rows):
    invalid_counts = Counter()
    valid_rows = []
    scored_closed = Counter()
    seen_ticket_ids = set()

    for row in rows:
        problems, score = validate_row(row, seen_ticket_ids)
        invalid_counts.update(problems)
        if not problems:
            valid_rows.append(row)
            if value_of(row, "status") == "CLOSED" and score is not None:
                scored_closed[score] += 1

    category_counts = Counter(value_of(row, "category") for row in valid_rows)
    status_counts = Counter(value_of(row, "status") for row in valid_rows)
    scored_count = sum(scored_closed.values())
    average = (
        sum(score * count for score, count in scored_closed.items()) / scored_count
        if scored_count
        else 0
    )

    return {
        "total": len(rows),
        "valid": len(valid_rows),
        "invalid": len(rows) - len(valid_rows),
        "invalid_counts": invalid_counts,
        "category_counts": category_counts,
        "status_counts": status_counts,
        "score_counts": scored_closed,
        "scored_count": scored_count,
        "closed_count": status_counts["CLOSED"],
        "average": average,
    }


def summary_for_api(results, source_filename):
    valid_total = results["valid"]
    categories = {
        category: {
            "count": results["category_counts"][category],
            "percentage": round(
                results["category_counts"][category] / valid_total * 100, 1
            ) if valid_total else 0,
        }
        for category in CATEGORIES
    }
    statuses = {
        status: {
            "count": results["status_counts"][status],
            "percentage": round(
                results["status_counts"][status] / valid_total * 100, 1
            ) if valid_total else 0,
        }
        for status in STATUSES
    }
    return {
        "source_filename": source_filename,
        "total_records": results["total"],
        "valid_records": results["valid"],
        "invalid_records": results["invalid"],
        "invalid_breakdown": {
            rule: results["invalid_counts"][rule] for rule, _ in INVALID_RULES
        },
        "categories": categories,
        "statuses": statuses,
        "satisfaction": {
            "scored_tickets": results["scored_count"],
            "closed_tickets": results["closed_count"],
            "average": round(results["average"], 2),
            "scores": {
                str(score): results["score_counts"][score]
                for score in SCORE_LABELS
            },
        },
    }


def results_csv_bytes(results):
    metrics = [
        ("total_records", results["total"]),
        ("valid_records", results["valid"]),
        ("invalid_records", results["invalid"]),
    ]
    metrics.extend(
        (f"invalid_{rule}", results["invalid_counts"][rule])
        for rule, _ in INVALID_RULES
    )
    for category in CATEGORIES:
        count = results["category_counts"][category]
        metrics.append((f"category_{category}_count", count))
        percentage = count / results["valid"] * 100 if results["valid"] else 0
        metrics.append((f"category_{category}_percent", f"{percentage:.1f}"))
    for status in STATUSES:
        count = results["status_counts"][status]
        metrics.append((f"status_{status}_count", count))
        percentage = count / results["valid"] * 100 if results["valid"] else 0
        metrics.append((f"status_{status}_percent", f"{percentage:.1f}"))
    metrics.extend(
        (
            ("scored_closed_tickets", results["scored_count"]),
            ("closed_tickets", results["closed_count"]),
            ("average_satisfaction_score", f"{results['average']:.2f}"),
        )
    )
    metrics.extend(
        (f"satisfaction_score_{score}_count", results["score_counts"][score])
        for score in SCORE_LABELS
    )

    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(("métrica", "valor"))
    writer.writerows(metrics)
    return buffer.getvalue().encode("utf-8")