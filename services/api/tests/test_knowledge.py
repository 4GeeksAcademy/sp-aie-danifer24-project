from unittest.mock import patch


def test_knowledge_query_returns_only_generated_answer(api):
    client, _, _ = api
    answer = "La tarifa estándar es del 22%."

    graph_result = {
        "answer": answer,
        "run_id": "trace-123",
        "trace": ["receive_question", "retrieve", "generate_answer"],
    }
    with patch(
        "services.api.routes.knowledge.run_knowledge_graph",
        return_value=graph_result,
    ) as run_graph:
        response = client.post(
            "/knowledge/query",
            json={"question": " ¿Cuál es la tarifa? "},
        )

    assert response.status_code == 200
    assert response.json() == {"answer": answer, "run_id": "trace-123"}
    run_graph.assert_called_once_with("¿Cuál es la tarifa?")


def test_knowledge_query_rejects_blank_question(api):
    client, _, _ = api

    response = client.post("/knowledge/query", json={"question": "   "})

    assert response.status_code == 422


def test_knowledge_query_hides_internal_errors(api):
    client, _, _ = api

    with patch(
        "services.api.routes.knowledge.run_knowledge_graph",
        side_effect=RuntimeError("qdrant internals"),
    ):
        response = client.post("/knowledge/query", json={"question": "Pregunta"})

    assert response.status_code == 502
    assert "qdrant internals" not in response.text
    assert response.json()["detail"] == (
        "No se pudo consultar la base de conocimiento en este momento."
    )
