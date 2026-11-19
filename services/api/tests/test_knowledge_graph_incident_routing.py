"""Regression tests for natural-language incident ID routing."""

import json
from uuid import uuid4

import pytest

from services.api.services import knowledge_graph as kg
from services.api.services.incident_tool import (
    IncidentLookupOutput,
    IncidentToolOutcome,
)


@pytest.mark.parametrize(
    "question",
    [
        "ticket 1",
        "incidencia 1",
        "incidente 1",
        "¿Qué incidente tiene el ID 1?",
        "Busca el ticket con identificador 1",
        "Dime la incidencia número 1",
    ],
)
def test_incident_id_phrasings_route_to_incidents(question, tmp_path, monkeypatch):
    monkeypatch.setattr(kg, "TRACE_DIR", tmp_path)
    graph = kg.build_knowledge_graph(
        retrieve_fn=lambda _: [],
        generate_fn=lambda *_: "unused",
        incident_fn=lambda _: IncidentLookupOutput(
            outcome=IncidentToolOutcome.NOT_FOUND,
            message="No encontrada",
        ),
    )
    run_id = str(uuid4())

    result = graph.invoke(
        {"question": question, "run_id": run_id, "chunks": [], "trace": []},
        config={"configurable": {"thread_id": run_id}},
    )

    events = [json.loads(line) for line in (tmp_path / f"{run_id}.jsonl").read_text(encoding="utf-8").splitlines()]
    route_event = next(event for event in events if event["node"] == "route_request")
    lookup_event = next(event for event in events if event["node"] == "incident_lookup")
    assert route_event["sources"] == ["incident_lookup"]
    assert route_event["ticket_id"] == 1
    assert lookup_event["outcome"] == "not_found"
    assert "incident_lookup" in result["trace"]


def test_unrelated_id_does_not_route_to_incidents(tmp_path, monkeypatch):
    monkeypatch.setattr(kg, "TRACE_DIR", tmp_path)
    graph = kg.build_knowledge_graph(
        retrieve_fn=lambda _: [],
        generate_fn=lambda *_: "unused",
    )
    run_id = str(uuid4())

    result = graph.invoke(
        {"question": "¿Qué significa el ID 1?", "run_id": run_id, "chunks": [], "trace": []},
        config={"configurable": {"thread_id": run_id}},
    )

    events = [json.loads(line) for line in (tmp_path / f"{run_id}.jsonl").read_text(encoding="utf-8").splitlines()]
    route_event = next(event for event in events if event["node"] == "route_request")
    assert route_event["sources"] == ["rag"]
    assert route_event["ticket_id"] is None
    assert "incident_lookup" not in result["trace"]
