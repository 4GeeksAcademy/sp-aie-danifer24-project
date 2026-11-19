from datetime import datetime, timezone

from services.api.models import IncidentCategory, IncidentOrigin, IncidentStatus
from services.api.services.incident_tool import (
    IncidentLookupInput,
    IncidentLookupOutput,
    IncidentRecord,
    IncidentToolOutcome,
)
from services.api.services.knowledge_graph import build_knowledge_graph
from mcps.nexova_mcp.request_context import api_bearer_token


def found_incident():
    now = datetime(2026, 1, 2, tzinfo=timezone.utc)
    return IncidentRecord(
        id=42,
        title="Cannot access account",
        description="Login fails.",
        status=IncidentStatus.OPEN,
        category=IncidentCategory.TECHNICAL_FAILURE,
        origin=IncidentOrigin.CUSTOMER,
        branch="central",
        created_at=now,
        updated_at=now,
    )


def test_graph_restores_run_scoped_mcp_token_inside_worker_node(monkeypatch, tmp_path):
    observed_tokens = []

    def incident_tool(request):
        observed_tokens.append(api_bearer_token.get())
        return IncidentLookupOutput(outcome=IncidentToolOutcome.NOT_FOUND)

    from services.api.services import knowledge_graph as graph_module

    monkeypatch.setattr(graph_module, "TRACE_DIR", tmp_path)
    monkeypatch.setattr(
        graph_module, "knowledge_graph", build_knowledge_graph(incident_fn=incident_tool)
    )
    result = graph_module.run_knowledge_graph(
        "Estado del ticket 123", run_id="token-propagation-test", mcp_token="scoped-token"
    )

    assert result["answer"] == "No se encontró una incidencia que coincida con la consulta."
    assert observed_tokens == ["scoped-token"]
    assert api_bearer_token.get() is None


def test_graph_routes_ticket_id_to_incident_tool_and_returns_actual_data():
    calls = []

    def incident_tool(request):
        calls.append(request)
        return IncidentLookupOutput(
            outcome=IncidentToolOutcome.FOUND, incidents=[found_incident()]
        )

    graph = build_knowledge_graph(
        lambda question: (_ for _ in ()).throw(AssertionError("RAG should not run")),
        lambda question, context: (_ for _ in ()).throw(AssertionError("generation should not run")),
        incident_fn=incident_tool,
    )
    result = graph.invoke(
        {"question": "¿Cuál es el estado del ticket 42?", "run_id": "incident-42"},
        config={"configurable": {"thread_id": "incident-42"}},
    )

    assert calls == [IncidentLookupInput(ticket_id=42)]
    assert result["trace"] == [
        "receive_question", "route_request", "incident_lookup", "incident_response"
    ]
    assert "Incidencia 42" in result["answer"]
    assert "open" in result["answer"]


def test_graph_routes_unfiltered_incident_plural_to_rag_and_fallback_is_honest():
    calls = []
    graph = build_knowledge_graph(
        lambda question: calls.append(("retrieve", question)) or [],
        lambda question, context: "should not generate",
        incident_fn=lambda request: calls.append(("incident", request))
        or IncidentLookupOutput(outcome=IncidentToolOutcome.ERROR, message="internals"),
    )

    general_result = graph.invoke(
        {"question": "¿Qué incidentes existen?", "run_id": "incidents-unfiltered"},
        config={"configurable": {"thread_id": "incidents-unfiltered"}},
    )
    failed_result = graph.invoke(
        {"question": "Estado del ticket 789", "run_id": "incident-fallback"},
        config={"configurable": {"thread_id": "incident-fallback"}},
    )

    assert general_result["trace"] == [
        "receive_question", "route_request", "retrieve", "no_context"
    ]
    assert failed_result["answer"] == "No pude confirmar el estado de ese ticket ahora mismo."
    assert "internals" not in failed_result["answer"]
    assert failed_result["trace"] == [
        "receive_question", "route_request", "incident_lookup", "incident_response"
    ]
