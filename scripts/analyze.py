import argparse
import csv
import re
import sys
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


def value_of(row, column):
    value = row.get(column, "")
    return value.strip() if isinstance(value, str) else ""


def validate_row(row, seen_ticket_ids):
    problems = []
    ticket_id = value_of(row, "ticket_id")
    row_has_extra_fields = None in row

    if row_has_extra_fields:
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


def load_records(csv_path):
    try:
        with csv_path.open("r", encoding="utf-8-sig", newline="") as source:
            reader = csv.DictReader(source)
            if reader.fieldnames is None:
                raise ValueError("the file is empty or has no header")
            missing_columns = [
                column for column in REQUIRED_COLUMNS if column not in reader.fieldnames
            ]
            if missing_columns:
                raise ValueError("missing required columns: " + ", ".join(missing_columns))
            return list(reader)
    except (OSError, UnicodeError, csv.Error) as error:
        raise ValueError("could not read the CSV file") from error


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


def print_breakdown(label, count, percentage=None):
    line = f"  {label:<42} {count:>4}"
    if percentage is not None:
        line += f"  {percentage:>5.1f}%"
    print(line)


def print_report(source_name, results):
    separator = "=" * 68
    print(separator)
    print("  NEXOVA | ANÁLISIS DE INCIDENCIAS DE SOPORTE")
    print(f"  Archivo de origen: {source_name}")
    print(separator)
    print()
    print("RESUMEN DE REGISTROS")
    print_breakdown("Total procesado", results["total"])
    print_breakdown("Registros válidos", results["valid"])
    print_breakdown("Registros inválidos o incompletos", results["invalid"])
    print()
    print("DETALLE DE REGISTROS INVÁLIDOS")
    for rule, label in INVALID_RULES:
        print_breakdown(label, results["invalid_counts"][rule])
    print()
    print("INCIDENCIAS POR CATEGORÍA (registros válidos)")
    for category in CATEGORIES:
        count = results["category_counts"][category]
        percentage = count / results["valid"] * 100 if results["valid"] else 0
        print_breakdown(category, count, percentage)
    print()
    print("REGISTROS POR ESTADO (registros válidos)")
    for status in STATUSES:
        count = results["status_counts"][status]
        percentage = count / results["valid"] * 100 if results["valid"] else 0
        status_label = {
            "OPEN": "OPEN (abierto)",
            "CLOSED": "CLOSED (cerrado)",
            "DISCARDED": "DISCARDED (descartado)",
        }[status]
        print_breakdown(status_label, count, percentage)
    print()
    print("ÍNDICE DE SATISFACCIÓN (tickets cerrados)")
    print(
        f"  Tickets con puntuación: {results['scored_count']} "
        f"de {results['closed_count']} cerrados"
    )
    print(f"  Promedio: {results['average']:.2f} / 5.00")
    for score, label in SCORE_LABELS.items():
        print_breakdown(f"Puntuación {score} ({label})", results["score_counts"][score])
    print()
    print(separator)


def export_results(results):
    export_path = Path.cwd() / "results.csv"
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
    metrics.append(("scored_closed_tickets", results["scored_count"]))
    metrics.append(("closed_tickets", results["closed_count"]))
    metrics.append(("average_satisfaction_score", f"{results['average']:.2f}"))
    metrics.extend(
        (f"satisfaction_score_{score}_count", results["score_counts"][score])
        for score in SCORE_LABELS
    )

    try:
        with export_path.open("w", encoding="utf-8", newline="") as destination:
            writer = csv.writer(destination)
            writer.writerow(("métrica", "valor"))
            writer.writerows(metrics)
    except OSError:
        print("No se pudo guardar results.csv.", file=sys.stderr)
        return 1
    print(f"Resultados exportados a {export_path}")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Analiza incidencias de soporte sin exponer emails de clientes."
    )
    parser.add_argument("csv_file", type=Path, help="path to the input CSV file")
    args = parser.parse_args()

    try:
        rows = load_records(args.csv_file)
    except ValueError as error:
        print(f"Error: no se pudo leer el CSV ({error}).", file=sys.stderr)
        return 2

    results = analyze(rows)
    print_report(args.csv_file.name, results)
    try:
        export_choice = input("¿Deseas exportar los resultados a CSV? [s / n] ").strip().lower()
    except EOFError:
        export_choice = "n"
    while export_choice not in {"s", "si", "sí", "n", "no", ""}:
        print("Respuesta no válida. Escribe 's' para exportar o 'n' para salir.")
        export_choice = input("¿Deseas exportar los resultados a CSV? [s / n] ").strip().lower()
    if export_choice in {"s", "si", "sí"}:
        return export_results(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())