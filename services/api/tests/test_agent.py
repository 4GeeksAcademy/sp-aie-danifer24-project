from unittest.mock import patch


def test_agent_query_invokes_compiled_graph_and_returns_run_id(api):
    client, _, _ = api
    graph_result = {
        "answer": "Tarifa del 22% sobre el salario anual.",
        "run_id": "run-agent-123",
        "trace": ["receive_question", "retrieve", "generate_answer"],
    }
    with patch(
        "services.api.routes.agent.run_knowledge_graph", return_value=graph_result
    ) as run_graph:
        response = client.post(
            "/agent/query", json={"question": "¿Cuál es la tarifa de headhunting?"}
        )

    assert response.status_code == 200
    assert response.json() == {
        "answer": "Tarifa del 22% sobre el salario anual.",
        "run_id": "run-agent-123",
    }
    run_graph.assert_called_once_with("¿Cuál es la tarifa de headhunting?")


def test_agent_query_returns_safe_error_when_graph_node_fails(api):
    client, _, _ = api
    with patch(
        "services.api.routes.agent.run_knowledge_graph",
        side_effect=RuntimeError("raw qdrant stack details"),
    ):
        response = client.post("/agent/query", json={"question": "Pregunta"})

    assert response.status_code == 502
    assert "raw qdrant stack details" not in response.text
    assert response.json()["detail"] == (
        "No se pudo completar la consulta del agente. Inténtalo de nuevo más tarde."
    )
