"""Offline trace evaluations for the LangGraph RAG agent.

Run with: uv run pytest tests/pipelines/test_knowledge_graph_trace_evals.py -q
These assertions consume recorded trace fixtures; they do not invoke the live graph.
"""

import json
from pathlib import Path

import pytest

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "knowledge_graph_trace_evals.json"
EVAL_CASES = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", EVAL_CASES, ids=lambda case: case["case_id"])
def test_recorded_agent_trace_and_grounding_evaluation(case):
    events = case["events"]
    nodes = [event["node"] for event in sorted(events, key=lambda item: item["sequence"])]

    # Verify persisted trace order and that retrieval precedes generation when used.
    assert nodes == case["expected_nodes"]
    if "generate_answer" in nodes:
        assert nodes.index("retrieve") < nodes.index("generate_answer")
        generate_event = next(event for event in events if event["node"] == "generate_answer")
        retrieve_event = next(event for event in events if event["node"] == "retrieve")
        assert generate_event["context_chunk_count"] == retrieve_event["chunk_count"]
    if "expected_sources" in case:
        route_event = next(event for event in events if event["node"] == "route_request")
        assert route_event["sources"] == case["expected_sources"]
        assert route_event["execution_order"] == case["expected_execution_order"]
        if "rag" in case["expected_sources"]:
            assert "retrieve" in nodes
            assert nodes.index("retrieve") > nodes.index("route_request")
        if "incident_lookup" in case["expected_sources"]:
            assert nodes.index("incident_lookup") < nodes.index("incident_response")
        if "inventory_lookup" in case["expected_sources"]:
            assert nodes.index("inventory_lookup") < nodes.index("inventory_response")

        # Check the executed nodes, not just the router's plan, to ensure the
        # trace records which sources actually contributed to the answer.
        source_nodes = {
            "incident_lookup": "incident_response",
            "inventory_lookup": "inventory_response",
            "rag": "generate_answer" if "generate_answer" in nodes else "no_context",
        }
        for source in case["expected_sources"]:
            source_node = source_nodes[source]
            event = next(event for event in events if event["node"] == source_node)
            assert source in event.get("sources_used", [])

        actual_order = [
            source
            for source in case["expected_execution_order"]
            if source_nodes[source] in nodes
        ]
        actual_node_order = [source_nodes[source] for source in actual_order]
        assert actual_node_order == [node for node in nodes if node in actual_node_order]

    if "incident_lookup" in nodes:
        route_event = next(event for event in events if event["node"] == "route_request")
        lookup_event = next(event for event in events if event["node"] == "incident_lookup")
        assert "incident_lookup" in route_event["sources"]
        assert lookup_event["outcome"] == "found"

    # A known Nexova policy question must remain grounded in its expected KB source/data.
    if case["expected_source"]:
        retrieval = next(event for event in events if event["node"] == "retrieve")
        assert case["expected_source"] in retrieval["sources"]
        retrieved_text = " ".join(
            chunk["text"]
            for chunk in retrieval["retrieved_chunks"]
            if chunk["source_document"] == case["expected_source"]
        ).casefold()
        for term in case["expected_answer_terms"]:
            assert term.casefold() in retrieved_text
        answer = case["answer"].casefold()
        for term in case.get("expected_response_terms", case["expected_answer_terms"]):
            assert term.casefold() in answer
    else:
        for term in case["expected_answer_terms"]:
            assert term.casefold() in case["answer"].casefold()

    if case["case_id"] == "blank-question-short-circuit":
        assert "retrieve" not in nodes
        assert events[0]["valid"] is False
        assert events[0]["error"] == "La pregunta no puede estar vacía."
