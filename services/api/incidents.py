from collections import Counter

from packages.shared.incidents_csv import (
    CATEGORIES,
    INVALID_RULES,
    REQUIRED_COLUMNS,
    SCORE_LABELS,
    STATUSES,
    CsvInputError,
    load_records,
    load_records_from_text,
    validate_row,
    value_of,
)


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