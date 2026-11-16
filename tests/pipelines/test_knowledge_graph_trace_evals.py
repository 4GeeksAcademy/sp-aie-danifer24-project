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
    if "incident_lookup" in nodes:
        route_event = next(event for event in events if event["node"] == "route_request")
        lookup_event = next(event for event in events if event["node"] == "incident_lookup")
        assert route_event["route"] == "incident_lookup"
        assert lookup_event["outcome"] == "found"
        assert nodes.index("incident_lookup") < nodes.index("incident_response")

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
        for term in case["expected_answer_terms"]:
            assert term.casefold() in answer
    else:
        for term in case["expected_answer_terms"]:
            assert term.casefold() in case["answer"].casefold()

    if case["case_id"] == "blank-question-short-circuit":
        assert "retrieve" not in nodes
        assert events[0]["valid"] is False
        assert events[0]["error"] == "La pregunta no puede estar vacía."
