import pytest

from services.api.services import knowledge_graph as knowledge_graph_module
from services.api.services.knowledge_graph import (
    build_knowledge_graph,
    inspect_knowledge_graph_run,
    read_knowledge_graph_trace,
    run_knowledge_graph,
)


def run_config(thread_id):
    return {"configurable": {"thread_id": thread_id}}


def test_graph_retrieves_once_then_generates_from_retrieved_chunks():
    calls = []
    chunks = [{"text": "Tarifa 22%"}]

    def fake_retrieve(question):
        calls.append(("retrieve", question))
        return chunks

    def fake_generate(question, context):
        calls.append(("generate", question, context))
        return "Respuesta basada en contexto"

    graph = build_knowledge_graph(fake_retrieve, fake_generate)
    result = graph.invoke(
        {"question": " ¿Cuál es la tarifa? ", "run_id": "test-1"},
        config=run_config("test-1"),
    )

    assert result["answer"] == "Respuesta basada en contexto"
    assert result["chunks"] == chunks
    assert result["trace"] == ["receive_question", "retrieve", "generate_answer"]
    assert calls == [
        ("retrieve", "¿Cuál es la tarifa?"),
        ("generate", "¿Cuál es la tarifa?", chunks),
    ]


def test_graph_routes_blank_question_to_end_without_retrieval_or_generation():
    calls = []
    graph = build_knowledge_graph(
        lambda question: calls.append(("retrieve", question)) or [],
        lambda question, context: calls.append(("generate", question, context)) or "bad",
    )

    result = graph.invoke(
        {"question": "   ", "run_id": "test-2"}, config=run_config("test-2")
    )

    assert result["error"] == "La pregunta no puede estar vacía."
    assert result["answer"] == ""
    assert result["trace"] == ["receive_question"]
    assert calls == []


def test_graph_routes_empty_retrieval_to_honest_no_context_answer():
    calls = []

    def fake_generate(question, context):
        calls.append((question, context))
        return "No debe generarse"

    graph = build_knowledge_graph(lambda question: [], fake_generate)
    result = graph.invoke(
        {"question": "¿Qué información hay?", "run_id": "test-3"},
        config=run_config("test-3"),
    )

    assert result["answer"] == (
        "No tengo información suficiente en la base de conocimiento para responder esa pregunta."
    )
    assert result["trace"] == ["receive_question", "retrieve", "no_context"]
    assert calls == []


def test_graph_run_persists_queryable_trace_and_checkpoints(tmp_path, monkeypatch):
    monkeypatch.setattr(knowledge_graph_module, "TRACE_DIR", tmp_path)
    graph = build_knowledge_graph(
        lambda question: [{"text": "Tarifa 22%", "source_document": "pricing-model"}],
        lambda question, context: "La tarifa es 22%.",
    )
    monkeypatch.setattr(knowledge_graph_module, "knowledge_graph", graph)

    result = run_knowledge_graph("¿Cuál es la tarifa?", run_id="checkpoint-test")

    events = read_knowledge_graph_trace("checkpoint-test")
    snapshots = inspect_knowledge_graph_run("checkpoint-test")
    assert [event["node"] for event in events] == result["trace"]
    assert [event["sequence"] for event in events] == [1, 2, 3]
    assert len(snapshots) >= 2
    assert any(snapshot.values.get("question") == "¿Cuál es la tarifa?" for snapshot in snapshots)


def test_graph_compile_fails_clearly_for_invalid_structure(monkeypatch):
    monkeypatch.setattr(knowledge_graph_module, "_NODE_NAMES", {"receive_question"})
    with pytest.raises(ValueError, match="edge/node mismatch"):
        build_knowledge_graph(lambda question: [], lambda question, context: "")
