import inspect
import json
import re
import unicodedata
from pathlib import Path

from data.pipelines.rag import retrieve


ROOT = Path(__file__).resolve().parents[1]
QUERY_FILE = ROOT / "data" / "eval" / "test-queries.json"


def normalize(value):
    value = unicodedata.normalize("NFKD", str(value))
    value = "".join(char for char in value if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", value).strip().lower()


def as_dict(item):
    if isinstance(item, dict):
        return item
    if hasattr(item, "model_dump"):
        return item.model_dump()
    if hasattr(item, "dict"):
        return item.dict()
    return getattr(item, "__dict__", {})


def payload_text(item):
    item = as_dict(item)
    payload = item.get("payload", item.get("metadata", item))
    payload = as_dict(payload)
    return " ".join(
        str(payload.get(key, ""))
        for key in ("text", "page_content", "content", "source_document")
    )


def result_list(results):
    if isinstance(results, tuple) and results and isinstance(results[0], list):
        results = results[0]

    if hasattr(results, "points"):
        results = results.points

    if isinstance(results, dict):
        for key in ("results", "points", "matches"):
            if key in results:
                results = results[key]
                break
        else:
            results = [results]

    return list(results)


def retrieve_top_three(question):
    signature = inspect.signature(retrieve)
    kwargs = {}

    for name in ("k", "top_k", "limit"):
        if name in signature.parameters:
            kwargs[name] = 3
            break

    return result_list(retrieve(question, **kwargs))[:3]


def main():
    queries = json.loads(QUERY_FILE.read_text(encoding="utf-8-sig"))
    hits = 0
    failures = []

    for entry in queries:
        results = retrieve_top_three(entry["question"])
        expected = normalize(entry["target_text"])
        found = any(expected in normalize(payload_text(result)) for result in results)

        if found:
            hits += 1
        else:
            failures.append(entry)

        status = "OK" if found else "FALLO"
        print(f"[{status}] {entry['source_document']}: {entry['question']}")

    total = len(queries)
    recall = hits / total if total else 0

    print(f"\nRecall@3: {hits}/{total} = {recall:.1%}")
    print("Objetivo mínimo: 80%")

    if failures:
        print("\nConsultas cuyo fragmento esperado no apareció entre los tres primeros:")
        for entry in failures:
            print(f"- [{entry['source_document']}] {entry['question']}")

    if recall < 0.80:
        raise SystemExit(1)


if __name__ == "__main__":
    main()