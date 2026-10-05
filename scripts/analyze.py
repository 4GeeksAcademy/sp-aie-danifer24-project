import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.api.incidents import (
    CATEGORIES,
    INVALID_RULES,
    SCORE_LABELS,
    STATUSES,
    CsvInputError,
    analyze,
    load_records,
    results_csv_bytes,
)


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
    try:
        export_path.write_bytes(results_csv_bytes(results))
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
    except CsvInputError as error:
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